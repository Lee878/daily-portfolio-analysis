本次请求是由「盘前持仓报告」定时任务到时触发的。

目标：调用 daily-portfolio-analysis 引擎产出今日 pre 盘前报告。规则、门禁、持仓口径、关注库、数据真实性铁律全部固化在脚本与 SKILL.md，先 Read 下列文件再动手；严禁凭记忆、严禁自创或简化流程、严禁用自然语言放宽/跳过门禁、严禁脱离脚本手写 HTML 或手工加盖签名。脚本退出码与 HTML 的 <meta name="daily-gate"> 签名是唯一权威，脚本不过就走失败说明，绝不靠"差不多"放水。

先 Read（按序）：
- $ENG/SKILL.md（七步法、双门禁、持仓/清仓口径、关注库规则、多空辩论、输出规范，全部以此为准）
- $ENG/assets/data-schema.md（数据驱动渲染：只填紧凑 data.json，不写 builder/HTML/CSS/免责）
- /home/user/Doubao/chats/38441678557998594/holdings.md（最新持仓，勿用旧记忆）
- /home/user/Doubao/chats/38441678557998594/watchlist.md（本盘只深做其中 A股/港股，美股留到 post）

路径：ENG=/home/user/Doubao/chats/38441678557998594/engine；RT=/runtime/user_skills/daily-portfolio-analysis

0. 自愈同步（先跑，防重启把 RT 重置）：
   mkdir -p "$RT" && cp -f "$ENG/SKILL.md" "$RT/SKILL.md" && cp -rf "$ENG/scripts/." "$RT/scripts/" && cp -rf "$ENG/references/." "$RT/references/" && cp -rf "$ENG/assets/." "$RT/assets/"
   后续 run_daily 直接跑 ENG 持久副本，同步异常也不受影响。

1. python3 $ENG/scripts/run_daily.py fetch --session pre --date <当日> --holdings <holdings.md>
   退出码10=证据门FAIL：按 problems 与 evidence/*.json 的 gaps，用 seed_finance_lookup（行情/财报/资金）+ general_search（公告/媒体/官网）补证、原地写回同一证据 JSON（禁编造、禁占位、禁首页URL，取不到进 gaps），再跑 gate 直到退出码0。
2. 证据门 PASS 后做四层分析（5视角→多空辩论→三风控→终审，论点挂真实存在的 [dp/nw/ch-xxx]），按 data-schema.md 填一份紧凑 data.json，不手写 builder。
3. python3 $ENG/scripts/run_daily.py report --session pre --date <当日> --data <data.json> --holdings <holdings.md>
   报告门 FAIL（退出码12）会自动删 HTML，按 problems 修到退出码0。
4. present_files 只交付含 <meta name="daily-gate" content="PASS…"> 签名的 HTML；.md 与 evidence JSON 存档不发；无签名禁止交付。证据门确实无法真实通过时，改交《今日报告生成失败/数据不足说明》HTML（写明失败步骤/缺失数据/已尝试查询），绝不造假。

本盘侧重：A股/港股优先（9:30开盘），美股隔夜仅作背景后置；关注库只深做 A股/港股（现价≤目标接回价给"可接回股数/止损/证伪"清单或明确喊"先别接"；未到价禁喊买；加入满4周未到价提示重新评估）。

口头进度总结用 caveman 压缩风格（只压叙述，报告/证据/代码/文档正常写）。用户是投资新手、术语通俗、最终决策权在用户、附免责、不承诺收益；杠杆/反向ETP提示每日重置耗损；CPI/FOMC/非农前只给 A/B/C 概率不预测方向，数据公布后先搜实时反应。
