#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qwen_cost.py — qwenthink profile 峰谷成本核算（按 deepseek-pricing skill §4 口径）

数据源：~/.hermes/profiles/qwenthink/state.db（只读 SQLite，WAL 安全）
  sessions表: input_tokens=缓存未命中的新输入(不含缓存), cache_read_tokens, output_tokens
  messages表: role='assistant' 行 = 每次 API 调用(带 epoch timestamp) → 峰谷拆分
峰谷窗口(北京时间): 工作日 09-12 / 14-18 为峰,其余(含周末)为谷, 谷=峰×0.5

计费(每1M tokens, 默认 Flash 档人民币):
  cost_peak += 新输入×未命中峰价 + 缓存×命中峰价 + 输出×输出峰价
  cost_off  = cost_peak/2
  f = 落在峰窗口的 assistant 调用占比(token 可选加权)
  cost_mixed = f×cost_peak + (1-f)×cost_off

用法:
  python qwen_cost.py                    # 全量: 全峰/全谷/混合三档, Flash 人民币
  python qwen_cost.py --pro              # 用 V4-Pro 档(约×3)作上限参照
  python qwen_cost.py --usd              # 用美元价
  python qwen_cost.py --since 2          # 只看最近 2 天
  python qwen_cost.py --token-weight     # f 用 token 加权而非计数
