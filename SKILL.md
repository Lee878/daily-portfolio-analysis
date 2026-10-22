---
name: daily-portfolio-analysis
description: "深度持仓分析引擎。读取持仓档案，对每只持仓标的执行四层多角色辩论分析（5视角数据采集→多空强制辩论→三视角风控评估→基金经理终审），输出盘前/午间/盘后三时段深度报告。证据门禁：取证不达标禁止辩论、论点无证据ID禁止交付。当用户要求做每日持仓分析、盘前报告、午间总结、盘后总结、持仓操作建议、持仓诊断时使用。支持A股、港股、美股、基金多账户组合。"
license: MIT
version: 2.7.0
metadata:
  requires-python: ">=3.10"
  entrypoint: "scripts/run_daily.py"
  gates: "证据门 + 报告门（退出码 0/10/11/12）"
---

# Daily Portfolio Analysis（证据门禁版 v2）

给定持仓档案，执行**带机械门禁**的多角色辩论流程，输出可操作、可追溯的持仓决策建议。

> **v2 核心变化：好规则装上牙齿。**
> 报告里的每个数字必须来自证据文件；取证不达标，脚本会直接阻断辩论；
> 论点不挂证据 ID、覆盖率自报、缺来源/免责，报告门禁止交付。
> agent 无法靠"自觉"绕过——两道 gate 都是机械校验、退出码硬性阻断。

## 核心承诺

> 5个分析师各说各的 → 证据门（脚本）确认取证达标 → 多空两方吵2轮 → 3个风控挑刺 → 报告门（脚本）核验引用 → 基金经理拍板

## 核心原则

1. **证据先行，门禁不可绕过**：先跑 `fetch_data.py` 生成证据文件，补证后过证据门，才能开始分析。证据门 FAIL 时禁止进入辩论，不得先写报告再补证据。
2. **强制站队辩论**：多空研究员必须立场对立，禁止中立发言；**每条论点必须挂证据 ID**（`[dp-xxx]`/`[nw-xxx]`/`[ch-xxx]`）。
3. **数字只来自两个地方**：holdings.md（持仓成本/数量）或证据 JSON。证据文件里没有的数字，不许出现在报告里。
4. **证据分级**：P1-P4，P4（社媒/传闻）不能单独支撑论点；每条核心结论至少 1 条 P1/P2。详见 [evidence-standards.md](references/evidence-standards.md)。
5. **覆盖率机械计算**：覆盖率以 `gate_check.py` 输出为唯一权威值，报告横幅照抄，禁止口述/估算/美化。
6. **反证优先**：每个核心判断附带"什么情况说明我错了"的证伪条件。
7. **市场 Regime 前置**：先判 S0-S6 大环境，再做个股（见 market-models.md）。
8. **用户偏好硬约束**：必含四维度（市场位置、环比同比、预期差、进场判断）。期权/VIX/IV/PCR 板块已按用户要求彻底移除，报告不再写期权策略方向。
9. **诚实缺口**：所有 missing 数据点必须写入证据文件 `gaps`；gaps 不是扣分，隐瞒缺口才是阻断项。
10. **取数两级优先**：脚本先出骨架（akshare/yfinance 直连；网络受限时全 missing），
   补证首选 NeoData MCP（平台侧通道，不受本机代理影响），派生指标用脚本算。
   agent 的判断力应花在新闻、财报、产业链、宏观上，而不是手工搬运行情数字。

## 强制工作流（七步法）

> 以下命令在**技能根目录**下执行；`python` 在部分环境为 `python3`。
> Windows 找不到 holdings 时用 `--holdings` 显式指定；报告根目录默认 holdings 同级 `daily-reports/`。

### ★ 唯一入口：run_daily.py（物理门禁，不可绕过）

七步法由统一编排脚本 `scripts/run_daily.py` 串成一条管道，**最终 HTML 只允许由它产出**。
门禁是确定性 Python、用退出码硬阻断，不依赖 agent"自觉"，因此每天触发结果一致、不会逐渐放水：

