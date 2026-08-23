#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""update_codex.py — 新增独立的 codex provider + PowerShell 别名（不覆盖现有）。

用法:
  python update_codex.py <public_base_url> <clone_n> <api_key>
示例:
  python update_codex.py https://u<xxx>.weste.seetacloud.com:8443/v1 1 sk-qwen36-...

作用:
  1. ~/.codex/config.toml 追加 [model_providers.qwen38clone<N>]（wire_api=responses）
  2. PowerShell profile 追加 function codex-clone<N>-free
  只增不改：不触碰 qwen38(5090)/qwen38-vgpu 等现有 provider。
"""
import os, re, sys

def expand(p): return os.path.expanduser(p)

def main():
    if len(sys.argv) < 4:
        print("用法: update_codex.py <base_url> <clone_n> <api_key>"); sys.exit(1)
    url, n, key = sys.argv[1], sys.argv[2], sys.argv[3]
    provider = f"qwen38clone{n}"
    alias_fn = f"codex-clone{n}-free"

    # 1) config.toml
    cfg = expand("~/.codex/config.toml")
    if os.path.isfile(cfg):
        txt = open(cfg, encoding="utf-8").read()
        if f"[model_providers.{provider}]" in txt:
            print(f"ℹ️  已存在 {provider}，跳过追加（如需改 base_url 请手动改）")
        else:
            block = (f"\n[model_providers.{provider}]\n"
                     f'name = "Qwen3.8-27B (AutoDL clone {n})"\n'
                     'wire_api = "responses"\n'
                     f'base_url = "{url.rstrip("/")}"\n'
                     f'experimental_bearer_token = "{key}"\n')
            open(cfg, "a", encoding="utf-8").write(block)
            print(f"✅ config.toml 已追加 [{provider}] base_url={url}")
    else:
        print(f"⚠️  找不到 {cfg}，跳过（Python 只追加，请手动加 provider）")

    # 2) PowerShell profile
    profiles = [expand("~/Documents/WindowsPowerShell/Microsoft.PowerShell_profile.ps1"),
                expand("~/Documents/PowerShell/Microsoft.PowerShell_profile.ps1")]
    prof = next((p for p in profiles if os.path.isfile(p)), profiles[0])
    fn = f"function {alias_fn} {{ codex -c 'model_provider=\"{provider}\"' -c 'model=\"qwen3.8-27b\"' --dangerously-bypass-approvals-and-sandbox @args }}"
    if os.path.isfile(prof):
        txt = open(prof, encoding="utf-8-sig", errors="replace").read()
        if f"function {alias_fn}" in txt:
            print(f"ℹ️  别名 {alias_fn} 已存在，跳过")
        else:
            tail = f"\n# Qwen3.8 clone {n} ({url})\n{fn}\n"
            open(prof, "a", encoding="utf-8", newline="\r\n").write(tail)
            print(f"✅ 已追加别名 {alias_fn} 到 {prof}")
    else:
        print(f"⚠️  找不到 profile {prof}，跳过（请手动加：{fn}）")

    print(f"\n完成。验证：codex exec -c 'model_provider=\"{provider}\"' -c 'model=\"qwen3.8-27b\"' --skip-git-repo-check 'Reply with exactly: CLONE_{n}_OK'")

if __name__ == "__main__":
    main()