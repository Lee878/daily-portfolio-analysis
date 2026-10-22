# Changelog

## v2.9.1 · 净化脚本：把「别看持仓成本」变成机制（2026-10-22）

v2.9.0 只做到「提示词告诉模型不要看持仓成本」——那是愿望，不是机制。
证据 JSON 里写着 holding.cost / holding.quantity / account（券商名），
只要子代理读了原件，它就一定知道这是用户持有的标的，锚定照样发生。

### 新增 scripts/debate_input.py

按**白名单**重建一份干净输入（白名单比黑名单可靠：新字段默认不进，而不是默认漏出）：

- 保留：ticker / name / market / instrument / data_points / news / chain_notes / gaps
- 剥除：holding（cost、quantity）、account、planned、generated_at
- 数据本体一字不动（有测试断言 data_points / news / chain_notes / gaps 完全相等）

三个模式：
- `--evidence <文件...> --out <目录>`：生成 `<ticker>.debate.json`
- `--verify <目录>`：递归扫禁用键，命中即 exit 1
- 净化后自检：若白名单里仍残留敏感键（比如某个 data_point 的嵌套字段），直接拒绝输出

### 为什么必须带 --verify

净化静默失效是这个链路上最危险的一种假绿：文件生成了、看着像净化过、
辩论照常进行、门禁照样 PASS —— 但模型其实看到了成本。所以 verify 用**递归**扫描
（不是只看顶层），并且把中文键（成本 / 持仓 / 浮盈）也列入禁用集合。

### 8 项回归测试

`tests/test_debate_input.py`：

- 剥掉 holding / account / planned
- 证据本体不被改动（数字零差异）
- 净化后无泄漏
- **嵌套在列表里的 cost 也能抓到**（只看顶层是典型假绿）
- 中文键也能抓到
- 端到端：净化文件 → verify 目录 → exit 0
- **反向：把带 holding 的文件冒充净化产物，verify 必须 exit 1**
- 幂等：净化两次结果相同

测试数 164 → **172**。

### 流程焊死

`assets/workbuddy-prompts/{pre,post}.md` 步骤 3 改为：
先跑净化脚本 → `--verify` 复核 → **exit 0 才允许开子代理** →
子代理只允许读 `<ticker>.debate.json`，**禁止读 evidence/ 原件**。

### 实测一次完整隔离辩论

通富微电（002156.SZ），2026-10-22 盘前，两个独立子代理：

- 空方引用了 **6 个多方完全没用的证据 ID**（dp-003 / dp-004 / dp-007 / dp-015 / nw-003 / nw-004）
- 空方抓到了多方刻意绕开的口径问题：**扣非 PE 实际 51 倍，不是 30 倍**
  （多方用 PEG 0.39 论证便宜，分母用含一次性收益的 PE、增速用扣非，口径不一致）
- 双方在「9.70 亿非经常性损益该不该全额剔除」「55.38 元定增价是支撑还是套牢盘」上真实对立

记录存档：`data/daily-reports/debate/2026-10-22-pre-002156.SZ.md`
（含双方共识、两个真分歧、裁决、以及两条需要人补的证据缺口）

### 仍然存在的限制

隔离是否真发生，产物上仍无法机械验证 —— 这一点没变。
能机械验证的是「空方有没有独立证据」和「输入里有没有持仓成本」，两件事现在都焊住了。

## v2.9.0 · 辩论隔离调用（2026-10-22）

### 改版动因（先量化再动手）

报告生成一直是「一个上下文里顺序跑完全部标的」，多空辩论也在同一个上下文里演：
先写多方，再写空方。这造成三个偏差，严重程度不同：

1. **顺序污染（最要命）**：空方动笔前已读完全部多方论证，反驳被锚定、倾向软化，
   变成「多方观点的折扣版」而不是真正的对手。这不是辩论，是自我辩护。
2. **证据池共用**：两方共用一次检索，空方引用的就是多方那几个 ID。
   这个门禁本来就能抓 —— 实测 2026-10-20 盘后就抓到过：
   「小米集团-W 空方论点没有任何独立于多方的证据（引用全是多方同源 ID）」。
3. **持仓锚定（最隐蔽）**：报告里写着成本与浮盈亏，模型一开头就知道「这是用户持有的」，
   会系统性偏向「继续持有、不必恐慌」。它不明说，体现在语气和结论方向上 ——
   **门禁完全查不出来**，因为它不体现在结构上。

### 隔离调用（isolated）

每只标的分别开两个独立子代理：

- 子代理 A（多方）：只给该标的证据 + 多头指令，不提持仓成本，不告诉它后面有空方
- 子代理 B（空方）：只给证据 + 空头指令，**绝不把 A 的输出给它**，也不给它其他标的的内容
- 主代理裁决：拿到两份文本后做交叉质询 → 三视角风控 → 终审

关键点：**Agent 的价值来自隔离的上下文，不是来自多个进程**。所以不需要换平台 ——
多调几次、每次给不同上下文，就等价于真多 Agent。这一点解掉了当初「豆包不能跑 Agent」的死结。

### 持仓锚定也在流程上挡掉了

辩论阶段把问题问成「这家公司现在该不该买」，不提已持有与成本；
成本与盈亏只在裁决阶段代入，用来判断加 / 减 / 保持，不用来判断好 / 坏。
把「买不买」和「我已持有」拆成两个独立判断，互相不污染。

### 成本：没有变大，盘前盘后反而更省

按实测均值估算（每只标的证据约 6,442 字，20 只）：

| 标的数 | 改前（单上下文） | 改后（隔离） | 变化 |
|---:|---:|---:|---:|
| 5（午间） | 236,180 字 | 299,246 字 | +27% |
| 16（盘前） | 1,498,672 字 | 921,373 字 | -39% |
| 20（盘后） | 2,211,020 字 | 1,147,601 字 | -48% |