```bash
# 阶段一：取证骨架 + 首检证据门（FAIL→退出码10，并打印待补清单）
python scripts/run_daily.py fetch --session <pre|noon|post> --date <日期> --holdings <holdings.md>
#   ……v2.6.0 起脚本已直取行情/估值/技术面（见下方「数据源」），
#     agent 只补：新闻、财报细节、产业链、宏观，以及填 data.json；
#     派生指标缺口跑 derive_indicators.py；全部原地写回 evidence/*.json……
python scripts/run_daily.py gate  --session <pre|noon|post> --date <日期> --holdings <holdings.md>  # 补证后复检，PASS(0) 才能继续
# 阶段二：填好紧凑 data.json 后：强制证据门复检 → 通用渲染器生成 HTML → 报告门
python scripts/run_daily.py report --session <pre|noon|post> --date <日期> \
    --holdings <holdings.md> --data <data.json>
# 兼容旧模式（新流程不用）：--builder scripts/build_report_<日期>.py 手写 builder
```

> **数据驱动渲染（默认）**：agent 只按 `assets/data-schema.md` 填一份紧凑 `data.json`（纯文字+结构化卡片字段，内含证据ID），
> `render_report.py` 读 assets 里固化的 CSS/免责/卡片壳/页面骨架出 HTML；**不手写 builder、不写 CSS、不复制模板文字**。
> 固定层（CSS、免责、来源折叠、卡片壳）全部在 `assets/`，由脚本读取渲染，agent 不复制粘贴。

物理保证（缺一不可）：

- **证据门不过 → 仍会出报告**，但首屏挂「数据不全」红条、签名写 `DEGRADED`，退出码 10。
  理由：缺口本身就是要给用户看的信息；拦住等于让他当天什么都拿不到。
- **报告门不过 → 产物保留 + 降级横幅**，退出码 12，**不再物理删除**。
- **双门全过 → 签名 `content="PASS ..."`；任一门不过 → `content="DEGRADED ... reason=evidence_gate|report_gate"`。**
- **交付铁律：只有带 `daily-gate` 签名（PASS 或 DEGRADED）的 HTML 才允许交付；没有签名 = 没走门禁，一律禁止。**
  DEGRADED 交付时，正文第一句必须说明"数据不全"，不得让读者以为数据是完整的。
- 退出码：`0` 双门 PASS；`10` 证据门 FAIL（已按降级交付）；`11` 覆盖率降级；`12` 报告门 FAIL（已按降级交付）；`2` 环境/参数错误。
- 下方 Step 1/3/6 的单条命令仅用于手动排错；**正常出报告一律走 run_daily**。回归测试：`python -m unittest discover -s tests`（须全绿）。

### 数据源（v2.6.0，脚本直取，别再逐只手工补）

行情与估值现在**由脚本直接取**，不再依赖 agent 用 MCP 逐只补：

| 市场 | 主源 | 兜底 | 能拿到的字段 |
|---|---|---|---|
| A股 | 腾讯（不封 IP） | baostock（纯 socket）、akshare | 现价/涨跌/量比/PE/PB/市值/换手/成交额/日K/52周分位/ATR |
| 港股 | 腾讯 | — | 同上（含量比以外全部，含 52 周高低） |
| 美股 | 新浪 | yfinance | 现价/涨跌/PE/市值/52周高低与分位/日K |
| A股资金流 | 东财 push2 | — | 主力净流入（万元）、换手 |
| 北向资金 | 同花顺沪深股通 | — | 当日累计净买入（万元） |
| 美股期权 | CBOE | — | 期权 PCR（成交量/持仓量） |

- 优先级链写在 `config/data-sources.json`（模板见 `config/data-sources.example.json`），**改配置即可换源，不用改脚本**。
- 适配层只用标准库，**不装任何第三方包也能跑** A股/港股/美股（akshare/baostock 是可选的兜底）。
- 东财在本机常被封 IP（`RemoteDisconnected`，绕代理也一样）：它只作补充，失败即降级并在 `gaps` 留痕，不要反复重试。
- 每批次产物含字段级覆盖度报表 `coverage/<日期>_<时段>.json`：哪个字段一直取不到、该不该接新源，看这个。
- **agent 的补证范围因此收窄**：行情/估值/技术面不用再补，专注新闻、财报、产业链、宏观与判断。

