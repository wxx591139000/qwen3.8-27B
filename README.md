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
└── skill: qwen38-clone-server（新机一键克隆/切换/接入）
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
| 实例(ali as) | 子项目 | 卡/sm | codex | Hermes | 思考 | 状态 |
|---|---|---|---|---|---|---|
| autodl-5090 | 5090 | 5090/sm120 | codex-q38/-free | - | off | 离线 |
| autodl-qwen-vgpu | vgpu | 4080/sm89 | codex-q38new-free | - | off | 离线 |
| autodl-qwen-clone1 | 5090(克隆) | 4080SUPER/sm89 | codex-clone1-free | - | on | 离线 |
| autodl-qwen-clone2 | 5090(克隆) | 4080/sm89 | (被思考占) | qwenthink | **on** | 在线 |

- codex provider：qwen36/qwen38/qwen38-vgpu/qwen38clone1/qwen38clone2
- Hermes：`hermes-qwen` = `hermes -p qwenthink`（per-window，仅 qwen 窗口用；全局 deepseek）
- 续接：说「按交接提示继续」→ `qwen38-5090-deploy/docs/接交接.md`

> 版本 v1.1 ｜ 2026-08-23 ｜ **重构归档**：两子项目移入 `branches/`，结构定型
> 归档节点：子项目① `archive-20260823-v2`，子项目② `archive-20260823`（均在各自 repo）
> 续接：说「按交接提示继续」→ 记忆 `qwen38-clone-switch-resume-handoff`