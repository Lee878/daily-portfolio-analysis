# 股票每日更新 · 迁移方案（豆包 → WorkBuddy）

> 生成时间：2026-10-21 19:43（Asia/Shanghai）；选型确认：**2026-10-21 用户拍板 WorkBuddy、整体迁移、交付通道目标平台自定**
> 迁移对象：daily-portfolio-analysis 每日报告体系（pre 8:30 / noon 12:00 / post 20:00）
> 原则：**内容一字不砍、双门禁不放松、防偏倚机制原样延续**；豆包专属能力逐项替换，非豆包资产整体搬迁。

---

## 一、现状盘点（只读实测，2026-10-21）

### 1.1 资产清单（持久数据盘 `/home/user/Doubao/chats/38441678557998594/`）

| 资产 | 大小/数量 | 说明 | 迁移方式 |
|---|---|---|---|
| `engine/` | 2.3MB | **权威引擎**：SKILL.md / BOOTSTRAP.md / CHANGELOG / VERSION.json / MANIFEST.json / scripts(核心6+发布2+测试) / references(10) / assets(含 cron-templates×3) / evals / examples | 整体原样复制 |
| `holdings.md` | 8.6KB | 持仓档案（A股/基金/港股/美股） | 原样复制（数据文件，随时更新） |
| `watchlist.md` | 5KB | 关注库（持久表，脚本机械解析列序） | 原样复制 |
| `watchlist_depth.json` | 443B | 关注库深度分析名单 | 原样复制 |
| `daily-reports/` | 12MB / 1280 文件 | 历史报告 + 1111 个证据 JSON + recon 对账摘要 | 整体打包归档（见 §4.1 决策 D2） |

### 1.2 定时任务清单（豆包 cron，3 个，均为 `Asia/Shanghai`、`1-5` 交易日）

| cron_job_id | 标题 | 表达式 | 触发时段 |
|---|---|---|---|
| 13059551223042 | 盘前持仓报告 | `30 8 * * 1-5` | 08:30 |
| 12406182911746 | 盘中半日总结 | `0 12 * * 1-5` | 12:00 |
| 12432755283458 | 盘后总结与美股前瞻 | `0 20 * * 1-5` | 20:00 |

> 另有保护清单任务（周度复盘、健身等）不在本次迁移范围，切流时**不得误删**。

### 1.3 豆包平台绑定点（迁移的真正难点，共 4 类）

| 绑定点 | 现状 | 迁移后替代 |
|---|---|---|
| **① 取数**：`seed_finance_lookup`（行情/财务/资金）、`general_search`（新闻） | cron 模板里 agent 靠这两个豆包工具补证 | 见 §3.1 取数替代方案 |
| **② 交付**：`present_files`（HTML 直链 aka.doubaocdn.com） | 手机直链看报告 | 见 §3.2 交付替代方案 |
| **③ 调度**：豆包 cron（create/delete_cron_job） | 云电脑内定时触发 | 见 §3.3 调度替代方案 |
| **④ 运行环境**：豆包云电脑 Linux + python3 | 已装 akshare/yfinance（部分 403） | 目标平台需可跑 python3 + 网络 |

> **好消息**：引擎本身（run_daily/fetch_data/gate_check/render_report/release/redeploy 及全部 references/assets）是**纯 Python 标准库 + 可选 akshare/yfinance**，不含豆包 SDK。`daily-gate` 签名是引擎自己写入 HTML 的，与平台无关——**双门禁在任何平台都原样生效**，这是防偏倚的根，必须原样带走。

---

## 二、目标平台选型（✅ 已定：WorkBuddy）

> 2026-10-21 用户确认：**用 WorkBuddy，整体迁移；报告在目标平台用别的方式交付（本方案不锁交付通道）**。

### 2.1 能力对照（按本体系必需能力）

| 必需能力 | Claude Code | WorkBuddy |
|---|---|---|
| 跑任意本地 Python 脚本 | ✅ `claude -p` + bash | ⚠️ 需确认（能否执行本地脚本） |
| 定时调度（交易日 8:30/12:00/20:00） | ✅ 系统 crontab / 平台 cron 包装 `claude -p` | ⚠️ 需确认（调度语法/时区） |
| 网络搜索 / 金融数据（替代 seed/general_search） | ✅ MCP 服务器（搜索 MCP / 金融 MCP）或脚本直连数据源 | ⚠️ 需确认（内置工具或 MCP） |
| 报告送达手机（替代 present_files） | ⚠️ 无原生通道，需自建：飞书 API / 邮件 / 网盘 | ⚠️ 需确认（内置推送） |
| 项目级标准固化（替代 SKILL.md 角色） | ✅ CLAUDE.md + 引擎 BOOTSTRAP.md | ⚠️ 需确认 |
| 门禁签名（daily-gate） | ✅ 引擎自带，平台无关 | ✅ 引擎自带，平台无关 |
| 成本模型 | Anthropic 订阅/API 计费 | 需确认 |