### Step 1 读持仓 + 脚本取证

```bash
python scripts/fetch_data.py --holdings <holdings.md> --session <pre|noon|post>
# 可选：--date YYYY-MM-DD --no-network（只生成取证骨架）--tickers AAPL,GOOG（快速诊断）
```

- 必须先读 holdings.md（默认查找：`--holdings` → `$DAILY_HOLDINGS` → `./holdings.md`
  → `config/holdings.md` → `./holdings.md`）。
- 脚本解析持仓，批量拉取行情/估值/资金流/K线，机械计算 MA、52周分位、ATR、量比，
  生成 `daily-reports/evidence/<日期>_<时段>_<代码>.json`；拿不到的点显式标 `missing` 并列入 gaps。
- 同时生成 `*_macro.json` 宏观骨架（quick 时段除外）。
- akshare 未安装或网络不通时，脚本生成全 missing 骨架——**这不是失败，是给 agent 的明确待补清单**。
  本机代理拦截东方财富是常见原因（脚本会把报错写进 `gaps` 首条），此时改用 NeoData MCP 补证。

#### 已清仓/卖出标的识别（机械规则，脚本强制，不靠自觉）

持仓表里以下两类标的**视为已清仓、不是持仓**，取证、证据、报告卡片一律不得包含：

1. 名称带 Markdown 删除线，如 `| ~~AMDL~~ | AMDL.US | 已清仓 | - | - | … |`；
2. 数量/状态列写明 `已清仓 / 已卖出 / 已售 / 已了结 / 已离场 / 退市 / 不再持有`。

- 两份解析器都会自动剔除这些行，清仓清单单独提取。
- **报告门机械拦截**：已清仓标的若以标题/独立卡片（`#` 标题、`<h1-4>`、`card-title`）出现，
  `check_report` 直接 FAIL，`run_daily` 保留产物但签名改 `DEGRADED`、首屏挂红条、退出码 12
  （v2.6.0 起不再删除 HTML，但降级签名同样不允许当作正常报告交付）；
  只允许在「跨报告对账」正文里用一句话提及（如"AMDL 已于 9/18 清仓"）。
- 清仓标的遗留的旧证据 JSON（`evidence/*_<代码>.json`）会被报告门自动忽略，不计覆盖率、不提供 ID，
  无需手动删除。
- 用户卖出后，应先在 holdings.md 对应行加删除线、状态写"已清仓"并记入变动日志；
  **报告卡片标的集合必须严格等于 holdings 解析出的在册持仓**，写 builder 时按当日 holdings 重新生成名单，
  禁止照抄历史 builder 里的已清仓卡片。

### Step 2 agent 补证（写回同一份 JSON，不要新建文件）

用工具把脚本拿不到的数据补进证据文件，字段规范见 [evidence-schema.md](references/evidence-schema.md)。

**取数首选 NeoData MCP**——它走平台侧通道，不受本机代理影响（本机代理常拦东方财富，
导致 akshare 全线失败）。字段映射、覆盖缺口、9 个实测坑见
[mcp-data-source.md](references/mcp-data-source.md)，动手前必须先读。

- **行情/估值/财务/资金**：MCP 批量取（单次 ≤10 个代码，按市场批量而非逐只调用）。
  `atr14`、`range_52w_pct`、`volume_ratio` 三个字段 MCP 不提供，**必须**用
  `python scripts/derive_indicators.py --mcp <kline.json> --ticker <代码>` 从 K 线算，
  不许目测、不许估；样本不足时写 `missing` + `gaps`，不许拿近似值充数。
- **脚本已经取到的不许再补**：先看 `fetch_data` 灌进证据文件的点（`source` 以
  `tencent:` / `sina:` / `eastmoney:` / `north:` / `cboe:` 开头的都是脚本取的），**只补空着的字段**。
- **仍取不到的**：美股机构持仓 `put_call_or_inst`（PCR 脚本已给，机构部分仍缺）、
  基金规模变化/经理变更/前十大持仓——走搜索或其他公开渠道，取不到就写进 `gaps`。
- **新闻**：用本环境可用的搜索工具，每只标的完整版 ≥2 条（≥1 条 P1/P2，必须带可访问 URL），午间 ≥1 条。
  MCP 只给结构化行情，**不能替代新闻**。
