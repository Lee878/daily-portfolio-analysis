# 报告 HTML 视觉与布局规范 v2.7.0（Brief 版式）

> 只在 Step 5 写报告时读本文件。**HTML 由 scripts/render_report.py 生成**，
> agent 只填 data.json（见 assets/data-schema.md），不写标签、CSS、卡片函数。
> 本文件是渲染器的实现契约：改样式先改这里，再改 assets/style.css 与渲染器。

---

## 1. 设计原则

1. **报告是读物，不是仪表盘**：1.7 万字里绝大部分是解读性文本，指标只占 6 格。
   排版优先级是「连续读下去不累」，不是「一屏塞满数字」。
2. **手机优先**：默认按 390px 宽设计，桌面只做增强，不另出手机版。
3. **无盒子**：不用深色卡片与圆角，靠发丝线 + 留白分区。滚动时视野里只有一条条横线，
   没有一堆色块抢注意力。
4. **结论优先**：一屏内先看到"该干什么"，长分析折叠。
5. **红涨绿跌**（A 股习惯）：涨/多方=红 `#c0392b`，跌/空方=绿 `#16704a`。
   涨跌色**只作用文字**，不做背景填充——深色底上的红绿块在阳光下几乎看不出差别。
6. **单文件自包含**：无 CDN、无外链图、无 JS 框架、无外部字体。

---

## 2. 基础参数

| 项 | 手机 | 桌面（≥720px） |
|---|---|---|
| 正文 | 15.5px / 行高 1.78 | 16px |
| 标题 h1 | 衬线 30px | 衬线 38px |
| 标题 h2 | 衬线 17px | 衬线 22px |
| 卡片标题 h3 | 19px / 660 | 21px |
| 关键数字 | 23px `tabular-nums` | 27px |
| 次要文字 | 12px，`--ink3` | 同 |
| 正文级最小对比度 | **≥ 4.5:1**（WCAG AA） | 同 |
| 页面边距 | 20px | 32px |
| 内容最大宽 | 100% | 760px |

颜色 token（assets/style.css 的 `:root`）：

```
--bg #faf9f6   --paper #ffffff  --rule #e2ded4  --rule2 #eeebe3
--ink #15181d  --ink2 #454d59   --ink3 #6c727b（4.61:1）  --ink4 #989ea6（纯装饰）
--rise #c0392b（涨/多方）  --fall #16704a（跌/空方）
--gold #8f6119（提示/证伪，5.13:1）  --accent #1c4b78（链接）
```

**语义约定**：颜色只表达"涨跌/多空"，不表达"利好利空"。
利好利空用文字（`利好`/`利空`/`中性`）+ 中性灰，避免两套红绿打架。
`--ink4` 只许用于装饰（分隔点、下划线、列表圆点），**不许承载正文**。

---

## 3. 页面结构（自上而下）

1. **报头**：`2026-10-20 周二 · 盘后` + 右侧 `覆盖 NN%` 小标签
2. `h1` 报告标题（衬线大字）
3. **Regime 段**：默认折 3 行 +「读全文」，点开看全文（纯 CSS `line-clamp` + 渐隐遮罩）
4. **指数格**：2 列（桌面 3 列），每格「数值 + 涨跌」同行，状态词换行
5. **今日动作横滑条**：全部持仓的 `名称 + 动作`，一眼看全组合
6. **区块目录**（区块 ≥3 时）：横滑 chips，点击跳转
7. 区块：对账 → 板块雷达 → 热点 → 卡片组 → 新闻 → 作战池 → 观察名单 → 缺口
8. **数据来源与口径折叠区**：含 `数据覆盖率 NN%` 与来源链接（≥4 条）
9. **免责声明** + 引擎版本条（`run_daily` 注入）

---

## 4. 持仓卡片（核心组件）

```html
<div class="card hold">
  <div class="chead"><div class="cl">
    <h3 id="c-601899-sh">紫金矿业</h3><span class="cc">601899.SH</span>
  </div><div class="cr">
    <span class="chg rise">▲+0.97%</span><span class="act hold">持有</span>
  </div></div>
  <div class="dbar">                        <!-- 脚本算出的成本/现价/浮动 -->
    <div class="dcell"><span class="dk">成本</span><span class="dv">28.6</span></div>
    <div class="dcell"><span class="dk">现价</span><span class="dv">27.4</span></div>
    <div class="dcell"><span class="dk">浮动</span><span class="dv fall">-4.20%</span></div>
  </div>
  <p class="concl" data-ev="[dp-001]">量价共振，持有 <sup class="evm">1</sup>。</p>
  <div class="bb">
    <div class="side bull" data-ev="[nw-002] [dp-002]">
      <span class="sl">多方</span><p>铜价上行 <sup class="evm">2</sup><sup class="evm">3</sup></p></div>
    <div class="side bear" data-ev="[dp-003] [nw-003]">
      <span class="sl">空方</span><p>金价失守 <sup class="evm">4</sup><sup class="evm">5</sup></p></div>
  </div>
  <div class="kv risk" data-ev="[dp-003]"><span class="kl">风控</span><p>下方看 28/27 元 <sup class="evm">4</sup></p></div>
  <div class="kv op" data-ev="[dp-005]"><span class="kl">操作</span><p>1500 股拿住 <sup class="evm">6</sup></p></div>
  <div class="folds">
    <details class="fold"><summary>市场位置 / 估值<em>…</em></summary><div class="fb">…</div></details>
    <details class="fold"><summary>证据<em>12 条</em></summary>
      <ul class="ev"><li><span class="enum">1</span><span class="eid">dp-001</span>
        <span class="elv">P1</span><span class="esrc">交易所</span><a>来源</a></li></ul>
    </details>
  </div>
</div>
```

