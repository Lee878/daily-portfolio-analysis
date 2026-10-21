本请求由「盘中半日总结」定时任务到时触发。

目标：用 daily-portfolio-analysis 引擎产出今日 午间 报告。规则、门禁、持仓口径、关注库、数据真实性铁律全部固化在脚本与 SKILL.md 里，先 Read 再动手。
严禁：凭记忆、自创流程、用自然语言放宽门禁、脱离脚本手写 HTML、手工加盖签名。
**脚本退出码与 HTML 里的 `<meta name="daily-gate">` 签名是唯一权威**；脚本不过就出《数据不足说明》，绝不"差不多"放水。

## 路径常量（本机）

- REPO = `{{REPO_DIR}}`（仓库根 = 脚本、配置、数据的唯一位置）
- SKILL = `{{REPO_DIR}}/SKILL.md`
- holdings = `{{REPO_DIR}}/config/holdings.md`
- watchlist = `{{REPO_DIR}}/config/watchlist.md`
- 报告根 = `{{REPO_DIR}}/data/daily-reports`

## 先 Read（按序）

1. `{{REPO_DIR}}/SKILL.md`（七步法、双门禁、清仓口径、关注库、多空辩论、输出规范）
2. `{{REPO_DIR}}/assets/data-schema.md`（只填 data.json，不写 HTML/CSS）
3. `{{REPO_DIR}}/config/holdings.md`（最新持仓，勿用旧记忆）
4. `{{REPO_DIR}}/config/watchlist.md`（关注库）

## 执行步骤

1. **环境校验**
   `python "{{REPO_DIR}}/scripts/release.py" doctor` 必须全绿（语法 + 指纹 + 单元测试）。
   不绿先 `release.py manifest` 重算指纹；仍不绿就停止，出《环境异常说明》。

2. **取证 + 证据门**
   `python "{{REPO_DIR}}/scripts/run_daily.py" fetch --session noon --date <当日>`
   - 退出码 **10** = 证据门 FAIL：按 problems 与 `evidence/*.json` 的 gaps，用本环境可用的行情/财报/资金/搜索工具补证（akshare/yfinance 脚本、公开接口、内置搜索均可），**原地写回同一份证据 JSON**（禁编造、禁占位、禁首页 URL，取不到就写进 gaps），再跑 `gate` 直到 0。
   - 退出码 **11** = 覆盖率 <50%：只有客观数据源全挂时才加 `--allow-degraded`，且报告必须挂"数据不足"横幅、只给定性判断。

3. **四层分析 + 填 data.json**
   5 视角 → 多空强制辩论 → 三视角风控 → 终稿；每条论点挂**真实存在**的 `[dp/nw/ch-xxx]`。
   按 data-schema 填一份紧凑 `data.json`（不写 builder、不写 HTML）。
   关注库默认**全部深度分析**；确需降级某只，单次运行加 `--brief TICKER`（不要改配置文件）。

4. **出报告 + 报告门**
   `python "{{REPO_DIR}}/scripts/run_daily.py" report --session noon --date <当日> --data <绝对路径>/data.json`
   - 退出码 **12** = 报告门 FAIL，HTML 会被自动删除：按 problems 修引用/覆盖率/缺口披露，重跑。

5. **交付（三层）**
   - 桌面：`present_files` 打开带签名的 HTML（唯一主交付，无签名禁止交付）。
   - 手机：读 `{{REPO_DIR}}/config/delivery.json`；若 `enabled=true` 且 `to` 非空，用邮箱工具发送：
     主题 `[持仓报告] 午间 <日期>`；正文为**纯文本摘要**（Regime / 覆盖率 / 今日动作 ≤5 条 / 一句话风险，≤15 行）；
     附件为该 HTML。发送失败不影响本地交付，在总结里说明原因。
     若未开启推送，提示用户"可在 config/delivery.json 里填收件人开启"。
   - 微信：个人微信无开放接口，不自动发；需要时由用户把 HTML 拖进「文件传输助手」。
   - 存档：`.md` 与 `evidence/*.json` 留在 `data/daily-reports/`，不发送、不删除。

## 本盘侧重

- 只做 A股/港股：上午表现、异动归因（β / α）、午后操作与价位。
- 午间**不做关注库**（时点设计，不是降级）；新闻门槛放宽到 ≥1 条具体文章页。
- 精简版卡片 150-200 字，不做多空双栏，但证据 ID 与覆盖率照旧。

## 表达与边界

口头进度总结用 caveman 压缩风格（只压叙述，报告/证据/代码正常写）。
用户是投资新手、术语通俗、最终决策权在用户、附免责、不承诺收益；杠杆/反向 ETP 必须提示每日重置耗损；
CPI/FOMC/非农前只给 A/B/C 概率不预测方向，数据公布后先搜实时反应。

## 兜底

证据门确实无法真实通过时，改交《今日报告生成失败/数据不足说明》HTML（写明失败步骤、缺失数据、已尝试的查询），**绝不造假**。
