#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qwen_cost.py — qwenthink profile 每日峰谷成本核算（纯本地，零 token 消耗）

数据源：~/.hermes/profiles/qwenthink/state.db（只读 SQLite，WAL 安全，不调任何模型）
  sessions表: input_tokens=缓存未命中新输入(不含缓存) / cache_read_tokens / output_tokens
  messages表: role='assistant' 行=每次 API 调用(带 epoch timestamp) → 峰谷拆分
峰谷(北京时间): 工作日 09-12 / 14-18 为峰, 其余(含周末)为谷, 谷=峰×0.5
计费(每1M tokens): cost_peak=新输入×未命中峰+缓存×命中峰+输出×输出峰
                    f=落在峰窗口的调用占比; cost_mix=f×peak+(1-f)×off

用法:
  python qwen_cost.py                 # 按天汇总每日成本(默认)
  python qwen_cost.py --detail        # 追加每会话明细(含日期, 分会话看)
  python qwen_cost.py --day 2026-08-26  # 只看某一天的会话明细
  python qwen_cost.py --pro | --usd   # 档位/币种
  python qwen_cost.py --since 3       # 只能最近 3 天
"""
from __future__ import annotations

import argparse
import os
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from decimal import Decimal

_CST = timezone(timedelta(hours=8))
_DB = os.path.expanduser("~/.hermes/profiles/qwenthink/state.db")

# 每百万 tokens 峰价(谷=×0.5)。来源 api-docs.deepseek.com/quick_start/pricing
PRICE = {
    "cny": {
        "flash": {"miss": Decimal("3.0"), "hit": Decimal("0.10"), "out": Decimal("9.0")},
        "pro":   {"miss": Decimal("9.0"), "hit": Decimal("0.30"), "out": Decimal("27.0")},
    },
    "usd": {
        "flash": {"miss": Decimal("0.44"), "hit": Decimal("0.014"), "out": Decimal("1.32")},
        "pro":   {"miss": Decimal("1.32"), "hit": Decimal("0.044"), "out": Decimal("3.96")},
    },
}
SYM = {"cny": "¥", "usd": "$"}


def is_peak_bj(epoch: float) -> bool:
    dt = datetime.fromtimestamp(epoch, _CST)
    if dt.weekday() >= 5:
        return False
    return (9 <= dt.hour < 12) or (14 <= dt.hour < 18)


def load(db: str, since_days: int | None):
    con = sqlite3.connect("file:" + db.replace("\\", "/") + "?mode=ro", uri=True)
    cur = con.cursor()
    since_ts = (datetime.now(_CST) - timedelta(days=since_days)).timestamp() if since_days else None
    cols = ["id", "started_at", "ended_at", "input_tokens", "output_tokens",
            "cache_read_tokens", "cache_write_tokens", "api_call_count"]
    sql = f"SELECT {', '.join(cols)} FROM sessions"
    if since_ts:
        sql += " WHERE ended_at IS NOT NULL AND ended_at >= ?"
        rows = cur.execute(sql, (since_ts,)).fetchall()
    else:
        rows = cur.execute(sql).fetchall()
    sessions = [dict(zip(cols, r)) for r in rows]
    asst = cur.execute("SELECT session_id, timestamp, token_count FROM messages WHERE role='assistant'").fetchall()
    con.close()
    per = defaultdict(list)
    for sid, ts, tc in asst:
        per[sid].append((ts, tc or 0))
    return sessions, per


def M(x) -> Decimal:
    return Decimal(x) * Decimal("0.000001")


def build(sessions, asst, p, token_w: bool):
    """返回 每条会话 dict(cost_peak/off/mix/date/...)，及按天聚合、profile 合计。"""
    items = []
    day = defaultdict(lambda: {"in": 0, "cache": 0, "out": 0, "calls": 0, "peakN": 0, "totN": 0})
    for s in sessions:
        i = s["input_tokens"] or 0
        c = s["cache_read_tokens"] or 0
        o = s["output_tokens"] or 0
        calls = s["api_call_count"] or 0
        tups = asst.get(s["id"], [])
        n_peak = sum(1 for ts, _ in tups if is_peak_bj(ts))
        w_peak = sum(Decimal(tc) for ts, tc in tups if is_peak_bj(ts))
        w_all = sum(Decimal(tc) for _, tc in tups)
        f = (w_peak / w_all) if (token_w and w_all) else (n_peak / len(tups) if tups else 0.0)
        cpk = M(i) * p["miss"] + M(c) * p["hit"] + M(o) * p["out"]
        coff = cpk / 2
        fd = Decimal(str(f))
        cmix = fd * cpk + (1 - fd) * coff
        start = s["started_at"]
        d = datetime.fromtimestamp(start, _CST).strftime("%Y-%m-%d") if start else "?"
        items.append({"id": s["id"][:20], "date": d, "start": start,
                      "in": i, "cache": c, "out": o, "calls": calls,
                      "f": f, "peak": cpk, "off": coff, "mix": cmix,
                      "running": start and not s["ended_at"]})
        g = day[d]; g["in"] += i; g["cache"] += c; g["out"] += o
        g["calls"] += calls or len(tups)
        g["peakN"] += n_peak; g["totN"] += len(tups)
    return items, day


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pro", action="store_true")
    ap.add_argument("--usd", action="store_true")
    ap.add_argument("--since", type=int, default=None)
    ap.add_argument("--token-weight", action="store_true")
    ap.add_argument("--detail", action="store_true", help="追加每会话明细")
    ap.add_argument("--day", default=None, help="只看某天(YYYY-MM-DD)会话明细")
    ap.add_argument("--db", default=_DB)
    a = ap.parse_args()

    if not os.path.exists(a.db):
        print(f"[err] 找不到 {a.db}"); return 1
    tray = "usd" if a.usd else "cny"
    tier = "pro" if a.pro else "flash"
    p = PRICE[tray][tier]; sym = SYM[tray]
    sessions, asst = load(a.db, a.since)
    items, day = build(sessions, asst, p, a.token_weight)

    now = datetime.now(_CST).strftime("%Y-%m-%d %H:%M")
    print(f"qwenthink 每日成本 · {tier.upper()}/{tray.upper()} · {now} 北京 · 价(每百万{tray.upper()}): 未命中{p['miss']} 命中{p['hit']} 输出{p['out']}(谷=峰×0.5)")
    print(f"{'日期':11} {'新输入':>10} {'缓存':>12} {'输出':>9} {'calls':>6} {'峰f':>4} {'全峰':>11} {'全谷':>11} {'混合':>11}")
    print("-" * 86)
    gtot = {"in": 0, "cache": 0, "out": 0, "peakN": 0, "totN": 0, "calls": 0}
    for d in sorted(day, reverse=True):
        g = day[d]
        f = (g["peakN"] / g["totN"]) if g["totN"] else 0.0
        fd = Decimal(str(f))
        ck = M(g["in"]) * p["miss"] + M(g["cache"]) * p["hit"] + M(g["out"]) * p["out"]
        ck_off = ck / 2
        ck_mix = fd * ck + (1 - fd) * ck_off
        for k in gtot: gtot[k] += g[k]
        print(f"{d:11} {g['in']:>10,} {g['cache']:>12,} {g['out']:>9,} {g['calls']:>6} {f:>4.0%} {sym}{ck:>9.2f} {sym}{ck_off:>9.2f} {sym}{ck_mix:>9.2f}")
    # profile 合计
    fA = gtot["peakN"] / gtot["totN"] if gtot["totN"] else 0.0
    fAd = Decimal(str(fA))
    cA = M(gtot["in"]) * p["miss"] + M(gtot["cache"]) * p["hit"] + M(gtot["out"]) * p["out"]
    cA_mix = fAd * cA + (1 - fAd) * (cA / 2)
    print("-" * 86)
    print(f"{'合计':11} {gtot['in']:>10,} {gtot['cache']:>12,} {gtot['out']:>9,} {gtot['calls']:>6} {fA:>4.0%} {sym}{cA:>9.2f} {sym}{cA/2:>9.2f} {sym}{cA_mix:>9.2f}")

    # 会话明细
    show = []
    if a.day:
        show = [it for it in items if it["date"] == a.day]
    elif a.detail:
        show = items
    if show:
        print("\n— 会话明细" + (f" ({a.day})" if a.day else "") + " —")
        print(f"{'会话':21} {'日期':10} {'新输入':>9} {'缓存':>10} {'输出':>8} {'峰f':>4} {'全峰':>10} {'混合':>10}")
        for it in sorted(show, key=lambda x: (-(x["start"] or 0))):
            run = "＊" if it["running"] else " "
            fd = Decimal(str(it["f"]))
            print(f"{it['id']:21} {it['date']:10} {it['in']:>9,} {it['cache']:>10,} {it['out']:>8,} {it['f']:>4.0%} {sym}{it['peak']:>8.2f} {sym}{it['mix']:>8.2f}{run}")
    print("\n(纯本地计算·零token消耗·金额均带单位·进行中会话＊未计入最后1次调用)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())