**为什么反直觉**：改前有个隐性浪费 —— 跑第 20 只标的时，上下文里堆着前面 19 只的全部证据与辩论，
**每一轮对话都要重发一遍**，所以成本按平方涨（20 只比 10 只贵 3.2 倍）。
改前 73% 的输入花在「重复读已经分析过的标的」上，只有 27% 是真正必要的。
隔离后每只单独起头，变回线性。标的少时累积本来就不多，所以午间反而贵约 27% ——
这也是午间保留 `inline` 的原因。

### 按盘段分别配置

新增 `config/debate.example.json`（复制成 config/debate.json 生效）：

| 模式 | 做法 | 用在哪 |
|---|---|---|
| `isolated` | 每只标的两独立子代理 | 盘前 / 盘后（标的 ≥ 8 只） |
| `inline` | 同一上下文内先多后空 | 仅午间（标的 ≤ 5 只） |

**读不到配置时按 `isolated` 执行** —— 宁可慢，不要假辩论。

### 一个诚实的限制

隔离是否真的发生，**无法从产物机械验证**：模型完全可能不开子代理、在原地演两方，
然后照常输出格式正确、ID 齐全的内容。

门禁能做的近似约束是「多空证据必须不同源」（按域名 / 媒体来源族判，转载也算同源），
它能抓出「空方抄多方 ID」这种最典型的假辩论，但抓不出「两方各自独立引证、结论却互相让步」。

已在 `references/debate-protocol.md` 写明人工复核口径：**看空方有没有提出一个真正会让多方难受的点**，
而不是看它有没有挂够 ID。另加一条自检 —— 空方至少有一条论点的证据 ID 是多方没引用的。

### 文档

docs/INSTALL-v2.8.0.md 改名为 `docs/INSTALL.md`（去掉版本号，以后 bump 不用再改名），
并补入 v2.9.0 章节：隔离原理、模式对照、成本对比、持仓锚定处理。

## v2.8.0 · 双主题（深色默认 + 浅色切换）（2026-10-22）

### 改版动因
v2.7.0 把版式重做成浅色 Brief，落地后发现两个问题：
- **浅色在手机上的长时间阅读体验不佳** —— 盯盘场景多在户外/低光环境，浅底白字刺眼；
- **没有主题切换** —— 同一份报告在电脑（浅）与手机（深）之间只能二选一。

本次把「双主题」做成 CSS 层的结构性能力，而不是加一层滤镜。

### 双主题机制（Chroma Duality）
- `assets/style.css` 用**同一组变量名**承载两套取值：`:root{}` 放浅色（v2.7.0 原值**一字不改**），`[data-theme="dark"]{}` 放深色。**101 处 `var()` 引用一行不动** —— 这是本改版能低风险落地的关键。
- 深色块放在浅色块**之后**：这是刻意的。反过来（深色在 `:root`）会让浅色校验完全不执行，深色假绿。
- 新增 4 个**告警语义色** `--warn-bg` / `--warn-fg` / `--warn-strong` / `--warn-rule`（深浅各一套），专供降级横幅使用。**不使用 `--rise` 充当告警底色** —— 实算 `ink2 on --rise` 深色仅 1.51:1，严重不达标。

### 主题切换与首帧无闪烁
- `<html data-theme="dark">` 默认深色；报头右上角一个**固定宽度**圆形按钮，图标在太阳/月亮之间切换。
- 选择写入 `localStorage['dpa-theme']`（键名刻意**不含 `dp-` 片段** —— 门禁按 `dp-`/`nw-`/`ch-` 统计证据 ID，误计会污染覆盖率）。
- **首帧无闪烁**：`<head>` 首位一段**同步**内联脚本，在 CSS 解析**之前**读 `localStorage` 并直接设好 `data-theme`。放在 `<style>` 之后只能消掉"解析完成后"的跳变，消不掉首帧闪白。
- 切换时同步 `<meta name="theme-color">`，让移动端浏览器地址栏跟着变色。
- 切换脚本用 `getElementsByTagName('meta')` 而非 `querySelector` —— 后者的属性选择器带方括号，会污染"可见文本无裸方括号"这条门禁。

### 对比度实算与三道防假绿守卫
docs/ui-preview/a11y_check.py 重写为双主题实算（此前只读第一个 `:root{}` 块，深色在 `:root` 时深色会**完全不可见、实算假通过**）：

| 守卫 | 拦住什么 |
|---|---|
| 主题块解析为空 / 变量数不足 → exit 1 | 「只读首块」导致深色假绿 |
| **两套主题变量名集合必须完全相同**，差集非空 → exit 1 | 新增变量只加到一块（实测：只加任一块均 exit 0 放行） |
| 检查表覆盖完整性约束 | 漏测「文字色 × 承载面」组合 |

- 检查表补齐 **前景 × (bg, paper) 完整交叉**。此前 `ink3` 只配了 `bg` —— 但**深色下 `--paper` 比 `--bg` 更亮**，`ink3` 的紧侧是 `paper`（5.88:1），只测 `bg`（6.29:1）恰好在深色下测错了对象。
- 覆盖性判定做**参数空间穷举**（5168 候选 / 358 个绕过解 / 补齐后归零），**单个反例不成立 ≠ 覆盖成立**。
- 配套**防假红**口径：`--paper` 是承载面底色变量、仅作 `background` 使用，底色与底色的差异（浅 1.05 / 深 1.07）不适用文本对比度门槛 —— 否则会诱导实现者去"修"一个本无问题的配色。**假红比漏测更危险。**
- 最终：浅色 16 组 + 深色 16 组正文级全部 ≥ 4.5:1，余量最薄的一对是浅色 `ink3 on bg` = 4.61。

### 降级横幅深色适配（scripts/run_daily.py）
降级横幅原先写死浅色值（`#fdf2f0` / `#7d2f28` / `#a3261f` / `#f0c2bd`），深色主题下不可读 —— 全部改为 `var(--warn-*)` 语义 token。
P4 弱证据徽标的虚线描边由 `rgba(143,97,25,.55)` 改为**不透明 `var(--gold)`**：那个 alpha 是按浅色调的，叠到深底上几乎消失（≈1.84:1）；`var(--gold)` 浅底 5.13:1、深底 9.51:1。**不用 `color-mix()`** —— 旧版 WebView（微信 X5 等）不支持该函数会导致整条声明被丢弃。

