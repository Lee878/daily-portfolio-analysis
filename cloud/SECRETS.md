# CloudAgent Secrets 配置说明

云端沙箱**没有你的电脑文件**，所以持仓、Bark key、COS 配置这三样隐私数据，
必须通过在 CloudAgent 里设置 **secrets（密文）** 注入。本文件说明要设哪些。

> 安全红线：这些 secret **只存在云端 Agent 的密文里**，绝不会进公开仓库、不会被打印到日志。
> `git` 传输走 HTTPS，token 仅用于 clone 私有仓，用后即弃。

---

## 必填（方法 B：secret 直接存文本）

| Secret 名 | 内容 | 怎么拿到 |
|---|---|---|
| `HOLDINGS_MD` | 你本机 `config/holdings.md` 的**全文** | 打开本机 `D:\Workplace\stock\config\holdings.md`，整份复制 |
| `NOTIFY_JSON` | 你本机 `config/notify.json` 的**全文**（含 Bark key） | 同上，复制 `config/notify.json` |
| `DELIVERY_JSON` | 你本机 `config/delivery.json` 的**全文**（含 COS） | 同上，复制 `config/delivery.json` |

设好这三个，bootstrap 每次任务开头会自动把它们写成云端工作区的对应文件。

---

## 可选（方法 A：私有仓库存持仓）

如果你不想把持仓全文贴在 secret 里，可以改用私有仓库：

| Secret 名 | 内容 |
|---|---|
| `HOLDINGS_REPO` | 私有仓地址，如 `github.com/yourname/private-holdings.git` |
| `HOLDINGS_TOKEN` | 有该私有仓读权限的 GitHub PAT |

设了这两个，bootstrap 会**优先**从私有仓拉 `holdings.md` 覆盖 secret 里的版本。
改持仓只改私有仓那一个文件即可，不用动 secret。

---

## 更新持仓（方法 B 的后续怎么改）

`HOLDINGS_MD` 就是持仓的「唯一真相来源」。要改持仓：

1. 打开 CloudAgent 里这个 Agent 的 secrets 设置；
2. 把 `HOLDINGS_MD` 的内容替换成新的 `config/holdings.md` 全文；
3. 保存。下一次任务跑起来就用新持仓了。

> 懒得自己改？直接跟我说「我买了/卖了 X」，我帮你改好本机文件，
> 你把那段新文字贴进 `HOLDINGS_MD` 即可。

---

## 方法 C（发截图 AI 就地更新）说明

如果你想像「爸的方案」一样发截图让 AI 改持仓：
- 在任务里直接发持仓截图，AI 读图后用 `scripts/holdings_update.py` 写回 `config/holdings.md`。
- **注意**：若云端沙箱每次任务都是全新环境（不保留 /workspace 文件），
  截图改的持仓下一次会丢失。此时必须配合方法 A 或 B 作持久化兜底，
  或确认沙箱在多次任务间保留文件（见 README 的「持久化探针」）。
