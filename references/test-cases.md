# 门禁测试场景（Evals）

技能的回归测试集。每次改动脚本或证据规则后，必须重跑自动测试并人工过一遍场景 1-5。

## 自动测试（每次改动必跑）

```bash
cd scripts
python -m unittest discover -s tests -p "test_*.py" -v   # 全量：test_gate / test_run_daily / test_release
```

覆盖：持仓解析、代码归一化、技术指标计算、证据门（缺价格/缺新闻/只有 P4/缺产业链/
隐瞒缺口/低覆盖降级；期权板块已移除不再硬要求）、报告门（无引用/伪造 ID/覆盖率虚高/缺来源免责）。

## 端到端联调（手动，使用虚构样例，禁止用于真实报告）

```bash
# 0. 准备临时工作区，复制 evals/fixtures/holdings.sample.md 为 holdings.md
# 1. 取证（骨架）
python scripts/fetch_data.py --holdings <work>/holdings.md --session pre --date 2026-09-20 --no-network
# 2. 证据门对骨架：必须 FAIL（价格缺失、新闻 0、产业链 0）
python scripts/gate_check.py --report-root <work>/daily-reports --holdings <work>/holdings.md \
    --date 2026-09-20 --session pre --stage evidence        # 期望退出码 1
# 3. 模拟 agent 补证
python evals/simulate_supplement.py --report-root <work>/daily-reports --date 2026-09-20 --session pre
# 4. 证据门：必须 PASS，组合覆盖率约 80%
python scripts/gate_check.py ... --stage evidence           # 期望退出码 0
# 5. 生成合规报告并过报告门：必须 PASS
python evals/simulate_report.py --report-root <work>/daily-reports --holdings <work>/holdings.md \
    --date 2026-09-20 --session pre --out <work>/daily-reports/report.md
python scripts/gate_check.py ... --stage report --report-file <work>/daily-reports/report.md  # 0
# 6. 反面：抹掉报告中的 [dp/nw/ch-xxx] 引用后，报告门必须 FAIL（14 个阻断项）
```

## 场景清单

### 场景 1：正常盘前（数据源可用）
- 前置：akshare 可用，网络通畅。
- 期望：fetch 后技术面/估值点 verified；agent 只补新闻/财报/产业链/宏观；证据门 PASS；
  覆盖率 ≥70%；报告门 PASS；HTML 交付。
- 失败信号：技术点大面积 missing 而没有 gaps 说明 → 取数回归问题。

### 场景 2：数据源全挂（akshare 缺失或网络不通）
- 前置：`--no-network` 或未装 akshare。
- 期望：fetch 仍退出码 0，生成全 missing 骨架与 gaps；证据门 FAIL；
  agent 用 NeoData MCP / 搜索补证后 PASS；
  若客观无法补齐且低于 50%，允许 `--allow-degraded`，但报告顶部必须有"数据不足"横幅，
  且只给定性判断。
- 失败信号：脚本因缺库崩溃（不允许，必须优雅降级）；或未补证就放行辩论（门禁失效）。

### 场景 3：重大事件周（CPI/FOMC/非农/重磅财报）
- 前置：session=post 且当周有重大数据。
- 期望：报告含 A/B/C 三情景与概率，不预测明确方向；
  数据公布后必须先搜实时市场反应（期货/VIX/美元/美债）再给建议。
- 失败信号：期权/VIX/IV/PCR 策略板块已移除，报告不得再写卖 put 建议。

### 场景 4：持仓变动
- 前置：holdings.md 新增/删除标的后重跑 fetch。
- 期望：证据文件清单与最新 holdings 一一对应；门禁对"持仓有、证据无"的新标的报缺失；
  已删除标的的旧证据文件不参与本次门禁；证据文件原地更新、不产生重复副本。
- 失败信号：旧标的证据被当成新标的的证据；或新标的无证据却通过门禁。

### 场景 5：偷工减料报告（核心反作弊场景）
- 变体与期望：
  - 论点无证据 ID → 报告门 FAIL（每只完整版需唯一 ID ≥4、引用 ≥6）
  - 引用了证据文件里不存在的 ID（编造）→ FAIL
  - 报告横幅覆盖率与机械值偏差 >3pct（自报美化）→ FAIL
  - 只有 P4 传闻且作为论点唯一支撑（超过 2 条）→ FAIL
  - 缺 `<details>` 信息来源 / 免责声明 / "我不确定的是"缺口披露 → FAIL
- 失败信号：以上任一变体被放行，说明报告门回归失败，必须修脚本。

### 场景 6：午间精简（session=noon）
- 期望：新闻最低 1 条、产业链 1 条；报告门阈值放宽为唯一 ID ≥2；
  基本面计划点缩减；不要求 ATR/60 日线与宏观文件；卡片 150-200 字。
- 失败信号：用完整版阈值卡午间报告（误伤），或午间报告无任何证据引用（漏伤）。

### 场景 7：快速诊断（session=quick，单只）
- 命令：`fetch_data.py --session quick --tickers AAPL`
- 期望：只处理指定标的；价格硬必需不放松；新闻/产业链缺失为警告而非阻断；
  单只结论仍需挂证据 ID。

### 场景 8：版本指纹 / 漂移 / 蓝绿重建（v2.1）
- 命令：
  - `release.py verify --target ENG`（或 RT）：与已发布 MANIFEST 一致 → 0；
    篡改/缺失任一受管文件 → 1 并逐条列出。
  - `release.py doctor`：版本 + ENG/RT 指纹 + 全量测试，全绿才健康。
  - `redeploy.py plan` / `dry-run`：操作单完整、模板齐全、首句标题对应、ENG 指纹一致。
- 期望：占位值 / 缺 source / 首页 URL 被证据门拦；刷引用 / 非法方括号 token 被报告门拦；
  蓝绿先建后删且幂等；保护清单（周度复盘导师、每日健身训练报告）绝不被删改。
- 失败信号：verify 对篡改仍报 0；重建重复创建任务；或误伤保护清单任务。

## 版本纪律

- 改 `fetch_data.py` / `gate_check.py` / schema 阈值后：先跑自动测试，再跑场景 1/2/5。
- 覆盖率权重、最低条数、硬必需项属于"门禁宪法"，改动必须同步本文件、
  evidence-schema.md、evidence-standards.md 三处，并在变更记录中写明原因。