### 指纹体系加固（scripts/release.py）
- **CRLF→LF 归一化指纹**：`sha256_of` 对文本类内容归一化后再哈希（二进制不归一化），`bytes` 同口径，顶层加 `"eol": "lf"`。此前 MANIFEST 记的是工作区原始字节，而 `.gitattributes` 强制 `eol=lf` —— 受管 46 文件中 **20 个**在 fresh clone / Linux 上会集体指纹漂移。现在 **Windows 工作区 / git clone / zip 包内** 三态自洽。
- **受管清单 46 → 61**：补齐 `scripts/adapters/`(7)、`examples/`(3)、`config/*.example.json`(2)、`MANIFEST.json`、`VERSION.json`、`tests/fixtures/`(1)。此前 46 文件树跑测试只执行 62 项且有 10 个 ERROR —— **84 项静默不执行（假绿）**；61 文件树实跑 146 项全绿。
- 新增 `package` 子命令：白名单暂存树打包 + 产物卫生自检 + **包内解出重跑全量测试**。直接打包工作目录会带进 1510+ 个私有文件。
- 新增 `fixlinks` 子命令：按上架校验规则批量修断链（**默认只报告不写盘**，需显式 `--write`）。

### 上架元数据与文档
- `SKILL.md` frontmatter 补 `description_zh` / `description_en` / `author`，`license` 移入 `metadata.license`（顶层 `license` 不在校验白名单内）。
- 断链批量修复：上架校验在 61 文件暂存树上从 **156 个 error 降到 0**（149 断链 + 4 标题越级 + 3 缺字段）。
- 新增 docs/INSTALL-v2.8.0.md：安装步骤 / 验证命令 / 主题切换说明 / 贡献者须知。

### 隐私加固
- config/watchlist_depth.json.bak 与 `docs/ui-preview/` 下 2 份预览 HTML + 3 张截图（含**真实持仓金额**）已移出 git 跟踪，`.gitignore` 补 `*.bak` 与 `docs/ui-preview/*.html|png`。**推送前必须完成** —— PNG 是二进制，无法靠文本扫描发现。

### 分发方式（重要）
**本版本不创建标准 GitHub Release 对象、不上传 Release 附件、不创建 tag。**
GitHub MCP 工具集不提供 `create_release` / `upload_release_asset` / `create_tag`，且用户裁决不走 Release。
版本标记以**分支 v2.8.0** 承载，版本说明以仓库内 docs/INSTALL-v2.8.0.md 承载。
本地仍产 zip 安装包供本地安装，**不经 GitHub 分发**。

## v2.7.0 · 报告版式重做（Brief 浅色）（2026-10-22）

### 改版动因（先量化再动手）
原版 1.7 万字 / 147 个证据徽标 / 24 屏无导航：
- **147 个灰底方块散在正文里**（平均每 117 字一个），读长文时视觉噪点密集；
- 关键数字被降级：成本/现价/股数挤在 13px 灰字，**有成本却从不算盈亏**；
- 首屏前置 7 层（顶栏→h1→长副标→200 字机器口径→6 格指数→Regime→目录）；
- 25 张卡片 + 14 个 h2 + 表格三套容器混用，无区块导航。

### 版式（assets/style.css 全量重写）
- **去盒子化**：卡片不再有深色底与圆角，改发丝线 + 留白切分；标题衬线、正文无衬线。
- **红涨绿跌**保留（A 股习惯），但涨跌色只作用文字，不做背景填充；g/r/tg/tr 旧 token 仍兼容。
- **动作状态条**：加/减/观察三类动作在卡片左侧留 2px 状态条，滚动时能扫出"要动手的"。
- **今日动作横滑条** + **区块目录**：24 屏的报告终于有导航。
- **大势段折 3 行**（纯 CSS `-webkit-line-clamp` + 渐隐遮罩 +「读全文」），不再吃掉首屏。
- **覆盖率机器口径**从首屏移到页脚「数据来源与口径」——它是资料，不是今天要读的。
- 正文级文字对比度全部 ≥ 4.5:1（WCAG AA，33 组组合实算；`ink3 #6c727b` 4.61、`gold #8f6119` 5.13）。

### 证据呈现（关键改动，牵动门禁）
- 正文里的 `[dp-001]` **换成上标序号 ¹**，明细收进卡底「证据」折叠（编号/级别/来源/链接）。
- 方括号原文并未删除，而是移入所在元素的 **`data-ev` 属性**：门禁照旧按源码正则
  计数、判多空是否各引独立来源，人眼看到的是干净的正文。
- **修真 bug**：每个 evidence 文件的 ID 都从 `dp-001` 起编号，旧版用全局 dict 装载，
  后写覆盖先写 → 点「来源」跳到别的标的。改按 ticker 分桶后，同一份数据证据条目
  22 → 324 条，每张卡指向自己那份证据。

### 新增
- **浮动盈亏由脚本算**：从持仓串解析成本/现价/股数，输出成本 / 现价 / 浮动三格数据条。
- 指数格改为「数值 + 涨跌」同行，状态词单独落位，窄屏不再挤断（`约4115 连跌3日`）。
- `vendor`/`stat` 染色规则：只有带百分比的涨跌幅才给数值染色，避免把金价读成"跌"。

### 修复（版式改动连带暴露的）
- `run_daily._render_badges` 改为**只替换标签外文本**：全局 `sub` 会把 `<span>` 插进
  `data-ev` 属性，产出畸形标签。
- `run_daily._apply_degrade` 改为**只认 style/script 之外的 body 开标签**：样式表注释里
  出现 `body` 字样时，横幅会被插进 `<style>` 内部——CSS 注释提前结束、后续规则失效，
  且横幅本身被当 CSS 丢弃（本次实测踩中，首屏根本没横幅）。
- 降级横幅在浅色主题下重配颜色，问题清单默认收起，不再独占首屏。
- 版本页脚、徽标兜底样式改为浅色主题可用（原为深色硬编码）。

