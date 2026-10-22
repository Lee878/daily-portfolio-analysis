# 每日持仓分析（daily-portfolio-analysis）

一套**带机械门禁**的每日持仓分析流程：盘前 / 午间 / 盘后各出一份 HTML 报告，
所有数字可追溯到证据文件，取证不达标脚本直接拦住，不允许"先写报告再补证据"。

> 设计目标只有一句话：**让每天的产出不随时间放水**。强制力在脚本的退出码上，不在模型的自觉上。

---

## 这套东西怎么保证质量（两道门）

```
取证 fetch_data.py  →  证据门 gate_check  →  分析并填 data.json  →  渲染 HTML  →  报告门  →  写签名 → 交付
        ↑                      ↑                                      ↑              ↑
   生成证据骨架           不过：退出码 10                      渲染器套模板      不过：降级交付 + 标缺口，退出码 12
   取不到就标 missing      NEWS/产业链/覆盖率/防伪               agent 不写 CSS
```

- **证据门**：每只标的必须有真实现价、有效新闻（股票完整版 ≥2 条且含多空两边、≥2 个独立来源）、产业链笔记；
  缺口必须写进 `gaps`；覆盖率由脚本机械计算。
- **报告门**：每条论点必须挂真实存在的证据 ID；覆盖率横幅必须与机械值一致；多空必须各有独立证据；
  已清仓标的不得出现卡片；缺来源折叠区/免责/缺口披露一律拦。
- **签名**：双门 PASS 后 HTML 头部写入 `<meta name="daily-gate" content="PASS …">`；
  任一门未过则写 `DEGRADED …`。**没有签名 = 没走门禁，不许交付。**
- **降级交付（v2.6.0 起）**：门禁没过多半是「数据缺」，而缺什么本身就是用户要知道的信息。
  所以不再删产物，改为**保留真实内容 + 首屏红条标出缺口 + 签名写 DEGRADED**，退出码仍非 0 便于监控。
  阻断级问题（无现价 / 证据 ID 悬空 / 多空同源）仍然不许出结论，只在缺口区说明「证据不足未出结论」。

退出码：`0` 双门 PASS ｜ `10` 证据门 FAIL（已按降级交付）｜ `11` 覆盖率过低 ｜ `12` 报告门 FAIL（已按降级交付）｜ `2` 参数/环境错误。

---

## 数据从哪来（v2.6.0）

行情与估值由**脚本直接取**，不再需要 agent 逐只用 MCP 补——这是省时间省 token 的关键一步。

| 市场 | 主源 | 兜底 |
|---|---|---|
| A股 | 腾讯（不封 IP，一次返回含量比） | baostock（纯 socket）、akshare |
| 港股 | 腾讯 | — |
| 美股 | 新浪（含 52 周高低与 PE） | yfinance |
| A股资金流 | 东财 push2 | — |
| 北向资金 | 同花顺沪深股通 | — |
| 美股期权 PCR | CBOE | — |

- 优先级链在 config/data-sources.json（模板 `config/data-sources.example.json`），**改配置就能换源，不用动脚本**。
- 适配层只用标准库：**不装任何第三方包也能取到 A股/港股/美股行情**；akshare/baostock 只是可选兜底。
- 东财在本机常被封 IP（绕代理也断），所以它只作补充，失败就降级并写进 `gaps`，不反复重试。
- 每批次会生成字段级覆盖度报表 `data/daily-reports/coverage/<日期>_<时段>.json`：哪个字段一直缺、该不该接新源，看这个。

---

## 快速开始（Windows / macOS / Linux 通用）

需要 Python 3.10+（只用标准库；`akshare` / `yfinance` 可选，装了能自动取行情）。

**取数两条通道**：脚本用 `akshare`/`yfinance` 直连；本机网络受限时（企业代理常拦东方财富），
补证阶段改用 **NeoData MCP**（平台侧通道，不受本机代理影响）。字段映射与已知坑见
[references/mcp-data-source.md](references/mcp-data-source.md)。

```bash
# 1) 初始化本地配置（生成 config/ 与 data/，从 examples/ 复制模板）
python scripts/setup_local.py

# 2) 填自己的持仓与关注库
#    编辑 config/holdings.md、config/watchlist.md（格式见 examples/）

# 3) 自检：语法 + 版本指纹 + 164 项回归测试
python scripts/release.py doctor

# 4) 取证（网络可用时去掉 --no-network）
python scripts/run_daily.py fetch --session pre --no-network

# 5) 补证后复检证据门（退出码 0 才能继续）
python scripts/run_daily.py gate --session pre

# 6) 填好 data.json 后出报告（双门 PASS 才写签名）
python scripts/run_daily.py report --session pre --data <绝对路径>/pre.json
```

---

## 目录说明

| 目录 | 放什么 | 是否入库 |
|---|---|---|
| `SKILL.md` | 引擎标准（七步法、门禁口径、输出规范），**唯一权威** | ✅ |
| `scripts/` | 13 个核心脚本：取证 / 门禁 / 渲染 / 编排 / 通知 / 发布自检，外加 `adapters/` 数据源适配层 | ✅ |
| `references/` | 方法论与规范（分析流程、辩论协议、证据分级、HTML 规范…） | ✅ |
| `assets/` | 样式、免责、data.json 填写规范、三个时段的 prompt 模板 | ✅ |
| `tests/` | 164 项回归测试（含跨模块口径一致性测试） | ✅ |
| `examples/` | 持仓/关注库的空模板 | ✅ |
| `config/` | **你的真实持仓、关注库、送达配置** | ❌ 不入库 |
| `data/` | 每日报告与证据 JSON（含成本、账户信息） | ❌ 不入库 |
| `.archive/` | 历史迁移包与一次性脚本 | ❌ 不入库 |

