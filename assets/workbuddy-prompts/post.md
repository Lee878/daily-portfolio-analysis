本请求由「盘后总结与美股前瞻」定时任务到时触发。

目标：调用 daily-portfolio-analysis 引擎产出今日 post 盘后报告。规则、门禁、持仓口径、关注库、数据真实性铁律全部固化在脚本与 SKILL.md，先 Read 下列文件再动手；严禁凭记忆、严禁自创或简化流程、严禁放宽/跳过门禁、严禁脱离脚本手写 HTML 或手工加盖签名。脚本退出码与 daily-gate 签名是唯一权威，脚本不过走失败说明，绝不放水。

先 Read（按序）：
- $ENG/SKILL.md（七步法、双门禁、持仓/清仓口径、关注库，全部以此为准；期权/VIX/IV/PCR 板块已移除）
- $ENG/assets/data-schema.md（数据驱动渲染：只填紧凑 data.json，不写 builder/HTML/CSS/免责）
- $ENG/../holdings.md（最新持仓，勿用旧记忆）
- $ENG/../watchlist.md（本盘只深做其中美股条目，目标价/股数以文件当日为准，不凭记忆写死）

路径常量（<MIGRATED_ROOT> 为迁移解包后的实际根目录，先替换再执行）：
- ENG=<MIGRATED_ROOT>/engine
- holdings=<MIGRATED_ROOT>/holdings.md
- watchlist=<MIGRATED_ROOT>/watchlist.md
- 报告根=<MIGRATED_ROOT>/daily-reports

1. 环境校验：python3 $ENG/scripts/release.py doctor 必须全绿（版本/ENG 指纹/测试；单副本部署不要求 RT，只有配置了 DAILY_RT 才校验 RT）。ENG 指纹不一致先跑 python3 $ENG/scripts/release.py manifest 重算再 doctor；仍不通过则停止，出《环境异常说明》（写明失败步骤与缺口），不要继续。
2. python3 $ENG/scripts/run_daily.py fetch --session post --date <当日> --holdings <holdings.md>
   退出码10=证据门FAIL：按 problems 与 gaps 补证（本环境可用的行情/搜索工具，akshare/yfinance 脚本、公开行情接口、平台内置工具均可，工具名以实际可用为准）、原地写回同一证据 JSON（禁编造、禁占位、禁首页URL），再 gate 直到退出码0。不再要求期权/VIX/IV/PCR 证据。
3. 证据门 PASS 后做四层分析（论点挂真实 [dp/nw/ch-xxx]），按 data-schema.md 填紧凑 data.json，不手写 builder。
4. python3 $ENG/scripts/run_daily.py report --session post --date <当日> --data <data.json> --holdings <holdings.md>
   报告门 FAIL（退出码12）自动删 HTML，修到退出码0。
5. 交付：只交付含 <meta name="daily-gate" content="PASS…"> 签名的 HTML 单文件，交付通道以用户指定为准；.md 与 evidence JSON 存档不发；无签名禁止交付。无法真实通过时改交《数据不足说明》HTML，绝不造假。

本盘侧重：美股优先、为21:30开盘服务，A股/港股全天复盘后置；美股盘前机会、美股在册持仓完整卡片、美股关注库专家分析（现价≤目标接回价给可接回清单或喊先别接，未到价禁喊买，满4周提示重评估）；重大事件周 A/B/C 三情景不预测方向；不写期权/VIX/IV/PCR 策略板块；含次日实战候选作战池、操作建议汇总、观察名单、缺口、来源、免责。

口头进度总结用 caveman 压缩风格（只压叙述，报告/证据/代码正常写）。新手通俗、决策权在用户、附免责、不承诺收益；杠杆/反向ETP提示每日重置耗损；CPI/FOMC/非农公布后先搜实时市场反应（期货/VIX/美元/美债）再给建议，反应与预测不一致立即认错。
