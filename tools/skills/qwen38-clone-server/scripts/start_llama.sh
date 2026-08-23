#!/bin/bash
# ============================================================
# start_llama.sh — 远程写启动脚本 + 启动 build<SM> llama-server + 等 health
# 用法: bash start_llama.sh <ALIAS> <SM> [PORT]
# 默认 262K 全功能档（MTP+mmproj+关思考），端口默认 6006，6 key。
# ============================================================
set -euo pipefail
ALIAS="${1:?用法: $0 <ALIAS> <SM> [PORT]}"
SM="${2:?}"
PORT="${3:-6006}"
ssh -o BatchMode=yes "$ALIAS" "cat > /root/autodl-tmp/start_clone$SM.sh << 'EOF'
#!/bin/bash
BIN=/root/autodl-tmp/llama.cpp/build$SM/bin/llama-server
MODEL=/root/autodl-tmp/models/Qwen3.8-27B-Q4_K_M.gguf
MTP=/root/autodl-tmp/models/mtp-Qwen3.8-27B-Q4_0.gguf
MMPROJ=/root/autodl-tmp/models/mmproj-Qwen3.8-27B-Q8_0.gguf
TEMPLATE=/root/autodl-tmp/qwen38_template.jinja
KEYS=/root/autodl-tmp/.api_keys
pkill -f \"build$SM/bin/llama-server\" 2>/dev/null
sleep 1
cd /root/autodl-tmp
nohup \$BIN -m \$MODEL --alias qwen3.8-27b -ngl 999 -c 262144 -fa on \\
  -ctk q4_0 -ctv q4_0 -np 1 --reasoning off --jinja \\
  --chat-template-file \$TEMPLATE -md \$MTP --spec-type draft-mtp \\
  --mmproj \$MMPROJ --host 0.0.0.0 --port $PORT --api-key-file \$KEYS \\
  > /root/autodl-tmp/llama_clone$SM.log 2>&1 &
echo \"llama-server (sm$SM) PID=\$!\"
EOF
chmod +x /root/autodl-tmp/start_clone$SM.sh
bash /root/autodl-tmp/start_clone$SM.sh"
echo ">>> 等待 /health ..."
for i in $(seq 1 30); do
  H=$(ssh -o BatchMode=yes "$ALIAS" "curl -s -m 3 http://127.0.0.1:$PORT/health 2>/dev/null" 2>&1)
  if echo "$H" | grep -q '"ok"'; then echo "✅ 服务就绪(第${i}次): $H"; break; fi
  sleep 10
done
ssh -o BatchMode=yes "$ALIAS" 'nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv,noheader' 2>&1 | head -1