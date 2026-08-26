#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qwen_cost.py — qwenthink 每日峰谷成本核算（纯本地，零 token 消耗）
默认同时输出 Flash / Pro 两档，按天表格汇总；可 --day/--detail 看会话明细。
数据源 ~/.hermes/profiles/qwenthink/state.db（只读）；峰谷=北京工作日 09-12/14-18，谷=峰×0.5。

用法:
  python qwen_cost.py                      # 每日两档成本表(默认)
  python qwen_cost.py --day YYYY-MM-DD     # 某天会话明细
  python qwen_cost.py --detail             # 全部分会话明细
  python qwen_cost.py --usd --since 3      # 美元价 / 只看近 3 天
  python qwen_cost.py --since 1 --report   # 追加快照到 monitor/daily_cost.log (自动任务用)
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
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "daily_cost.log")

# 每百万 tokens 峰价(谷=×0.5)。来源 api-docs.deepseek.com/quick_start/pricing
PRICE = {
    "cny": {"flash": (Decimal("3.0"), Decimal("0.10"), Decimal("9.0")),
            "pro":   (Decimal("9.0"), Decimal("0.30"), Decimal("27.0"))},
    "usd": {"flash": (Decimal("0.44"), Decimal("0.014"), Decimal("1.32")),
            "pro":   (Decimal("1.32"), Decimal("0.044"), Decimal("3.96"))},
}
SYM = {"cny": "¥", "usd": "$"}
TIERS = ("flash", "pro")


def is_peak_bj(epoch):
    dt = datetime.fromtimestamp(epoch, _CST)
    if dt.weekday() >= 5:
        return False
    return (9 <= dt.hour < 12) or (14 <= dt.hour < 18)


def load(db, since_days):
    con = sqlite3.connect("file:" + db.replace("\\", "/") + "?mode=ro", uri=True)
    cur = con.cursor()
    since_ts = (datetime.now(_CST) - timedelta(days=since_days)).timestamp() if since_days else None
    cols = ["id", "started_at", "ended_at", "input_tokens", "output_tokens",
            "cache_read_tokens", "api_call_count"]
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


def M(x):
    return Decimal(x) * Decimal("0.000001")


def cost(miss, hit, out, i, c, o, f):
    fd = Decimal(str(f))
    peak = M(i) * miss + M(c) * hit + M(o) * out
    off = peak / 2
    return peak, off, fd * peak + (1 - fd) * off


def collect(sessions, asst):
    """返回 items(每会话 token + 峰占比) 与 day(按天聚合)"""
    items, day = [], defaultdict(lambda: {"in": 0, "cache": 0, "out": 0, "calls": 0, "pN": 0, "tN": 0})
    for s in sessions:
        i, c, o = (s["input_tokens"] or 0), (s["cache_read_tokens"] or 0), (s["output_tokens"] or 0)
        tups = asst.get(s["id"], [])
        nP = sum(1 for ts, _ in tups if is_peak_bj(ts))
        f = (nP / len(tups)) if tups else 0.0
        st = s["started_at"]
        d = datetime.fromtimestamp(st, _CST).strftime("%Y-%m-%d") if st else "?"
        items.append({"id": s["id"][:20], "date": d, "start": st,
                      "in": i, "cache": c, "out": o, "calls": s["api_call_count"] or len(tups),
                      "f": f, "run": bool(st and not s["ended_at"])})
        g = day[d]; g["in"] += i; g["cache"] += c; g["out"] += o
        g["calls"] += s["api_call_count"] or len(tups)
        g["pN"] += nP; g["tN"] += len(tups)
    return items, day


