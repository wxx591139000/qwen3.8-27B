# qwen 逐窗口监控 + Token 计价配置

本目录记录 qwen(Hermes qwenthink profile) 的**逐窗口用量监控**与 **Hermes token 计价接入**。

## 一、逐窗口用量常驻监控

**数据源**：`~/.hermes/profiles/qwenthink/logs/agent.log`

Hermes 每个窗口是独立进程，agent.log 每行 API 调用带 `[session_id]`（即窗口标识），含 `in/out/total`(token) 与 `latency`(秒)。同一 session_id 前缀 = 同一个窗口的生命周期。

**监控脚本**：`qwen_window_monitor.py`
```bash
python qwen_window_monitor.py            # 看当日各窗口摘要（calls/token/latency/活跃至）
python qwen_window_monitor.py --dump     # 全部历史窗口累计
python qwen_window_monitor.py --append   # 追加一份快照到 monitor.log
```

**常驻**：Windows 计划任务 `qwen-window-monitor`，每 10 分钟跑一次 `--append`，快照追加进 `monitor.log`（只读 agent.log，不打扰任何运行窗口）。

**局限**：服务器 `/metrics` 未开(Prometheus 未启)，且 llama-server 不区分请求来源，**只有 Hermes 侧 agent.log 能归属到具体窗口**；服务器 `/slots` 只能看当前正在处理的那 1 个请求峰值。

**峰谷成本核算**（补 deepseek-pricing skill §4 口径）：
```bash
python qwen_cost.py               # 按天汇总每日成本(默认, 必选之一)
python qwen_cost.py --day 2026-08-26  # 某一天会话明细(分会话看)*
python qwen_cost.py --detail      # 追加全部分会话明细*
python qwen_cost.py --pro | --usd # 档位(V4-Pro作上限)/币种(美元)
python qwen_cost.py --since 3     # 只看最近 3 天
```
数据源 `~/.hermes/profiles/qwenthink/state.db`（只读）：sessions 表分列 input(input=新输入不含缓存)/cache_read/output；messages 表 role=assistant 的 epoch 时间戳做峰谷拆分（按会话 started_at 归属到天）。峰谷窗口=北京时间工作日 09-12/14-18，谷=峰×0.5。**纯本地计算、零 token 消耗**；金额均带 ¥/$ 单位；进行中会话标＊。
实测(2026-08-26 按天合计)：缓存命中 89%，混合 Flash ¥31.15 / Pro ≈¥90（与 deepseek-pricing skill 基准 ¥26/¥80 区间相符，含今日新增）。

## 二、Hermes Token 计价接入

**背景**：Hermes 计价核心 `agent/usage_pricing.py`，来源只有 (a)内置价格表 `_OFFICIAL_DOCS_PRICING` / (b) `/models` 端点的 `pricing` 字段。clone4 llama-server 的 `/models` 不返回 pricing → qwen 原本报「未配置计价」。
**架构限制**：Hermes `PricingEntry` 只有静态 input/output/cache_read/cache_write 四价，成本为纯乘法，**无"峰/谷/时间"维度** → 峰谷无法表达，只能静态一价。

**已做**：在 `_OFFICIAL_DOCS_PRICING` 加条目
```
("qwenthink", "qwen3.8-27b") → 高峰价（deepseek-v4-flash）
  input_cost_per_million   = $0.44    (缓存未命中输入·峰)
  cache_read...per_million = $0.014   (缓存命中输入·峰)
  output_cost_per_million  = $1.32    (输出·峰)
  source_url = https://api-docs.deepseek.com/quick_start/pricing
  pricing_version = deepseek-pricing-2026-08-flash-peak
```
**取价来源**（deepseek 官网「模型 & 价格」，2026-08，USD/百万tokens）：
| V4-Flash | 谷 | 峰 |
|---|---|---|
| 输入·缓存命中 | 0.007 | **0.014** |
| 输入·缓存未命中 | 0.22 | **0.44** |
| 输出 | 0.66 | **1.32** |
（V4-Pro 为 3×：未命中 0.66/1.32，命中 0.022/0.044，输出 1.98/3.96）

**切换谷价**：把上面三个 Decimal 改成 0.22 / 0.007 / 0.66 即可（或换成 V4-Pro 峰 1.32/0.044/3.96）。备份 `usage_pricing.py.bak-20260826`。

**生效范围**：改的是 Hermes 源码文件 → **新开的 qwen 窗口生效**；已打开的窗口进程持有旧模块，需重启该窗口才显示成本。

## 三、关联
- 伞归档 `ARCHIVE-2026-08-25.md` ｜ 记忆 `qwen38-clone-switch-resume-handoff`
- Hermes 源码 `E:\ObsidianHouse\hermes-agent-main\agent\usage_pricing.py`