### 2.2 选型结论

**已定 WorkBuddy**（用户 2026-10-21 拍板）。迁移按 WorkBuddy 执行：
- 资产整体迁移（含 daily-reports 全部历史，见 §1.1）；
- 交付通道不在本方案锁定（用户将 WorkBuddy 侧自定）；
- WorkBuddy 具体能力（脚本执行 / 调度 / 搜索金融工具）以官方文档为准；若它与豆包同账号同文件系统，迁移最轻——现有路径直接可读，只改工具名；若独立环境，按 §4 Phase 1-2 部署。
- **适配核对点（6 项，部署前过一遍）**见 §6；若 WorkBuddy 未提供某项能力，按 §3 的替代方案兜底。

---

## 三、迁移总体架构（五层）

```
┌─────────────────────────────────────────────────────────┐
│  第 5 层 调度   cron 触发 → 拉起"值班 prompt"（交易日）      │
├─────────────────────────────────────────────────────────┤
│  第 4 层 交付   HTML → 飞书/邮件/网盘 → 手机                │
├─────────────────────────────────────────────────────────┤
│  第 3 层 取数   fetch_data.py(akshare/yfinance) + 搜索/金融 MCP │
├─────────────────────────────────────────────────────────┤
│  第 2 层 引擎   run_daily.py 双门禁（原样，零改动）          │
├─────────────────────────────────────────────────────────┤
│  第 1 层 资产   engine/ + holdings/watchlist + daily-reports │
└─────────────────────────────────────────────────────────┘
```

### 3.1 取数替代（第 3 层）

优先级从高到低，**先解决网络，再补工具**：

1. **fetch_data.py 内置路径**：它本就尝试 akshare / yfinance。豆包云电脑 403 是网络出口问题，目标平台（尤其自托管/本地）可能直接可用。迁移后先跑 `python3 $ENG/scripts/fetch_data.py --no-network` 不通的部分再补。
2. **MCP 服务器（Claude Code）**：接一个搜索 MCP（如 Tavily / Brave）替代 `general_search`；金融数据用 akshare 脚本 + 公开行情接口（新浪/腾讯/东财在目标网络可用性实测）。
3. **保留"agent 补证"模式**：cron 模板里的补证动作从"用豆包工具"改为"用 MCP 工具/脚本"，证据 JSON 写回逻辑不变。
4. **诚实缺口兜底不变**：取不到就 `missing` + gaps +《数据不足说明》，**永不占位、永不造假**（这是引擎铁律，平台无关）。

### 3.2 交付替代（第 4 层）

用户手机看报告，HTML 单文件自包含。**已定：交付通道由用户在 WorkBuddy 侧自定**（豆包的 present_files 直链不复用）。候选：飞书机器人 / 邮件 / 网盘 / WorkBuddy 内置推送，任选其一即可；cron prompt 里交付步骤写成"按用户指定通道交付"（见 §7）。

### 3.3 调度替代（第 5 层）

```bash
# 系统 crontab（目标机器，Asia/Shanghai；与豆包 cron 同表达式）
30 8  * * 1-5  /home/user/portfolio/bin/run_pre.sh    >> /home/user/portfolio/logs/pre.log 2>&1
0  12  * * 1-5  /home/user/portfolio/bin/run_noon.sh   >> /home/user/portfolio/logs/noon.log 2>&1
0  20  * * 1-5  /home/user/portfolio/bin/run_post.sh   >> /home/user/portfolio/logs/post.log 2>&1
```

每个 run_*.sh 只做三件事：`cd` 到项目 → 读取对应 cron 模板作为 prompt → `claude -p "$(cat $ENG/assets/cron-templates/<pre|noon|post>.md)"`（Claude Code 非交互模式；WorkBuddy 若支持定时执行同理）。**cron 模板改写**：去掉 `seed_finance_lookup / general_search / present_files` 三处豆包工具名，换成目标平台等价物（见 §7 模板差异清单）。

