# 证据文件 Schema（Evidence JSON）

> 这是整个技能的"取证门禁"核心。任何持仓在进入多空辩论前，必须先存在一份符合本 schema 的证据文件；
> 辩论论点必须引用证据 ID；覆盖率由 scripts/gate_check.py 机械计算，禁止 agent 口述。

## 1. 文件位置与命名

```
<report_root>/evidence/<YYYY-MM-DD>_<session>_<safe_ticker>.json
<report_root>/evidence/<YYYY-MM-DD>_<session>_macro.json        # 宏观/期权共享证据
```

- `report_root`：默认为 holdings.md 同级的 `daily-reports/`，可用 `--report-root` 覆盖。
- `session`：`pre`（盘前）/ `noon`（午间）/ `post`（盘后）/ `quick`（快速诊断）。
- `safe_ticker`：把代码中的 `.` 换成 `_`，如 601899.SH → 601899_SH、00700.HK → 00700_HK、`AAPL → AAPL`。
- 同一只标的同一时段只有一份证据文件；补证时**原地更新**，不要新建副本。
- **已清仓标的不生成证据文件**：holdings 中名称带 `~~删除线~~` 或数量/状态列写"已清仓/已卖出/已了结/退市"的标的，两份 `parse_holdings` 都会自动剔除、不取证；其历史遗留 JSON 被报告门自动忽略（不计覆盖率、不提供 ID），无需手动删除。

## 2. 完整结构

```json
{
  "schema_version": "1.0",
  "report_date": "2026-09-20",
  "session": "pre",
  "generated_at": "2026-09-20T08:12:00+08:00",
  "ticker": "601899.SH",
  "name": "紫金矿业",
  "market": "A股",
  "account": "A股人民币账户",
  "holding": { "quantity": 1000, "cost": 28.5, "last_close_in_holdings": 31.2 },

  "data_points": [
    {
      "id": "dp-001",
      "dimension": "technical",
      "field": "price_last",
      "label": "最新价",
      "value": 31.68,
      "unit": "CNY",
      "as_of": "2026-09-20 11:30",
      "source": "akshare:stock_zh_a_hist",
      "source_url": "",
      "evidence_level": "P3",
      "fetched_by": "script",
      "status": "verified"
    }
  ],
  "news": [
    {
      "id": "nw-001",
      "headline": "一句话标题",
      "url": "https://...",
      "source": "公司公告/财新/Bloomberg/雪球用户@xxx",
      "published_at": "2026-09-19 20:05",
      "evidence_level": "P1",
      "impact": "bullish",
      "summary": "2-3 句摘要，区分事实与解读",
      "status": "verified"
    }
  ],
  "chain_notes": [
    {
      "id": "ch-001",
      "sector": "有色/贵金属",
      "claim": "铜供给偏紧，库存处于近三年低位",
      "lifecycle": "强化期",
      "sei": 55,
      "leader_backbone": "健康共振",
      "evidence_level": "P2",
      "source": "行业协会库存数据/交易所库存",
      "status": "verified"
    }
  ],
  "gaps": [
    "ROE/营收增速未取到，需用 NeoData financial_indicators 补最新财报数据"
  ]
}
```

## 3. 字段规则（强制）

### data_points 单条

| 字段 | 取值 | 说明 |
|---|---|---|
| `id` | `dp-001` 起顺序编号 | 报告论点引用用，**不得重复、不得跳号复用** |
| `dimension` | `technical` / `fundamental` / `flow` / `news` / `chain` / `macro` / `options` | 五视角 + 宏观 + 期权 |
| `field` | 见 §4 计划点清单 | 取计划点中的标准字段名 |
| `value` | 数字或字符串 | 估算值必须在 `status` 标 `estimated` |
| `evidence_level` | `P1` / `P2` / `P3` / `P4` | 分级定义见 [evidence-standards.md](evidence-standards.md) |
| `fetched_by` | `script` / `agent` | 脚本取数 vs agent 补证 |
| `status` | `verified` / `estimated` / `missing` | `missing` 点必须同时出现在 `gaps` |

### news 单条