- **财报/估值缺口**：MCP 的 `valuation` / `financial_indicators` 优先（注意 A 股要用 `H1`/`9M`/`FY`
  累计报告期，单季报不返回 ROE）；仍缺再用 akshare/yfinance 或搜索。单位统一：市值=亿元、资金流=万元。
- **产业链**：填 `chain_notes`（生命周期、SEI、中军龙头，必须带来源）。
- **宏观**：补 `*_macro.json`（指数期货/美元/美债/油价/黄金等）；不再要求期权/VIX/IV/PCR 证据。
- 补证后把对应数据点 `status` 改为 `verified`、补全 `source`/`source_url`/`evidence_level`；
  MCP 取到的点写 `source: "neodata:<工具名>"`、`fetched_by: "agent"`、`evidence_level: "P3"`；
  确实查不到的保持 `missing` 但要确保已在 `gaps`。

### Step 3 证据门（辩论前必须 PASS）

```bash
python scripts/gate_check.py --report-root <daily-reports> --date <日期> \
    --session <pre|noon|post> --stage evidence
```

- **FAIL（退出码 1）**：回去补证，禁止进入辩论。常见原因：价格缺失、新闻不足/无 P1P2、缺产业链笔记、缺口未披露、verified 字段填了非数字。
- **深度/广度红线（股票完整版 pre/post，机械判定）**：
  1. 有效新闻须来自 **≥2 个独立来源族**（按 URL 域名/媒体计，禁止多条同源于一处或互相转载凑数）；
  2. 证据须**同时含 bullish 与 bearish 立场**的新闻——只搜利好或只搜利空、缺独立反面证据，直接 FAIL。
  （基金/投顾与午间精简版放宽：来源族 ≥1、不强制双边。）
- **PASS（退出码 0）**：进入 Step 4。
- 覆盖率 50-69%：门禁可能放行但**只给定性判断**，禁止精确评分/具体仓位数字（gate 会给警告）。
- 覆盖率 <50%：标 **DEGRADED（退出码 3；经 run_daily 时表现为 11）**，不自动放行。
  若客观数据源全挂，可 `--allow-degraded` 显式放行，但报告顶部必须挂"数据不足"横幅，且只给定性判断。
- 覆盖率分母由脚本按 market/instrument/session 机械推导，**不读证据文件里的 planned**
  （那个字段可被改写，改小就能刷高覆盖率）；也正因如此，不要手工改 planned 求过关。
- gate 输出的**组合覆盖率**记下来，报告横幅必须照抄。

### Step 4 五视角分析 → 多空辩论 → 风控 → 终审

按 [analysis-workflow.md](references/analysis-workflow.md) 和 [debate-protocol.md](references/debate-protocol.md) 执行：
第零层 Regime → 5 视角采集 → 2 轮多空辩论 → 3 视角风控 → 基金经理终审。

- 分析师结论引用数据点/新闻/产业链时，直接写证据 ID；**不在证据文件中的论据一律视为不存在**。
- 重大事件周（FOMC/CPI/非农/重磅财报）输出 A/B/C 三情景概率，不预测明确方向。

### Step 5 填 data.json（渲染器出 HTML，MD 存档）

- 按 [assets/data-schema.md](assets/data-schema.md) 填紧凑 `data.json`：meta/stats/regime/blocks/sources，
  卡片用结构化字段，渲染器套固化壳；分析细节参考 [output-templates.md](references/output-templates.md) 与
  [report-html-template.md](references/report-html-template.md)。
- 每条多空论点末尾挂真实证据 ID，例：`铜库存连续三周下降，支撑铜价 [dp-007][nw-002]`。
- 覆盖率横幅数字 = Step 3 机械值（run_daily 会校准）；信息来源折叠区列关键词/数据源/具体文章URL；每只标的列 gaps。

### Step 6 报告门（交付前必须 PASS）

```bash
python scripts/gate_check.py --report-root <daily-reports> --date <日期> \
    --session <pre|...> --stage report --report-file <报告.md或.html>
```

