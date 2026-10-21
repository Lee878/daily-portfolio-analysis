本请求由「盘中半日总结」定时任务到时触发。

目标：调用 daily-portfolio-analysis 引擎产出今日 noon 午间精简报告。规则、门禁、持仓口径、数据真实性铁律全部固化在脚本与 SKILL.md，先 Read 下列文件再动手；严禁凭记忆、严禁自创流程、严禁放宽/跳过门禁、严禁手写 HTML 或手工加盖签名。脚本退出码与 daily-gate 签名是唯一权威，脚本不过走失败说明，绝不放水。

先 Read（按序）：
- $ENG/SKILL.md（七步法、双门禁、持仓/清仓口径、精简版规范，全部以此为准）
- $ENG/assets/data-schema.md（数据驱动渲染：只填紧凑 data.json，不写 builder/HTML/CSS/免责）
- $ENG/../holdings.md（最新持仓，勿用旧记忆）

路径常量（<MIGRATED_ROOT> 为迁移解包后的实际根目录，先替换再执行）：
- ENG=<MIGRATED_ROOT>/engine
- holdings=<MIGRATED_ROOT>/holdings.md
- 报告根=<MIGRATED_ROOT>/daily-reports

1. 环境校验：python3 $ENG/scripts/release.py doctor 必须全绿（版本/ENG 指纹/测试；单副本部署不要求 RT，只有配置了 DAILY_RT 才校验 RT）。ENG 指纹不一致先跑 python3 $ENG/scripts/release.py manifest 重算再 doctor；仍不通过则停止，出《环境异常说明》（写明失败步骤与缺口），不要继续。
2. python3 $ENG/scripts/run_daily.py fetch --session noon --date <当日> --holdings <holdings.md>
   退出码10=证据门FAIL：按 problems 与 gaps，用本环境可用的行情/资金工具与搜索工具补证（akshare/yfinance 脚本、公开行情接口、平台内置搜索工具均可，工具名以实际可用为准）、原地写回同一证据 JSON（禁编造、禁占位、禁首页URL），再 gate 直到退出码0。午间门槛：技术面硬必需、新闻≥1条具体文章页、产业链≥1。
3. 证据门 PASS 后做精简分析（每只150-200字），按 data-schema.md 填紧凑 data.json，不手写 builder。
4. python3 $ENG/scripts/run_daily.py report --session noon --date <当日> --data <data.json> --holdings <holdings.md>
   报告门 FAIL（退出码12）自动删 HTML，修到退出码0。
5. 交付：只交付含 <meta name="daily-gate" content="PASS…"> 签名的 HTML 单文件，交付通道以用户指定为准；.md 与 evidence JSON 存档不发；无签名禁止交付。无法真实通过时改交《数据不足说明》HTML，绝不造假。

本盘侧重：A股/港股午后操作优先；含上午板块轮动雷达、A股半日、港股半日、逐只在册持仓精简卡片（上午表现/异动归因β还是α/多空分歧一句话/午后操作+价位）、下午关注要点。午间不做关注库分析；期权/VIX/IV/PCR 板块已移除，不写期权策略。

口头进度总结用 caveman 压缩风格（只压叙述，报告/证据/代码正常写）。新手通俗、决策权在用户、附免责、不承诺收益。
