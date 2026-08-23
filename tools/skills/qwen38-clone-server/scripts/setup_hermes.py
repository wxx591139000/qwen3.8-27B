#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""setup_hermes.py — 把 Hermes 的 qwen-思考入口(qwenthink profile)指到新克隆服务器。

用法:
  python setup_hermes.py <public_base_url> <api_key>
示例:
  python setup_hermes.py https://u<xxx>.westc.seetacloud.com:8443/v1 sk-qwen36-Wu...

作用:
  仅改 ~/.hermes/profiles/qwenthink/config.yaml 里的 providers.qwenthink
  {base_url, api_key, default_model} → 指向新服务器。其余(全局 config/tts/stt/
  memory/delegation 的 provider)一律不动，deepseek 全局默认保持。

  改完后：新开 PowerShell → `hermes-qwen`(=hermes -p qwenthink chat) 即用新机器 qwen。
  （新机须以 --reasoning on 起 llama-server 才有思考；此只改端点，思考档由 start 脚本控制。）
"""
import os, sys

QW = os.path.expanduser("~/.hermes/profiles/qwenthink/config.yaml")
MODEL = "qwen3.8-27b"

def main():
    if len(sys.argv) < 3:
        print("用法: setup_hermes.py <public_base_url> <api_key>"); sys.exit(1)
    url, key = sys.argv[1].rstrip("/"), sys.argv[2]
    if not os.path.isfile(QW):
        print(f"⚠️  找不到 qwenthink profile: {QW}（先建 профиль，参考伞 README/Hermes 接入）"); sys.exit(1)
    import re
    txt = open(QW, encoding="utf-8").read()
    # 精确只改 providers 段内 qwenthink 的 base_url/api_key/default_model
    block = re.search(r'(?m)^  qwenthink:\s*\n(?:[ \t]{4}.*\n)+', txt)
    if not block:
        print("⚠️  qwenthink profile 里没有 providers.qwenthink 块，请先按 Hermes 接入步骤建 profile"); sys.exit(1)
    seg = block.group(0)
    seg = re.sub(r'(?m)^(\s{4}base_url:).*$', r'\1 ' + url, seg)
    seg = re.sub(r'(?m)^(\s{4}api_key:).*$', r'\1 ' + key, seg)
    seg = re.sub(r'(?m)^(\s{4}default_model:).*$', r'\1 ' + MODEL, seg)
    txt = txt[:block.start()] + seg + txt[block.end():]
    # 备份 + 写回（UTF-8 无 BOM，与 Hermes 读取一致）
    import shutil, datetime
    shutil.copy(QW, QW + f".bak.{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}")
    open(QW, "w", encoding="utf-8").write(txt)
    print(f"✅ qwenthink profile -> base_url={url} model={MODEL}")
    print("   新开 PowerShell → hermes-qwen → 即连新机 qwen（新机须 --reasoning on 才有思考）")

if __name__ == "__main__":
    main()