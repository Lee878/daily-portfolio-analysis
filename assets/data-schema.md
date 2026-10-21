# data.json 填写规范（数据驱动渲染）

每轮报告不再手写 builder 脚本。只填一份紧凑 `data.json`，`render_report.py` 套固定壳出 HTML。
CSS、卡片函数、页面骨架、免责、来源折叠容器全部固化在脚本/assets，**agent 不写任何标签、CSS、函数、免责文案**。
只填纯文字（结论/多空/操作/证伪）+ 结构化卡片字段，证据ID直接写在文字里，如 `[dp-001]`。

## 顶层结构

```json
{
  "meta": {"h1":"盘前持仓报告 · 2026-10-19 周一","sub":"时段说明","coverage":"79","coverage_note":"机械值说明"},
  "stats": [{"v":"+0.16%","cls":"g","k":"上证 3722"}],
  "regime": "市场天气段落HTML纯文字，可含<b>与证据ID",
  "blocks": [ ... 按出现顺序 ... ],
  "sources_note": "数据源总述",
  "sources": [{"label":"标题","url":"https://具体文章页"}]
}
```

- `stats.cls`：`g`涨/`r`跌/`b`蓝/`y`黄。
- `coverage` 填 gate 机械值，run_daily 会再校准，不必精确。
- 来源 `url` 必须是可点开的具体文章页，禁止首页/栏目页；pre≥4条、noon≥3条。

## blocks 类型

| kind | 用途 | 字段 |
|---|---|---|
| `card` | 普通叙述段（对账/新闻/宏观/背景/作战池/缺口） | `h2`(可选), `paras`[文字段，可含ID] |
| `sectors` | 板块雷达 | `h2`, `items`:[{`cls`bull/mid/bear, `paras`[]}] |
| `cards` | 持仓/基金/现金/投顾卡片组 | `h2`, `cards`:[卡片对象] |
| `table` | 操作建议汇总表 | `h2`, `rows`:[{`pos`,`act`,`cond`,`cls`}] |
| `warn`/`buy` | 预警/可接回高亮块 | `h2`, `paras`[] |
| `raw` | 特殊HTML（极少用） | `html` |

每个 block 可带 `h2` 标题（自动套 h2 样式）。

## 卡片对象字段（按 type）

- **cn / us（完整股票）**：`type`,`name`,`code`(含数量成本),`chg`,`tagcls`(tg涨/tr跌/ty黄),`concl`,`pos`,`bull`,`bear`,`cons`,`risk`,`act`,`fals`
  - `bull`行必须含"多方"语境、`bear`行含"空方"语境；pre/post 双方各挂对方没有的独立证据ID。
  - 章节内唯一ID≥4、总引用≥6、同一ID不得重复≥5次。
- **etf（杠杆/反向ETP）**：`type`,`name`,`code`,`chg`,`tagcls`,`concl`,`top`(跟踪结构+每日重置耗损提示),`bull`,`bear`,`act`,`fals`
- **fund（场外基金）**：`type`,`name`,`code`,`chg`,`tagcls`,`concl`,`bull`,`bear`,`act`
- **wl（关注库）**：`type`,`name`,`code`,`chg`,`price`,`target`,`qty`,`stop`,`dist`(距目标%/状态),`concl`,`pos`,`bull`,`bear`,`cons`,`act`,`fals`
  - 到价：`act`含"可接回"+股数+止损+证伪；未到价禁喊买；满4周提示"重新评估"。
- **sgov（现金管理）**：`type`,`name`,`code`,`chg`,`concl`,`bull`,`bear`,`act`
- **advisory（投顾列示）**：`type`,`name`,`code`,`note`

## 硬红线（与门禁一致，渲染器不放松）

- 卡片集合严格等于 holdings 在册持仓；已清仓标的只在对账段一句话提及，不得独立卡片。
- 每条论点挂真实存在的证据ID；P4不得单独支撑核心结论。
- 必须含：覆盖率横幅、Regime条、板块雷达、每只完整卡片（结论/市场位置/多空/共识/风控/操作/证伪）、缺口披露（"我不确定的/gaps"）、来源折叠、免责；不写期权/VIX/IV/PCR 策略板块。
- 缺数据如实写进 gaps，禁止编造、禁止占位值。
