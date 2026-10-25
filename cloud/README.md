# 云端部署指南（让你的电脑不用一直开着）

本目录是 `daily-portfolio-analysis` 的**云端运行套件**。把三个定时任务从「本机」搬到
WorkBuddy 的**云端沙箱**后，电脑关机、离线也能照常出报告，报告通过 Bark 推到你手机。

> 前提：你已在 WorkBuddy 客户端里见过「云端定时任务」（定时任务 → 新建 → 来源选「云端」）。
> 若没有该选项，说明客户端版本不支持，需要先升级。

---

## 一、套件里有什么

| 文件 | 作用 |
|---|---|
| `prompts/cloud-pre.md` | 盘前（08:30）云端版 prompt |
| `prompts/cloud-noon.md` | 盘中（12:00）云端版 prompt |
| `prompts/cloud-post.md` | 盘后（20:00）云端版 prompt |
| `bootstrap.sh` | 每次任务开头执行：拉仓库 + 注入隐私配置 + 门禁自检 |
| `SECRETS.md` | 要在云端填的密文（持仓/Bark/COS）说明 |
| `build_prompts.py` | 从本机 prompt 模板重新生成云端版（维护用，不用管） |

三个 prompt 已把 `{{REPO_DIR}}` 换成 `/workspace/dpa`、`python` 换成 `python3`，**不含任何隐私**。

---

## 二、一次性配置（只做一次）

### 1. 建云端工作区并挂载公开仓
在 CloudAgent 新建工作区时：
- **Git 仓库**：填 `https://github.com/Lee878/daily-portfolio-analysis.git`，分支 `main`
- **初始化命令**（init command）：填 `bash /workspace/dpa/cloud/bootstrap.sh`
  - 作用：每次会话/任务启动自动拉最新代码 + 注入你的配置 + 跑自检
- 若你的 CloudAgent 不支持「挂载仓库 + 初始化命令」，则跳过这步，改用下方「方式二」。

> 不想挂仓库也行（方式二）：三个定时任务的 prompt 开头都先写一句
> `先执行 bash /workspace/dpa/cloud/bootstrap.sh，再按以下流程…`，bootstrap 会自己 clone。

### 2. 填 secrets（关键，见 SECRETS.md）
在 CloudAgent 的 secrets 设置里填：
- `HOLDINGS_MD` = 你本机 `config/holdings.md` 全文
- `NOTIFY_JSON` = 你本机 `config/notify.json` 全文（含 Bark key）
- `DELIVERY_JSON` = 你本机 `config/delivery.json` 全文（含 COS）

三个都填好，云端才有你的真实持仓和推送通道。

### 3. 连接 NeoData MCP
云端任务靠 **NeoData MCP** 取行情/估值/财务/资金。确认 CloudAgent 已连接该连接器
（连接器状态里 NeoData 显示 `connected`）。没连，报告会缺数据。

---

## 三、建三个云端定时任务

在 WorkBuddy 客户端：**定时任务 → 新建 → 来源选「云端」**，建三个：

| 任务 | 时间（交易日） | 用哪份 prompt |
|---|---|---|
| 盘前 | 周一~周五 08:30 | `cloud/prompts/cloud-pre.md` 全文 |
| 盘中 | 周一~周五 12:00 | `cloud/prompts/cloud-noon.md` 全文 |
| 盘后 | 周一~周五 20:00 | `cloud/prompts/cloud-post.md` 全文 |

**每个任务的 prompt 填写方式（二选一）：**
- 若工作区已挂仓库 + 初始化命令 → 直接把对应 `cloud-*.md` 全文贴进 prompt。
- 若没挂仓库 → prompt 第一行先写 `先执行 bash /workspace/dpa/cloud/bootstrap.sh，再按以下流程：`，
  然后贴 `cloud-*.md` 全文。

> 注意：云端定时任务**不支持推送到企业微信**；报告走 Bark（你手机装 Bark App）即可。

---

## 四、验证（第一次务必跑）

建好后，对每个任务点「立即运行」一次，重点看日志里有没有：
- `[bootstrap] ✅ 已写入 config/holdings.md (from secret HOLDINGS_MD)` —— 说明持仓注入成功
- `python3 .../scripts/release.py doctor` 全绿 —— 环境 OK
- 任务结束手机收到 Bark 推送、点开能看到报告 HTML

任一不对，先查：secrets 是否填全、`NOTIFY_JSON` 里的 Bark key 是否你自己的、NeoData 是否 connected。

---

## 五、持仓怎么更新

见 `SECRETS.md` 的「更新持仓」。简言之：改 `HOLDINGS_MD` 那段文字 = 改持仓，
下次任务自动生效。

---

## 六、持久化探针（排查用）

若怀疑云端沙箱「每次任务都是全新环境、不保留 /workspace 文件」，建一个探测任务，
prompt 贴：

```
在云端沙箱执行并原样输出：
echo probe-$(date +%s) > /workspace/_probe.txt; cat /workspace/_probe.txt
```

再建第二个立即运行：`cat /workspace/_probe.txt`。
- 能读到第一次写的数字 → 文件跨任务保留，配置稳。
- 读不到 → 每次新建，bootstrap 已做幂等处理（每次重拉+重注入），功能不受影响，
  只是稍慢；若用「方法 C 发截图」，需按 SECRETS.md 说明加持久化兜底。

---

## 七、与本机部署的关系

- 云端部署**不影响**你本机已有的定时任务。若想彻底关机，把本机三个任务删掉/停用即可。
- 公开仓库 `cloud/` 目录**不含任何隐私**；你的持仓和 key 只存在于云端 secrets 里。
