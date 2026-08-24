# Qwen3.8-27B 自建大模型项目（伞/上级项目 Umbrella）

> 大项目 `qwen3.8-27B`（自建 Qwen3.8-27B 推理服务生态）的总索引。
> 下设 **2 个平级子项目**（各自独立 git 仓库）+ 若干**运行实例**（AutoDL 服务器，数据盘克隆派生）。

## 结构
```
qwen3.8-27B（本伞项目 = E:\myClaudCodeWorkspace\qwen3.8-27B\）
├── README.md                 ← 本索引
├── branches/                             ← ★两子项目独立 git 仓库（勿改其依赖）
│   ├── qwen38-5090-deploy/   ← 子项目①：RTX 5090 生产部署（多朋友正式档）★源/主
│   │     ├─ 实例 autodl-5090 (5090/sm120, codex-q38, 生产)
│   │     └─ 克隆实例 autodl-qwen-clone1(4080SUPER/sm89), autodl-qwen-clone2(4080/sm89, Hermes思考)
│   └── qwen38-vgpu-deploy/   ← 子项目②：vGPU-32GB(RTX4080) 平价部署（单用户/试验）
│         └─ 实例 autodl-qwen-vgpu (4080/sm89, codex-q38new-free via隧道6112)
├── tools/skills/qwen38-clone-server/   ← 一键克隆skill的归档快照
│      （活技能在本机 ~/.claude/skills/qwen38-clone-server/，随本伞入库备份）
└── watchdog-vps/                       ← ★辅助子项：阿里云VPS看门狗（开机自启+崩溃自愈拉起qwen服务）
       （VPS 常开监测，机器在线∧llama down → 自动 SSH 起 llama-server；存档脚本+systemd unit+README）
```
> 两子项目各自的 `.git` 随目录移动、远端/tag/历史完整保留；服务器跑在 `/root/autodl-tmp`(AutoDL)，与本位置无关 → **分支依赖零影响**。

## 两个子项目定位
| 子项目 | 卡 | 性能 | 定位 |
|---|---|---|---|
| **qwen38-5090-deploy** | RTX 5090/sm120 | 短75/长94 tok/s | **生产正式档**（朋友共享、多用户） |
| **qwen38-vgpu-deploy** | vGPU-32GB=RTX4080/sm89 | 短48/长58 tok/s | **平价单用户/试验** |

- **同源**：模型(ggml-org Q4_K_M)、llama.cpp、修复模板、启动脚本、6把key、压测脚本均同源；vGPU 数据盘从 5090 克隆。
- **异构**：sm 不同(120 vs 89)→ 各用 `build`/`build89` 独立编译，性能随卡带宽降档。
- **归属**：两仓库平级，各自独立 git/push；通用改动主改 5090 再同步，卡专属改动各项目自理。

## 运行实例清单（2026-08-23，AutoDL 4 台）
| 实例(alias) | 卡/sm | 角色 | 思考 | 状态 |
|---|---|---|---|---|
| autodl-5090 | 5090/sm120 | codex-q38(生产，off 可codex) | off | 离线 |
| autodl-qwen-clone1 | 4080SUPER/sm89 | Hermes 思考 | on | 离线(带卡可起) |
| autodl-qwen-clone2 | 4080/sm89 | Hermes 思考 | **on** | **在线(看门狗自动拉起)** |
| autodl-qwen-clone3(=原autodl-qwen-vgpu) | 4080/sm89 | Hermes 思考 | on | 离线(带卡可起) |

> clone1/clone2/clone3 均为 clone2 系统盘+数据盘克隆（build89/sm89 通用），VPS 看门狗 3 台巡检（开机自启+崩溃自愈）。

- **代码x provider**：qwen38clone1/qwen38clone2/qwen38clone3（**暂停启用**，见下方决策）。qwen36/qwen38(5090,off)/qwen38-vgpu 保留。
- **★决策（2026-08-23）**：**codex + qwen（思考机）组合暂停**——codex 走 `/v1/responses` 强制 high 思考，与服务器 `--reasoning on` 冲突超时（根因见 qwen38_facts §codex）。要 codex 用 qwen 须 `--reasoning off` 的机；**当前主力开发路径 = Hermes + qwen 思考（✔ 兼容）**。codex provider/别名保留未删（"暂时"，随时可回）。
- **Hermes**：`hermes-qwen` = `hermes -p qwenthink`（per-window 仅 qwen 窗口，指向 clone2 公网；全局 deepseek 不动）
- **★主力思考档（2026-08-24）**：`--reasoning-budget 2000`（budget 三档对比甜区：aime 复核≥无界、coding 75% 最优；无界=假天花板/500=劣档）。clone2 `start_clone89.sh` 已改；标准档 `watchdog-vps/start_clone89_std.sh`；clone1/clone3 待开机同步。VPS 看门狗拉起即带 budget。
- 续接：说「按交接提示继续」→ `qwen38-5090-deploy/docs/接交接.md`

> 版本 v1.4 ｜ 2026-08-24 ｜ **归档v4**：主力思考档落定 `--reasoning-budget 2000`（budget 三档对比甜区，无界假天花板/500 劣档）；伞 tag `archive-20260824`
> 归档节点：子项目① `archive-20260823-v2`，子项目② `archive-20260823`（均在各自 repo）｜伞 `archive-20260823-v3`
> 续接：说「按交接提示继续」→ 记忆 `qwen38-clone-switch-resume-handoff`