def build_lines(day, sym, tray):
    """返回(示范)每日两档表格的文本行列表 + profile 合计行。"""
    H = f"{'日期':11} {'新输入':>9} {'缓存':>11} {'输出':>8} {'calls':>6} {'峰f':>4} " \
        f"{'Flash混合':>10} {'Flash全峰':>10} {'Pro混合':>10} {'Pro全峰':>10}"
    lines = [H, "-" * (len(H) + 6)]
    gtot = {"in": 0, "cache": 0, "out": 0, "calls": 0, "pN": 0, "tN": 0}
    for d in sorted(day, reverse=True):
        g = day[d]
        for k in gtot: gtot[k] += g[k]
        f = (g["pN"] / g["tN"]) if g["tN"] else 0.0
        pF = cost(*PRICE[tray]["flash"]) if False else None
        fl = PRICE[tray]["flash"]; pr = PRICE[tray]["pro"]
        fp_, fo_, fm = cost(*fl, g["in"], g["cache"], g["out"], f)
        pp_, po_, pm = cost(*pr, g["in"], g["cache"], g["out"], f)
        lines.append(f"{d:11} {g['in']:>9,} {g['cache']:>11,} {g['out']:>8,} {g['calls']:>6} "
                     f"{f:>4.0%} {sym}{fm:>8.2f} {sym}{fp_:>8.2f} {sym}{pm:>8.2f} {sym}{pp_:>8.2f}")
    fA = (gtot["pN"] / gtot["tN"]) if gtot["tN"] else 0.0
    fl = PRICE[tray]["flash"]; pr = PRICE[tray]["pro"]
    aF, _, aFm = cost(*fl, gtot["in"], gtot["cache"], gtot["out"], fA)
    aP, _, aPm = cost(*pr, gtot["in"], gtot["cache"], gtot["out"], fA)
    lines.append("-" * (len(H) + 6))
    lines.append(f"{'合计':11} {gtot['in']:>9,} {gtot['cache']:>11,} {gtot['out']:>8,} {gtot['calls']:>6} "
                 f"{fA:>4.0%} {sym}{aFm:>8.2f} {sym}{aF:>8.2f} {sym}{aPm:>8.2f} {sym}{aP:>8.2f}")
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--usd", action="store_true")
    ap.add_argument("--since", type=int, default=None)
    ap.add_argument("--day", default=None)
    ap.add_argument("--detail", action="store_true")
    ap.add_argument("--report", action="store_true", help="追加快照到 daily_cost.log")
    ap.add_argument("--db", default=_DB)
    a = ap.parse_args()
    if not os.path.exists(a.db):
        print(f"[err] 找不到 {a.db}"); return 1
    tray = "usd" if a.usd else "cny"; sym = SYM[tray]
    sessions, asst = load(a.db, a.since)
    items, day = collect(sessions, asst)
    if not day:
        print("(无会话数据)"); return 0

    title = f"qwenthink 每日成本 · {'/'.join(t.upper() for t in TIERS)} × {tray.upper()} · {datetime.now(_CST).strftime('%Y-%m-%d %H:%M')} 北京"
    head = f"(价每1M{tray.upper()}: Flash 未命中{PRICE[tray]['flash'][0]}/命中{PRICE[tray]['flash'][1]}/输出{PRICE[tray]['flash'][2]}; Pro 未命中{PRICE[tray]['pro'][0]}/命中{PRICE[tray]['pro'][1]}/输出{PRICE[tray]['pro'][2]}; 谷=峰×0.5)"
    body = "\n".join(build_lines(day, sym, tray))

    out = f"{title}\n{head}\n{body}\n"

    # 会话明细(两档混合)
    show = [it for it in items if a.day is None or it["date"] == a.day] if (a.day or a.detail) else []
    if show:
        h2 = (f"{'会话':21} {'日期':10} {'新输入':>8} {'缓存':>9} {'输出':>7} {'峰f':>4} {'Flash混合':>9} {'Pro混合':>9}")
        det = [h2, "-" * len(h2)]
        pos = PRICE[tray]["flash"]; pro = PRICE[tray]["pro"]
        for it in sorted(show, key=lambda x: -(x["start"] or 0)):
            _, _, fm = cost(*pos, it["in"], it["cache"], it["out"], it["f"])
            _, _, pm = cost(*pro, it["in"], it["cache"], it["out"], it["f"])
            run = "＊" if it["run"] else " "
            det.append(f"{it['id']:21} {it['date']:10} {it['in']:>8,} {it['cache']:>9,} {it['out']:>7,} "
                       f"{it['f']:>4.0%} {sym}{fm:>7.2f} {sym}{pm:>7.2f}{run}")
        out += "\n— 会话明细" + (f" ({a.day})" if a.day else "") + " —\n" + "\n".join(det) + "\n"
    out += "(纯本地·零token·均带单位·进行中会话＊未计最后一次调用)\n"

    if a.report:
        ts = datetime.now(_CST).strftime("%Y-%m-%d %H:%M:%S")
        with open(OUT, "a", encoding="utf-8") as f:
            f.write(f"==== {ts} ====\n{out}\n")
        print(f"[ok] 已追加到 {OUT}")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())