> 换电脑：`git clone` 代码 → 把 `config/` 和 `data/` 用 U 盘/私密网盘拷过去 → `doctor` 自检。

---

## 每天怎么看报告

- 报告是**单文件 HTML**，双击就能看，不依赖网络。
- **Brief 版式（v2.7.0）**：浅底、衬线标题、发丝线分区，没有卡片盒子——
  1.7 万字的报告当"读物"排，不当仪表盘排。
- **指数一行一对**（数值 + 涨跌），**今日动作**横滑条，**区块目录**点击直跳，
  24 屏的报告不用再盲滑。
- **证据是脚注制**：正文只留上标序号 ¹²，卡底「证据」折叠给出编号/级别/来源/链接；
  方括号原文保留在源码 `data-ev` 属性里，所以门禁照样能查、鼠标悬停也照样能看到。
- **成本 / 现价 / 浮动**三格数据条：浮动盈亏由 `scripts/render_report.py` 从持仓串算出，
  不再靠人眼比对（原版有成本却不算盈亏）。
- **涨红跌绿**（A 股习惯）：涨/多方红，跌/空方绿；涨跌色只作用文字，不做背景填充。
- 大势段默认折 3 行 +「读全文」，首屏直接是数据与动作，不是一大段文字。

**手机接收（v2.6.1）**：Bark 负责叫醒，正文只放 3–5 行摘要（结论/动作/到价/缺口），
全文点开 App 看——**App 已实测能直接渲染报告 HTML**，所以不需要上传到任何空间。

配置 config/notify.json（复制 `config/notify.example.json`，填 `bark_key` 即生效）后，
**`run_daily report` 会自动推送**，不用手动跑：

```bash
# 正常出报告：PASS/DEGRADED 自动发通知，可带一句人话摘要
python scripts/run_daily.py report --session post --data data.json --notify-summary "今日动作：持有为主"

# 排错/回放时关掉推送
python scripts/run_daily.py report --session post --data data.json --no-notify
```

手动补发或单独告警才直接用 `scripts/notify.py`：

```bash
python scripts/notify.py --session post --status FAIL --reason "取数全失败"   # 不受静默时段限制
```

邮件通道已冻结（不再依赖 Agent 邮箱）。个人微信无开放接口，只能手动转发。

---

## 关注库（想低位接回的标的）

- config/watchlist.md 一张表：名称｜代码｜市场｜目标接回价｜计划股数｜预计金额｜止损｜加入日期｜状态｜逻辑。
- **默认全部深度分析**（含多空、产业链、到价执行清单）。
- 需要临时降级某只（例如财报暴雷、数据源全挂）：
  在 config/watchlist_brief.json 对应时段数组里写 ticker，或单次运行加 `--brief SNDK`。
- 到价判定：现价 ≤ 目标接回价 → 报告标红，并给"可接回清单（股数/止损/证伪）"或明确"先别接"。

---

## 定时任务

三份 prompt 在 `assets/workbuddy-prompts/`（pre / noon / post），已本地化（无云电脑路径）。
在 WorkBuddy 里建三个定时任务（周一至周五）：

| 时段 | 时间 | prompt |
|---|---|---|
| 盘前 | 08:30 | pre.md |
| 午间 | 12:00 | noon.md |
| 盘后 | 20:00 | post.md |

安装到 WorkBuddy 技能目录并检查副本一致性：

```bash
python scripts/install_skill.py          # 同步到 ~/.workbuddy/skills/daily-portfolio-analysis
python scripts/install_skill.py --check  # 只检查，不改文件
```

---

## 常见问题

**取不到行情怎么办？**
`scripts/fetch_data.py` 会生成"全 missing 骨架"并列出待补清单，agent 用搜索/行情工具补证写回同一 JSON。
门禁只看证据字段与 URL，不看数据来自哪个接口。取不到就如实写进 `gaps`，**禁止占位、禁止造假**。

**报告门说"引用不存在"？**
论点里挂了证据文件里没有的 ID。去 `data/daily-reports/evidence/` 里核实真实 ID。

**覆盖率为什么比我预期低？**
分母由脚本按 市场/品种/时段 机械推导，不读证据文件里的 `planned`（那个字段可以改小来刷分，已禁用）。

**改了脚本之后 doctor 报漂移？**
受管文件改动后必须重算指纹：`python scripts/release.py manifest`（发版则用 `bump minor`）。

---

## 版本

当前 2.6.0。版本号在 `VERSION.json`、`pyproject.toml`、`MANIFEST.json` 三处保持一致；
`MANIFEST.json` 用于校验"本机这份副本有没有被手改过"。

---

## 免责

仅提供研究分析与决策参考，不构成投资建议或买卖指令；不承诺收益、不保证准确性；
信息来自公开渠道，可能存在时效性不足；投资决策与后果由使用者自行承担。