检查：每标的论点引用数/唯一 ID 数达标、引用 ID 真实存在（防编造）、覆盖率横幅与机械值偏差 ≤3pct、
P4 不得唯一支撑论点（超 2 条阻断）、信息来源折叠区/免责声明/缺口披露齐全。
**多空不同源（完整版 pre/post）**：每只卡片必须有明确标注"多方/多头"与"空方/空头"的对立区块，
且双方各至少 1 个对方没有的独立证据 ID——空方照抄多方同源 ID、或缺对立区块，直接 FAIL。
**FAIL 禁止交付。**

### Step 7 交付与存档

- 交付前确认 HTML 含 `<meta name="daily-gate" ...>` 签名（由 `run_daily.py report` 写入）；**无签名 = 没走门禁，禁止交付**。
  签名有两种：`content="PASS …"` 是双门全过；`content="DEGRADED …"` 是降级交付（**可交付，但正文必须照实说缺口**）。
- **只交付 HTML 单文件**（桌面 present_files 预览 + 手机 Bark 通知 → App 打开看全文）；MD 与证据 JSON 存档 `data/daily-reports/`（跨报告对账依据，不要删）。
- 手机侧**不发邮件**（D-02 已冻结；Agent 邮箱本身 `not_bound`）。推送由 `run_daily report`
  **自动完成**（PASS/DEGRADED 都发，FAIL 走 `timeSensitive` 告警），不需要 agent 手动调 `notify.py`；
  要带人话摘要加 `--notify-summary`，排错加 `--no-notify`。`notify.py` 只用于手动补发或单独告警。
  App 已实测可渲染报告 HTML（RK-01 关闭），所以通知只叫醒、全文在 App 内看。
- 口头总结：Regime、机械覆盖率、综合建议、Top3 多空理由、买入区间、核心风险。

## 快速诊断（轻量模式）

用户随手问单只"XX 怎么样"：
`fetch_data.py --session quick --tickers <代码>` → 补关键证据 → 证据门（quick 放宽新闻/产业链为警告）
→ 简化辩论 → 结论。即使 quick，**价格硬必需和论点挂 ID 不放松**。

## 工作流路由

| 报告类型 | 触发 | 卡片深度 | 侧重点 |
|---|---|---|---|
| 盘前 8:30 | 定时/盘前 | 完整版 400-500 字 | 隔夜美股总结 + A股港股机会预判 + 持仓盘前检查 |
| 午间 12:00 | 定时/午间 | 精简版 150-200 字 | 上午复盘 + 异动归因 + 午后价位 |
| 盘后 20:00 | 定时/盘后 | 完整版 400-500 字 | 全天总结 + 持仓归因 + 美股前瞻 + 明日计划 |
| 快速诊断 | 随手问单只 | 轻量 | 单只快速判断 |

## 板块排序：跟着"下一个要开盘的市场"走

- **盘前**：A股/港股新闻与持仓分析在前（9:30 开盘），美股隔夜作背景后置。
- **午间**：A股/港股半日总结与午后操作在前。
- **盘后**：美股盘前机会、美股持仓在前（21:30 开盘），A股港股复盘后置。
- 同一板块内部同样按此优先级（新闻卡片、持仓卡片皆然）。

## A股资金流向体检（盘前/盘后硬必需，2026-09-27 复盘新增）

> 起因：9/24 上证 -1.22%/深成 -2.34%/创业板 -2.48% 大跌前，9/22、9/23 主力已连续净流出 150 亿+，但报告仍写"窄幅震荡"。

1. **盘前必查最近 2 日主力资金净流入/流出 + 北向方向**（行情/资金工具或 akshare 脚本）。
   - 若连续 2 日主力净流出 >100 亿，盘前报告顶部必须挂黄色"资金面预警"横幅，禁止再写"窄幅震荡/观望"。
2. **指数必须拆结构**：每次 A 股盘前/盘后同时报上证、深成、创业板三者涨跌幅及差值。
   - 若创业板/深成明显跑输上证（差值 >1pct），必须单独提示："你持仓里的小米/阿里/港股科技ETF/半导体都是成长β，实际跌幅会大于上证"。