### 验收
- **前后差分**：同一份 post_2026-10-20_data.json，旧渲染器 42 项问题 → 新 24 项
  （剩余项源于该历史数据里关注库标的没有独立卡片，属数据陈旧，非回归）；
  21 个持仓的证据 ID 集合**逐个完全一致**，无一张卡的证据串到别家。
- 手机 390px 视口 `scrollWidth == 390`，无横向溢出；桌面 1280px 正常。
- 测试 132 → **146** 项全绿，新增 `tests/test_render_ui.py` 14 条：
  卡片起始正则匹配、多空分行不同源、ID 可计数但不可见、上标序号与证据清单对齐、
  覆盖率锚点在位、CSS 注释不得含尖括号标签、`_sub_outside_tags`/`_inject_into_body`。

## v2.6.1 · 手机侧送达打通（2026-10-22）

### 验证结论
- **App 内可直接渲染报告 HTML**（卡片/折叠/锚点目录正常），PRD 最高风险项 **RK-01 关闭**，
  A4「独立站点」备选不需要启用。
- 实现比原设计更轻：**不必先上传 Library** —— `present_files` 的产物在 App 任务详情里就是
  原生渲染的卡片，Bark 只负责叫醒。`read_url_base` 保持留空，少一个上传失败点、少一次数据出本机。

### 新增
- **推送改为脚本机械接线**：`run_daily report` 在三个终态自动发通知——
  PASS / DEGRADED 走 `notify_report`，取证脚本失败走 `alert`（`timeSensitive`，突破静默）。
  之前完全依赖 agent 记得调用 `scripts/notify.py`，模型漏一次就等于没有告警，PRD G3「告警 ≤30 分钟」形同虚设。
- `run_daily report --notify-summary "…"`：把 agent 的一句话摘要塞进通知正文。
- `run_daily {fetch,gate,report} --no-notify`：排错/回放时关推送。
- `notify._suppressed()`：跑单元测试时自动闭嘴（否则测试会大量走失败路径，把手机刷屏），
  另可用 `DAILY_NO_NOTIFY=1` 显式抑制。
- `tests/test_notify.py`（8 条）：抑制开关、`--no-notify`、PASS/DEGRADED/FAIL 分流、推送异常不影响出报告。

### 变更
- 三份 `assets/workbuddy-prompts/*.md` 删除「手动跑 notify.py」步骤，改为「report 已自动推送」，
  避免重复推送。
- config/notify.json 已配置真实 `bark_key`（该文件不入库）；实测 PASS 与 FAIL 两条通知均收到。

### 测试
- 123 → **132** 项全绿。

### 定时任务（automation 侧，不在仓库内）
- 三个定时任务（盘前 8:30 / 午间 12:00 / 盘后 20:00）的 prompt 原先内嵌了一份「铁律」，
  把流程文件里的门禁与交付规则又抄了一遍。本版改了流程，那份副本没跟着变，
  于是每天三次都在执行「只交付 PASS 签名」「用邮箱工具发附件」这类过期指令。
  现改为**单一真相**：prompt 只指向 `assets/workbuddy-prompts/<时段>.md`，并注明
  `{{REPO_DIR}}` 代入仓库根；只保留三条不随版本漂移的约束（仓库根执行 / 不许造假 /
  用户已定通道：Bark + App、不发邮件、不要手动跑 notify.py）。
- 新增守卫 `test_prompts_have_no_frozen_channel_or_manual_push`：prompt 里再出现
  「邮箱工具」「config/delivery.json」「notify.py --session」即失败。

## v2.6.0 · 数据源适配层 + 降级交付（2026-10-22）

### 语义变更（重要，接的人先看这条）
- **门禁 FAIL 不再删除 HTML，改为「降级交付」**：产物保留、首屏插红条（最多列 8 项
  问题 + "另有 N 项"）、签名写 `content="DEGRADED date=… evidence=FAIL report=FAIL
  coverage=… reason=…"`，**退出码仍非 0**（10/11/12），监控照旧能抓到。
  理由：数据不全时报废等于当天零信息；留产物 + 显式降级标记，既能看到结论又不会误当正常报告。
  横幅用 `<!--/degrade-->` 哨兵保证重复调用不叠加，问题文本走 html.escape。

