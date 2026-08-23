---
name: qwen38-clone-server
description: 一键克隆/切换 Qwen3.8-27B AutoDL 服务器并打通本地 codex 全链路。当用户说"克隆服务器/换新服务器/新机器/qwen3.8克隆"并给新的 AutoDL SSH(host+端口+密码) 时，务必用本 skill。自动完成：免密SSH+建别名+检测GPU架构(sm_120/sm_89)按需重编llama-server+启动服务等health，然后等用户提供控制台公网URL，自动新增独立 codex provider+qwen38-clone<N>-free 别名并实测。目标：克隆后用户直接用 codex+qwen3.8 服务器，无需手工配。
---

# 一键克隆 Qwen3.8-27B 服务器 & 打通 codex

把「租/克隆一台新的 AutoDL 卡，部署 qwen3.8-27B，并将本地 codex 指过去」整条流程自动化。你只需依次提供：`SSH(host/port/password)` →（中间在控制台拿公网 URL）。其余免密、sm 重编、起服务、更新 codex 全部自动。

## 输入（用户提供）
| 信息 | 示例 | 必填 |
|---|---|---|
| SSH 端口 | `45313` | ✅ |
| SSH 域名 | `connect.westd.seetacloud.com` | ✅ |
| root 密码 | `9G4yM8g4SS1d` | ✅ |
| 本次克隆名称/编号 | `clone1`、`clone2`…（用于别名/provider 命名，避免覆盖已有机） | 建议 |

> 关键约束：**并发 / 每次克隆都要"新建独立"的 codex provider + 别名**（名字含克隆编号），绝不覆盖现有 `qwen38`(5090) 或 `qwen38-vgpu`。5090 生产档永远不动。

## 流程总览
```
① 免密 SSH + 建别名（autodl-qwen-clone<N>）
② 检测 GPU 架构 + 核对克隆数据
③ 按 sm 重编 llama-server（sm≠已有则重编）
④ 启动服务 + 等 health
⑤ 让用户在控制台映射 6006 拿【公网 URL】
⑥ 自动新增 codex provider + 别名 + 实测
⑦ Hermes qwen-思考接入（set qwenthink profile → 新机）
```

---

## ① 免密 SSH + 建别名

执行 `scripts/setup_keyless_ssh.sh <PORT> <HOSTNAME> <PASSWORD> <ALIAS>`：
- 用 SSH_ASKPASS 把 `~/.ssh/id_rsa_musetalk.pub` 装入新机（Windows 无 sshpass）
- 验证免密（`-i id_rsa_musetalk` 必带，否则 BatchMode 用错默认 key 报 Permission denied）
- 在 `~/.ssh/config` 里插入/更新别名块（HostName/Port/User/IdentityFile/心跳）。改配置前先 `cp ~/.ssh/config ~/.ssh/config.bak`。

别名命名：`autodl-qwen-clone<N>`。

## ② 检测架构 + 核对数据

`ssh <ALIAS> 'nvidia-smi --query-gpu=name,memory.total,compute_cap --format=csv,noheader'`：
- `compute_cap` 大=形如 `12.0`(→sm_120)、`8.9`(→sm_89)。**sm = major×10+minor**（整数，如 8.9→89，12.0→120）。
- AutoDL「vGPU-32GB」名不副实——**必须实测**底层卡：常是 RTX 4080(sm_89)，也可能别的。
- 同时核对 `/root/autodl-tmp`：`models/*.gguf`(Q4_K_M 18G/MTP 1.6G/mmproj 0.6G)、`llama.cpp/`、`qwen38_template.jinja`、`start_llama_server*.sh`、`.api_keys`(6 key)。

**若数据盘空的**（未从旧机克隆）：需补充 (a) 用 `scripts/parallel_dl.py` 下模型，(b) 拿 llama.cpp 源码。见 `references/qwen38_facts.md`。

## ③ 按 sm 重编 llama-server

- 若已克隆的 `llama.cpp/build/bin/llama-server` 是为同 sm 编的 → 跳过。
- 否则用**独立编译目录** `build<sm>`（如 `build89`），**绝不覆盖**克隆来的 `build/`（那是旧卡 sm，覆盖会污染）：
  ```bash
  cd /root/autodl-tmp/llama.cpp
  cmake -B build<sm> -DGGML_CUDA=ON -DCMAKE_CUDA_COMPILER=/usr/local/cuda/bin/nvcc \
    -DCMAKE_CUDA_ARCHITECTURES=<sm> -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=OFF \
    -DGGML_CCACHE=OFF -DCUDA_cuda_driver_LIBRARY=/usr/local/cuda/lib64/stubs/libcuda.so \
    -DCMAKE_EXE_LINKER_FLAGS="-lcuda -L/usr/local/cuda/lib64/stubs" -DLLAMA_BUILD_UI=OFF
  cmake --build build<sm> --config Release -j16 --target llama-server
  ```
