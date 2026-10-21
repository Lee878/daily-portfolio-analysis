# 运维手册（本地单副本）

> 这份文档回答三件事：**怎么每天跑、怎么改标准、出问题怎么查**。
> 旧版的"云电脑 / runtime 副本 / 蓝绿重建 cron"已随本地化移除。

---

## 1. 每天怎么跑

三个时段由 WorkBuddy 定时任务触发（08:30 / 12:00 / 20:00，周一至周五），
任务内容是 `assets/workbuddy-prompts/{pre,noon,post}.md` 渲染后的全文。

手动跑一次的完整链路：

```bash
python scripts/run_daily.py fetch  --session pre --date 2026-10-22   # 取证骨架 + 证据门首检
python scripts/run_daily.py gate   --session pre --date 2026-10-22   # 补证后复检（0 才能继续）
python scripts/run_daily.py report --session pre --date 2026-10-22 \
       --data data/daily-reports/pre_2026-10-22.json                 # 渲染 + 报告门 + 签名
```

退出码：

| 码 | 含义 | 怎么办 |
|---|---|---|
| 0 | 双门 PASS，HTML 已签名 | 交付 |
| 10 | 证据门 FAIL | 按 problems 补证，写回同一 evidence JSON |
| 11 | 覆盖率 <50%（降级） | 补证；确无数据才加 `--allow-degraded`，报告挂"数据不足"横幅 |
| 12 | 报告门 FAIL，HTML 已删 | 按 problems 修引用/覆盖率/缺口披露 |
| 2 | 参数/环境错误 | 看报错路径，跑 `doctor` |

---

## 1.5 手机端怎么收报告

三条路，按推荐顺序：

### 路径一：WorkBuddy App / 微信小程序（推荐，零配置）

App 的通知权限里包含「任务完成提醒、自动化通知」，定时任务跑完会在手机上弹出通知，
点开能在产物里看报告。微信里搜「WorkBuddy」小程序，效果类似，不用装 App。

**三个前提，缺一不可**：

1. 手机与电脑**登录同一个微信/QQ 账号**（不同账号无法连到这台电脑）；
2. 电脑端打开「连接电脑」开关，且**电脑开机联网**（定时任务跑在本机）；
3. App 里允许通知权限。

⚠️ 电脑关机 = 任务不跑 = 收不到。这是本机部署的固有性质，云端沙箱没有你的
Python 环境和 `config/holdings.md`，替代不了。

### 路径二：Bark 通知（叫醒用，v2.6.0 起为手机侧主通道）

`config/notify.json`（不入库，模板见 `config/notify.example.json`）：

```json
{
  "enabled": true,
  "bark_key": "在 Bark App 里复制到的设备 key",
  "bark_endpoint": "https://api.day.app",
  "read_url_base": "",
  "quiet_hours": ["23:00", "07:30"]
}
```

Bark **只负责叫醒**：通知栏放不下整份报告，正文截断在 400 字以内（3-5 行摘要），
全文点开 App 看。午间自动用 `level=passive`（不响铃），告警走 `timeSensitive` 不受静默时段限制。
`bark_key` 没填时脚本不发送，也不会伪造成功。

### 路径二·原邮件通道（**已冻结，不要用**）

按决策 D-02，邮件推送不再投入、`config/delivery.json` 的邮件位仅保留不开发。
原因有二：Agent 邮箱本身 `not_bound`（未开通就发不出），且邮件明文经第三方服务器，
不如 App 内读。**不要再让定时任务调邮箱工具**。

### 路径三：手动转微信（兜底）

个人微信**没有开放推送接口**，任何"自动发到微信"都要走企业微信机器人之类的中转。
最省事的做法：报告出来后自己把 HTML 拖进「文件传输助手」。

> 注：把报告发布成公网链接再推链接，技术上可行，但你的持仓金额、成本价会暴露在
> 公网地址上，不建议这么做。

---

## 2. 怎么改标准

引擎只有一份，就是本仓库。改动分三类：

### 2.1 改分析标准 / 门禁阈值 / 报告结构

1. 改对应文件：`SKILL.md`（流程）、`scripts/gate_check.py`（阈值）、
   `references/*.md`（方法论）、`assets/*`（样式与数据契约）。
2. **必须补回归用例**：`tests/test_regressions.py`，能复现改动前后的差异。
3. 跑测试：`python -m unittest discover -s tests`（67 项，必须全绿）。
4. 升版本并重算指纹：

   ```bash
   python scripts/release.py bump minor      # 同步 VERSION / pyproject / SKILL.md / MANIFEST
   ```

5. 补 `CHANGELOG.md`。
6. 更新技能副本：`python scripts/install_skill.py`。

### 2.2 改数据（持仓、关注库、目标价）

只改 `config/` 下的文件，**不用重建定时任务、不用升版本**：

- `config/holdings.md`：持仓（真实数据，不入库）
- `config/watchlist.md`：关注库（列顺序固定）
- `config/watchlist_brief.json`：降级名单（留空 = 全部深度分析）

### 2.3 改报告样式

