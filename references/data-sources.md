# Data Sources

各市场的数据源指南和取数优先级。

## 数据优先级原则

**第一优先级：seed_finance_lookup（同花顺数据库）**
- 标准化金融数据的第一入口
- 行情数据、财务数据、资金流向、技术指标
- A股资金流向（主力/北向）必须用这个

**第二优先级：general_search（通用搜索）**
- 新闻、公告、政策、行业事件
- 公司公告原文、监管文件
- 券商研报、行业分析

## A股数据源

### 行情数据
- **第一来源**：seed_finance_lookup
  - 当前价格、涨跌幅、成交额、换手率、量比
  - PE TTM、PB、PS、总市值
  - 主力资金流向、北向资金
  - 技术指标（MA、MACD、RSI）

### 财务数据
- **第一来源**：seed_finance_lookup
  - 营收、净利润、ROE、毛利率
  - 资产负债表、现金流量表
- **补充来源**：general_search 搜索年报/季报原文

### 新闻公告
- **第一来源**：general_search
  - 交易所公告（上交所、深交所）
  - 公司官网投资者关系
  - 主流财经媒体

## 港股数据源

### 行情数据
- **第一来源**：seed_finance_lookup
  - 当前价格、涨跌幅、成交额
  - PE、PB、总市值
- **补充来源**：general_search

### 财务数据
- **第一来源**：seed_finance_lookup
- **补充来源**：general_search 搜索 HKEX 披露易公告

### 资金流向
- **南向资金**：seed_finance_lookup
- **主力资金**：general_search 补充

## 美股数据源

### 行情数据
- **第一来源**：seed_finance_lookup
  - 当前价格、涨跌幅、成交额
  - PE、PB、总市值
- **补充来源**：general_search

### 财务数据
- **第一来源**：seed_finance_lookup
- **补充来源**：general_search 搜索 SEC 文件（10-K、10-Q）

### 资金流向
- **机构持仓/主力资金**：general_search（期权/VIX/IV/PCR 板块已移除，不取证）

## 宏观数据

- **第一来源**：seed_finance_lookup
  - 利率（国债收益率）
  - 汇率
  - 大宗商品价格（黄金、原油）
- **第二来源**：general_search
  - CPI、PMI、非农就业
  - 美联储/央行政策决议

## 取证预算（下限，不是上限）

> v2 关键变化：旧版把搜索写成"最多 5+5 次"的上限，是产物偏浅的结构性原因之一。
> 现在以**证据门 PASS** 为终点：脚本已批量拉取的行情不占搜索预算，agent 的搜索次数
> 按下表保底，上不封顶；搜索的目的是填满证据文件并通过 gate，不是凑次数。

**脚本负责（不占搜索次数）**：最新价、涨跌幅、MA、52 周分位、ATR、量比、PE/PB/市值、
A股主力资金（akshare 可用时）。脚本拿不到的会在证据文件里标 missing 并写入 gaps。

**agent 最低搜索投入（每只标的）**：

| 取证项 | 完整版 pre/post | 午间 noon |
|---|---|---|
| 个股新闻/公告（general_search，逐只） | ≥1 次检索，登记 ≥2 条（≥1 条 P1/P2） | ≥1 次检索，≥1 条 |
| 财报缺口（seed_finance_lookup：ROE/增速等 missing 点） | ≥1 次，直到补全或确认无数据 | 按缺口 |
| 产业链/板块（general_search） | ≥1 次，形成 ≥1 条 chain_note | ≥1 条 |
| 宏观（期货/美元/美债/油金） | pre/post 各 ≥1 组 | 可选 |

**原则**：
- 一次查询只解决一个主要问题，不要把财务、新闻、行业混在一个 query
- 先补硬必需（价格/新闻），再补财报、产业链、宏观
- 查不到就保留 missing + gaps，**严禁为了过门而编造数字或 URL**（伪造 ID/URL 在报告门与抽查中会被发现）
- 同一公告多家转载只登记一条（独立证据族）

## 数据质量检查

取数后必须检查：
1. **时间一致性**：所有数据是否都是同一个时间点？
2. **口径一致性**：同比还是环比？reported 还是 adjusted？
3. **单位一致性**：亿元还是万元？美元还是人民币？
4. **来源可靠性**：是不是权威来源？

如果数据有冲突，两个都写出来，不要擅自选一个。

## 权威信源白名单（国外优先，拒绝小报）

### 国际权威财经媒体（主用）
Bloomberg、Reuters、Wall Street Journal、Financial Times、CNBC、MarketWatch、Seeking Alpha、Barron's。

### 华尔街投行公开观点
Morgan Stanley、Goldman Sachs、JPMorgan、Bank of America、汇丰、德银等的公开研报/评级观点（券商观点按 evidence-standards 打折，注意利益关联）。

### Twitter/X 权威金融博主
Serenity（@aleabitoreddit / @SerenityRSH）、@zerohedge、@biancoresearch、@LiveSquawk。社媒/KOL 属弱证据，只作线索，需强证据印证，不能单独支撑决策。

### 国内权威源（辅助）
东方财富、同花顺、格隆汇、财新、智通财经、证券时报/上证报/中国证券报；交易所与监管官网为强证据。

### 禁止
不使用小道消息、无来源截图、营销号/自媒体小报作为判断依据；传闻必须标注"未经证实"。
