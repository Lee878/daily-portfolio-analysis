# daily-portfolio-analysis · 安装与使用

> **版本与分支**：仓库只有 `main` 一个分支，**没有版本分支、也没有 tag**。
> 下载 `main` 就是最新版。**不要**执行 `git checkout v2.8.0` 之类的命令——那个分支不存在，
> 照抄会直接报 `pathspec 'v2.8.0' did not match any file(s) known to git`。

---

## 零、2026-10-24 补件（本节先看）

本次只**补件**，不动版本号（仍是 2.9.1）：公开包里原本缺「持仓截图 → 自动更新持仓」这一环，
而它恰恰是「不写代码的人」最需要的一步。补进来的东西：

| 文件 | 作用 |
|---|---|
| `scripts/holdings_update.py` | 把「规范化快照 JSON」安全写回 `config/holdings.md` |
| `assets/holdings-snapshot-schema.md` | 快照 JSON 契约：读图那一端只要产出这个结构就能对接 |
| `tests/test_holdings_update.py` | 对应回归测试 |

同时修正本文档此前两处会把人带沟里的说明：

- 「版本标记是分支 v2.8.0」→ 仓库**只有 main**，没有版本分支（上一条提示框已改）；
- 方式 A 里的 `git checkout v2.8.0` → 已删除；
- 方式 B 原来写的是本机打包路径（外人拿不到）→ 改成 GitHub 页面直接下载 ZIP。

`scripts/holdings_update.py` 的四条硬保证（写在代码注释里，也在这里复述一遍）：

1. **校验不通过绝不写** —— 防止 OCR 把 6 看成 8 这类错误污染持仓；
2. **写前必备份**，可 `--restore` 还原到 `config/.holdings-backup/`；
3. **快照里没出现的持仓绝不自动清仓**，只标「待确认」；
4. **默认 dry-run** 只打印变更，加 `--apply` 才真正写入。

---

## 一、v2.9.0 改了什么（辩论隔离）

**辩论执行方式从「一个上下文里演完两方」改成「隔离调用」。**

原因：同一段对话里先写多方再写空方，空方动笔前已经读完了多方的全部论证，反驳被锚定、
倾向软化；两方还共用一次证据检索，空方引用的往往就是多方那几个 ID —— 看起来辩论了，
其实是同一批材料正反两说。

| 模式 | 做法 | 用在哪 |
|---|---|---|
| `isolated` | 每只标的开两个独立子代理（多方 / 空方），互不可见，主代理裁决 | 盘前 / 盘后（标的 ≥ 8 只） |
| `inline` | 同一上下文内先多方后空方 | 仅午间（标的 ≤ 5 只） |

配置在 config/debate.json（模板 `config/debate.example.json`），按盘段可分别指定。
**读不到配置时按 `isolated` 执行。**

顺带修掉一个更隐蔽的偏差：**持仓锚定**。辩论阶段不再把「你已持有、成本多少、浮盈亏多少」
告诉子代理，问题问成「这家公司现在该不该买」；成本只在裁决阶段代入，用来判断加 / 减 / 保持。
模型一旦知道用户持有，会系统性偏向「继续持有」，且不体现在结构上 —— 门禁查不出来，只能靠流程挡。

**成本没有变大，盘前盘后反而更省**（实测按 20 只、每只证据约 6500 字估算）：

| 标的数 | 改前（单上下文） | 改后（隔离） | 变化 |
|---:|---:|---:|---:|
| 5（午间） | 236,180 字 | 299,246 字 | +27% |
| 16（盘前） | 1,498,672 字 | 921,373 字 | **−39%** |
| 20（盘后） | 2,211,020 字 | 1,147,601 字 | **−48%** |

原因是改前有个隐性浪费：跑第 20 只时，上下文里堆着前面 19 只的全部证据与辩论，
**每一轮都要重发一遍**，所以成本按平方涨。改前 73% 的输入花在「重复读已经分析过的标的」上。
隔离后每只单独起头，变回线性。标的少的时候累积本来就不多，所以午间反而略贵 —— 这也是午间保留 inline 的原因。

---

## 二、v2.8.0 改了什么（双主题）

v2.8.0 是一次**双主题化**改版：报告 UI 从「浅色 Brief」升级为「**深色默认 + 浅色可切换**」。

