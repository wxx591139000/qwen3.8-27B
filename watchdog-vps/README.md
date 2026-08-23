# watchdog-vps — 阿里云 VPS 看门狗（辅助子项）

> **目的**：qwen 自建服务器（AutoDL）每天 1:15 自动关机、用户早 7 点重开。
> AutoDL 容器 PID1=`/init/boot/boot.sh`（无 systemd/cron 可挂靠），控制台「自定义服务」**只做端口映射、不能执行命令**。
> 因此用**常开的阿里云 VPS** 做看门狗：检测到 qwen 机器在线但 llama-server 未就绪 → 自动 SSH 进去拉起 → 等 `/health` ok。
> **附带价值**：白天 llama-server 崩溃也会自动恢复，不只开机一次。

## 架构
```
[阿里云VPS 常开]  ──每60s 探测──►  [qwen AutoDL 服务器]
      │ systemd: qwen-watchdog          │
      │ 若 机器在线 ∧ llama-server down │
      │  → SSH 跑 start_clone<sm>.sh ──► /health ok ⇄ Hermes/公网 可用
```
- 机器关机（AutoDL 自动关）→ 探测失败 → 看门狗静默空转，不误操作。
- 机器一开机（sshd 起来）→ 下一轮发现 llama 没起 → 自动拉起（开机自启）。
- 步骤依赖：qwen 端已有 `start_clone<sm>.sh`（`--reasoning on` Hermes 思考档），且公网映射规则静态存在、重启不失效。

## 组成
| 文件 | 说明 |
|---|---|
| `qwen_watchdog.sh` | 长驻循环：每 60s 探测 → 拉起 → 轮询等 health（≤150s） |
| `qwen-watchdog.service` | systemd unit：`Restart=always`，`enabled` 开机自启（VPS 本身是正规 systemd） |

## 部署（当前已完成的 clone2 实例）
**VPS 侧**（`vps-aliyun`，101.200.227.65）：
```bash
scp/rsh 到 /opt/qwen-watchdog/ 下 id_watchdog(私钥) 与 known_hosts
cat > /etc/systemd/system/qwen-watchdog.service   # 见 qwen-watchdog.service
systemctl daemon-reload && systemctl enable --now qwen-watchdog.service
```
**qwen 服务器侧**（把 VPS 公钥 `id_watchdog.pub` 追加到 `/root/.ssh/authorized_keys`）。

## 复刻到另一台 qwen（参数化）
改 `qwen_watchdog.sh` 顶部三处即可：
```bash
PORT=19407                      # 该机 SSH 端口
HOST=connect.westc.seetacloud.com   # 该机 SSH 域名
START='/bin/bash /root/autodl-tmp/start_clone<sm>.sh'  # 该机启动脚本
```
再配独享 SSH key + 授权，重命名 unit（如 `qwen-watchdog-clone2.service`）即可并行多机。

## 日志 / 运维
```bash
journalctl -u qwen-watchdog -f     # VPS 上看门狗日志（logger -t qwen-watchdog）
systemctl is-active qwen-watchdog  # 应为 active
pgrep -af qwen_watchdog.sh         # 长驻进程
```
- VPS 复刻的钥匙：`/opt/qwen-watchdog/id_watchdog`（独立于本机 `id_rsa_musetalk`，权责分离）。
- 撤销：`systemctl disable --now qwen-watchdog.service`；qwen 侧删对应公钥行。

## 为什么不用 AutoDL 自带自启
实测 clone2：PID1=`bash /init/boot/boot.sh`（systemd offline，`systemctl` 不可用）；无 cron；AutoDL 自带 supervisord 配置在 `/init/` 临时区重启丢。**唯一持久可靠通道 = 自家 VPS 看门狗**（本辅助子项）。

> 相关：`tools/skills/qwen38-clone-server/references/qwen38_facts.md` §开机自启。