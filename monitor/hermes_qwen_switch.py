#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hermes_qwen_switch.py — Hermes qwen「开哪台连哪台」自动切换器（纯本地，零 token 消耗）

背景：Hermes 的 qwen 入口 profile `~/.hermes/profiles/qwenthink/config.yaml` 的
`qwenthink` provider.base_url 只能写死一个地址，不会自动找在线 clone。
本脚本：启动时探测各 clone 公网，选「在线且服务正常」的那台，把它的公网 base_url
写回 profile（只改 base_url 一行，先备份，api_key / model / 其它字段一律不动）。
满足「不管开 clone1-5 哪台，hermes-qwen 都连那台」。

用法:
  python hermes_qwen_switch.py --scan        # 只探测各 clone 在线状态（不改任何配置）
  python hermes_qwen_switch.py [--switch]    # 探测→选在线机→回写 base_url→打印切到哪台
  python hermes_qwen_switch.py --set clone4  # 强制指到指定 clone（跳过探测）
  python hermes_qwen_switch.py --restore     # 从备份恢复上次的 config.yaml

采纳提醒：AutoDL 机按小时计费，检测到在线会自动切过去，跑完记得关机。
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime

from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

import yaml

# ---- 配置 ----
# Hermes qwen 入口 profile（改的是这个文件里 qwenthink provider 的 base_url）
PROFILE_YAML = os.path.expanduser("~/.hermes/profiles/qwenthink/config.yaml")

# 各 clone 公网 base_url 表（AutoDL 隧道 8443 + /v1）。
# key = clone 名（--set 用它）；value = (公网 base_url, 备注)。
# 未知/临时未开的留 None 占位；探测时自动跳过。
TARGETS = {
    "clone1": (None, "westc(未知公网，待补)"),
    "clone2": ("https://u1068217-b9c1-805a0fa4.westc.seetacloud.com:8443/v1", "westc:19407"),
    "clone3": (None, "westd(未知公网，待补)"),
    "clone4": ("https://u1068217-x588-77ebd208.westd.seetacloud.com:8443/v1", "westd:18574 现役"),
    "clone5": ("https://u1068217-tvka-e5d7d4be.westb.seetacloud.com:8443/v1", "westb:27190 已校准(2026-09-16健康200)"),
}

# llama-server /v1/models 探测超时(秒)，连不上判离线
TIMEOUT = 8
BACKUP_SUFFIX = ".bak-switch"


def probe(base_url: str, api_key: str | None) -> int:
    """探测一个 base_url 是否在线且服务正常。返回 HTTP 状态码；失败返回 0。"""
    if not base_url:
        return 0
    url = base_url.rstrip("/") + "/models"
    req = Request(url)
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    try:
        with urlopen(req, timeout=TIMEOUT) as r:
            return r.status
    except (URLError, HTTPError, OSError, TimeoutError):
        return 0


def current_base(full: dict) -> str | None:
    """从已解析 profile 里取 qwenthink provider 当前 base_url（探测时参考）。"""
    try:
        return full["providers"]["qwenthink"]["base_url"]
    except (KeyError, TypeError):
        return None


def load() -> dict:
    with open(PROFILE_YAML, encoding="utf-8") as f:
        return yaml.safe_load(f)


def scan(all_cfg: dict, api_key: str | None) -> list:
    """探测所有 target，返回 [(name, base_url, http_code, note)] 按成功率排。"""
    cur = current_base(all_cfg)
    rows = []
    for name, (base, note) in TARGETS.items():
        # 当前正在用的也会探测（作为候选）
        status = probe(base, api_key)
        tag = " ← 当前在用" if base and base == cur else ""
        rows.append((name, base, status, note + tag))
    # 在线优先，其次当前在用，再其次原名顺序
    rows.sort(key=lambda r: (r[2] > 0, r[2] == 200 and r[2] == cur, r[2]))
    # 200 最优先在前面
    rows.sort(key=lambda r: - (1 if r[2] == 200 else 0) - (0.5 if r[2] > 0 else 0), )
    return rows


