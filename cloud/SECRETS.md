# CloudAgent Secrets 配置说明

云端沙箱**没有你的电脑文件**，所以持仓、Bark key、COS 配置这三样隐私数据，
必须通过在 CloudAgent 里设置 **secrets（密文）** 注入。本文件说明要设哪些。

> 安全红线：这些 secret **只存在云端 Agent 的密文里**，绝不会进公开仓库、不会被打印到日志。
> `git` 传输走 HTTPS，token 仅用于 clone 私有仓，用后即弃。

---

## 已选方案：方法 A（私有仓库存持仓）✅

你的持仓已放在私有仓库 **`Lee878/dpa-holdings`**（仅你自己可见，公开仓里不存在）。
云端任务每次开头自动从那里拉最新的 `holdings.md`，改持仓只改这一个私有仓即可。

### 持仓相关（方法 A，必填）

| Secret 名 | 内容 |
|---|---|
| `HOLDINGS_REPO` | `github.com/Lee878/dpa-holdings.git` |
| `HOLDINGS_TOKEN` | 有该私有仓**读取权限**的 GitHub token（见下方「token 怎么拿」） |

设好这两个，bootstrap 每次任务开头会 `git clone` 私有仓并覆盖 `config/holdings.md`。

### 推送通道（Bark / COS，必填）

| Secret 名 | 内容 | 怎么拿到 |
|---|---|---|
| `NOTIFY_JSON` | 你本机 `config/notify.json` 的**全文**（含 Bark key） | 打开本机 `D:\Workplace\stock\config\notify.json`，整份复制 |
| `DELIVERY_JSON` | 你本机 `config/delivery.json` 的**全文**（含 COS 配置） | 同上，复制 `config/delivery.json` |

> 这两个**不要**进任何仓库（含私有仓），只放在云端密文里。

---

## `HOLDINGS_TOKEN` 怎么拿（二选一）

**方式 1（推荐，最安全）：建一个细粒度只读 token**
1. GitHub → 右上角头像 → Settings → Developer settings → Fine-grained tokens → Generate new token
2. Token name 随便填（如 `dpa-cloud-read`）
3. Resource owner 选 `Lee878`
4. Repository access → **Only select repositories** → 勾 `dpa-holdings`
5. Permissions → Repository permissions → **Contents → Read-only**
6. Generate → 复制那串 `github_pat_...`，粘进 CloudAgent 的 `HOLDINGS_TOKEN`

**方式 2（最快，但权限较宽）：复用你现有的经典 PAT**
- 直接把你生成过的 `ghp_...` 那个 PAT 填进 `HOLDINGS_TOKEN` 也能用，
  但它能读写你名下所有仓库。个人自用可接受，若介意就用方式 1。

---

## 更新持仓（方法 A 的后续怎么改）

`Lee878/dpa-holdings` 私有仓里的 `holdings.md` 就是持仓的「唯一真相来源」。要改持仓：

1. 在浏览器打开 `https://github.com/Lee878/dpa-holdings`
2. 点 `holdings.md` → 右上角铅笔图标 → 改内容（或直接本地改完 push）
3. 提交（Commit）。下一次云端任务跑起来会自动拉到新持仓，**不用动任何 secret**。

> 懒得自己改？直接跟我说「我买了/卖了 X」，我帮你改好本机 `config/holdings.md`，
> 再把它同步（push）到这个私有仓即可。

---

## 其他可选方法（当前未启用，备用）

### 方法 B（secret 直接存文本）
不设 `HOLDINGS_REPO`/`HOLDINGS_TOKEN`，改设 `HOLDINGS_MD` = 本机 `config/holdings.md` 全文。
bootstrap 会把它写成云端文件。更新方式见上「更新持仓」思路——改密文里那段文字。

### 方法 C（发截图 AI 就地更新）
在任务里发持仓截图，AI 读图后用 `scripts/holdings_update.py` 写回 `config/holdings.md`。
**注意**：若云端沙箱每次任务都是全新环境（不保留 /workspace 文件），
截图改的持仓下一次会丢失，必须配方法 A 作持久化兜底，或确认沙箱保留文件。
