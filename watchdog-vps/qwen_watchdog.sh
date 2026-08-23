#!/bin/bash
# qwen llama-server 看门狗：qwen机器在线但 llama-server 未起(开机/崩溃) → 自动拉起。
# 由 VPS systemd 服务长驻运行；qwen AutoDL 每天自动关机时机器不可达→本脚本静默等待。
SSH="/usr/bin/ssh -i /opt/qwen-watchdog/id_watchdog -o BatchMode=yes -o ConnectTimeout=8 \
     -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/opt/qwen-watchdog/known_hosts \
     -p 19407 root@connect.westc.seetacloud.com"
HEALTH_CHECK='curl -s -m 6 http://127.0.0.1:6006/health'
START='/bin/bash /root/autodl-tmp/start_clone89.sh'
while true; do
  if $SSH 'true' 2>/dev/null; then                     # 机器在线(sshd 通)
    h=$($SSH "$HEALTH_CHECK" 2>/dev/null)
    if ! echo "$h" | grep -q '"status":"ok"'; then
      logger -t qwen-watchdog "llama-server 未就绪(health='${h:-空}')，尝试拉起..."
      $SSH "$START" 2>/dev/null
      for _ in $(seq 1 30); do                          # 轮询最多 ~150s 等模型加载
        sleep 5
        h2=$($SSH "$HEALTH_CHECK" 2>/dev/null)
        echo "$h2" | grep -q '"status":"ok"' && { logger -t qwen-watchdog "llama-server 已恢复"; break; }
      done
    fi
  fi
  sleep 60                                             # 机器关机则空转等待开机
done