- `url` 必填且必须是可访问的具体页面，**禁止填"东方财富网"这种首页**；没有原文链接的传闻标 `P4` 且 `impact` 不得作为结论依据。
- `impact`：`bullish` / `bearish` / `neutral`。
- 同一条公告被 10 个自媒体转载，只登记 1 条（独立证据族原则）。

### chain_notes 单条

- 板块生命周期、SEI、中军龙头关系等定性判断登记于此，必须写 `source`；纯盘感无来源的标 `P4`。

### gaps

- 所有 `missing` 数据点、取数失败的维度、agent 知道自己没查到的东西，全部显式列入。
- gaps 不是扣分表，是**诚实清单**：写了 gaps 不阻断，隐瞒缺口被报告门发现才阻断。

## 4. 计划采集点（最低取证清单）

### 股票（A股/港股/美股），完整版（pre/post）

| 维度（权重） | 计划点 | 硬必需 |
|---|---|---|
| technical（20%） | `price_last`、`day_change_pct`、`ma5`、`ma20`、`ma60`、`range_52w_pct`、`atr14`、`volume_ratio` | **`price_last`、`day_change_pct` 必须 verified，否则证据门直接不通过** |
| fundamental（25%） | `pe_ttm`、`pb`、`market_cap`、`roe`、`revenue_growth_yoy`、`profit_growth_yoy` | 盘前/盘后至少 4/6 项 verified 或 estimated |
| flow（20%） | `main_net_inflow`、`north_south_flow`（A股/港股）；`put_call_or_inst`（美股） | 至少 1 项 |
| news（20%） | 新闻条目 | **≥2 条，至少 1 条 P1/P2；≥2 个独立来源族（按 URL 域名/媒体计，禁同源转载）；impact 须同时含 bullish 与 bearish，缺反面证据证据门 FAIL** |
| chain（15%） | chain_notes | ≥1 条，含生命周期判断 |

### 精简版（noon）

- technical 硬必需不变；fundamental 可只保留估值 3 项；news ≥1 条；chain_notes ≥1 条。

### 基金

- 无实时行情，technical 替换为：`nav_latest`（最新净值）、`nav_change_pct`、`nav_position_pct_1y`（近一年净值分位）。
- fundamental 替换为：基金重仓方向、规模变化、基金经理是否变更（agent 搜索补证）。
- flow/chain 维度合并为"赛道板块暴露"，至少 1 条 chain_note。

### macro 共享文件（pre/post 必需，noon 可选）

- 必含数据点：美股三大指数/期货、VIX（仅作宏观情绪参考）、美元指数、美债10年、原油、黄金、比特币（按时段取相关项）。
- 期权/VIX策略/IV/PCR 板块已移除：post 不再要求 options 维度证据。

## 5. 证据 ID 在报告中的引用规则

- 多空辩论的**每一条论点**末尾必须挂引用，形如：`铜库存连续三周下降 [dp-007][nw-002]`。
- 一条论点至少 1 个 ID；关键结论（操作建议、证伪条件）至少 2 个独立维度的 ID。
- **P4 证据不得作为任何论点的唯一支撑**；只有 P4 的论点必须降级为"待验证线索"或删除。
- 报告中的数字必须能在证据文件中按 ID 找到；证据文件里没有的数字不许出现在报告里（持仓成本等来自 holdings.md 的数字除外）。
- **多空不同源（完整版 pre/post）**：报告须有明确"多方/多头"与"空方/空头"区块，且每侧至少 1 个对方没有的独立证据 ID；空方照抄多方同源 ID 或缺对立区块，报告门 FAIL。

## 6. 与两个门禁的关系

```
fetch_data.py（脚本取证，能批量拿的全拿）
      ↓ 生成 evidence/*.json（含 missing 与 gaps）
agent 补证（NeoData MCP / 搜索，写回同一文件）
      ↓
gate_check.py --stage evidence   ← 不通过：禁止进入辩论，回去补证或走降级声明
      ↓
五视角分析 → 多空辩论（论点挂 ID）→ 风控 → 终审 → 写报告
      ↓
gate_check.py --stage report     ← 不通过：禁止交付，回去补引用/改覆盖率横幅
      ↓
present_files 交付
```

覆盖率机械计算口径见 [evidence-standards.md](evidence-standards.md) §覆盖率审计（以 gate_check 输出为唯一权威值）。