> 时区陷阱：系统 cron 用目标机器本地时区，务必 `timedatectl` 确认是 Asia/Shanghai；交易日 `1-5` 沿用（节假日不另配，报告里按实际盘面走）。

---

## 四、迁移步骤（分 6 阶段，蓝绿切流）

> 沿用引擎 BOOTSTRAP 的蓝绿思想：**先建新、自检通过、并行验证，最后才删旧**，不空窗、可回滚。

### Phase 0 · 冻结与打包（0.5 天）
1. `release.py doctor` 确认 ENG/RT 全绿，记录当前版本与 MANIFEST 短指纹。
2. 打包资产：`tar -czf portfolio-migrate-<date>.tar.gz engine holdings.md watchlist.md watchlist_depth.json daily-reports/`
   （约 14MB；`daily-reports` 是否整体迁见决策 D2）。
3. 复制豆包 3 个 cron 的**完整 query**（`get_cron_job` 逐条存成 `<title>.query.txt`，作为新平台 prompt 的改写底稿）——本方案生成时已确认 3 个任务在运行、schedule 正确。

### Phase 1 · 目标平台部署（0.5-1 天）
1. 目标机器装 python3 + `pip install akshare yfinance`（失败不影响，缺什么用什么）。
2. 解包到目标目录（示例 `/home/user/portfolio/`），跑：
   - `python3 engine/scripts/release.py doctor` → 必须全绿（指纹自校验，确认资产没在传输中损坏）。
   - `python3 engine/scripts/run_daily.py fetch --session pre --date <今日> --holdings holdings.md` → 验证取证与网络。
3. 配置取数替代（§3.1）与交付通道（§3.2）各通一次最小冒烟。

### Phase 2 · cron 模板改写（0.5 天）
3 个模板按 §7 差异清单改写（工具名替换 + 路径常量替换），**逻辑与门槛一句不动**，存到新平台对应目录。改写后用 `diff` 与原模板核对：只允许出现"工具名/路径/交付通道"差异，禁止出现分析标准、门禁、措辞变化。

### Phase 3 · 并行试运行（建议 3-5 个交易日）
1. 新平台 cron 先建起来，**豆包旧 cron 保持运行**，双轨并行。
2. 每天同一时段产出两份 HTML，人工对照：**报告结构一致、数据一致、结论一致**；重点核 07709/杠杆 ETP 提示、关注库到价判定、覆盖率横幅。
3. 用 `release.py verify` + 报告页脚版本条核对两边跑的是同一版本指纹。
4. 任一天不一致：定位差异（取数源不同？模板改写误伤？），修到连续 3 天一致再进 Phase 4。

### Phase 4 · 切流（用户拍板，0.5 天）
1. 确认新平台连续 3 个交易时段输出一致、交付通道可送达。
2. **在豆包侧删除 3 个旧 cron**（13059551223042 / 12406182911746 / 12432755283458）——由用户确认后执行；保护清单任务不动。
3. 豆包侧可保留一个"权威编辑对话"用于后续改标准（见 §5）。

### Phase 5 · 回归与归档
1. 新平台跑满一周：双门 PASS 率、覆盖率、缺口披露率与原体系对比。
2. 迁移包 `portfolio-migrate-<date>.tar.gz` 与豆包旧证据归档到冷存储（如需）。

---

## 五、防偏倚机制如何延续（关键）

你之前的核心诉求：**"本对话作为调整 → 定时任务输出一致"**。这套机制已固化在 engine 里，迁移后**原样保留**，只换载体：

| 机制 | 豆包现状 | 迁移后 |
|---|---|---|
| 标准唯一来源 | ENG 权威目录 | 同（目标机器 `engine/`） |
| 版本指纹 | VERSION + MANIFEST + release.py | 同 |
| 双门禁签名 | run_daily.py 写入 daily-gate | 同（平台无关） |
| 值班重建 | BOOTSTRAP.md 复制区 + 豆包定时工具 | BOOTSTRAP 保留；"蓝绿重建"的增删动作换成目标平台调度 API / 手动 cron |
| 更新手册 | 改 ENG → bump → test → sync → 重建 cron | 同；"重建 cron"一步换成目标平台操作 |
| 周期性漂移审计 | 建议挂周度复盘 | 同（把 `release.py doctor` 挂进新平台周度任务） |

**关键差异点**：豆包里"改标准 → 值班对话蓝绿重建定时任务"走的是豆包 cron 工具；迁移后这一步变成"改标准 → `release.py bump+test+sync` → 更新目标平台 cron 的 prompt 文件（模板是文件，改文件即生效，比豆包更简单）"。

