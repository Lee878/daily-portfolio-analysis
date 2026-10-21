本次请求是由「盘中半日总结」定时任务到时触发的。

目标：调用 daily-portfolio-analysis 引擎产出今日 noon 午间精简报告。规则、门禁、持仓口径、数据真实性铁律全部固化在脚本与 SKILL.md，先 Read 下列文件再动手；严禁凭记忆、严禁自创流程、严禁放宽/跳过门禁、严禁手写 HTML 或手工加盖签名。脚本退出码与 daily-gate 签名是唯一权威，脚本不过走失败说明，绝不放水。

先 Read（按序）：
- $ENG/SKILL.md（七步法、双门禁、持仓/清仓口径、精简版规范，全部以此为准）
- $ENG/assets/data-schema.md（数据驱动渲染：只填紧凑 data.json，不写 builder/HTML/CSS/免责）
- /home/user/Doubao/chats/38441678557998594/holdings.md（最新持仓，勿用旧记忆）

路径：ENG=/home/user/Doubao/chats/38441678557998594/engine；RT=/runtime/user_skills/daily-portfolio-analysis

0. 自愈同步（先跑，防重启把 RT 重置）：
   mkdir -p "$RT" && cp -f "$ENG/SKILL.md" "$RT/SKILL.md" && cp -rf "$ENG/scripts/." "$RT/scripts/" && cp -rf "$ENG/references/." "$RT/references/" && cp -rf "$ENG/assets/." "$RT/assets/"

1. python3 $ENG/scripts/run_daily.py fetch --session noon --date <当日> --holdings <holdings.md>
   退出码10=证据门FAIL：按 problems 与 gaps，用 seed_finance_lookup（行情/资金）+ general_search（公告/媒体/官网）补证、原地写回同一证据 JSON（禁编造、禁占位、禁首页URL），再 gate 直到退出码0。午间门槛：技术面硬必需、新闻≥1条具体文章页、产业链≥1。
2. 证据门 PASS 后做精简分析（每只150-200字），按 data-schema.md 填紧凑 data.json，不手写 builder。
3. python3 $ENG/scripts/run_daily.py report --session noon --date <当日> --data <data.json> --holdings <holdings.md>
   报告门 FAIL（退出码12）自动删 HTML，修到退出码0。
4. present_files 只交付含 daily-gate PASS 签名的 HTML；.md 与 evidence JSON 存档不发；无签名禁止交付。无法真实通过时改交《数据不足说明》HTML，绝不造假。

本盘侧重：A股/港股午后操作优先；含上午板块轮动雷达、A股半日、港股半日、逐只在册持仓精简卡片（上午表现/异动归因β还是α/多空分歧一句话/午后操作+价位）、下午关注要点。午间不做关注库分析，不写期权/VIX 板块。

口头进度总结用 caveman 压缩风格（只压叙述，报告/证据/代码正常写）。新手通俗、决策权在用户、附免责、不承诺收益。
