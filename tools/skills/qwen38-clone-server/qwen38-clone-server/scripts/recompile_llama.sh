#!/bin/bash
# ============================================================
# recompile_llama.sh — 远程按目标 sM 重编 llama-server（用独立 build<sM>）
# 用法: bash recompile_llama.sh <ALIAS> <SM>
#   ALIAS  ssh 别名；SM    目标架构数字，如 89 / 120
# 说明：绝不覆盖克隆来的 build/（旧卡 sm）。带卡模式 -j16；无卡(cgroup≈2G)必须 -j1。
# ============================================================
set -euo pipefail
ALIAS="${1:?用法: $0 <ALIAS> <SM>}"
SM="${2:?}"
echo ">>> 检查内存决定并行度 ..."
MEM=$(ssh -o BatchMode=yes "$ALIAS" "cat /sys/fs/cgroup/memory.max 2>/dev/null || echo 0")
J="16"
if echo "$MEM" | grep -qE '^[0-9]+$' && [ "$MEM" -lt 8000000000 ]; then J="1"; fi
echo "   内存限制=$MEM → 用 -j$J"
ssh -o BatchMode=yes "$ALIAS" "cd /root/autodl-tmp/llama.cpp && cmake -B build${SM} -DGGML_CUDA=ON -DCMAKE_CUDA_COMPILER=/usr/local/cuda/bin/nvcc -DCMAKE_CUDA_ARCHITECTURES=${SM} -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=OFF -DGGML_CCACHE=OFF -DCUDA_cuda_driver_LIBRARY=/usr/local/cuda/lib64/stubs/libcuda.so -DCMAKE_EXE_LINKER_FLAGS=\"-lcuda -L/usr/local/cuda/lib64/stubs\" -DLLAMA_BUILD_UI=OFF > /root/autodl-tmp/cmake${SM}.log 2>&1 && echo CMakeOK && grep -i 'CUDA_ARCHITECTURES' /root/autodl-tmp/cmake${SM}.log | head -1 && nohup cmake --build build${SM} --config Release -j${J} --target llama-server > /root/autodl-tmp/build${SM}.log 2>&1 & echo build_started_pid=\$!"