### 新增
- **scripts/adapters/**：数据源适配层（`tencent` / `sina` / `eastmoney` / `north` /
  `cboe` / `baostock_src`），只用标准库 `urllib`，**不装任何第三方包也能取 A股/港股/美股**。
  统一出口 `snapshot(market, ticker)` / `kline(market, ticker, days)`，按
  config/data-sources.json 的优先级链「先到先得」合并，失败源写进 `notes` 并降级。
- **config/data-sources.example.json**：源链模板。换源改配置，不改代码。
- **scripts/notify.py**：Bark 通知。只叫醒——正文上限 400 字，全文点链接去 App；
  午间 `level=passive` 不响铃；告警走 `timeSensitive` 绕过静默时段；`bark_key` 空则不发送、不伪造。
- **coverage/<日期>_<时段>.json**：字段级覆盖度报表（got/miss/rate/sources），
  用来判断"哪个字段一直取不到、该不该接新源"，而不是凭感觉加数据源。
- **docs/PRD-日报产品化-v1.0.md**：15 段完整 PRD，18 条 FR 全带 Given-When-Then，
  5 个目标指标、8 项风险、RTM。用户三项决策：App 阅读 + Bark 通知 / 不做邮件 / 数据不全照发并标缺口。
- **docs/数据源评估-开源Skill实测-2026-10-22.md**：两个开源 skill（87 + 50 端点）12 项实跑
  通过、5 项不通过记录，结论是「抽成适配器」而不是运行时读 62 万字节 SKILL.md。

### 补齐的旧缺口
- `north_south_flow`（北向）：`scripts/adapters/north.py` 直取，单位万元，**不再写 gaps**。
- 美股 `pcr_volume` / `pcr_oi`：`scripts/adapters/cboe.py` 解析 OSI 合约名，只回聚合值不落 1.9MB 原始链。

### 修复
- **东财 `f62` 语义错**：实测返回 2（`f184` 才是 15.78%），改走 fflow/kline 的 `f52`，
  实测 `601899 = -345,490,048 元 → -34549.0 万元`。
- **源链提前 break 漏字段**：原来看 `price_last` + `day_change_pct` 齐了就停，导致东财的
  `main_net_inflow` 永远取不到；改为 `_CORE_FIELDS` 全齐才 break。
- **港股成交额单位**：原为港元原值 1.5e10，改 `round(amt/1e4, 2)` → 万元。
- **重复实现收敛**：`safe_name` / `ensure_utf8_stdout` 三处各有一份 → 统一委托 `paths`，
  并用 `tests/test_parity.py`（7 条）断言 `parse_holdings` / `normalize_ticker` 两套实现结论一致。

### 文档一致性（防模型偏差）
全栈 review 查出并清掉了一批"教模型调不存在的工具"的旧文案：
- `assets/cron-templates/`（3 份）归档到 `.archive/cron-templates-deprecated-2026-10-22/`：
  硬编码另一台机器路径（`/home/user/Doubao/chats/…`）、引用已不存在的
  `seed_finance_lookup` / `general_search`、且写着"报告门 FAIL 自动删 HTML"。
- 三份 `assets/workbuddy-prompts/*.md`：改为降级交付语义；手机侧从「邮箱附件」改为
  **Bark 通知 + App 阅读**（D-02 邮件冻结）。
- `references/data-sources.md` 按 v2.6.0 重写为三层取数（脚本直取 → MCP → 搜索）；
  `references/mcp-data-source.md` 的缺口表同步北向与美股 PCR 已由脚本覆盖。
- SKILL.md / fetch_data.py / run_daily.py 内的 gaps 提示语与 docstring 清掉死工具名。

### 测试与门禁
- 测试 82 → **123** 项全绿。新增 `tests/test_adapters.py`（24）、`tests/test_parity.py`（7），
  以及两条文档漂移守卫：
  - `test_readme_counts_are_accurate`：README 的「N 个核心脚本 / N 项回归测试」必须等于实际值
    （本次发现写着 13 脚本 / 126 测试，实际 12 / 121 —— 说多了比说少了更误导）。
  - `test_no_dead_tool_names_in_agent_facing_files`：agent 面向的文件里不许出现已废弃的工具名。

### 已知未做
- 阅读载体能否在 App 内渲染 HTML 仍未验证（PRD RK-01 最高风险项）。
- config/notify.json 的 `bark_key` 待用户填（当前 `enabled:false`）。
- P1 告警尚未接进三个 WorkBuddy 定时任务。

## v2.5.0 · 接入 NeoData MCP 取数（2026-10-22）

### 背景
本机代理拦截东方财富（`ProxyError` / `RemoteDisconnected`），A 股/港股取数为 0，
美股正常。MCP 走平台侧通道，不受本机网络策略影响——实测三市场全通。

### 新增
- **NeoData MCP 作为补证首选取数通道**：`quote_and_kline` / `technical` / `valuation` /
  `financial_indicators` / `fund_flow`，按市场批量调用（单次 ≤10 个代码）。
  SKILL.md Step 2 与三份 prompt 均已改为「MCP 优先，akshare/搜索兜底」。
- **scripts/derive_indicators.py**：从日 K 线派生门禁要求但 MCP 不提供的三个字段
  （`atr14` / `range_52w_pct` / `volume_ratio`），含内建自检。这三个量决定止损位，
  不许心算——报告门只校验"有没有值"，算错了没人拦。
- **references/mcp-data-source.md**：字段映射表、覆盖缺口、9 个实测坑、单位换算、调用节奏。
- tests/test_derive.py：15 条用例（占位行/省略标记行剔除、倒序翻转、多段合并、
  样本不足返回 None 而非 0）。

### 覆盖缺口（已写入文档，绝不编造）
北向资金 `north_south_flow`、美股 `put_call_or_inst`、基金全部字段——MCP 均不覆盖，
走搜索，取不到写 `gaps`。

### 文档
- docs/operations.md 新增「手机端怎么收报告」：App/小程序通知（含三个前提）、
  邮件附件（需先开通 Agent 邮箱）、微信手动兜底；4.2 补 7 条 MCP 相关故障。
- 明确记录：Agent 邮箱当前未开通，邮件推送会返回 `not_bound`。
- README 说明双通道取数；测试基线 67 → 82。

## v2.4.0 · 迁到本地 + 规范化 + 报告样式重做（2026-10-21）

### 目录与工程化
- 按 skill 规范重组：`SKILL.md` + `scripts/` + `references/` + `assets/` + `tests/`；仓库根 = skill 根。
- 新增 `scripts/paths.py`：全项目路径唯一来源（CLI > ENV > 默认），删掉 `/home/user/Doubao` 回退。
- `scripts/release.py` 重写：删除豆包 RT/`sync`（本地单副本不需要，且会让 doctor 永远不绿）；
  MANIFEST 键名改新布局；`bump` 同步 VERSION / pyproject / SKILL.md 三处版本；doctor 增加语法检查与本地数据就绪检查。
- 数据与代码分离：`config/`、`data/`、`.archive/` 不入库；新增 README / LICENSE / .gitignore / .gitattributes。
- 删除 redeploy.py（豆包 cron 蓝绿重建机制在本地不适用）。

### 报告样式（手机优先）
- **红涨绿跌**：涨/多方红、跌/空方绿；旧 token g/r/tg/tr 保留为别名，历史 data.json 零迁移。
- 正文 13.3px → 15.5px（桌面 16px）、行高 1.75、正文提亮；字体栈补苹方/鸿蒙/雅黑。
- 卡片重排：头部（名称/涨跌▲▼/动作徽章）→ 结论条 → 多空双栏 → 风控/操作常显 → 折叠细节。
- 新增常驻顶栏（Regime + 覆盖率 + 今日动作）、锚点目录、每卡证据清单（ID+级别+来源+链接）。
- 市场位置/共识/证伪/证据默认折叠；桌面 ≥900px 用纯 CSS 自动全展开；表格窄屏自动堆叠。
- `<meta name="color-scheme" content="dark">`，避免安卓浏览器强制反色。

### 关注库
- **语义反转**：watchlist_depth.json（深度白名单）→ watchlist_brief.json（降级名单，缺省=**全部深度分析**）。
  盘后 7 只美股关注标的从"简列"恢复为深度分析。旧文件存在时忽略并提示迁移。
- 新增单次降级开关 `--brief TICKER,TICKER`，不改文件、不影响下一轮。

### 修复
- 渲染器把整张卡压成一行时，报告门会误判"多空同源"——改为按行输出（实测复现后修复）。
- 动作标签排除否定词（"不加仓"不再被判为"加"）。
- 测试导入路径改 `scripts/`；新增 brief 语义 4 条回归用例（共 67 项）。

## v2.3.0 · 迁移到 Windows/WorkBuddy 的阻塞性缺陷修复（2026-10-21）

代码审查发现：架构本身成立（双门禁 + 指纹 + 数据驱动渲染），但**换平台即失效**——
Windows 上 fetch 第一步就崩、4 只场外基金永久漏取证、证据门必然 FAIL。本次逐条修复，
新增 13 条回归用例（46 → 59，全绿）。**以下改动会影响报告呈现与门禁松紧，见每条标注。**

### P0 阻断（不修就出不了报告）
- `scripts/fetch_data.py` / `scripts/gate_check.py`：`safe_name()` 补上 Windows 非法字符（`\ * ? " < > |`）。
  holdings.md 里 `帮你投 \| 全球精选100` 转义后名称含反斜杠，旧版在 Windows 写证据文件
  直接 `FileNotFoundError`，整条管道死在 fetch。只增替换、不改原有 `.`/`:` 映射，历史文件名不变。
- `scripts/fetch_data.py`：`parse_holdings` 的表格列数门槛 4 → 2。基金表只有 3 列
  （名称|金额|收益），旧版会**漏掉全部场外基金**，证据门随即报"缺少证据文件"并阻断。
  **影响**：报告会重新出现这 4 只基金卡片（此前靠历史遗留证据勉强通过）。

### P1 严重
- `scripts/run_daily.py` / `scripts/gate_check.py` / `scripts/release.py` 等：入口统一把 stdout/stderr 切 UTF-8，
  并把 `✗/✓/✅` 换成 ASCII。中文 Windows（GBK）下旧版打印问题清单就
  `UnicodeEncodeError`，退出码从 10 变成 1，门禁的反馈闭环直接断掉。
- `scripts/release.py`：RT 改为**可选**（`DAILY_RT` 环境变量，未配置则 doctor 跳过 RT 校验）。
  旧版硬编码 `/runtime/...`，WorkBuddy/Windows 上 `doctor` 永不通过，而定时 prompt 又要求
  "doctor 必须全绿"，结果是每天只出《环境异常说明》；真跑 `sync` 还会在盘根造垃圾副本。
- `scripts/fetch_data.py`：`market_cap` 归一为**亿元**、`main_net_inflow` 归一为**万元**；
  `scripts/gate_check.py` 同步把市值下限 30 亿降到 0.5 亿。akshare 返回的是"元"，旧版会被
  真实性校验判成"疑似伪造/占位"（紫金矿业 7.78e11 元）。**影响**：市值/资金流数字的
  量纲统一，报告里出现的是"7777 亿"而不是一串元。
- `scripts/gate_check.py`：`_slice_sections` 改为**按卡片边界切片**，并在去标签文本里认票。
  旧版按名称出现位置切原文，会命中徽标属性 `title="P1 · 中芯国际官方"`，把紫金卡片的
  空方整行算给中芯国际（实测切片 10340 字符混入两家内容）。**影响**：报告门更准，
  以前靠相邻卡片"蹭引用"通过的薄卡片现在会真的 FAIL。
- `scripts/run_daily.py`：`--holdings` / `--report-root` 默认值改为 `None`，报告根按 holdings 同级
  推导；`--data` 相对路径按当前目录解析。旧版把豆包路径写成默认值，只传 `--holdings`
  时会去 `/home/user/...` 找证据并误报"缺少证据文件"。
- `scripts/gate_check.py`：覆盖率分母**不再信任证据文件里的 `planned`**，改按 market/instrument/
  session 机械推导。旧版删掉 `planned` 就能用 2 条新闻 + 1 条产业链刷到 100%。
  **影响**：覆盖率数字会普遍下降（更真实），可能有标的从 PASS 掉到 WARN/50% 以下。
- `scripts/gate_check.py`：`status=verified` 的数值型字段必须是数字，字符串占位（如
  "暂无数据，稍后补"）现在会被拦。**影响**：`main_net_inflow` 这类字段必须填数值，
  文字说明请放 `note` 字段或降级为 `estimated`。

### P2/P3
- `scripts/run_daily.py`：`gate --allow-degraded` 真正放行（旧版无分支、恒返回 10）；退出码 11
  （覆盖率降级）恢复可达；`--session quick` 不再 `KeyError`。
- `scripts/gate_check.py`：`SECTION_MARKET` 与 `fetch_data` 对齐（只认 `## XX持仓`），并新增
  "两个解析器结果必须一致"的回归用例。
- `scripts/render_report.py`：所有文本走 HTML 转义（保留 `<b>/<br>/<em>` 白名单），来源 URL
  单独转义；旧版正文含 `<` 会吞内容。
- `scripts/reuse_evidence.py`：复用追加的条目补编号（旧版 docstring 承诺"统一编号"但实际没人做）。
- `scripts/fetch_data.py`：`fetch_us` 不再因 akshare 缺失直接返回空（yfinance 独立可用）；
  美股 ticker 只剥离已知券商后缀，BRK.B 不再被截成 `BRK`。
- `scripts/release.py`：测试文件改为 glob 纳入 MANIFEST；`bump` 容忍带后缀的版本号；
  `scripts/preflight.py` 的 ID 正则与门禁对齐为三位数字。
- `scripts/preflight.py`：`ids_in` 改用 `finditer` 取完整编号（`findall` 带捕获组只返回 dp/nw/ch
  前缀，唯一 ID 数永远 ≤3，自查结论失准）；卡片的"多方/空方"改为检查 `bull`/`bear`
  字段非空——渲染器会自动加前缀，旧版逼 agent 手写一遍，产出"多方：多方："。
- `scripts/release.py`：doctor 增加**全量语法检查**（回归用例只覆盖被 import 的模块，
  `preflight`/`redeploy` 这类命令行脚本坏了测试发现不了，2026-10-21 踩过一次）。
- 新增 scripts/tests/test_regressions.py（16 条，对应上述每条原始缺陷）。

## 修复短 ticker 子串误命中导致报告门错切卡片（2026-10-20，post 07709 卡）

- `scripts/gate_check.py`：`_slice_sections` 按名称/代码位置把报告切成章节，此前用纯 re.escape
  子串匹配，纯 ASCII 短 ticker 会误命中更长单词。典型：关注库可口可乐 ticker **KO** 命中
  07709 卡片空方行里的 **KOSPI**（"KO"为其子串），把该空方行及后续证据 ID 错切给 KO，
  使 07709 误报"证据引用总次数 4 / 空方 0 ID"，报告门反复 FAIL 删 HTML。
- 新增 `_name_pattern`：纯 ASCII 的代码/短 ticker（`[A-Za-z0-9.\-]+`）加左右词边界
  `(?<![A-Za-z0-9])…(?![A-Za-z0-9])`，含中文名称仍按普通子串匹配。可一并杜绝
  KO→KOSPI、MU→MUST 之类短代码误命中。
- 报告写法不变；中文简称（如"美光"对全名"美光科技"）本就不命中，无需改动。
  46 项回归全绿，MANIFEST 重算一致。

## 移除期权板块（2026-10-19，用户要求三份报告全删、连门禁一起去）

- 彻底删除期权/VIX/IV/PCR/卖put 策略板块，pre/noon/post 均不再写、不再取证。
- `scripts/gate_check.py`：去掉 post 强制 options 维度 verified 证据的硬校验；`scripts/fetch_data.py` 删
  post 专用 options_fields（vix_now/iv_vs_hv/event_calendar/put_call_ratio）与对应 gap 提示，
  macro 仅保留指数期货/美元/美债/油金等宏观项（VIX 仅作宏观情绪参考，非策略）。
- SKILL.md / data-schema.md / cron 三模板 / references（output-templates、report-html-template、
  analysis-workflow、data-sources、evidence-schema）/ evals / 示例同步清除期权要求与章节；
  测试删除 `test_post_requires_options`，46 项回归全绿，MANIFEST 重算一致。
- 重大事件周 A/B/C 三情景、事件后实时市场反应（期货/VIX/美元/美债）规则保留不变。

## 工程降 token（2026-10-19，门禁与报告内容零改动）

目标：报告内容一字不砍、功能全保留，纯工程降固定层与返工的 token 消耗。

- **数据驱动渲染（默认）**：新增 `scripts/render_report.py` 通用渲染器 + `assets/style.css`、
  `assets/disclaimer.html`、`assets/data-schema.md`。agent 只填紧凑 data.json，不再每轮手写
  25-38KB builder；CSS/卡片壳/页面骨架/免责全部由脚本读 assets 渲染。`scripts/run_daily.py report`
  新增 `--data` 分支，`--builder` 保留为兼容旧模式。
- **cron 模板瘦身**：pre/noon/post 三份去掉与 SKILL 重复的声明/铁律复述，改为"先 Read SKILL.md
  + data-schema.md"指针，仅保留路径/自愈bash/本时段侧重/交付铁律；三份合计 18.6KB→9.0KB。
- **同日增量复用**：新增 `scripts/reuse_evidence.py`，noon/post 取证前复用同日早时段 verified
  慢变量（财报/估值/ROE）与产业链，实时行情与当日新闻仍新补。
- **对账摘要**：渲染器自动落盘 `recon-<date>-<session>.md`，下轮先读几百字摘要而非整份报告。
- **提交前预校验**：新增 `scripts/preflight.py`，渲染前静态自查多空/ID/来源/缺口，提前拦报告门返工。
- 修正：关注库"首批 LITE/MU"等写死名单改为"以 watchlist.md 当日条目为准"，避免长期偏倚。

## v2.2.2 — 修复报告门 combo 误计入 brief 低覆盖（2026-10-14）

报告门 `check_report` 自行重算组合覆盖率用于横幅校验，但装载证据时未排除 brief
关注标的，导致只有价格、覆盖率极低的 brief 卡片（7只）被计入，把 combo 从证据门的
76.2% 拉低到 57.9%，进而误判"报告自报覆盖率偏差超3个百分点"。

- **`scripts/gate_check.py`**：报告门建立 `brief_tickers` 集合，组合覆盖率计算排除 brief
  关注标的，与证据门 combo 口径完全对齐。

## v2.2.1 — 修复 brief 卡片误触发低覆盖降级（2026-10-14）

v2.2.0 把未列入 watchlist_depth.json 的关注标的收口为 brief 简列、覆盖率按设计记
0.0，但证据门汇总的 `low_cov` 判定仍遍历全部卡片，把 brief 的 0.0 误判为"覆盖率
<50% 的标的"，导致在所有在册标的均 PASS、组合覆盖率 76.2% 时仍错误返回 FAIL。

- **`scripts/gate_check.py`**：`low_cov` 计算排除 level 以 `BRIEF` 开头的卡片。brief 不进
  组合覆盖率（沿用 v2.2.0），也不触发个人覆盖率降级，仅在关注库总览表列示。

## v2.2 — 关注库深度/简列分层 + 现金管理类型（2026-10-14）

问题背景：随着关注库（watchlist）扩张，美股关注标的累计达 13 只。若每只都按完整
深度口径（≥2 独立来源族且同时多空的新闻 + 产业链 + 基本面）取证，单次报告取证不可行、
篇幅失控，而真正需要当晚决策的只有首批 LITE/MU；同时短债 ETF SGOV 净值稳定在 100
附近，落在门禁 ETF 价格区间（0.15–60）之外被误判为越界。

本次改造把"哪些标的值得深度分析"变成可迭代、可正确读取的机器配置：

- **新增权威配置 watchlist_depth.json**（与 holdings/watchlist 同级）：按 session
  列出需"完整多空 + 产业链 + 独立卡片"的关注 ticker；未列出的关注标的为 **brief
  简列**，只取真实现价、在"关注库总览表"展示现价/目标价/距目标%，不强制新闻产业链、
  不计入组合覆盖率。调整深度范围只需改这一个文件，引擎与定时任务读取同一真相，从机制上
  保证"本对话改配置、定时任务对话输出一致"。
- **新增证券类型 `CASH_MGMT`**：短债/货币 ETF（如 SGOV，名称含 SGOV/现金管理/
  0-3月国债/货币/短债）识别为现金管理，仅按持仓金额列示、覆盖率按 1.0，豁免个券
  四层分析与价格区间校验，解决净值 ~100 的越界误判。
- **`scripts/gate_check.py`**：新增 `depth_set()`；证据门对 CASH_MGMT 仅列示、对 brief
  关注只校验真实现价；报告门对 CASH_MGMT/brief 不要求独立章节，brief 到价只要求
  总览表标红提示"已进入目标区·待深度评估"，深度标的维持完整执行清单口径。
- **`scripts/fetch_data.py`**：`instrument_for` 同步识别 CASH_MGMT；按 depth 区分深度/
  简列骨架与 gaps；`main` 读取 depth 并传入。
- 测试：`TestWatchlist` setUp 写入 depth 配置以覆盖深度口径。

## v2.1 — 版本指纹 / 防漂移 / 蓝绿重建（2026-09-29）

问题背景：v2.0 的门禁已是确定性脚本，但标准只在文件里、没有机器可读版本与指纹，
cron 描述只在线上、易复制错；弱模型在取不到外部数据时曾批量填占位值（1.0）、用网站
首页 URL 冒充新闻，骗过"只看字段非空"的形式门禁，产出空壳报告。

本次改造让"跑的是不是最新版、数据是不是真的"可机械校验、可一键重建：

- **新增 `VERSION.json` / `MANIFEST.json`**：语义版本号 + 每个受管文件 sha256 指纹；
  一次性当日脚本（build_report_*/supplement_*）不纳入受管。
