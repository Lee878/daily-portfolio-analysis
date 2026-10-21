# MCP 取数手册（NeoData）

补证阶段的首选取数通道。**为什么需要它**：本机代理/DNS 常拦截东方财富（`push2.eastmoney.com`
返回 ProxyError 或 RemoteDisconnected），此时 `akshare` 全线失败，但 MCP 走平台侧通道，
不受本机网络策略影响。

> v2.4.0 实测（2026-10-21）：A 股 601899、港股 00700、美股 NVDA 三个市场全部取到。

## 1. 工具与证据字段对应

| 证据字段 | dim | 来源工具 | 取值路径 |
|---|---|---|---|
| `price_last` | technical | `quote_and_kline` | 最新一条**有效** `kline_list[].close` |
| `day_change_pct` | technical | `quote_and_kline` | 同一条的 `pct_change` |
| `ma5` `ma20` `ma60` | technical | `derive_indicators.py` | 用 K 线自算（见 §3） |
| `range_52w_pct` | technical | `derive_indicators.py` | 同上 |
| `atr14` | technical | `derive_indicators.py` | 同上 |
| `volume_ratio` | technical | `derive_indicators.py` | 同上 |
| `pe_ttm` | fundamental | `valuation` | A 股 `realtime_pe_ttm`；港股取 `history[-1].pe_ttm` |
| `pb` | fundamental | `valuation` | A 股 `realtime_pb`；港股 `history[-1].pb_lf` |
| `market_cap` | fundamental | `valuation` | `total_market_cap` ÷ 1e8 → **亿元** |
| `roe` | fundamental | `financial_indicators` | `roe_weighted`（无则 `roe_average`） |
| `revenue_growth_yoy` | fundamental | `financial_indicators` | `operating_revenue_yoy` |
| `profit_growth_yoy` | fundamental | `financial_indicators` | `parent_net_profit_yoy` |
| `main_net_inflow` | flow | `fund_flow` | `data[-1].main_net_inflow` ÷ 1e4 → **万元** |

**美股**的 `pe_ttm` / `pb` / `market_cap` 走 `financial_indicators`（`valuation` 不支持美股）。

## 2. 覆盖缺口（必须写进 gaps，不许编）

| 字段 | 状态 | 处理 |
|---|---|---|
| `north_south_flow` | **无** | 北向资金已停止实时披露；能搜到当日口径就填，取不到写 gaps |
| `put_call_or_inst`（美股 flow） | **无** | 用搜索补期权/机构持仓；取不到写 gaps（该字段允许文字） |
| 基金 / 场外基金全部字段 | **无** | `valuation`/`fund_flow` 不覆盖基金；走基金公司官网或搜索 |
| `atr14` / `range_52w_pct` / `volume_ratio` | 需派生 | 见 §3，不许目测估计 |

## 3. 三个派生指标：用脚本算，不许心算

```bash
# 1) 把 quote_and_kline 的完整返回存成 JSON 文件（整段，含 status/result）
# 2) 跑脚本（可传多个文件，自动合并去重）
python scripts/derive_indicators.py --mcp k1.json --mcp k2.json --ticker 601899.SH
```

输出即门禁字段名，直接搬进 `data_points`：

```json
{"price_last": 28.87, "day_change_pct": -0.65, "ma5": 29.404, "ma20": null,
 "range_52w_pct": 9.94, "atr14": 0.935, "volume_ratio": 0.928, "bars_used": 15}
```

`null` 表示样本不足，**该点写 `status: "missing"` 并进 gaps**，不要拿近似值充数。
`notes` 里若提示"非完整 52 周"，`range_52w_pct` 必须标 `status: "estimated"`。

自检：`python scripts/derive_indicators.py --selftest`

## 4. 九个实测坑

1. **不给 `start_date` 只返回当天**（默认值就是当天）。要历史必须显式传区间。
2. **长区间会被省略**：返回里插一行 `trade_date = "2026-09-01 ~ 2026-09-12"`、`open` 是
   "省略中间历史行情……"。单次有效行约 20 根。取 52 周行情要**分 10-13 段取**，
   每段约 20 个交易日，再用 `--mcp` 多文件合并。
3. **占位行**：非交易日/未开盘行 `close` 是 `"-"`，整行剔除（脚本已处理）。
4. **代码必须带市场后缀**：`601899.SH` / `00700.HK` / `NVDA.US`。基金、ETF 无对应后缀。
5. **A 股财务指标要累计报告期**：`fiscal_period` 用 `2026-H1` / `2026-9M` / `2026-FY`。
   传 `2026-Q2` 这类单季报**不返回 roe**（实测：Q2 只有 roic）。
6. **港股报告期枚举不同**：只有 `Q1/H2/9M/FY`，没有 Q2/Q3/Q4。
7. **港股估值快照可能缺 `pe_ttm`**：实时快照只有 `pe_lyr`，PE/PB 取 `history[-1]`。
8. **`valuation` 和 `fund_flow` 都不支持美股**。
9. **`technical` 的 `tech_data` 可能滞后**（实测 10-21 却只到 10-08），均线一律用
   K 线自算，不要直接抄 `tech_data.ma5`。

## 5. 单位（写进报告前必须换算）

- 市值：`total_market_cap` 是**元** → ÷1e8 = 亿元。
- 资金流：`main_net_inflow` 是**元** → ÷1e4 = 万元。
- 换手率、涨跌幅已是百分数，直接写数值，不要带 `%` 符号进 `value`。

## 6. 推荐调用节奏（省调用次数）

单次最多 10 个代码，所以**按市场批量**而不是逐只调用：

| 步骤 | 调用 | 覆盖 |
|---|---|---|
| 1 | `quote_and_kline` 批量（≤10 只，带 `start_date`） | 全部标的的价格/涨跌 |
| 2 | `technical` 批量 | 指标语境（可选，均线仍自算） |
| 3 | `valuation` A 股+港股批量 | PE/PB/市值 |
| 4 | `financial_indicators` A 股 `H1`、港股 `H2`、美股 `Q2` 各一次 | ROE/增速 |
| 5 | `fund_flow` A 股+港股批量 | 主力净流入 |
| 6 | `derive_indicators.py` 逐只跑（合并多段 K 线） | 三个派生指标 |

新闻与产业链**不走 MCP**，照旧用搜索工具，`url` 必须是可访问的具体文章页。

## 7. 与门禁的关系

MCP 取到的数据点写 `source: "neodata:<tool>"`、`fetched_by: "agent"`、`evidence_level: "P3"`。
`data_points` 不强制 `source_url`（只有 `news` 强制），所以不填 URL 不会挂门禁；
但**不许把 MCP 的数当成 P1/P2**，它只是结构化行情数据源。
