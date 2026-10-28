> **云端运行模式（WorkBuddy CloudAgent 沙箱）**
> - `REPO_DIR` = `/workspace/dpa`，所有 `python` 命令已改为 `python3`。
> - 持仓（方法 A：私有仓 `HOLDINGS_REPO`）/ 通知(Bark) / COS 配置由 `cloud/bootstrap.sh` 从 secrets 注入，任务开始时已是最新。
> - 数据源优先走 **NeoData MCP**，需云端 Agent 已连接该连接器；它走平台侧通道，不受本机代理影响。
> - 其余流程、门禁、输出规范与本机完全一致。

本请求由「盘前持仓报告」定时任务到时触发。

目标：用 daily-portfolio-analysis 引擎产出今日 盘前 报告。规则、门禁、持仓口径、关注库、数据真实性铁律全部固化在脚本与 SKILL.md 里，先 Read 再动手。
严禁：凭记忆、自创流程、用自然语言放宽门禁、脱离脚本手写 HTML、手工加盖签名。
**脚本退出码与 HTML 里的 `<meta name="daily-gate">` 签名是唯一权威**；脚本不过就出《数据不足说明》，绝不"差不多"放水。

## 路径常量（云端：/workspace/dpa）

- REPO = `/workspace/dpa`（仓库根 = 脚本、配置、数据的唯一位置）
- SKILL = `/workspace/dpa/SKILL.md`
- holdings = `/workspace/dpa/config/holdings.md`
- watchlist = `/workspace/dpa/config/watchlist.md`
- 报告根 = `/workspace/dpa/data/daily-reports`

## 先 Read（按序）

1. `/workspace/dpa/SKILL.md`（七步法、双门禁、清仓口径、关注库、多空辩论、输出规范）
2. `/workspace/dpa/assets/data-schema.md`（只填 data.json，不写 HTML/CSS）
3. `/workspace/dpa/config/holdings.md`（最新持仓，勿用旧记忆）
4. `/workspace/dpa/config/watchlist.md`（关注库）

## 执行步骤

1. **环境校验**
   `python3 "/workspace/dpa/scripts/release.py" doctor` 必须全绿（语法 + 指纹 + 单元测试）。
   不绿先 `scripts/release.py manifest` 重算指纹；仍不绿就停止，出《环境异常说明》。

2. **取证 + 证据门**
   `python3 "/workspace/dpa/scripts/run_daily.py" fetch --session pre --date <当日>`
   - 退出码 **10** = 证据门 FAIL：按 problems 与 `evidence/*.json` 的 gaps 补证，**原地写回同一份证据 JSON**（禁编造、禁占位、禁首页 URL，取不到就写进 gaps），再跑 `gate` 直到 0。补证按下面的优先级走：
     - **行情 / 估值 / 财务 / 资金 → NeoData MCP 优先**。它走平台侧通道，不受本机代理影响（本机代理常拦东方财富，akshare 会全线失败）。动手前先 Read `/workspace/dpa/references/mcp-data-source.md`（字段映射 + 9 个坑），按市场批量调用，单次 ≤10 个代码，不要逐只调。
     - `atr14` / `range_52w_pct` / `volume_ratio` 三个字段 MCP 不提供，**必须**跑 `python3 "/workspace/dpa/scripts/derive_indicators.py" --mcp <kline.json> --ticker <代码>` 算（52 周区间要分段取 K 线再用多个 `--mcp` 合并）。样本不足就写 `missing` + `gaps`，**不许目测估计、不许拿近似值充数**。
     - **基金走 `fund_nav`**（场外代码加 `.OF` 后缀；`limit` 是总条数，给足否则会静默少几只）。净值三字段用 `python3 "/workspace/dpa/scripts/derive_indicators.py" --fund <fn.json> --ticker <基金代码>` 算，混算会被脚本拒绝；基金的规模变化/经理变更/前十大持仓仍走搜索。
     - **MCP 覆盖不到**：北向资金（`north_south_flow`）、美股期权/机构（`put_call_or_inst`）→ 走搜索，取不到进 gaps。
     - **新闻与产业链不走 MCP**（MCP 只给结构化行情），照旧用搜索工具，`url` 必须可访问的具体文章页。
     - MCP 取到的点写 `source: "neodata:<工具名>"`、`fetched_by: "agent"`、`evidence_level: "P3"`。
   - 退出码 **11** = 覆盖率 <50%：只有客观数据源全挂时才加 `--allow-degraded`，且报告必须挂"数据不足"横幅、只给定性判断。