- **新增 `scripts/release.py`**：bump / manifest / verify / test / sync / doctor，
  发布先跑测试、同步后校验 RT 指纹。
- **新增 scripts/redeploy.py**：输出确定性《重建操作单》与 dry-run；cron 增删由
  agent 按单执行（纯脚本无法直接调 cron 工具），蓝绿先建后删、幂等、含回滚。
- **新增 `assets/cron-templates/{pre,noon,post}.md`**：把三份标准 cron query 固化为
  ENG 权威模板，改任务描述 = 改模板 + bump + 重建。
- **新增 BOOTSTRAP.md**：可携带值班/重建 prompt 与更新手册，同云电脑同账号新对话
  整段粘贴即可重建。
- **`scripts/run_daily.py`**：daily-gate 签名带 engine/build；双门 PASS 后注入可见页脚版本条。
- **防伪门禁加固（gate_check）**：verified 数值必须有 source、量纲不同字段同值判占位、
  逐字段合理性区间；新闻须具体文章页（首页/栏目页判 FAIL）；刷引用、全局非法方括号
  token、信息源折叠区链接数纳入报告门。
- 三份线上 cron query 增加「执行标准固化声明」。

## v2.0 — 证据门禁版（2026-09-20）

问题背景：v1 的流程要求（五视角、P1-P4、覆盖率、自检清单）全部是自然语言"必须"，
没有机械强制；搜索预算甚至写成上限（5+5 次），agent 可零成本绕行，产物偏浅。

