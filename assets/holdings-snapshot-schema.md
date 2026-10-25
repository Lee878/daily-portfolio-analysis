# 持仓快照 JSON 契约

`scripts/holdings_update.py` 只认这一份结构。**读图（视觉）这一端可以由任何模型/人完成**，
只要产出的 JSON 符合本契约，脚本就能安全地写回 `config/holdings.md`。
这样把「截图长什么样」和「怎么安全写库」解耦——银河 / 盈立 / 蚂蚁 三套界面都能对接。

## 顶层字段

| 字段 | 必填 | 说明 |
|---|---|---|
| `market` | ✅ | `A股` / `基金` / `港股` / `美股`（必须与 holdings.md 的分节对应） |
| `positions` | ✅ | 该账户该市场的持仓数组（非空） |
| `account` | 建议 | 账户名，如「A股人民币账户」，写进变动记录 |
| `broker` | 建议 | 券商/平台，如「中国银河证券」 |
| `as_of` | 建议 | 截图时点，如 `2026-10-22 14:30` |
| `totals` | 可选 | 汇总（见下），提供则用于核对，不提供也不影响写表 |

```json
{
  "market": "A股",
  "account": "A股人民币账户",
  "broker": "中国银河证券",
  "as_of": "2026-10-22 14:30",
  "positions": [
    {
      "name": "紫金矿业",
      "code": "601899.SH",
      "qty": 1500,
      "cost": 34.913,
      "last": 29.920,
      "market_value": 44880.00,
      "pnl": -7489.54,
      "pnl_pct": -14.30
    }
  ]
}
```

## 单条持仓（A股 / 港股 / 美股）

| 字段 | 必填 | 说明 |
|---|---|---|
| `name` | ✅ | 名称 |
| `code` | ✅ | 代码，脚本会归一化为 `601899.SH` / `00700.HK` / `AAPL` |
| `qty` | ✅ | 持仓数量（正数），可写 `600` 或 `"600股"` |
| `cost` | 建议 | 成本价；缺了只影响成本判断，不影响写表 |
| `last` | 建议 | 现价；缺了市值无法交叉校验 |
| `market_value` | 可选 | 市值；**不填则由 `qty × last` 推算** |
| `pnl` | 可选 | 盈亏；**不填则由 `(last-cost) × qty` 推算** |
| `pnl_pct` | 可选 | 盈亏比例；**不填则由 `(last-cost)/cost` 推算** |

> 读图时**只保证 `name / code / qty / cost / last` 就够**，其余脚本自动推。
> 但如果截图里明明有市值/盈亏，也一并填上——脚本会用它做「数字有没有读错」的交叉校验。

## 单条持仓（基金）

基金只有三列，不要写 qty/cost：

```json
{ "name": "华安黄金ETF联接C（000217）", "amount": 17714.72, "pnl": -1751.86 }
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `name` | ✅ | 基金全名（含代码更佳，作为唯一键） |
| `amount` | ✅ | 持仓金额（正数） |
| `pnl` | 可选 | 持有收益 |

## 脚本会做的校验（校验不过＝拒绝写入）

- 名称非空、代码非空、数量 > 0
- **数量 × 现价 ≈ 市值**：偏差 > 3% 判为**阻断错误**（这是抓 OCR 把 6 看成 8 最有效的一条）
- **盈亏 ≈ (现价 − 成本) × 数量**、**盈亏比例 ≈ (现价−成本)/成本**：偏差大只**提醒**，不阻断
- 同一快照内代码不得重复
- 代码格式可疑（如 A股写成 `SH601899`）只提醒

## 写回行为

1. 先备份到 `config/.holdings-backup/holdings-<时间戳>.md`
2. 只重写 `## {market}持仓` 分节的持仓表；**其他分节、已清仓行、注释原样保留**
3. 更新文首 `> 最后更新：…`
4. 在「持仓变动更新记录」表末尾追加一行
5. **快照里没出现的持仓不删、不清仓**，只在预览里标「❓ 截图未包含」；
   要标清仓必须显式 `--mark-cleared <ticker>`

## 典型调用

```bash
# 预览（默认，不写）
python scripts/holdings_update.py --snapshot /tmp/snap.json

# 确认后写回
python scripts/holdings_update.py --snapshot /tmp/snap.json --apply

# 截图里少了某只、且你确认已卖出
python scripts/holdings_update.py --snapshot /tmp/snap.json --apply --mark-cleared 09988.HK

# 还原
python scripts/holdings_update.py --list-backups
python scripts/holdings_update.py --restore config/.holdings-backup/holdings-20261022-153000.md
```