3. **海外重大事件日（CPI/FOMC/PCE/非农）A股分层判断**：
   - 第一层：A股自身资金流/技术面给方向（这是主）。
   - 第二层：海外事件只解释"晚上美股怎么开"，禁止用"PCE前全球观望"一句话概括全天A股。
4. 保留"我不确定的"一栏 + 重大事件周 A/B/C 三情景（本周验证有效）。

## 同日增量复用（省 token）

pre 建当日全量底库；noon/post 只补当日增量（实时行情、当日新闻、新公告）。
noon/post 生成骨架后、补证前，先跑复用，慢变量（财报/估值/ROE/产业链）从同日早时段自动合并，不重复搜：

```bash
python3 $ENG/scripts/reuse_evidence.py --report-root <daily-reports> --date <日期> \
    --from-session pre --to-session noon   # post 用 --from-session noon（或pre）
```

只复用 verified 慢变量与产业链；实时行情、当日新闻、宏观行情不复用，必须新补。被复用条目带 `reused_from` 标记。

## 跨报告对账机制

每次报告前先读上一时段/前一日报告与当时的证据 JSON，对账核销：
1. 上次建议的操作执行了吗、效果如何；2. 证伪条件出现了吗；3. 板块生命周期/SEI 判断验证了吗；
4. 观察名单触发了吗。输出：较上次变化 / 假设确认或失效 / 结论变化原因 / 仍存在的风险。

> 对账摘要已由渲染器自动落盘为 `daily-reports/recon-<日期>-<时段>.md`（每只上轮建议/止损/证伪 + 对账段）。
> 下一轮对账先只读这份几百字摘要，不必重读整份 30KB 报告 MD。

## 新闻与板块雷达（所有报告必含，三层顺序）

**先归纳板块暴露**：把持仓按产业链归并成板块簇（如 AI算力/半导体、互联网平台、有色贵金属、电网电力、红利防御、创新药），
列明每簇包含哪些持仓、仓位轻重，新闻围绕板块簇组织。

1. **我的持仓板块雷达（最前）**：逐板块卡片——标签（利好绿/利空红/分化黄）、生命周期阶段、
   SEI 衰竭指数、中军vs龙头关系、2-4 条带产业逻辑的消息、一句"拿住/减/等"结论。
2. **市场热点板块**：4-6 个资金主攻方向小卡片，点明哪些与持仓共振、哪些是新机会。
3. **个股/宏观新闻**：4-8 张卡片（分类标签 + 标题 + 摘要 + 对持仓影响）。
新闻筛选：与持仓板块直接相关 > 对大盘板块影响大 > 一般宏观。

## 取证预算（下限，不是上限）

| 项目 | 完整版（pre/post） | 精简版（noon） |
|---|---|---|
| 每只标的有效新闻 | ≥2 条，≥1 条 P1/P2 | ≥1 条 |
| 每只标的产业链笔记 | ≥1 条（带来源） | ≥1 条 |
| 每只标的硬必需行情 | 最新价 + 当日涨跌幅（verified） | 同左 |
| 组合机械覆盖率 | ≥70% 才可给具体操作建议 | ≥70% 给价位；50-69% 只给定性 |
| 宏观证据文件 | 必需 | 可选 |

- 一次查询只解决一个问题，不要把财务/新闻/行业混在一个 query。
- 脚本已批量拉取的行情数据**不要重复搜索**；agent 的搜索预算优先投给新闻、财报原文、产业链、宏观。
- 独立证据族：同一公告被 10 个号转载只算 1 条。

## 输出产物规范

| 文件 | 命名 | 处理 |
|---|---|---|
| 可视化 HTML | `YYYY-MM-DD-盘前报告-可视化.html` 等 | **唯一主交付**，单文件自包含 |
| 报告正文 MD | `YYYY-MM-DD-盘前报告.md` 等 | 存档，不 present |
| 证据文件 | `evidence/<日期>_<时段>_<代码>.json`、`*_macro.json` | 存档，对账依据，不 present |

HTML 设计规范（Brief 浅色版式、响应式多空双栏、Regime 折叠、证据脚注、板块卡、信息来源折叠区）全部移到
[report-html-template.md](references/report-html-template.md)，写报告时按该文件执行，不在此占用流程篇幅。