"""
from __future__ import annotations

import argparse
import os
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from decimal import Decimal

# 北京 = UTC+8(固定，避免 Windows 缺 tzdata)
_CST = timezone(timedelta(hours=8))
_BJ_DEFAULT = os.path.expanduser("~/.hermes/profiles/qwenthink/state.db")

# 每百万 tokens 峰价。谷 = ×0.5。来源 api-docs.deepseek.com/quick_start/pricing
PRICE = {
    # 人民币
    "cny": {
        "flash": {"miss": Decimal("3.0"), "hit": Decimal("0.10"), "out": Decimal("9.0")},
        "pro":   {"miss": Decimal("9.0"), "hit": Decimal("0.30"), "out": Decimal("27.0")},
    },
    # 美元(独立定价，≠汇率换算)
    "usd": {
        "flash": {"miss": Decimal("0.44"), "hit": Decimal("0.014"), "out": Decimal("1.32")},
        "pro":   {"miss": Decimal("1.32"), "hit": Decimal("0.044"), "out": Decimal("3.96")},
    },
}
SYM = {"cny": "¥", "usd": "$"}


def is_peak_bj(epoch: float) -> bool:
    """北京时间工作日 09-12 / 14-18 为高峰。"""
    dt = datetime.fromtimestamp(epoch, _CST)
    if dt.weekday() >= 5:          # 周末全谷
        return False
    return (9 <= dt.hour < 12) or (14 <= dt.hour < 18)


def load(db: str, since_days: int | None):
    con = sqlite3.connect("file:" + db.replace("\\", "/") + "?mode=ro", uri=True)
    cur = con.cursor()
    since_ts = (datetime.now(_CST) - timedelta(days=since_days)).timestamp() if since_days else None

    cols = ["id", "model", "started_at", "ended_at", "end_reason",
            "input_tokens", "output_tokens", "cache_read_tokens",
            "cache_write_tokens", "api_call_count"]
    sql = f"SELECT {', '.join(cols)} FROM sessions"
    if since_ts:
        sql += " WHERE ended_at IS NOT NULL AND ended_at >= ?"
        rows = cur.execute(sql, (since_ts,)).fetchall()
    else:
        rows = cur.execute(sql).fetchall()
    sessions = [dict(zip(cols, r)) for r in rows]

    # 每次 assistant 消息 = 一次 API 调用，取时间戳做峰谷拆分
    asst = cur.execute(
        "SELECT session_id, timestamp, token_count FROM messages WHERE role='assistant'"
    ).fetchall()
    con.close()
    per = defaultdict(list)
    for sid, ts, tc in asst:
        per[sid].append((ts, tc or 0))
    return sessions, per


def fmt_money(x: Decimal) -> str:
    return f"{x:.2f}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pro", action="store_true", help="用 V4-Pro 档(约×3)作上限")
    ap.add_argument("--usd", action="store_true", help="用美元价")
    ap.add_argument("--since", type=int, default=None, help="只看最近 N 天")
    ap.add_argument("--token-weight", action="store_true", help="峰谷 f 用 token 加权")
    ap.add_argument("--db", default=_BJ_DEFAULT, help="state.db 路径")
    a = ap.parse_args()

    if not os.path.exists(a.db):
        print(f"[错误] 找不到 {a.db}"); return 1
    tray = "usd" if a.usd else "cny"
    tier = "pro" if a.pro else "flash"
    p = PRICE[tray][tier]
    sym = SYM[tray]

    sessions, asst = load(a.db, a.since)

    # 汇总
    tot = {"in": 0, "cache": 0, "out": 0, "calls": 0}
    peak_num = 0; tot_calls = 0; peak_w = Decimal("0"); tot_w = Decimal("0")
    rows_out = []

    for s in sessions:
        i = s["input_tokens"] or 0
        c = s["cache_read_tokens"] or 0
        o = s["output_tokens"] or 0
        calls = s["api_call_count"]
        tups = asst.get(s["id"], [])
        n_peak = sum(1 for ts, _ in tups if is_peak_bj(ts))
        w_peak = sum(Decimal(tc) for ts, tc in tups if is_peak_bj(ts))
        w_all = sum(Decimal(tc) for _, tc in tups)
        f_c = (n_peak / len(tups)) if tups else 0.0
        f_w = (w_peak / w_all) if w_all else 0.0
        f = f_w if a.token_weight else f_c

        cost_peak = Decimal(i) * p["miss"] + Decimal(c) * p["hit"] + Decimal(o) * p["out"]
        cost_off = cost_peak / 2
        fd = Decimal(str(f))
        cost_mix = fd * cost_peak + (1 - fd) * cost_off

        tot["in"] += i; tot["cache"] += c; tot["out"] += o
        calls_c = calls or (len(tups) if tups else 1)
        tot["calls"] += calls_c
        peak_num += n_peak; tot_calls += len(tups)
        peak_w += w_peak; tot_w += w_all

        start = datetime.fromtimestamp(s["started_at"], _CST).strftime("%m-%d %H:%M") if s["started_at"] else "?"
        if s["started_at"] and s["ended_at"] is None:
            end = "进行中"
        elif s["ended_at"]:
            end = datetime.fromtimestamp(s["ended_at"], _CST).strftime("%m-%d %H:%M")
        else:
            end = "?"
        model = (s["model"] or "?")[:26]
        rows_out.append((s["id"][:18], model, i, c, o, calls_c,
                         f, cost_peak, cost_off, cost_mix, f"{start}~{end}"))

    def M(x):  # 每百万折算×百万
        return Decimal(x) * Decimal("0.000001")

    # 三档合计(用每百万价 × tokens/1000000)
    ck_peak = M(tot["in"]) * p["miss"] + M(tot["cache"]) * p["hit"] + M(tot["out"]) * p["out"]
    ck_off = ck_peak / 2
    f_all = (peak_w / tot_w) if (a.token_weight and tot_w) else (peak_num / tot_calls if tot_calls else 0.0)
    f_d = Decimal(str(f_all))
    ck_mix = f_d * ck_peak + (1 - f_d) * ck_off

    head = (f"%-16s %-10s %12s %8s %10s %7s %5s %10s %10s %10s  %14s" %
            ("会话", "模型", "新输入", "缓存", "输出", "calls", "峰f", "全峰", "全谷", "混合", "时间"))
    print("=" * 110)
    print(f"qwenthink 峰谷成本核算 · {tier.upper()}/{tray.upper()}档 · {datetime.now(_CST).strftime('%Y-%m-%d %H:%M')} 北京")
    print(f"价目(每百万{tray.upper()}): 输入未命中峰{p['miss']} 缓存命中峰{p['hit']} 输出峰{p['out']} 谷=峰×0.5")
    print(head)
    print("-" * 110)
    for sid, model, i, c, o, calls, f, cpk, coff, cmix, rng in sorted(
            rows_out, key=lambda r: -(r[7])):
        print("%-16s %-10s %12d %8d %10d %7d %5.2f %9s%s %9s%s %9s%s  %14s" %
              (sid, model, i, c, o, calls, f, fmt_money(cpk), sym, fmt_money(coff), sym,
               fmt_money(cmix), sym, rng))
    print("-" * 110)
    print(f"合计: 新输入{tot['in']:,} 缓存{tot['cache']:,} 输出{tot['out']:,} "
          f"calls{tot['calls']} 峰占{f_all:.1%}")
    print(f"  😱全峰: {sym}{fmt_money(ck_peak)}")
    print(f"  🌙全谷: {sym}{fmt_money(ck_off)}   (=峰×0.5)")
    print(f"  ⚖混合(峰{f_all:.0%}): {sym}{fmt_money(ck_mix)}")
    print("=" * 110)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())