| 变化点 | 说明 |
|---|---|
| 双主题 CSS | `assets/style.css` 用**同一组变量名**承载两套取值：`:root{}` 放浅色（v2.7.0 原值一字不改），`[data-theme="dark"]{}` 放深色。**101 处 `var()` 引用一行不动** |
| 默认深色 | `<html data-theme="dark">`；报告首屏即深色 |
| 主题切换 | 报头右上角一个固定宽度的圆形按钮，图标随主题在太阳/月亮之间切换 |
| 选择记忆 | 写入 `localStorage`，键名 `dpa-theme`；下次打开同一份报告自动恢复上次选择 |
| 首帧无闪烁 | `<head>` 首位一段**同步**内联脚本，在 CSS 解析**之前**读 `localStorage` 并直接设好 `data-theme` —— 不会出现"先闪一下浅色再变深色" |
| 告警语义色组 | 新增 `--warn-bg` / `--warn-fg` / `--warn-strong` / `--warn-rule`（深浅各一套），降级横幅不再硬编码浅色值 |
| 降级横幅 | 数据不全时照发，首屏横幅在深色主题下同样清晰可读（不再是浅底浅字） |

**浅色主题的观感保持不变** —— 浅色块 12 个颜色值相对 v2.7.0 **零改动**。

### 对比度实测

两套主题下所有正文级「文字色 × 承载面」组合均 ≥ 4.5:1（WCAG 2.1 AA 正文级），
由 docs/ui-preview/a11y_check.py 实算，退出码 0 即通过。

| 主题 | 正文 | 次级正文 | 辅助标签 | 涨 | 跌 | 链接 | 告警文字 | 告警强调 |
|---|---|---|---|---|---|---|---|---|
| 浅色 | 16.90 | 8.11 | 4.61 | 5.17 | 5.78 | 8.57 | 8.29 | 6.70 |
| 深色 | 15.67 | 9.99 | 6.29 | 6.63 | 7.29 | 7.33 | 9.31 | 8.31 |

余量最薄的一对是浅色主题的 `ink3 on bg` = **4.61**（阈值 4.5）。
docs/ui-preview/a11y_check.py 另有两道**防假绿**守卫：
- 主题块解析为空 / 变量数不足 → exit 1（防止"只读第一个 `:root{}` 块"导致深色不可见）
- **两套主题变量名集合必须完全相同**，差集非空即 exit 1（防止新增变量只加到一块）
  —— 主题无关的字体栈 `--serif` / `--mono` 只在 `:root` 定义一次，列入白名单

---

## 三、安装

### 方式 A：从 GitHub 克隆

```bash
git clone https://github.com/Lee878/daily-portfolio-analysis.git
cd daily-portfolio-analysis
```

克隆完就在 `main` 上，**不需要再 checkout 任何分支**。

### 方式 B：不装 git，直接下 ZIP

GitHub 仓库页 → 绿色 `Code` 按钮 → `Download ZIP` → 解压。

解压出来的文件夹名带 `-main` 后缀（如 `daily-portfolio-analysis-main`），这很正常，
脚本不依赖文件夹名。

```bash
cd daily-portfolio-analysis-main
```

### 初始化本地配置

```bash
python scripts/setup_local.py
```

幂等：只补缺失项，不覆盖你已有的真实数据。要强制覆盖示例文件用 `--force`（**会丢真实数据，慎用**）。

它会做三件事：
1. 建好 `config/` 与 `data/daily-reports/` 目录
2. 从 `examples/` 复制持仓与关注库模板
3. 检查依赖

### 装成 WorkBuddy 技能

```bash
python scripts/install_skill.py
```

装到：`%USERPROFILE%\.workbuddy\skills\daily-portfolio-analysis`

只同步代码与资产；`config/` `data/` `.git/` 一律不同步（数据留在仓库这边）。
检查副本是否与 MANIFEST 一致：

```bash
python scripts/install_skill.py --check
```

---

## 四、验证（装完照跑一遍）

```bash
# 1. 语法检查 + 指纹一致性 + 全量测试
python scripts/release.py doctor

# 2. 只跑测试
python scripts/release.py test

# 3. 对比度实算（双主题）
python docs/ui-preview/a11y_check.py

# 4. 打包自检（白名单暂存树 + 产物卫生 + 包内重跑测试）
python scripts/release.py package --dry-run
```

**预期**：`doctor` 三项全绿（语法通过 / 指纹一致 / `Ran 184 tests` + `OK`）；
a11y_check.py 退出码 0；`package --dry-run` 报暂存树文件数与产物卫生检查全通过。

### 指纹与换行说明

`MANIFEST.json` 的 `sha256` 按 **CRLF→LF 归一化后**的字节计算（二进制文件不归一化），
顶层 `"eol": "lf"` 标注了这一口径。

这样 **Windows 工作区（CRLF）/ git clone（LF）/ zip 包内（LF）** 三种形态算出的指纹完全一致 ——
换机或换系统跑 `scripts/release.py verify` 不会因为换行符集体漂移。

