#!/bin/bash
# qwen llama-server 看门狗(多机版)：逐台探测——机器在线但 llama-server 未起(开机/崩溃) → 自动拉起。
# 由 VPS systemd 服务长驻；3 台 clone 均为 clone2 系统盘克隆，共用同一把 key id_watchdog。
# 机器缺失/关机 → SSH 探测失败 → 静默跳过，不误操作。
KEY=/opt/qwen-watchdog/id_watchdog
KH=/opt/qwen-watchdog/known_hosts
# target 格式: host:port:user:start_script   (start 脚本带 --reasoning on Hermes思考档)
TARGETS=(
  "connect.westc.seetacloud.com:19407:root:/bin/bash /root/autodl-tmp/start_clone89.sh"   # clone2
  "connect.westc.seetacloud.com:46949:root:/bin/bash /root/autodl-tmp/start_clone89.sh"   # clone1
  "connect.westd.seetacloud.com:31102:root:/bin/bash /root/autodl-tmp/start_clone89.sh"   # clone3(原vgpu)
)
HEALTH='curl -s -m 6 http://127.0.0.1:6006/health'
while true; do
  for t in "${TARGETS[@]}"; do
    host=${t%%:*}; rest=${t#*:}
    port=${rest%%:*}; rest=${rest#*:}
    user=${rest%%:*}; start=${rest#*:}
    SSH="/usr/bin/ssh -i $KEY -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=$KH -p $port $user@$host"
    if $SSH 'true' 2>/dev/null; then                    # 机器在线(sshd 通)
      h=$($SSH "$HEALTH" 2>/dev/null)
      if ! echo "$h" | grep -q '"status":"ok"'; then
        logger -t qwen-watchdog "[$host] llama-server 未就绪(health='${h:-空}')，拉起..."
        $SSH "$start" 2>/dev/null
        for _ in $(seq 1 30); do                        # 轮询~150s 等模型加载
          sleep 5
          h2=$($SSH "$HEALTH" 2>/dev/null)
          echo "$h2" | grep -q '"status":"ok"' && { logger -t qwen-watchdog "[$host] 已恢复"; break; }
        done
      fi
    fi
  done
  sleep 60
done
