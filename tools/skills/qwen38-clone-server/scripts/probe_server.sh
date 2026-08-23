#!/bin/bash
# ============================================================
# probe_server.sh — 检测克隆机的 GPU 架构 + 核对 qwen3.8 数据盘
# 用法: bash probe_server.sh <ALIAS>
# 输出：卡型号 + compute_cap + 换算的 sM + /root/autodl-tmp 数据核对
# ============================================================
set -euo pipefail
ALIAS="${1:?用法: $0 <ALIAS>}"
ssh -o BatchMode=yes "$ALIAS" '
echo "=== GPU / compute_cap ==="
nvidia-smi --query-gpu=name,memory.total,compute_cap --format=csv,noheader 2>/dev/null
echo "=== 数据盘 /root/autodl-tmp ==="
du -sh /root/autodl-tmp 2>/dev/null
echo "--- models ---"
ls /root/autodl-tmp/models/*.gguf 2>/dev/null || echo "无 models（空盘）"
echo "--- llama.cpp build 目录 ---"
ls -d /root/autodl-tmp/llama.cpp/build*/ 2>/dev/null || echo "无 build"
echo "--- 模板/启动/keys ---"
ls /root/autodl-tmp/qwen38_template.jinja /root/autodl-tmp/start_llama_server*.sh /root/autodl-tmp/.api_keys 2>/dev/null
echo "--- key 有效行数 ---"
grep -vcE "^[[:space:]]*(#|$)" /root/autodl-tmp/.api_keys 2>/dev/null
echo "--- 内存(cgroup/size) ---"
free -g 2>/dev/null | head -2 | tail -1
cat /sys/fs/cgroup/memory.max 2>/dev/null && echo ""
'
echo ""
echo "计算架构映射：compute_cap major.minor → sM=major×10+minor（8.9→89, 12.0→120）"