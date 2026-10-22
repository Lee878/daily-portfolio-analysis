# 数据源与取数优先级（v2.6.0）

取数分三层，**顺序不能反**：脚本能拿的不要交给 agent，agent 能拿的不要靠猜。

| 层 | 谁来做 | 覆盖什么 | 成本 |
|---|---|---|---|
| ① 脚本直取 | `scripts/adapters/`（零第三方依赖） | 实时行情、日K、估值、市值、资金流、北向、美股 PCR | 0 token |
| ② NeoData MCP | agent 补证时调用 | 结构化行情/财务/资金/基金净值（脚本取不到的） | 中 |
| ③ 搜索 | agent 补证时调用 | 公告、新闻、研报、官网、产业链 | 高 |

> 优先级链配置在 config/data-sources.json（模板 config/data-sources.example.json），
> 按顺序「先到先得」合并，某源挂了自动落到下一个，并把失败原因写进 `gaps`。
> 改数据源**只改配置**，不改代码。

## ① 脚本直取（adapters）

| 适配器 | 覆盖 | 说明 |
|---|---|---|
| tencent.py | A股 / 港股 实时 + 前复权日K | 首选源。含 PE/PB/总市值/量比/52周高低/`is_stale` 僵尸报价 |
| sina.py | 美股 实时 + 日K | 36 字段解析，含 PE/52周高低/市值 |
| eastmoney.py | A股 / 港股 主力净流入、市值 | 走 fflow/kline 的 `f52`（元→万元）；有 0.35s 节流 |
| north.py | 北向资金 | data.hexin.cn；输出单位**万元** |
| cboe.py | 美股期权 PCR（成交量/持仓量） | 只回聚合值，不落 1.9MB 原始链 |
| baostock_src.py | A股日K兜底 | 纯 socket；未装包时静默跳过 |

- 出口字段口径固定：市值=**亿元**、资金流=**万元**、涨跌与分位=**%**。
- 每次取证后看 `coverage/<日期>_<时段>.json` 的字段级覆盖度，它决定该不该接新源。

## ② NeoData MCP

字段映射、单位换算、9 个已踩过的坑，全部写在 references/mcp-data-source.md，**动手前先读**。

关键分工：MCP 只给**结构化数据**；新闻与产业链不走 MCP。

## ③ 搜索

- `WebSearch`：公告、政策、研报、产业链、突发。
- `url` 必须是**可访问的具体文章页**，禁首页 URL、禁占位。

## 按市场看

### A股
- 行情/估值/资金：① `tencent` → `eastmoney`（脚本直取，通常不需要 agent 介入）
- 北向：① `north`
- 财务（ROE/增速）：② `financial_indicators`
- 新闻公告：③ 交易所公告、公司 IR、主流财经媒体

### 港股
- 行情/估值：① `tencent` → `eastmoney`
- 财务：② `financial_indicators`（报告期只有 Q1/H2/9M/FY）
- 南向资金：① `north`；公告：③ HKEX 披露易

### 美股
- 行情：① `sina`
- 估值/财务：② `financial_indicators`（`valuation` 不支持美股）
- 期权 PCR：① `cboe`；机构持仓：③ 搜索
- 财报原文：③ SEC 10-K / 10-Q

### 场外基金
- 净值：② `fund_nav`（代码加 `.OF`；`limit` 是**总条数**）
- 净值三字段派生：`../scripts/derive_indicators.py --fund`
- 规模变化/经理变更/前十大持仓：③ 基金公司官网、天天基金

### 宏观
- 利率/汇率/大宗：① 暂无适配器 → ② `macro_cn` / `macro_global` → ③ 搜索
- 宏观日历：② `macro_calendar`

## 缺口处理铁律

取不到就写 `gaps`，**不许编、不许占位、不许拿近似值充数**。
门禁只看「有没有值」，编一个假值能过门但会直接毁掉结论。