**常显**：卡片头、数据条、结论、多空、风控、操作。
**默认折叠**：市场位置、共识、证伪、证据清单（摘要行右侧自动出现「展开/收起」）。
**动作状态条**：`act-add` / `act-cut` / `act-watch` 给卡片左侧 2px 竖条，
滚动时能扫出"要动手的"；`act-hold` 不加竖条（多数持仓是持有，全加等于没加）。

---

## 5. 证据呈现：脚注制（v2.7.0 关键改动）

正文不再出现灰底 `[dp-001]` 方块，改为**上标序号**，明细收在卡底「证据」折叠。

| 位置 | 内容 |
|---|---|
| 可见正文 | `<sup class="evm">3</sup>` |
| 元素属性 | `data-ev="[dp-003]"`（方括号原文，供门禁计数） |
| 卡底清单 | `3 · dp-003 · P2 · 券商研报 · 来源链接` |

**编号规则**：按"字段展示顺序首现"分配（结论 → 多空 → 风控 → 操作 → 附加折叠 → 证伪），
因此正文序号顺序与卡底清单顺序天然一致，不会出现"点开找第 7 条"的负担。

**非卡片正文**（大势段、对账段落）不做编号——脚注序号在卡片里才有对应清单，
段落里编号会指向不存在的条目。那里保留 `[nw-001]` 裸文本，由 `run_daily._render_badges`
兜底包成静默上标。

---

## 6. 报告门的兼容约束（改模板时必须守住）

这四条都是**踩过的坑**，破坏任一条都不会报错，只会让门禁判错或让报告静默变形。
tests/test_render_ui.py 已把它们钉成测试。

1. **卡片开标签只能是 `<div class="card …">`，class 之后不许再挂属性**
   门禁用 `<div class="card(?![^"]*sector)[^"]*">` 认卡片起点。多一个 `data-ev`
   就匹配不上 → 后续卡片被并入前一张卡的区间 → **别家标的的证据算到这张卡头上**
   （不报错，只是结论错）。需要挂兜底 ID 时，挂到 `.folds` 那一行。
2. **「多方」「空方」必须各占一行，且同行带自己的 `data-ev`**
   门禁按"行"取 ID 判"多空是否各引独立来源"。多空压在一行 → 两边拿到同一批 ID →
   直接判「多方照抄空方同源」。同理各段落必须用换行连接，不许压成一行。
3. **`数据覆盖率 NN%` 字面必须在 HTML 里**
   `run_daily._sync_coverage_banner` 按这个锚点做机械校准；丢了就校不了，门禁还会判
   "缺少覆盖率横幅"。它现在位于页脚「数据来源与口径」折叠区，不在首屏。
4. **样式表注释里不许出现尖括号包裹的标签名**
   `run_daily` 用正则找 body 开标签插入降级横幅。注释里写一个 `<body>`，
   横幅就会被插进 `<style>` 内部：CSS 注释提前结束、后续规则全失效、横幅本身被当
   CSS 丢弃（本次改版实测踩中，首屏根本没横幅）。注入函数已改为只认 style/script
   之外的标签，但注释里也别写。

---

## 7. 响应式断点

| 断点 | 变化 |
|---|---|
| `<600px` | 表格转块状（隐藏表头，`td::before` 显示列名） |
| `<720px` | 多空上下堆叠（多方在上）、指数 2 列 |
| `≥720px` | 指数 3 列、多空双栏、正文 16px、边距 32px |
| `print` | 白底黑字、隐藏动作条与目录、展开全部细节 |

---

## 8. 手机阅读细则

- 可点区域（`summary`、目录 chips、链接）最小高度 40px。
- 长链接 `word-break:break-all`，防止横向溢出。
- 徽标不做 hover 交互：手机上 hover 无效，改为卡片底部"证据清单"。
- 横滑条（动作条、目录）必须 `overflow-x:auto` + 隐藏滚动条，**不能让整页横向滚动**。
- 锚点跳转靠 `id`，不依赖 JS。

---

## 9. 交付前自查

- [ ] 手机宽度（360/390px）`scrollWidth == 视口宽`，无横向滚动
- [ ] 首屏能看到：日期/时段、覆盖率、标题、指数、今日动作
- [ ] 涨红跌绿、多方红空方绿；涨跌色只作用文字
- [ ] 每张卡的成本/现价/浮动三格有数（有成本却浮动为空 = 解析失败）
- [ ] 每个上标序号都能在卡底「证据」里找到对应条目
- [ ] 覆盖率数字与 `gate_check` 输出一致
- [ ] HTML 含 `<meta name="daily-gate">` 签名
- [ ] 单文件双击可开，无外部请求