def do_switch(force: str | None = None) -> int:
    if not os.path.exists(PROFILE_YAML):
        print(f"❌ 找不到 profile: {PROFILE_YAML}")
        return 1

    all_cfg = load()
    api_key = all_cfg.get("providers", {}).get("qwenthink", {}).get("api_key")

    if force:
        base, note = TARGETS.get(force, (None, ""))
        if not base:
            print(f"❌ 未知 clone: {force}。可选: {', '.join(TARGETS)}")
            return 1
        pick_name, pick_base, pick_note = force, base, note
        confirmed = True
    else:
        rows = scan(all_cfg, api_key)
        print("探测结果:")
        for n, b, s, note in rows:
            st = f"HTTP {s}" if s else "离线/不通"
            url = b or "（公网未登记）"
            print(f"  [{n}] {st}  {url}  {note}")
        # 选在线且 200 的第一台；否则在线(>0)的第一台；都不行报错
        ok = [r for r in rows if r[2] == 200]
        if not ok:
            ok = [r for r in rows if r[2] > 0]
        if not ok:
            print("\n❌ 没有任何 clone 在线正常。请先开一台再切。")
            return 1
        if len(ok) > 1:
            # 多台在线：优先当前在用的（避免无谓切换）
            cur = current_base(all_cfg)
            cur_ok = [r for r in ok if r[1] == cur]
            if cur_ok:
                ok = cur_ok
        pick_name, pick_base, pick_note = ok[0][0], ok[0][1], ok[0][3]
        confirmed = False

    # 备份（保留每次）
    bak = PROFILE_YAML + BACKUP_SUFFIX
    shutil.copy2(PROFILE_YAML, bak)

    # 只改 qwenthink provider 的 base_url
    all_cfg["providers"]["qwenthink"]["base_url"] = pick_base
    # fallback 里若也有指向 clone 的 base_url 不动（只动主 provider）
    with open(PROFILE_YAML, "w", encoding="utf-8") as f:
        yaml.safe_dump(all_cfg, f, allow_unicode=True, sort_keys=False)

    mode = "[强制指定]" if confirmed else "[自动探测]"
    print(f"\n✅ {mode} Hermes qwen 已切到 {pick_name} → {pick_base}")
    print(f"   备注: {pick_note}")
    print(f"   备份: {bak}")
    print("\n现在可用 `hermes -p qwenthink chat` 跑 Hermes。")
    return 0


def do_scan() -> int:
    if not os.path.exists(PROFILE_YAML):
        print(f"❌ 找不到 profile: {PROFILE_YAML}")
        return 1
    all_cfg = load()
    api_key = all_cfg.get("providers", {}).get("qwenthink", {}).get("api_key")
    rows = scan(all_cfg, api_key)
    cur = current_base(all_cfg)
    print(f"当前 Hermes qwen base_url: {cur or '(未设置)'}\n")
    print("各 clone 探测:")
    for n, b, s, note in rows:
        st = f"HTTP {s} ✓在线" if s else "离线/关机"
        print(f"  [{n}] {st}  {b or '（公网未登记）'}  {note}")
    print("\n(autoDL 按小时计费，脚本只是探测不修改任何配置)")
    return 0


def do_restore() -> int:
    bak = PROFILE_YAML + BACKUP_SUFFIX
    if not os.path.exists(bak):
        print("❌ 没有可用备份。")
        return 1
    shutil.copy2(bak, PROFILE_YAML)
    print(f"✅ 已从 {bak} 恢复 base_url。")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Hermes qwen 自动切换克隆机")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--scan", action="store_true", help="只探测在线状态，不改配置")
    g.add_argument("--switch", action="store_true", help="探测→选在线机→回写 base_url（默认行为）")
    g.add_argument("--set", metavar="CLONE", help="强制切到指定 clone（跳过探测）")
    g.add_argument("--restore", action="store_true", help="从备份恢复")
    args = ap.parse_args()

    if args.scan:
        raise SystemExit(do_scan())
    if args.restore:
        raise SystemExit(do_restore())
    if args.set:
        raise SystemExit(do_switch(force=args.set))
    raise SystemExit(do_switch())


if __name__ == "__main__":
    main()