本次改造给好规则"装上牙齿"：

- **新增取证脚本 `scripts/fetch_data.py`**：解析 holdings，akshare/yfinance 批量拉
  行情/估值/资金流/K线，机械计算 MA、52 周分位、ATR、量比；缺库/断网时优雅降级为
  missing 骨架 + gaps，绝不编造。
- **新增证据文件 schema（`references/evidence-schema.md`）**：每只持仓每时段一份
  `evidence/<日期>_<时段>_<代码>.json`，数据点/新闻/产业链笔记统一 ID（dp/nw/ch）。
- **新增双门禁 `scripts/gate_check.py`**：
  - 证据门（辩论前）：价格硬必需、新闻条数与 P1/P2、产业链笔记、缺口诚实披露、
    覆盖率机械计算；FAIL 禁止进入辩论。
  - 报告门（交付前）：论点必须挂真实存在的证据 ID、覆盖率横幅必须等于机械值（±3pct）、
    P4 不得唯一支撑论点、来源折叠区/免责/缺口披露齐全；FAIL 禁止交付。
- **搜索预算从上限改为下限**（`references/data-sources.md`）：脚本批量取数不占预算，
  agent 按标的/板块/宏观/期权保底投入，以过门为终点。
- **SKILL.md 瘦身**：HTML 视觉规范外迁到 `references/report-html-template.md`，
  主文件只保留流程、门禁与取证预算。
- **辩论与模板接入证据 ID**：analysis-workflow / debate-protocol / output-templates
  全部要求论点挂 ID；终审建议需 ≥2 个维度 ID 支撑。
- **测试与回归**：scripts/tests/test_gate.py（16 用例）、`evals/`（fixture、
  补证/报告模拟脚本、7 个场景的 test-cases）。
- 样例报告改为带证据 ID 的合规示范。

保留 v1 的优势设计：三时段轮转、跨报告对账、组合板块雷达（生命周期/SEI/中军龙头）、
四维度与期权强制、A/B/C 三情景规则、观察名单克制写法。

## v1.0

初版：五视角采集 + 多空两轮辩论 + 三视角风控 + 基金经理终审；Regime/SEI/二八撕裂/
连板梯队等量化模型；盘前/午间/盘后三时段模板。