改 `assets/style.css` 或 `scripts/render_report.py`，然后：

1. 用真实 data.json 渲染一版看效果：
   `python scripts/render_report.py --data <data.json> --out <tmp>.html --date … --session … --evidence-dir data/daily-reports/evidence`
2. 手机宽度（360/390px）检查：无横向滚动、首屏能看到顶栏与结论。
3. 跑一次完整 `run_daily report`，确认报告门仍 PASS。

> 渲染器有两条容易被踩坏的约束：卡片必须是 `<div class="card">`（class 后不加属性）、
> "多方/空方"必须各占一行且同行带证据 ID。详见 `references/report-html-template.md`。

---

## 3. 安装 / 更新技能副本

```bash
python scripts/install_skill.py           # 同步到 %USERPROFILE%\.workbuddy\skills\daily-portfolio-analysis
python scripts/install_skill.py --check    # 只检查副本是否与仓库一致（比对 MANIFEST 指纹）
```

- 只同步代码与资产，**不同步** `config/`、`data/`、`.git/`、`.archive/`。
- skill 规范要求 `frontmatter.name` 与目录名一致，脚本会校验并提示。
- 改了受管文件后没重算指纹，`--check` 会报漂移。

---

## 4. 出问题怎么查

### 4.1 先跑体检

```bash
python scripts/release.py doctor
```

输出四段：语法检查 → ENG 指纹 → 单元测试 → 本地数据就绪。
任何一段红，先修那一段，不要继续跑报告。

### 4.2 常见故障

| 现象 | 原因 | 处理 |
|---|---|---|
| `找不到 holdings.md` | `config/holdings.md` 不存在 | 跑 `scripts/setup_local.py` 或从 `examples/` 复制 |
| 证据门报"缺少证据文件" | fetch 没跑，或标的集合不一致 | 先跑 `fetch`，再 `gate`；确认 holdings 表头是 `## XX持仓` |
| 报告门报"引用不存在" | 论点挂了证据文件里没有的 ID | 打开对应 evidence JSON 核对真实 ID |
| 报告门报"多空同源" | 多方/空方用了同一批 ID | 给双方各补独立来源 |
| 覆盖率突然变低 | 分母是机械值，不读文件里的 `planned` | 补数据点；不要改 `planned` 刷分 |
| `doctor` 报漂移 | 改了受管文件没重算指纹 | `release.py manifest`（发版用 `bump`） |
| 取数全部 missing | akshare 未装 | `python -m pip install akshare yfinance`，或 `--no-network` 出骨架后由 agent 补证 |
| **A股/港股取数全 missing，美股正常** | 系统代理拦了东方财富接口（`ProxyError` / `RemoteDisconnected`） | 关代理，或给东财加白名单：`set NO_PROXY=eastmoney.com,push2.eastmoney.com,push2his.eastmoney.com,sina.com.cn,qq.com`；证据 `gaps` 里会写明具体报错 |
| 报告里出现"多方：多方：" | data.json 的 bull 字段自己写了前缀 | 只写论点，渲染器会加"多方：" |
| MCP 返回只有当天一行 | 没传 `start_date`（默认就是当天） | 显式给 `start_date` + `end_date` |
| MCP 返回里有"省略中间历史行情"行 | 长区间被服务端截断 | 分段取（每段约 20 个交易日），用多个 `--mcp` 合并 |
| A 股财务指标缺 ROE | 传了 `2026-Q2` 单季报 | 改累计报告期 `2026-H1` / `2026-9M` / `2026-FY` |
| 港股财务查不到 | 用了 Q2/Q3/Q4 | 港股只有 `Q1/H2/9M/FY` |
| 美股估值查不到 | `valuation` 不支持美股 | 改用 `financial_indicators`（含美股估值字段） |
| Bark 报 `bark_key 为空` | `config/notify.json` 没填 key | 填 key 后重跑；不影响桌面交付 |
| 推送成功但点开没内容 | `read_url_base` 留空 | 填成报告在 App 中的可访问前缀，否则通知只带摘不带链接 |

### 4.3 报告被删了

报告门 FAIL 时 `run_daily` 会物理删除不合格 HTML（设计如此）。修完 problems 重跑即可；
证据 JSON 不会删，是跨报告对账的依据。

---

## 5. 备份与恢复

- **代码**：git（`git log` 可回溯每一次改动）。
- **数据**：`config/` + `data/`，建议每周复制到私密网盘/U 盘。
- **换电脑**：`git clone` → 拷贝 `config/`、`data/` → `python scripts/release.py doctor`。
- **回滚代码**：`git checkout <tag>`；引擎版本在 `VERSION.json` 与 `git tag` 双重记录。

## 6. 数据安全

- `config/` 含真实持仓金额与券商名；`data/` 含历史成本与账户信息。
- 两者都在 `.gitignore` 里，**不要**强制提交。
- Bark 通知会经过第三方服务器（仅摘要文本），`bark_key` 等同于推送凭证，勿外泄。
- 任何截图/日志贴到 issue 前，先把金额与账号打码。
