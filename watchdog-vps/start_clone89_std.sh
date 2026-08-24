#!/bin/bash
BIN=/root/autodl-tmp/llama.cpp/build89/bin/llama-server
MODEL=/root/autodl-tmp/models/Qwen3.8-27B-Q4_K_M.gguf
MTP=/root/autodl-tmp/models/mtp-Qwen3.8-27B-Q4_0.gguf
MMPROJ=/root/autodl-tmp/models/mmproj-Qwen3.8-27B-Q8_0.gguf
TEMPLATE=/root/autodl-tmp/qwen38_template.jinja
KEYS=/root/autodl-tmp/.api_keys
pkill -f "build89/bin/llama-server" 2>/dev/null
sleep 1
cd /root/autodl-tmp
nohup $BIN -m $MODEL --alias qwen3.8-27b -ngl 999 -c 262144 -fa on \
  -ctk q4_0 -ctv q4_0 -np 1 --reasoning on --reasoning-budget 2000 --jinja \
  --chat-template-file $TEMPLATE -md $MTP --spec-type draft-mtp \
  --mmproj $MMPROJ --host 0.0.0.0 --port 6006 --api-key-file $KEYS \
  > /root/autodl-tmp/llama_clone89.log 2>&1 &
echo "llama-server (sm89) PID=$!"
