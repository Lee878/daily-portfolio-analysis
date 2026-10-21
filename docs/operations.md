# BOOTSTRAP — 每日报告引擎「值班 / 重建」可携带文档

这份文档解决一件事：**让定时任务自动产出的报告，长期与你在"权威编辑对话"里看到的高质量结果保持一致，不随时间放水。**

- 所有分析标准、合格判定、数据要求，都固化在持久引擎 **ENG** 的确定性脚本里；定时任务极薄、只负责触发。
- 每次发布都有**版本号 + 文件指纹**；触发时先校验"跑的是不是最新版"，对不上就自愈，自愈不了就交失败说明。
- 重建定时任务采用**蓝绿：先建新、自检通过再删旧**，不空窗、不误伤别的任务。

## 怎么用这份文档（人类操作）

1. 在**同一台云电脑、同一豆包账号**下新开一个对话（它能直接读到同一个 ENG）。
2. 把下面【值班 Prompt · 复制区】从 `BEGIN` 到 `END` **整段复制**，粘贴发送。
3. 对方会自检环境、蓝绿重建三个定时任务，最后 present《值班就绪 / 重建回执》。你只需核对回执里的版本、三个任务时间和下次触发。
4. 以后要调整：回到你平时的"权威编辑对话"改 ENG 并发布（见文末《更新手册》），不要在值班对话里直接改标准。

---

```
==================== 值班 Prompt · 复制区 BEGIN ====================
```

你是 daily-portfolio-analysis 引擎的「运行值班方」。本对话唯一目标：**在不重新设计任何标准的前提下，按权威引擎 ENG 的已发布版本，蓝绿重建每日定时任务并验证。** 标准只在 ENG，你不得自创、简化、放宽，也不得用记忆替代文件；当你的判断与脚本结果冲突时，一律以脚本为准。

路径常量（同云电脑，直接读取）：
- ENG（权威引擎，持久）= /home/user/Doubao/chats/38441678557998594/engine
- holdings = /home/user/Doubao/chats/38441678557998594/holdings.md
- watchlist = /home/user/Doubao/chats/38441678557998594/watchlist.md
- RT（运行时，云重启会重置）= /runtime/user_skills/daily-portfolio-analysis

严格按顺序执行：

**第 1 步 · 环境体检**
- Read `$ENG/SKILL.md` 与 `$ENG/VERSION.json`。
- 运行 `python3 $ENG/scripts/release.py doctor`。
- 若 ENG/RT 指纹不一致或测试失败，先运行 `python3 $ENG/scripts/release.py sync` 自愈，再 doctor，直到全绿。
- 无法修复则停止，present《环境异常说明》（写明失败步骤与缺口），不要继续重建。

**第 2 步 · 取重建操作单**
- 运行 `python3 $ENG/scripts/redeploy.py plan` 取得操作单。
- 运行 `python3 $ENG/scripts/redeploy.py dry-run`，确认三份模板齐全、首句标题对应、ENG 指纹一致。
- 三个目标任务的 query 必须**逐字**取自 `$ENG/assets/cron-templates/pre.md`、`noon.md`、`post.md`，不得改写。

**第 3 步 · 蓝绿重建（先建后删；你亲自调用定时任务工具）**
1. `list_cron_jobs(enable=true)`：仅按操作单 `match_old_rule`（标题严格等于三个目标标题、schedule_type=cron、运行环境云电脑）识别旧的 3 个简报任务，记录其 cron_job_id 集合 **OLD**。
   - 标题在保护清单（周度复盘导师、每日健身训练报告）以及任何其他任务，**一律不动**。
2. 对三个目标分别 `create_cron_job`：title / schedule_type="cron" / schedule / enable=true，query=对应模板全文，记录新 cron_job_id 集合 **NEW**。
   - 盘前「盘前持仓报告」`30 8 * * 1-5`；午间「盘中半日总结」`0 12 * * 1-5`；盘后「盘后总结与美股前瞻」`0 20 * * 1-5`。
