---
name: deepseek-pricing
description: DeepSeek 官方峰谷定价 + 图像 token 规则 + Hermes 会话成本核算方法。凡涉及"核算/估算成本、token 计费、DeepSeek 价格"的任务，先加载本技能。
tags: [deepseek, pricing, cost, tokens, billing]
related_skills: []
---

# DeepSeek 峰谷定价与成本核算（2026-08-26 官方价目）

用户指令（2026-08-26）：以后核算成本一律按本技能的 DeepSeek 官方峰谷定价来。

## 1. 峰谷时段规则
- 高峰时段：北京时间 周一至周五 9:00–12:00、14:00–18:00（= UTC 周一至周五 01:00–04:00、06:00–10:00）
- 空闲（谷）时段：其余所有时段（含周末全天）
- 空闲时段价格 = 高峰时段价格 × 0.5
- 官方按每个请求的实际时刻计费；估算时按"落在峰时窗口的 API 调用占比"近似（误差 ±10% 内）

## 2. 价格表（每百万 tokens，人民币，官方中文版页面）
| 项目 | V4-Flash (V4-Flash-0731) | V4-Pro (V4-Pro-0813) | V4-Flash-Vision-Exp |
|---|---|---|---|
| 输入·缓存命中 | 谷 ¥0.05 / 峰 ¥0.10 | 谷 ¥0.15 / 峰 ¥0.30 | 谷 ¥0.05 / 峰 ¥0.10 |
| 输入·缓存未命中 | 谷 ¥1.5 / 峰 ¥3.0 | 谷 ¥4.5 / 峰 ¥9.0 | 谷 ¥1.5 / 峰 ¥3.0 |
| 输出 | 谷 ¥4.5 / 峰 ¥9.0 | 谷 ¥13.5 / 峰 ¥27.0 | 谷 ¥4.5 / 峰 ¥9.0 |

美元版价目（官方英文版页面，独立定价，≠ 人民币×汇率）：
- V4-Flash: 未命中 峰$0.44/谷$0.22；命中 峰$0.014/谷$0.007；输出 峰$1.32/谷$0.66
- V4-Pro: 未命中 峰$1.32/谷$0.66；命中 峰$0.044/谷$0.022；输出 峰$3.96/谷$1.98
- Vision-Exp 同 V4-Flash 价

模型档位映射：27B 级小模型（如 qwen3.8-27b）≈ V4-Flash 档；旗舰级（如 Qwen3.8-Max）≈ V4-Pro 档。默认用 Flash 档算，Pro 档作上限参照（约 ×3）。
上下文 1M，最大输出 384K。并发：flash 2500 / pro 500。

## 3. 图像计价规则（vision，2026-08 官方）
- 图片进模型前自动缩放（保持长宽比）：
  - 总像素 < 约 384×384：放大
  - 更大：缩小到总像素 ≈ 800×800（约 64 万像素）
- 每张图片 token 上限 = 384 tokens（2000×2000 与 5000×5000 缩放后消耗相同）
- 多张图片各自独立按同一规则计算，无额外算法
- 图片按输入 token 计费（随峰谷价）
- 精确值用官方"Token 与用量计算"页的图片 Token 计算器（api-docs.deepseek.com 的 Token & Token Usage 页）

图像限制：
- 格式 JPEG / PNG / GIF / WebP
- 外部 URL ≤ 8192 字符；请求体 48 MiB
- 单图 ≤ 32 MiB（base64/外部 URL）；≤ 64 MiB（Files API file_id）
- 单请求 ≤ 600 张；图片总大小 ≤ 64 MiB（不含 file_id）/ ≤ 200 MiB（含 file_id）
- 单边最大 8192 px；单请求 ≥15 张时降为单边 4096 px

## 4. Hermes 成本核算方法（qwenthink profile 实测口径）
1. 数据源：`~/.hermes/profiles/<profile>/state.db`（SQLite）
   - `sessions` 表：input_tokens / output_tokens / cache_read_tokens / cache_write_tokens / api_call_count / started_at / ended_at
   - **关键口径：input_tokens = 缓存未命中的新输入，不含缓存读取**（cache_read 单独计）。若假设含缓存，新输入会算出负值 → 用这个校验
   - `messages` 表：role='assistant' 的行 = 每次 API 调用，timestamp（epoch，本地时区）用于峰谷拆分
   - 注意：会话行在运行中实时累加；进行中会话的最后 1 次调用可能尚未入账
2. 峰谷拆分：统计每个会话 assistant 消息时间戳落在"北京工作日 9-12 / 14-18"的比例 f（按 token 加权汇总到 profile 级）
3. 计费公式（每 1M tokens）：
   cost_peak = 新输入×未命中峰价 + 缓存×命中峰价 + 输出×输出峰价
   cost_off = cost_peak / 2
   cost_mixed = f × cost_peak + (1−f) × cost_off
4. 输出报告格式：分别给出 全峰价 / 全谷价 / 按实际峰谷混合 三档，注明模型档位假设与误差说明
5. 参考基准（2026-08-26 实测）：qwenthink profile 25 会话 8/23–8/26 共 1.27 亿 tokens（缓存命中占 95%），混合峰谷后 Flash 档约 ¥26、Pro 档约 ¥80

## 5. 陷阱
- state.db 的 estimated_cost_usd 字段默认 0.00（profile 未配置计价），别用它
- 并行会话会同时更新各自行；按会话 id 区分，别把别的会话算进当前任务
- 脚本里循环变量会遮蔽外层同名变量（tin/tout 被会话循环覆盖），profile 级合计要单独再查一次 SUM
- Windows 下 curl -o 不能用 /tmp（bash 是 MSYS，用 /c/Users/... 或 $TEMP）
- 官方价目页：api-docs.deepseek.com/quick_start/pricing（Docusaurus 静态 HTML，curl 即可抓，无需浏览器）
- 价格可能调整，重大核算前建议重新抓取官方页核对