- 配 cgroup 内存用 `free -g` 估 `-j`：带卡模式(>16G)用 `-j16`；无卡模式只有 2GB，必须 `-j1`。CUDA emediated 编译 ~10-20min。

## ④ 启动服务 + 等 health

创建 `/root/autodl-tmp/start_clone<sm>.sh`（参考 `references/qwen38_facts.md` 的启动参数：262K 全功能 = MTP+mmproj+关思考+6006+`--api-key-file`，BIN 指向 `build<sm>/bin/llama-server`），`nohup` 启动，轮询 `/health` 直到 `{"status":"ok"}`（模型加载约 1-2min）。核对 `nvidia-smi` 显存 ~27.7GB。

## ⑤ 让用户提供公网 URL（唯一人工交接点）

向用户说明：在 AutoDL 控制台把新实例**端口 6006** 映射成公网自定义服务，把返回的 `https://u<xxx>.weste/westd.seetacloud.com:8443` 发我。**此步无法自动化，必等用户。**（本 skill 不做隧道兜底，坚持只用公网 URL。）

## ⑥ 更新 codex + 加别名 + 实测

拿到公网 URL 后执行 `scripts/update_codex.py <URL> <CLONE_N> <API_KEY>`：
1. `~/.codex/config.toml` **新增** `[model_providers.qwen38clone<N>]`（wire_api=responses，base_url=`<URL>/v1`，bearer_token=该机 `.api_keys` 一把 key，通常是 `sk-qwen36-Wu…` 主 key）。**只增不改**现有 `qwen38`/`qwen38-vgpu`。
2. `Microsoft.PowerShell_profile.ps1` **新增** `function codex-clone<N>-free { codex -c 'model_provider="qwen38clone<N>"' -c 'model="qwen3.8-27b"' --dangerously-bypass-approvals-and-sandbox @args }`。
3. 实测：`codex exec -c 'model_provider="qwen38clone<N>"' -c 'model="qwen3.8-27b"' --skip-git-repo-check "Reply with exactly: CLONE_<N>_OK"` 应返回 `CLONE_<N>_OK`。

只有实测通过才算完成。

## ⑦ Hermes qwen-思考接入（让 hermes-qwen 用新机）

用户主用 **Hermes 带思考做 qwen 代码开发**。克隆后默认把 Hermes 的 `qwenthink` profile 指到新机：

```bash
python scripts/setup_hermes.py <公网URL>/v1 <API_KEY>
```
- 仅改 `~/.hermes/profiles/qwenthink/config.yaml` 的 `providers.qwenthink` base_url/api_key/default_model → 新机；**全局 `~/.hermes/config.yaml`(deepseek) 与 tts/stt/memory 全不动**。
- 改后 `hermes-qwen`(= `hermes -p qwenthink chat`) 即连新机 qwen。
- **前提**：新机要用思考，启动脚本须 `--reasoning on`（改 `start_clone<sm>.sh` 并重启）。
- **角色互斥注意**：codex 需要新机 `--reasoning off`，Hermes 思考需要 `on`——**一台机只能跑一种角色**（同 llama-server 进程）。默认给新机按 Hermes 思考档(`on`)，此时 `codex-clone<N>-free` 连不上（responses+思考冲突，见 qwen38_facts §codex）；要 codex 就改回 `off`。

> 若用户明确新机只做 codex（快档），可跳过本步。

---

## 验证清单
- [ ] `ssh autodl-qwen-clone<N> 'echo ok'` 免密直达
- [ ] `nvidia-smi` compute_cap → sm 确认；`/health` ok
- [ ] codex provider `qwen38clone<N>` 存在 + alias `codex-clone<N>-free` 存在；`CLONE_<N>_OK`
- [ ] Hermes：`qwenthink` profile base_url → 新机；`hermes -p qwenthink`(或 `hermes-qwen`) 顶部显示 `qwen3.8-27b`
- [ ] 新机思考档 = `--reasoning on`（如做 Hermes 角色）

## 注意 / 约束
- **不动 5090 生产档**：不覆盖 `qwen38` provider、不关停 `autodl-5090`、不碰其配置。
- **每次新建独立 codex 入口**，避免克隆间互相干扰；Hermes 是单一 `qwenthink` profile，指到最新 qwen-思考机。
- **codex 与服务器思考互斥**：codex 走 /v1/responses，服务器 --reasoning on 时 responses 超时→codex 连不上。要 codex 用新机需 off；Hermes 思考需 on。一台机二选一。
- 服务器按小时计费，测完不用可关机省费。
- 完成后更新项目记忆/归档（`qwen38-clone-switch-20260823`）记录新机。相关部署事实见 `references/qwen38_facts.md`。