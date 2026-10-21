本请求由「盘前持仓报告」定时任务到时触发。

目标：调用 daily-portfolio-analysis 引擎产出今日 pre 盘前报告。规则、门禁、持仓口径、关注库、数据真实性铁律全部固化在脚本与 SKILL.md，先 Read 下列文件再动手；严禁凭记忆、严禁自创或简化流程、严禁用自然语言放宽/跳过门禁、严禁脱离脚本手写 HTML 或手工加盖签名。脚本退出码与 HTML 的 <meta name="daily-gate"> 签名是唯一权威，脚本不过就走失败说明，绝不靠"差不多"放水。

先 Read（按序）：
- $ENG/SKILL.md（七步法、双门禁、持仓/清仓口径、关注库规则、多空辩论、输出规范，全部以此为准）
- $ENG/assets/data-schema.md（数据驱动渲染：只填紧凑 data.json，不写 builder/HTML/CSS/免责）
- $ENG/../holdings.md（最新持仓，勿用旧记忆）
- $ENG/../watchlist.md（本盘只深做其中 A股/港股，美股留到 post）

路径常量（<MIGRATED_ROOT> 为迁移解包后的实际根目录，先替换再执行）：
- ENG=<MIGRATED_ROOT>/engine
- holdings=<MIGRATED_ROOT>/holdings.md
- watchlist=<MIGRATED_ROOT>/watchlist.md
- 报告根=<MIGRATED_ROOT>/daily-reports

1. 环境校验：python3 $ENG/scripts/release.py doctor 必须全绿（版本/ENG 指纹/测试；单副本部署不要求 RT，只有配置了 DAILY_RT 才校验 RT）。ENG 指纹不一致先跑 python3 $ENG/scripts/release.py manifest 重算再 doctor；仍不通过则停止，出《环境异常说明》（写明失败步骤与缺口），不要继续。
2. python3 $ENG/scripts/run_daily.py fetch --session pre --date <当日> --holdings <holdings.md>
   退出码10=证据门FAIL：按 problems 与 evidence/*.json 的 gaps，用本环境可用的行情/财报/资金工具与搜索工具补证（akshare/yfinance 脚本、公开行情接口、平台内置搜索工具均可，工具名以实际可用为准）、原地写回同一证据 JSON（禁编造、禁占位、禁首页URL，取不到进 gaps），再跑 gate 直到退出码0；若返回 11，说明覆盖率<50%，只有客观数据源全挂时才可加 --allow-degraded 放行，且报告必须挂“数据不足”横幅、只给定性判断。
3. 证据门 PASS 后做四层分析（5视角→多空辩论→三风控→终审，论点挂真实存在的 [dp/nw/ch-xxx]），按 data-schema.md 填一份紧凑 data.json，不手写 builder。
4. python3 $ENG/scripts/run_daily.py report --session pre --date <当日> --data <data.json> --holdings <holdings.md>
   报告门 FAIL（退出码12）会自动删 HTML，按 problems 修到退出码0。
5. 交付：只交付含 <meta name="daily-gate" content="PASS…"> 签名的 HTML 单文件，交付通道以用户指定为准；.md 与 evidence JSON 存档不发；无签名禁止交付。证据门确实无法真实通过时，改交《今日报告生成失败/数据不足说明》HTML（写明失败步骤/缺失数据/已尝试查询），绝不造假。

本盘侧重：A股/港股优先（9:30开盘），美股隔夜仅作背景后置；关注库只深做 A股/港股（现价≤目标接回价给"可接回股数/止损/证伪"清单或明确喊"先别接"；未到价禁喊买；加入满4周未到价提示重新评估）。

口头进度总结用 caveman 压缩风格（只压叙述，报告/证据/代码/文档正常写）。用户是投资新手、术语通俗、最终决策权在用户、附免责、不承诺收益；杠杆/反向ETP提示每日重置耗损；CPI/FOMC/非农前只给 A/B/C 概率不预测方向，数据公布后先搜实时反应。