## 观察名单（克制写法）

每次 2-3 只，明确标注"现在不买，加入观察池，触发 XX 条件再考虑"，不写"建议买入"、不写目标价。

## 关注库 / 接回库（Watchlist）

**和"观察名单"的区别**：观察名单每次临时列 2-3 只、不持久、不写目标价；关注库是**持久化**的一张表，收录"目前未持有、此前高位卖出、想等低位接回"的票，每条带**明确目标接回价、计划股数、止损**，到价即在报告里标红并给执行清单。

**文件（与 holdings 同级，默认在 `config/`）**：`watchlist.md`
列顺序固定（脚本机械解析，勿改列序）：名称｜代码｜市场｜目标接回价｜计划股数｜预计金额｜止损价(-15%)｜加入日期｜状态｜逻辑/备注。

**分析时点（跟随下一个开盘市场）**：
- 8:30 盘前：深度分析关注库中 **A股/港股** 标的；
- 20:00 盘后（美股盘前）：深度分析关注库中 **美股** 标的（名单/目标接回价/股数以 watchlist.md 当日条目为准，不凭记忆写死）；
- 12:00 午间**不做**关注库（时点设计：午间只做 A股/港股持仓的增量复盘，不是降级）。

**深度范围（v2.4.0 语义反转，重要）**：
- **默认：该时段对应市场的关注标的全部深度分析**——和持仓同标准走证据门；
- 只有写进 `config/watchlist_brief.json` 对应时段数组的 ticker 才降级为"简列"（只在关注库总览表列示现价/目标价，不要求多空/产业链/独立卡片）；
- 单次临时降级：`run_daily.py ... --brief SNDK,KO`（不影响文件，下次自动恢复）；
- 旧文件 `watchlist_depth.json`（深度白名单）**已废弃**：仍存在时被忽略并打印提示，请删除或改名为 `.bak`。
- 降级是逃生口，不是常态。数据源全挂时宁可降级并在报告里明说，也不要为了凑深度编数据。

**每条关注标的的分析要求（专家视角，数据必须真实）**：
- 先取证：fetch_data 已按 session 自动把对应市场关注标的纳入，和持仓同标准走证据门（现价 verified、新闻 ≥2 独立来源族、同时含多空、产业链、gaps）；
- 给多维专家分析：K线、成交量等技术面 + 利好利空新闻；展示现价 / 目标接回价 / 距目标价% / 距高点回撤%；
- 论点挂 `[dp/nw/ch-xxx]`，编数据 = 报告门 FAIL、删 HTML。

**到价判定与输出（机械执行）**：现价 ≤ 目标接回价 = **到价**，报告须在该标处**标红**并二选一——
1. "**可接回**"执行清单：接回股数 / 金额 / 止损 / 证伪条件（用户确认即下单；仅建议、决策权在用户）；
2. 明确喊"**先别接**"并挂证据：到价但基本面恶化、疑似价值陷阱时，专家判断优先、否决接回并降级待验证；

两者都没有 = 报告门 FAIL。现价 > 目标（未到价）可做专家分析、提示"接近低点"，但**不得喊"可接回/买入"**，违反 = FAIL。

**生命周期**：接回成功转入 holdings.md（关注库该条标"已接回"或删除线）；没接到又涨回去则留库继续等；自加入日起**满 4 周仍未到价不删除**，报告提示"重新评估、重定低位目标价"。

**明确不做**：不新增盘中盯盘/高频轮询任务；午间不分析关注库；不机械删除未到价条目；不自动下单（只给清单、用户拍板）。

## A/B/C 三情景使用规则

仅 FOMC、CPI、非农、重磅财报当周加，给概率分布（A 50%/B 30%/C 20%），不预测明确方向；平时不强行套。
重大数据公布后，必须先搜实时市场反应（期货、VIX、美元、美债）再给建议；综合环比+同比+预期差+油价+技术面+情绪，
单一指标 0.1pct 的偏离不等于大利空；市场反应与预测不一致时立即认错。

## 文件导航

