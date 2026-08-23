# Qwen3.8-27B 部署关键事实（skill 依赖）

## 模型与显存
- 主模型 `Qwen3.8-27B-Q4_K_M.gguf` (18.97G) + MTP `mtp-...-Q4_0.gguf` (1.68G) + mmproj `mmproj-...-Q8_0.gguf` (0.63G)
- 权重+投MTP+mmproj ≈ 21.3G；KV(q4_0)：131K≈1.9G / 262K≈3.7G / 512K≈7.4G
- **262K 全功能（默认）= MTP+mmproj 全开 ≈ 27.7GB（32GB 卡）**
- mmproj 需 ≥1024 image tokens（`--image-min-tokens 1024` 需用时可加，默认够）

## 启动参数（262K 全功能正式档）
```bash
llama-server -m <Q4_K_M> --alias qwen3.8-27b -ngl 999 -c 262144 -fa on \
  -ctk q4_0 -ctv q4_0 -np 1 --reasoning off --jinja \
  --chat-template-file /root/autodl-tmp/qwen38_template.jinja \
  -md <mtp> --spec-type draft-mtp --mmproj <mmproj> \
  --host 0.0.0.0 --port 6006 --api-key-file /root/autodl-tmp/.api_keys
```
- 模板 `qwen38_template.jinja` 两处修复：system 位置容忍 + 多轮空 thinking 块（否则多轮失忆/思考关不掉）
- `-fa on`（新版参数名）；`--api-key-file` 每行一把 key，`#`注释；`.api_keys` 有 6 把

## sM ↔ 卡
| compute_cap | sM | 卡 |
|---|---|---|
| 8.9 | 89 | RTX 4080（AutoDL vGPU-32GB 常是它，名不副实） |
| 12.0 | 120 | RTX 5090 / 5090D |
| 9.0 | 90 | H800/H100/H20 |

- 已编好为某 sM 的 llama-server 不能在其他 sM 上跑（CUDA arch 不匹配）→ 换卡必须重编，用独立 `build<sM>` 目录

## 编译
```bash
cd /root/autodl-tmp/llama.cpp
cmake -B build<SM> -DGGML_CUDA=ON -DCMAKE_CUDA_COMPILER=/usr/local/cuda/bin/nvcc \
  -DCMAKE_CUDA_ARCHITECTURES=<SM> -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=OFF \
  -DGGML_CCACHE=OFF -DCUDA_cuda_driver_LIBRARY=/usr/local/cuda/lib64/stubs/libcuda.so \
  -DCMAKE_EXE_LINKER_FLAGS="-lcuda -L/usr/local/cuda/lib64/stubs" -DLLAMA_BUILD_UI=OFF
cmake --build build<SM> --config Release -j<N> --target llama-server
```
- nvcc 不在 PATH → 显式。driver stub 链接必需（无卡 libcuda.so 是 0 字节）。
- 并行度按 cgroup：带卡(>16G)→ `-j16`；无卡(≈2GB)→ 必须 `-j1`。
- 数据盘空的补充：模型用 `parallel_dl.py`（ModelScope 16 线程），llama.cpp 源码从 gh-proxy tarball 或已有克隆拿。

## 免密 SSH（Windows）
- 无 sshpass → SSH_ASKPASS 注入密码；公钥 `~/.ssh/id_rsa_musetalk.pub`
- 验证必须带 `-i ~/.ssh/id_rsa_musetalk`（否则 BatchMode 用错默认 key 报 Permission denied）

## codex / 本地对接
- `~/.codex/config.toml` provider：`wire_api="responses"`，base_url=`<公网>/v1`，bearer=`.api_keys` 主 key（`sk-qwen36-Wu…`）
- 现有：`qwen38`(5090 公网)、`qwen38-vgpu`(vGPU 隧道6112)；**本 skill 新增 `qwen38clone<N>`，绝不覆盖**。
- PowerShell profile 别名 `codex-clone<N>-free`。
- codex 用 `-c 'model_provider="..."'` 覆盖 config。

## 性能参考（257 G memory-bound）
- 5090：短 75 / 长 94 tok/s；vGPU(4080 sm_89)：短 48.7 / 长 58.4
- 并发：聚合 ~70 tok/s（带宽受限），`-np N` 只降排队延迟不加总量 ⇒ 单用户足、多用户共享按人摊薄

## 现有两台（勿覆盖）
- 5090 生产：`autodl-5090` weste:15844, 公网 u1068217-f8tl-…:8443, codex-q38/-free
- vGPU 平价：`autodl-qwen-vgpu` westd:31102, RTX4080/sm_89, codex-q38new-free(隧道6112)
- 项目（伞 `qwen3.8-27B` 下两子项目）：`E:\myClaudCodeWorkspace\qwen3.8-27B\branches\qwen38-5090-deploy`、`E:\myClaudCodeWorkspace\qwen3.8-27B\branches\qwen38-vgpu-deploy`

## 开机自启 llama-server（AutoDL 复盘 2026-08-23）
- **结论：必须走 AutoDL 控制台「自定义服务 / 开机自启动」，一条 SSH 命令都不行。**
- 实测这台：PID1=`bash /init/boot/boot.sh`（非 systemd → `systemctl` offline 不可用）；无 cron(`crontab: not found`)；AutoDL 自带 supervisord(`/init/supervisor/supervisor.ini`) 配置在临时区重启丢，不能挂靠。
- 控制台做法：`控制台 → 实例 → 更多/自定义服务 → 新增开机自启动` → 命令填：
  ```
  /bin/bash /root/autodl-tmp/start_clone<sm>.sh
  ```
- 前提：`start_clone<sm>.sh` 已存在（对应克隆/部署的启动脚本，需含 `nohup` 让进程在命令返回后存活；`pkill` 防重复实例）。
- 服务与公网：开机自启只负责把 llama-server 起在 6006；公网 URL 是控制台另一条 6006 映射规则，**静态存在、重启不失效** → 服务一开，Hermes `qwenthink`(已指到该公网) 立即可用。

## 看门狗多机 TARGETS（2026-08-23 扩到 3 台）
- VPS 看门狗为**多机版**：单个长驻循环遍历 `TARGETS`(host:port:user:start)。当前：
  - clone2 = westc:19407 ｜ clone1 = westc:46949 ｜ clone3(原vgpu) = westd:31102，均 `start_clone89.sh`(思考档)。
- **★默认约定（用户偏好，已固化）**：以后**任何新克隆 qwen 机**，对接时**默认自动**加进 `TARGETS` + 复用 `id_watchdog` key（clone2 派生系自带），无需用户每次申请。
- key：clone2/clone1/clone3 均为 clone2 系统盘克隆 → authorized_keys 自带 `qwen-watchdog@vps`。
- clone2 派生系同理：改 `TARGETS` 加一行 → `systemctl restart qwen-watchdog` 即生效。
- 生效验证：开机后 `journalctl -u qwen-watchdog -f` 见 `[host] llama-server 未就绪，拉起...` → `已恢复`。
- 详见伞项目 `watchdog-vps/README.md`。