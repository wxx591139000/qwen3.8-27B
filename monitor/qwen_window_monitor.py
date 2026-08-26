#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qwen_window_monitor.py — 逐窗口(qwenthink)API 用量常驻监控

解析 ~/.hermes/profiles/qwenthink/logs/agent.log 里形如
  [session_id] agent.conversation_loop: API call #N: ... in=X out=Y total=Z latency=T
的行，按窗口(session_id)聚合 token 与耗时。只读 agent.log，不碰任何运行状态。

用法:
  python qwen_window_monitor.py            # 打印当前活跃窗口当日摘要
  python qwen_window_monitor.py --dump     # 输出所有窗口全量累计(历史)
  python qwen_window_monitor.py --append   # 追加一行快照到 monitor.log(计划任务用)
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import sys
from collections import defaultdict
from datetime import datetime

LOG = os.path.expanduser("~/.hermes/profiles/qwenthink/logs/agent.log")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "monitor.log")

# 只抓 "API call" 行；各字段与实时数据强绑定
PAT = re.compile(
    r"\[(\d{8}_\d{6}_[0-9a-f]+)\]"
    r".*API call #(\d+):"
    r".*in=(\d+) out=(\d+) total=(\d+)"
    r" latency=([\d.]+)s"
)
TS_PAT = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)")


def load_calls(path: str):
    """返回 [(ts, session_id, call#, in, out, total, latency)]"""
    calls = []
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            for line in f:
                m = PAT.search(line)
                if not m:
                    continue
                sid, num, i, o, t, lat = m.groups()
                ts = line[:19].strip()
                calls.append((ts, sid, int(num), int(i), int(o), int(t), float(lat)))
    except FileNotFoundError:
        pass
    return calls


def fmt_tok(n: int) -> str:
    n = int(n)
    if n < 1000:
        return str(n)
    units = ((10**9, "B"), (10**6, "M"), (10**3, "K"))
    for th, suf in units:
        if n >= th:
            v = n / th
            return f"{v:.2f}{suf}" if v < 100 else f"{v:.0f}{suf}"
    return str(n)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", action="store_true", help="输出所有窗口全量累计")
    ap.add_argument("--append", action="store_true", help="追加快照到 monitor.log")
    args = ap.parse_args()

    calls = load_calls(LOG)
    if not calls:
        print("[monitor] agent.log 暂无 API call 记录")
        return 0

    now = datetime.now()
    today = now.strftime("%Y-%m-%d")

    # 分组：当日 与 全量
    groups = {
        "today": [c for c in calls if c[0].startswith(today)],
        "all": calls,
    }
    # 当前活跃：最近 10 分钟内有请求的窗口
    active_cutoff = now.replace(second=0, microsecond=0)
    recent = [c for c in calls if c[0] >= now.strftime("%Y-%m-%d %H:%M")]
    cur_secs = {c[1] for c in recent}

    best = args.dump and "all" or "today"
    lines = []
    header = ("%-24s %6s %12s %10s %13s %10s %12s" %
              ("窗口(session)", "calls", "prompt_in", "out_tok", "total_tok",
               "avg_lat", "活跃至"))
    lines.append(header)
    lines.append("-" * len(header))

    for sid, cc in groups[best].items() if not isinstance(groups[best], list) else []:
        pass

    # 按 best 范围分组
    gmap = defaultdict(list)
    for c in groups[best]:
        gmap[c[1]].append(c)

    active_mark = set()
    for sid, cl in sorted(gmap.items(), key=lambda kv: -len(kv[1])):
        n = len(cl)
        i = sum(c[3] for c in cl)
        o = sum(c[4] for c in cl)
        t = sum(c[5] for c in cl)
        lat = sum(c[6] for c in cl) / n
        last = max(c[0][11:16] for c in cl)
        mark = " ●活跃" if sid in cur_secs else ""
        lines.append("%-24s %6d %12s %10s %13s %9.1fs %4s%s" %
                     (sid, n, fmt_tok(i), fmt_tok(o), fmt_tok(t), lat, last, mark))

    body = "\n".join(lines)
    stamp = f"[{now.strftime('%Y-%m-%d %H:%M:%S')}] qwenthink 窗口用量(范围={'全量' if best=='all' else '今日'})\n{body}"

    if args.append:
        with open(OUT, "a", encoding="utf-8") as f:
            f.write(stamp + "\n\n")
    else:
        print(stamp)
    return 0


if __name__ == "__main__":
    sys.exit(main())