---

## 六、WorkBuddy 适配自检表（若选它，请逐项确认）

1. 能否执行任意本地 Python 脚本（`python3 engine/scripts/run_daily.py ...`）？
2. 是否有定时调度能力？表达式是否支持 `30 8 * * 1-5` 与 Asia/Shanghai 时区？
3. 是否有网络搜索 / 金融数据工具（替代 seed_finance_lookup / general_search）？是否支持 MCP？
4. 报告 HTML 如何送达手机？（内置推送 / 飞书 / 邮件 / 网盘？）
5. 是否提供"项目级常驻文档"（如 CLAUDE.md / SKILL 装载），用于固化标准？
6. 是否支持非交互/无人值守运行（cron 触发时无需人工确认）？
7. 运行环境与豆包云电脑是否同账号同路径？（若同体系，资产直接可读，迁移降级为"只改模板工具名"）
8. 模型选择与成本？（门禁保证弱模型造不了假，但强模型输出质量更高）

---

## 七、cron 模板改写差异清单（迁移核心产物，WorkBuddy 版）

以 pre.md 为例，迁移后仅以下三处变化（noon/post 同理；成品见 `workbuddy-cron-prompts/` 目录）：

| 原模板（豆包） | 改写后（WorkBuddy） |
|---|---|
| `用 seed_finance_lookup（行情/财报/资金）+ general_search（公告/媒体/官网）补证` | `用本环境可用的行情/财报/资金工具与搜索工具补证（akshare/yfinance 脚本、公开行情接口、内置工具；工具名以实际可用为准）` |
| `present_files 只交付含 daily-gate 签名的 HTML` | `按用户指定交付通道交付含 daily-gate 签名的 HTML 单文件；无签名禁止交付` |
| 路径 `ENG=/home/user/Doubao/chats/38441678557998594/engine` | `ENG=<MIGRATED_ROOT>/engine`（部署后替换为实际根目录） |
| 自愈同步 RT（/runtime 云重启重置） | 删除（WorkBuddy 直接读持久副本）；保留 `release.py doctor` 指纹自校验 |

**必须逐字保留**：先 Read 顺序、`run_daily.py fetch/gate/report` 三命令与退出码语义、`--data` 数据驱动渲染、双门禁铁律、missing/gaps/《数据不足说明》规则、caveman 口头压缩、免责与决策权、杠杆/反向 ETP 提示、CPI/FOMC/非农 A/B/C 与先搜实时反应。

---

## 八、风险清单与回滚

| 风险 | 概率 | 影响 | 对策 |
|---|---|---|---|
| 目标平台网络不通（akshare 403 重演） | 中 | 取证缺口大、覆盖率低 | 先实测网络再定方案；备选公开接口/MCP；缺口如实披露 |
| 模板改写误伤分析标准 | 低 | 报告内容漂移 | Phase 2 diff 核对、Phase 3 并行对照 3 天 |
| 交付通道不稳定（飞书/邮件失败） | 低 | 报告收不到 | 双通道冗余；失败时落本地 + 告警 |
| 切流误删保护清单任务 | 低 | 周度复盘/健身任务丢失 | 切流前 list 全量备份；按 BOOTSTRAP 保护清单只删 3 个 |
| 历史证据丢失 | 低 | 跨报告对账断链 | Phase 0 先打包归档，迁移包留冷存储 |
| WorkBuddy 能力与预期不符 | 中 | 方案返工 | 选型确认前先过 §6 自检表；方案主体与平台无关，返工面小 |

**回滚**：Phase 3 并行期间豆包旧 cron 一直在跑，任何一天新平台不合格，直接停新平台 cron 即可回到原状，**旧体系零改动、零风险**。Phase 4 删旧后如需回滚：在豆包重新 create 3 个 cron（query 用 Phase 0 保存的 `.query.txt`）。

---

## 九、决策记录（2026-10-21 已拍板）

- **D1 选型**：✅ **WorkBuddy**（§2.2）
- **D2 历史数据**：✅ **整体迁移**（`daily-reports/` 12MB 全部随包迁移，迁移包 `portfolio-migrate-2026-10-21.tar.gz`）
- **D3 交付通道**：✅ **目标平台自定**（用户："报告到时候去那边用别的办法"）

> 迁移包、WorkBuddy 版 cron prompt、执行清单均已随本方案产出（见交付物清单）。若 WorkBuddy 能力自检（§6）暴露缺口，按 §3 替代方案兜底后在此追加修订。
