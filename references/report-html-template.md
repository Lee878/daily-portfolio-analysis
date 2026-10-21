# 报告 HTML 视觉与布局规范 v2.4.0

> 只在 Step 5 写报告时读本文件。**HTML 由 `scripts/render_report.py` 生成**，
> agent 只填 `data.json`（见 `assets/data-schema.md`），不写标签、CSS、卡片函数。
> 本文件是渲染器的实现契约：改样式先改这里，再改 `assets/style.css` 与渲染器。

---

## 1. 设计原则

1. **手机优先**：默认按 390px 宽设计，桌面只做增强，不另出手机版。
2. **始终深色**：不跟随系统、不提供切换；靠字号与对比度保证白天可读。
3. **结论优先**：一屏内先看到"该干什么"，长分析折叠。
4. **红涨绿跌**（A 股习惯）：涨/多方=红 `#f85149`，跌/空方=绿 `#3fb950`。
5. **单文件自包含**：无 CDN、无外链图、无 JS 框架、无外部字体。

---

## 2. 基础参数

| 项 | 手机 | 桌面（≥768px） |
|---|---|---|
| 正文 | 15.5px / 行高 1.75 | 16px |
| 结论条 | 15.5px，左侧 3px 蓝色竖条 + 淡蓝底 | 同 |
| 次要文字 | 13px，`#a9b6c3` | 同 |
| 证据徽标 | 11px 等宽，灰底细边 | 同 |
| 页面边距 | 12px | 18px |
| 内容最大宽 | 100% | 900px |
| 圆角 | 卡片 12px / 折叠 10px | 同 |

颜色 token（`assets/style.css` 的 `:root`）：

```
--bg #0d1117  --card #161b22  --card2 #1b212a  --line #21262d
--fg #e6edf3  --fg2 #a9b6c3   --fg3 #7d8590
--up #f85149（涨/多方）  --down #3fb950（跌/空方）  --blue #58a6ff  --warn #d29922
```

**语义约定**：颜色只表达"涨跌/多空"，不表达"利好利空"。
利好利空用文字（`利好`/`利空`/`中性`）+ 中性灰，避免两套红绿打架。

---

## 3. 页面结构（自上而下）

1. **常驻顶栏**（`position:sticky`）：Regime 摘要 + `覆盖 NN%` + `今日：票A 持有 · 票B 减`
2. `h1` 报告标题、`sub` 时段说明
3. **覆盖率横幅**：`数据覆盖率 NN% · 机械门禁计算`（数字必须等于 gate 机械值）
4. **统计小卡**（可选）：4-6 个，涨用 `.up`、跌用 `.down`
5. **Regime 条**
6. **锚点目录**（卡片 ≥3 张时）：一行横滑 chips，点击跳转
7. 区块：对账 → 板块雷达 → 热点 → 卡片组 → 新闻 → 作战池 → 观察名单 → 缺口
8. **信息来源折叠区**（`<details class="src">`，≥4 条具体文章链接）
9. **免责声明** + 引擎版本条（`run_daily` 注入）

---

## 4. 持仓卡片（核心组件）

```html
<div class="card">
  <div class="chead">
    <h3 id="c-601899-sh">紫金矿业 <span class="sub">601899.SH · 1500股 · 成本34.9</span></h3>
    <span class="chg down">▼ -0.43%</span>
    <span class="act act-hold">持有</span>
  </div>
  <p class="concl"><b>结论：</b>核心拿住，等三季报 [dp-001]</p>
  <div class="bb">
    <p class="side bull"><b>多方</b>：…… [nw-001]</p>
    <p class="side bear"><b>空方</b>：…… [nw-003]</p>
  </div>
  <p class="riskline"><b>风控</b>：…… [dp-004]</p>
  <p class="opline"><b>操作</b>：<span class="actv">…… [dp-005]</span></p>
  <details class="fold"><summary>市场位置 / 估值 / price-in</summary>
    <div class="fold-body"><p>……</p></div></details>
  <details class="fold"><summary>共识与分歧</summary>…</details>
  <details class="fold"><summary>证伪条件（什么情况说明我错了）</summary>…</details>
  <details class="fold"><summary>证据（N 条）</summary>
    <ul class="evlist"><li><b>[dp-001]</b> P1 · 来源 · <a>打开来源</a></li></ul>
  </details>
</div>
```

**常显**：卡片头、结论、多空、风控、操作。
**默认折叠**：市场位置、共识、证伪、证据清单。
**桌面 ≥900px 自动全展开**（纯 CSS，`details.fold:not([open])>.fold-body{display:block}`）。

### 报告门的兼容约束（改模板时必须守住）

- 卡片必须是 `<div class="card">`，**不要在 class 后面加其它属性**（门禁按该字符串切卡片）。
- `<h3 id="…">` 内必须能认出标的名称/代码（门禁据此归属卡片）。
- **"多方"、"空方"必须各自独占一行，且同行的论点要带证据 ID**（门禁按行统计多空独立来源）。
- 卡片内部各段必须换行（`\n`），不要压成一行。
- 证据 ID 保持裸文本 `[dp-001]`，徽标由 `run_daily` 统一包裹。

---

## 5. 响应式断点

| 断点 | 变化 |
|---|---|
| `<600px` | 表格转块状（隐藏表头，`td::before` 显示列名） |
| `<768px` | 多空上下堆叠（多方在上） |
| `≥768px` | 双栏、正文 16px、边距 18px |
| `≥900px` | 卡片细节自动展开、隐藏"展开/收起"提示 |
| `print` | 白底黑字、隐藏顶栏与目录、展开全部细节 |

---

## 6. 手机阅读细则

- 可点区域（`summary`、目录 chips、链接）最小高度 44px。
- 长链接 `word-break:break-all`，防止横向溢出。
- 徽标不做 hover 交互：手机上 hover 无效，改为卡片底部"证据清单"。
- 顶栏吸顶偏移与卡片 `scroll-margin-top:70px` 配合，锚点跳转不被遮挡。

---

## 7. 交付前自查

- [ ] 手机宽度（360/390px）无横向滚动
- [ ] 首屏能看到顶栏（Regime + 覆盖率 + 今日动作）
- [ ] 涨红跌绿、多方红空方绿
- [ ] 桌面宽度细节自动展开，无需点击
- [ ] 每张卡的证据清单可点开并跳转来源
- [ ] 覆盖率数字与 `gate_check` 输出一致
- [ ] HTML 含 `<meta name="daily-gate">` 签名
- [ ] 单文件双击可开，无外部请求