| 需求 | 读取 |
|---|---|
| 证据文件字段与 ID 规范 | `references/evidence-schema.md` |
| 证据分级、覆盖率机械口径、红旗 | `references/evidence-standards.md` |
| 完整分析流程（Regime/5视角/辩论/终审） | `references/analysis-workflow.md` |
| 多空与风控辩论流程 | `references/debate-protocol.md` |
| 市场量化模型（Regime/SEI/二八撕裂/连板梯队） | `references/market-models.md` |
| 角色定义与 prompt | `references/agent-roles.md` |
| 各市场数据源与信源白名单 | `references/data-sources.md` |
| 各时段输出模板 | `references/output-templates.md` |
| HTML 视觉与布局规范 | `references/report-html-template.md` |
| 数据驱动渲染：data.json 填写规范 | `assets/data-schema.md` |
| 合规边界 | `references/risk-compliance.md` |
| 门禁回归测试与场景用例 | `references/test-cases.md`、`tests/test_gate.py` |

## 部署与安装（本地单副本）

引擎的**唯一权威副本就是本仓库**（`SKILL.md` + `scripts/` + `references/` + `assets/`），
没有第二个"运行时副本"，也不需要在多台机器之间同步。旧版的 `/runtime` 与 `DAILY_RT` 已移除。

- 仓库根 = skill 根：目录名不必等于 `daily-portfolio-analysis`，但安装到 WorkBuddy 时必须叫这个名字
  （skill 规范要求 `frontmatter.name` 与目录名一致）。
- 安装/更新技能副本：`python scripts/install_skill.py`（robocopy 增量同步，排除 `config/ data/ .git/ .archive/`）；
  只检查不写入：`--check`。
- 数据与代码分开放：代码入库（git），`config/` 与 `data/` 不入库，换电脑单独拷贝。
- 改了受管文件（脚本/规范/样式/模板）后必须 `python scripts/release.py manifest`（发版用 `bump`）重算指纹，
  否则 `doctor` 会报漂移。
- 回归测试：`python -m unittest discover -s tests`（从仓库根跑，当前 67 项，须全绿）。

## 交付前自检（脚本门 + 人工确认）

```
□ 报告由 scripts/run_daily.py report 产出（退出码 0），未手动绕过
□ HTML 含 <meta name="daily-gate" content="PASS ..."> 签名（无签名禁止交付）
□ python gate_check.py --stage evidence 退出码 0（或已显式 --allow-degraded）
□ python gate_check.py --stage report   退出码 0
□ 报告横幅覆盖率 = gate 机械值
□ 卡片标的集合严格等于 holdings 在册持仓；无删除线/"已清仓/已卖出"标的的独立卡片
  （已清仓标的只允许在跨报告对账正文一句话提及）
□ 每条多空论点挂证据 ID，且 ID 均真实存在
□ 股票完整版每只标的新闻 ≥2 个独立来源族（不同域名/媒体，无同源转载）
□ 股票完整版证据同时含 bullish 与 bearish 新闻（缺独立反面证据不放行）
□ 完整版卡片有明确"多方/空方"对立区块，且各至少 1 个对方没有的独立证据 ID（多空不同源）
□ 组合总览条 + Regime 条 + 板块雷达（含生命周期/SEI/中军龙头）
□ 每只持仓卡片：结论置信度 / 市场位置与 price-in 审计 / 环比同比+预期差 /
  多空双栏 / 共识分歧 / 风控（风报比+止损+目标）/ 证伪条件
□ 重大事件周 A/B/C 情景（不预测方向）；报告不含期权/VIX/IV/PCR 策略板块
□ 盘后有次日作战池；观察名单克制；信息来源折叠区；免责声明；缺口披露
□ 关注库：已 Read watchlist.md 并按当盘市场纳入（pre→A股/港股，post→美股，午间不做）；
  到价标红且给"可接回清单(股数/止损/证伪)"或喊"先别接"；未到价不喊买；满4周提示重评估
□ MD + 证据 JSON 已存档（证据文件不删除）
```

## 风险边界

仅提供研究分析和决策参考，不做买卖指令；不承诺收益、不保证准确性；所有判断基于公开信息，可能有时效性不足；
投资决策与后果由用户自行承担。详见 [risk-compliance.md](references/risk-compliance.md)。