3. **四层分析 + 填 data.json**
   动手前先 Read `/workspace/dpa/config/debate.json`；读不到就按模板 `/workspace/dpa/config/debate.example.json` 走 **isolated**。
   **先净化输入（不跑这步就不许开子代理）**：
   `python3 "/workspace/dpa/scripts/debate_input.py" --evidence <该标的证据JSON> --out "/workspace/dpa/data/daily-reports/debate-input"`
   它会剥掉 holding 里的 cost 与 quantity 字段、account（券商名）、planned，只留行情、新闻、产业链与缺口。
   子代理**只允许读净化后的 `<ticker>.debate.json`**，**禁止读 `evidence/` 原件**
   —— 原件写着成本和券商名，模型一看就知道这是你持有的标的，结论会系统性偏向"继续持有"。
   跑完用 `--verify <目录>` 复核一遍，exit 0 才能进入下一步。
   **isolated（盘前盘后默认，标的 ≥8 只）——每只标的分别开两个独立子代理**：
   - 子代理 A（多方）：只给这只标的**净化后**的文件路径 + 多头角色指令。
     **不提你已经持有、成本多少、浮盈亏多少**；也不告诉它后面还有空方。
   - 子代理 B（空方）：同样只给证据 + 空头角色指令。**绝不把 A 的输出给它**，
     也不给它其他标的的任何内容（否则会横向锚定，比如前一只刚论证行业景气向上，这只的空方就不敢唱反调）。
   - 收回 A、B 两份文本后由**你**做交叉质询 → 三视角风控 → 终审。
     **成本与盈亏只在这一步代入**，用于判断加 / 减 / 保持，不用来判断好 / 坏。
   **inline（仅午间 ≤5 只）**：同一上下文内先多方后空方；即便如此，辩论段落也不要写持仓成本。
   完整流程、禁止项与自检方法见 `/workspace/dpa/references/debate-protocol.md`。
   5 视角 → 多空强制辩论 → 三视角风控 → 终稿；每条论点挂**真实存在**的 `[dp/nw/ch-xxx]`。
   按 data-schema 填一份紧凑 data.json（不写 builder、不写 HTML）。
   关注库默认**全部深度分析**；确需降级某只，单次运行加 `--brief TICKER`（不要改配置文件）。

4. **出报告 + 报告门**
   `python3 "/workspace/dpa/scripts/run_daily.py" report --session pre --date <当日> --data <绝对路径>/data.json`
   - 退出码 **12** = 报告门 FAIL，**HTML 保留但降级**（首屏红条 + 签名 `content="DEGRADED …"`）。
     降级产物**可以交付**，但必须照实说明缺口；要拿到 PASS 签名就按 problems 修引用/覆盖率/缺口披露后重跑。
   - 证据门没过（10/11）照样会出报告，签名同样是 `DEGRADED`——不要因为签名不是 PASS 就丢下用户不管。

5. **交付（三层）**
   - 桌面：`present_files` 打开带签名的 HTML（唯一主交付，无签名禁止交付）。
   - 手机：**Bark 通知 + App 阅读**（D-01/D-02 已定；邮件通道冻结，不要发邮件）。
     `run_daily report` **已自动推送**（PASS 与 DEGRADED 都会发），不要再手动跑 `scripts/notify.py`，会重复。
     想让通知带上人话摘要，就在 report 命令后加 `--notify-summary "今日动作/到价提醒，≤2 句"`。
     排错或回放时加 `--no-notify` 关掉推送。
     推送失败不影响本地交付，如实说明原因即可。
   - 微信：个人微信无开放接口，不自动发；需要时由用户把 HTML 拖进「文件传输助手」。
   - 存档：`.md` 与 `evidence/*.json` 留在 `data/daily-reports/`，不发送、不删除。

## 本盘侧重

- A股/港股优先（9:30 开盘），美股隔夜只作背景后置。
- 关注库只深做 **A股/港股** 标的（美股留到盘后）。到价（现价 ≤ 目标接回价）给"可接回股数/止损/证伪"清单，或明确喊"先别接"；未到价禁喊买；满 4 周未到价提示重新评估。
- A股必须拆结构：上证 / 深成 / 创业板三者涨跌幅与差值；连续 2 日主力净流出 >100 亿要挂资金面预警。

## 表达与边界

口头进度总结用 caveman 压缩风格（只压叙述，报告/证据/代码正常写）。
用户是投资新手、术语通俗、最终决策权在用户、附免责、不承诺收益；杠杆/反向 ETP 必须提示每日重置耗损；
CPI/FOMC/非农前只给 A/B/C 概率不预测方向，数据公布后先搜实时反应。

## 兜底

证据门确实无法真实通过时，改交《今日报告生成失败/数据不足说明》HTML（写明失败步骤、缺失数据、已尝试的查询），**绝不造假**。