> 贡献者须知：任何改动 `assets/style.css` / `scripts/**` / `references/**` / `tests/**` 的提交，
> 都必须紧跟一次 `python scripts/release.py manifest`，否则 `test_release` 的两个用例会红。

---

## 五、主题切换说明

### 手动切换

点报告报头右上角的圆形按钮（太阳/月亮图标）即在深浅之间切换。

### 行为约定

| 项 | 值 |
|---|---|
| 存储键 | `localStorage['dpa-theme']`，取值 `'light'` 或 `'dark'` |
| 默认 | 深色（`localStorage` 无值或读取抛异常时兜底为深色） |
| 持久化 | 切换即写回；下次打开同一份报告自动恢复 |
| 缓存依赖 | **不依赖** —— 每次打开都是首帧即正确主题，不存在"先深后浅"的跳变 |
| 打印 | `@media print` 强制白底，主题不影响打印稿 |

### 主题不影响内容

同一份报告的**内容、数据、证据、结论完全一致** —— 主题只改配色。
两套主题下的门禁判定、覆盖率、缺口披露完全相同。

---

## 六、跑一次日报

```bash
python scripts/run_daily.py --session pre
```

时段可选 `pre`（盘前）/ `noon`（午间）/ `post`（盘后）。

产出：一份单文件 HTML 报告 + 同目录 `evidence/` 证据文件。
**唯一可交付的产物是那份 HTML**；`.md` 存档与 `evidence/*.json` 是过程材料，不交付。

推送通知（可选，需先在 config/notify.json 配好 Bark key）：

```bash
python scripts/notify.py --session pre
```

---

## 七、持仓截图 → 更新持仓（补件功能）

这是给「不想手敲表格」的人准备的。整条链路拆成两段，中间用一份 JSON 交接：

```
券商 App 持仓截图  →  读图产出快照 JSON  →  holdings_update.py 校验/比对/备份/写回  →  config/holdings.md
                      （任何模型或人来做）        （脚本做，四条硬保证）
```

快照 JSON 的结构见 [`assets/holdings-snapshot-schema.md`](../assets/holdings-snapshot-schema.md)，
A股 / 港股 / 美股 / 基金四种市场各一张表，字段就那十来个，名字写清楚就能对上。

**第一步：先预览（默认就是 dry-run，不会动文件）**

```bash
python scripts/holdings_update.py --snapshot snap.json
```

会打印三块：新增哪些、改了什么、哪些在快照里没出现（后者只标「待确认」，**绝不自动清仓**）。
校验不过直接退出码 1，一个字都不写。

**第二步：确认无误再落盘**

```bash
python scripts/holdings_update.py --snapshot snap.json --apply
```

写之前自动备份到 `config/.holdings-backup/holdings-<时间戳>.md`。

**真清仓了要显式说**

```bash
python scripts/holdings_update.py --snapshot snap.json --apply --mark-cleared 09988.HK
```

**写错了怎么办**

```bash
python scripts/holdings_update.py --list-backups
python scripts/holdings_update.py --restore config/.holdings-backup/holdings-20261024-093000.md
```

`--json` 可以把比对结果输出成 JSON，方便套到别的流程里；
`--force` 是忽略阻断错误强写，**只在明确知道自己在干什么时用**。

---

## 八、退出码约定

| 码 | 含义 |
|---|---|
| `0` | 证据门 + 报告门**双门 PASS** |
| `10` | 证据门 FAIL（**已按降级交付**：保留真实内容 + 首屏标缺口 + 签名写 `DEGRADED`） |
| `11` | 覆盖率过低 |
| `12` | 报告门 FAIL（已按降级交付） |
| `2` | 参数 / 环境错误 |

**数据不全照发** —— 缺什么本身就是用户要知道的信息，所以不删产物，改为保留真实内容 + 首屏红条标出缺口。
签名写 `DEGRADED` 而非 `PASS`，退出码仍非 0 便于监控。

---

## 九、仓库结构

```
daily-portfolio-analysis/
├── SKILL.md                  技能主文档
├── scripts/                  15 个主脚本（含 holdings_update）+ adapters/ 数据源适配器
├── references/               12 份方法论文档（角色 / 流程 / 证据 / 模型 / 风控…）
├── assets/                   style.css（双主题）+ 声明 + 模板 + 三份 prompt + 快照契约
├── tests/                    14 个测试文件 + fixtures
├── examples/                 持仓 / 关注库示例
├── config/                   配置模板（*.example.*）
├── docs/INSTALL.md           本文档
├── VERSION.json              版本号
└── MANIFEST.json             受管文件指纹清单
```

**受管文件共 61 个**，`scripts/release.py` 的 `managed_files()` 用 glob 规则自动纳入，新文件不用手工登记。

---

## 十、许可

见仓库根目录 `LICENSE`。