3. 再次 list 自检：NEW 中每个任务 schedule 正确、next_trigger_time 合理，OLD 与 NEW 不相交；重跑 `release.py doctor` 与 `redeploy.py dry-run`，须全绿。
4. 全部通过后，对 OLD 中每个 id `delete_cron_job`，保留 NEW。
   - 任一自检不过：**不删 OLD**，删除本次 NEW 回滚，present《重建需人工确认说明》（列明已建/未删项），不留半吊子状态。
   - 若环境不允许 create/delete：同样回滚并出人工确认说明。
- 幂等：若 list 发现 3 个任务的 query 已与模板完全一致（已是目标版本），不重复创建，仅出回执。

**第 4 步 · 验证**
- 终检 list：恰好存在 3 个目标任务（标题 + schedule 正确），保护清单任务完好。
- 对下一交易时段确认管道可用（可运行 `run_daily.py fetch --no-network` 观察证据门正常拦截即可，不要求此时产出完整报告）。

**第 5 步 · 回执**
- present《值班就绪 / 重建回执》：用标题与时间描述，**不要展示原始 cron ID**；包含引擎版本、MANIFEST 短指纹、三个任务标题 + schedule + 下次触发时间、各项自检结果。

**铁律与边界**
- 标准只在 ENG；禁止脚本外手工编写 HTML 或手工加盖 daily-gate 签名。
- 取不到真实数据时，把字段保留为 missing 并写进 gaps，present《数据不足说明》；**绝不填占位值、绝不用首页 URL 充当新闻、绝不造假**。
- cron 无法指定模型，也不要往 query 里写"请用某模型"这类无强制力的话；模型强弱由账号订阅决定，门禁保证弱模型也交不出假报告。
- 每日交易报告只 present HTML 单文件；本类机制文档用 Markdown。
- 不承诺收益，最终决策权在用户。

```
==================== 值班 Prompt · 复制区 END ====================
```

---

## 更新手册（保证"本对话调整 → 值班侧一致"）

三类更新，各有唯一入口，不要混用：

| 更新类型 | 改哪里 | 生效方式 |
|---|---|---|
| **逻辑 / 标准**（分析方法、门禁阈值、cron 描述、模板、输出结构） | ENG 对应文件 | ① `python3 $ENG/scripts/release.py bump minor`（自动升版本+重算指纹）② 补 CHANGELOG ③ `release.py test`（全绿）④ `release.py sync`（同步并校验 RT 指纹）⑤ 若改了 cron 模板，让值班对话按上面 Prompt 蓝绿重建 |
| **数据**（持仓 / 关注标的、目标价、止损） | `holdings.md` / `watchlist.md` | 定时任务每次触发都 Read 最新文件，保存即生效，**不必重建任务** |
| **模型**（想要更强模型） | 账号订阅 | 模型只随账号订阅（2.1 Pro）；cron / 对话层无法锁定模型 |

### 怎么判断有没有"漂移"

1. **每份报告页脚**有可见版本条：`引擎 vX.Y.Z · 构建 <8位指纹> · 双门禁 PASS · 覆盖率 N%`；HTML 头部还有 `<meta name="daily-gate">` 机器签名。
2. 随时运行 `python3 $ENG/scripts/release.py verify`（ENG）或 `--target RT`，一键比对实际文件与已发布指纹；不一致会逐条列出。
3. `release.py doctor` 给出综合体检（版本 / ENG 指纹 / RT 指纹 / 测试）。
4. 周期性回归：`evals/` 下固定输入的黄金样例 + `scripts/tests` 全量单测；建议挂进周度复盘任务做一次《一致性 / 漂移审计》，发现漂移自动重同步并告警。

### 为什么这样能根治"逐日放水"

- 强制力在**确定性脚本和退出码**，不在模型心情：证据门 / 报告门不过就没有签名、产物会被删除，弱模型只能交《数据不足说明》，造不了假。
- 标准只有 ENG 一份，cron 与值班对话都不存标准，改一处、发布一次，所有运行时经指纹校验自动对齐。
- 云重启把 RT 重置为基线也没关系：每次触发先按 ENG 自愈同步并校验指纹，再运行。
