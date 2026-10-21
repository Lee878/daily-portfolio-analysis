# 每日持仓分析（daily-portfolio-analysis）

一套**带机械门禁**的每日持仓分析流程：盘前 / 午间 / 盘后各出一份 HTML 报告，
所有数字可追溯到证据文件，取证不达标脚本直接拦住，不允许"先写报告再补证据"。

> 设计目标只有一句话：**让每天的产出不随时间放水**。强制力在脚本的退出码上，不在模型的自觉上。

---

## 这套东西怎么保证质量（两道门）

```
取证 fetch_data.py  →  证据门 gate_check  →  分析并填 data.json  →  渲染 HTML  →  报告门  →  写签名 → 交付
        ↑                      ↑                                      ↑              ↑
   生成证据骨架           不过：退出码 10                      渲染器套模板      不过：删 HTML，退出码 12
   取不到就标 missing      NEWS/产业链/覆盖率/防伪               agent 不写 CSS
```

- **证据门**：每只标的必须有真实现价、有效新闻（股票完整版 ≥2 条且含多空两边、≥2 个独立来源）、产业链笔记；
  缺口必须写进 `gaps`；覆盖率由脚本机械计算。
- **报告门**：每条论点必须挂真实存在的证据 ID；覆盖率横幅必须与机械值一致；多空必须各有独立证据；
  已清仓标的不得出现卡片；缺来源折叠区/免责/缺口披露一律拦。
- **签名**：双门 PASS 后 HTML 头部写入 `<meta name="daily-gate" content="PASS …">`。
  **没有签名 = 没走门禁，不许交付。**

退出码：`0` 双门 PASS ｜ `10` 证据门 FAIL（去补证）｜ `11` 覆盖率过低（需显式 `--allow-degraded`）｜ `12` 报告门 FAIL（HTML 已删）｜ `2` 参数/环境错误。

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

# 3) 自检：语法 + 版本指纹 + 82 项回归测试
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
| `scripts/` | 8 个核心脚本：取证 / 门禁 / 渲染 / 编排 / 发布自检 … | ✅ |
| `references/` | 方法论与规范（分析流程、辩论协议、证据分级、HTML 规范…） | ✅ |
| `assets/` | 样式、免责、data.json 填写规范、三个时段的 prompt 模板 | ✅ |
| `tests/` | 62 项回归测试 | ✅ |
| `examples/` | 持仓/关注库的空模板 | ✅ |
| `config/` | **你的真实持仓、关注库、送达配置** | ❌ 不入库 |
| `data/` | 每日报告与证据 JSON（含成本、账户信息） | ❌ 不入库 |
| `.archive/` | 历史迁移包与一次性脚本 | ❌ 不入库 |

> 换电脑：`git clone` 代码 → 把 `config/` 和 `data/` 用 U 盘/私密网盘拷过去 → `doctor` 自检。

---

## 每天怎么看报告

- 报告是**单文件 HTML**，双击就能看，不依赖网络。
- 手机优先排版：正文 15.5px、顶部常驻摘要条（市场天气 + 覆盖率 + 今日动作）、
  卡片默认只展开"结论/操作/多空核心"，细节点开看；电脑上自动全展开。
- **涨红跌绿**（A 股习惯）：涨/多方红，跌/空方绿。
- 顶部有锚点索引，25 张卡不用一路滑。

**手机接收**：默认邮件推送（正文是纯文本摘要，附件是 HTML）。
个人微信没有开放接口，无法自动发；需要时把 HTML 拖进「文件传输助手」即可。

---

## 关注库（想低位接回的标的）

- `config/watchlist.md` 一张表：名称｜代码｜市场｜目标接回价｜计划股数｜预计金额｜止损｜加入日期｜状态｜逻辑。
- **默认全部深度分析**（含多空、产业链、到价执行清单）。
- 需要临时降级某只（例如财报暴雷、数据源全挂）：
  在 `config/watchlist_brief.json` 对应时段数组里写 ticker，或单次运行加 `--brief SNDK`。
- 到价判定：现价 ≤ 目标接回价 → 报告标红，并给"可接回清单（股数/止损/证伪）"或明确"先别接"。

---

## 定时任务

三份 prompt 在 `assets/workbuddy-prompts/`（pre / noon / post），已本地化（无云电脑路径）。
在 WorkBuddy 里建三个定时任务（周一至周五）：

| 时段 | 时间 | prompt |
|---|---|---|
| 盘前 | 08:30 | `pre.md` |
| 午间 | 12:00 | `noon.md` |
| 盘后 | 20:00 | `post.md` |

安装到 WorkBuddy 技能目录并检查副本一致性：

```bash
python scripts/install_skill.py          # 同步到 ~/.workbuddy/skills/daily-portfolio-analysis
python scripts/install_skill.py --check  # 只检查，不改文件
```

---

## 常见问题

**取不到行情怎么办？**
`fetch_data.py` 会生成"全 missing 骨架"并列出待补清单，agent 用搜索/行情工具补证写回同一 JSON。
门禁只看证据字段与 URL，不看数据来自哪个接口。取不到就如实写进 `gaps`，**禁止占位、禁止造假**。

**报告门说"引用不存在"？**
论点里挂了证据文件里没有的 ID。去 `data/daily-reports/evidence/` 里核实真实 ID。

**覆盖率为什么比我预期低？**
分母由脚本按 市场/品种/时段 机械推导，不读证据文件里的 `planned`（那个字段可以改小来刷分，已禁用）。

**改了脚本之后 doctor 报漂移？**
受管文件改动后必须重算指纹：`python scripts/release.py manifest`（发版则用 `bump minor`）。

---

## 版本

当前 `2.4.0`。版本号在 `VERSION.json`、`pyproject.toml`、`MANIFEST.json` 三处保持一致；
`MANIFEST.json` 用于校验"本机这份副本有没有被手改过"。

---

## 免责

仅提供研究分析与决策参考，不构成投资建议或买卖指令；不承诺收益、不保证准确性；
信息来自公开渠道，可能存在时效性不足；投资决策与后果由使用者自行承担。
