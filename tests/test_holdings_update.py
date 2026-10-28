# -*- coding: utf-8 -*-
"""holdings_update 的回归测试 —— 重点是「该拦的必须拦住」。"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import holdings_update as hu  # noqa: E402

A_MD = """# 持仓信息档案

> 最后更新：2026-01-01（初始）

## A股持仓（中国银河证券）

总资产：100,000.00 元 | 总市值：28,386.00 元

| 名称 | 代码 | 持仓数量 | 成本价 | 现价 | 市值(元) | 盈亏(元) | 盈亏比例 |
|---|---|---|---|---|---|---|---|
| 通富微电 | 002156.SZ | 600股 | 49.334 | 47.310 | 28,386.00 | -1,214.20 | -4.10% |
| ~~电网ETF~~ | 561380 | 已清仓 | - | - | - | - | 2026-10-13 卖出 |

## 持仓变动更新记录

| 日期 | 变动内容 | 变动后持仓 | 备注 |
|---|---|---|---|
| 2026-01-01 | 初始 | 如上 | - |
"""

FUND_MD = """# 持仓信息档案

> 最后更新：2026-01-01（初始）

## 基金持仓（蚂蚁财富）

| 基金名称 | 金额(元) | 持有收益 |
|---|---|---|
| 华安黄金ETF联接C（000217） | 17,714.72 | -1,751.86 |

## 持仓变动更新记录

| 日期 | 变动内容 | 变动后持仓 | 备注 |
|---|---|---|---|
| 2026-01-01 | 初始 | - | - |
"""


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="hu-"))
        self.h = self.tmp / "holdings.md"

    def write_holdings(self, text):
        self.h.write_text(text, encoding="utf-8")

    def snapfile(self, data):
        p = self.tmp / "snap.json"
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return str(p)

    def prepare(self, data):
        """load + derive + validate + diff 一步到位。"""
        snap = hu.load_snapshot(Path(self.snapfile(data)))
        for p in snap["positions"]:
            hu._derive(p, snap["market"])
        errors, warnings = hu.validate_snapshot(snap)
        md = self.h.read_text(encoding="utf-8")
        warnings += hu.check_cost_jumps(snap, md)
        d = hu.diff_snapshot(snap, md)
        return snap, errors, warnings, d


class ValidateTest(Base):
    def test_market_value_mismatch_is_blocking(self):
        """数量×现价 与 市值 严重不符 → 必须阻断（模拟 OCR 把数字读错）。"""
        self.write_holdings(A_MD)
        snap = {
            "market": "A股", "positions": [
                {"name": "通富微电", "code": "002156.SZ", "qty": 600,
                 "cost": 49.334, "last": 47.310, "market_value": 999999.0},
            ],
        }
        _, errors, _, _ = self.prepare(snap)
        self.assertTrue(any("市值对不上" in e for e in errors), errors)

    def test_correct_snapshot_has_no_errors(self):
        self.write_holdings(A_MD)
        snap = {
            "market": "A股", "positions": [
                {"name": "通富微电", "code": "002156.SZ", "qty": 600, "cost": 49.334, "last": 47.310},
            ],
        }
        _, errors, _, _ = self.prepare(snap)
        self.assertEqual(errors, [])

    def test_pnl_mismatch_warns_not_blocks(self):
        self.write_holdings(A_MD)
        snap = {
            "market": "A股", "positions": [
                {"name": "通富微电", "code": "002156.SZ", "qty": 600, "cost": 49.334,
                 "last": 47.310, "pnl": 50000.0},
            ],
        }
        _, errors, warnings, _ = self.prepare(snap)
        self.assertEqual(errors, [])
        self.assertTrue(any("盈亏对不上" in w for w in warnings), warnings)

    def test_duplicate_code_is_blocking(self):
        self.write_holdings(A_MD)
        snap = {"market": "A股", "positions": [
            {"name": "通富微电", "code": "002156.SZ", "qty": 100},
            {"name": "通富微电(重复)", "code": "002156.SZ", "qty": 100},
        ]}
        _, errors, _, _ = self.prepare(snap)
        self.assertTrue(any("代码重复" in e for e in errors), errors)

    def test_derives_market_value_and_pnl(self):
        self.write_holdings(A_MD)
        snap = {"market": "A股", "positions": [
            {"name": "通富微电", "code": "002156.SZ", "qty": 600, "cost": 49.334, "last": 47.310},
        ]}
        s, errors, _, _ = self.prepare(snap)
        p = s["positions"][0]
        self.assertAlmostEqual(p["market_value"], 600 * 47.310, places=2)
        self.assertAlmostEqual(p["pnl"], (47.310 - 49.334) * 600, places=2)
        self.assertEqual(errors, [])


class DiffTest(Base):
    def test_detects_quantity_change_and_new_position(self):
        self.write_holdings(A_MD)
        snap = {"market": "A股", "positions": [
            {"name": "通富微电", "code": "002156.SZ", "qty": 800, "cost": 49.334, "last": 47.310},
            {"name": "紫金矿业", "code": "601899.SH", "qty": 1500, "cost": 34.913, "last": 29.92},
        ]}
        _, errors, _, d = self.prepare(snap)
        self.assertEqual(errors, [])
        self.assertEqual([p["name"] for p in d["added"]], ["紫金矿业"])
        self.assertEqual([p["name"] for _, p, _, _ in d["qty"]], ["通富微电"])

    def test_missing_position_is_reported_not_cleared(self):
        self.write_holdings(A_MD)
        snap = {"market": "A股", "positions": [
            {"name": "紫金矿业", "code": "601899.SH", "qty": 1500, "cost": 34.913, "last": 29.92},
        ]}
        _, _, _, d = self.prepare(snap)
        self.assertIn("002156.SZ", [h["ticker"] for h in d["missing"]])


class ApplyTest(Base):
    def test_apply_updates_row_backs_up_and_is_idempotent(self):
        self.write_holdings(A_MD)
        sf = self.snapfile({"market": "A股", "account": "A股人民币账户", "as_of": "2026-01-02 09:30",
                            "positions": [
                                {"name": "通富微电", "code": "002156.SZ", "qty": 800,
                                 "cost": 49.334, "last": 47.310}]})
        rc = hu.main(["--snapshot", sf, "--holdings", str(self.h), "--apply"])
        self.assertEqual(rc, 0)
        txt = self.h.read_text(encoding="utf-8")
        self.assertIn("800股", txt)
        backup_dir = self.h.parent / ".holdings-backup"
        self.assertTrue(any(backup_dir.glob("holdings-*.md")))

        # 再跑一次同样的快照 → 无变动
        rc2 = hu.main(["--snapshot", sf, "--holdings", str(self.h), "--apply"])
        self.assertEqual(rc2, 0)
        self.assertEqual(txt, self.h.read_text(encoding="utf-8"))

    def test_closed_row_preserved_and_record_appended(self):
        self.write_holdings(A_MD)
        sf = self.snapfile({"market": "A股", "account": "银河", "positions": [
            {"name": "紫金矿业", "code": "601899.SH", "qty": 1500, "cost": 34.913, "last": 29.92}]})
        hu.main(["--snapshot", sf, "--holdings", str(self.h), "--apply"])
        txt = self.h.read_text(encoding="utf-8")
        self.assertIn("~~电网ETF~~", txt)          # 已清仓行保留
        self.assertIn("通富微电", txt)              # 缺失的持仓不删
        self.assertIn("持仓变动更新记录", txt)
        # 变动记录表应新增一行（含日期）
        self.assertIn("新增 紫金矿业", txt)

    def test_mark_cleared_marks_row(self):
        self.write_holdings(A_MD)
        sf = self.snapfile({"market": "A股", "positions": [
            {"name": "紫金矿业", "code": "601899.SH", "qty": 1500, "cost": 34.913, "last": 29.92}]})
        hu.main(["--snapshot", sf, "--holdings", str(self.h), "--apply", "--mark-cleared", "002156.SZ"])
        txt = self.h.read_text(encoding="utf-8")
        self.assertTrue("~~通富微电~~" in txt or "已清仓" in txt)

    def test_fund_amount_change_detected_and_written(self):
        self.write_holdings(FUND_MD)
        data = {"market": "基金", "positions": [
            {"name": "华安黄金ETF联接C（000217）", "amount": 18000.0, "pnl": -1500.0}]}
        sf = self.snapfile(data)
        _, errors, _, d = self.prepare(data)
        self.assertEqual(errors, [])
        self.assertEqual(len(d["amount"]), 1)
        hu.main(["--snapshot", sf, "--holdings", str(self.h), "--apply"])
        txt = self.h.read_text(encoding="utf-8")
        self.assertIn("18,000.00", txt)

    def test_blocking_error_prevents_write(self):
        self.write_holdings(A_MD)
        sf = self.snapfile({"market": "A股", "positions": [
            {"name": "通富微电", "code": "002156.SZ", "qty": 600,
             "cost": 49.334, "last": 47.310, "market_value": 999999.0}]})
        before = self.h.read_text(encoding="utf-8")
        rc = hu.main(["--snapshot", sf, "--holdings", str(self.h), "--apply"])
        self.assertEqual(rc, 1)
        self.assertEqual(before, self.h.read_text(encoding="utf-8"))


HK_MD = """# 持仓信息档案

> 最后更新：2026-01-01（初始）

## 账户总览

| 账户 | 券商/平台 | 总资产/净资产 | 总盈亏 | 仓位 |
|---|---|---|---|---|
| A股人民币账户 | 银河 | 100,000.00 元 | -1,000.00 元 | 60% |
| 盈立证券（港股） | 盈立证券 | 85,722.68 港币 | -39,873.60 港币 | - |

## 港股持仓（盈立证券 · 港股融资账户）

净资产：85,722.68 港币 | 持仓盈亏：-39,873.60 港币 | 今日盈亏：+540.00

| 名称 | 代码 | 持仓数量 | 成本价 | 现价 | 市值(港币) | 盈亏(港币) | 盈亏比例 |
|---|---|---|---|---|---|---|---|
| XL二南方海力士 | 07709.HK | 600股 | 59.495 | 24.000 | 14,400.00 | -21,297.00 | -59.67% |

## 持仓变动更新记录

| 日期 | 变动内容 | 变动后持仓 | 备注 |
|---|---|---|---|
| 2026-01-01 | 初始 | 如上 | - |
"""


class TotalsSyncTest(Base):
    def test_totals_syncs_overview_and_section_summary(self):
        """totals 应同时更新账户总览行与分节净资产/盈亏行。"""
        self.write_holdings(HK_MD)
        data = {
            "market": "港股", "account": "盈立证券（港股）", "as_of": "2026-10-28",
            "totals": {"net_assets": 84200.95, "pnl": -40974.80,
                       "today_pnl": 2503.00, "currency": "港币"},
            "positions": [{"name": "XL二南方海力士", "code": "07709.HK",
                           "qty": 600, "cost": 59.495, "last": 24.0}],
        }
        sf = self.snapfile(data)
        rc = hu.main(["--snapshot", sf, "--holdings", str(self.h), "--apply"])
        self.assertEqual(rc, 0)
        txt = self.h.read_text(encoding="utf-8")
        self.assertIn("84,200.95 港币", txt)
        self.assertIn("净资产：84,200.95 港币", txt)
        self.assertIn("持仓盈亏：-40,974.80 港币", txt)
        self.assertIn("今日盈亏：+2,503.00", txt)
        self.assertIn("-1,000.00 元", txt)          # A股行不得被误改

    def test_totals_syncs_a_share_summary(self):
        self.write_holdings(A_MD)
        data = {"market": "A股", "account": "A股人民币账户",
                "totals": {"net_assets": 101234.56, "pnl": -234.56, "currency": "元"},
                "positions": [{"name": "通富微电", "code": "002156.SZ",
                               "qty": 600, "cost": 49.334, "last": 47.310}]}
        sf = self.snapfile(data)
        hu.main(["--snapshot", sf, "--holdings", str(self.h), "--apply"])
        txt = self.h.read_text(encoding="utf-8")
        self.assertIn("总资产：101,234.56 元", txt)


class CostJumpTest(Base):
    def test_cost_jump_warns(self):
        """成本从 59.495 跳到 71.327（+19.9%）应告警，但不阻断。"""
        self.write_holdings(HK_MD)
        data = {"market": "港股", "positions": [
            {"name": "XL二南方海力士", "code": "07709.HK",
             "qty": 600, "cost": 71.327, "last": 24.0}]}
        _, errors, warnings, _ = self.prepare(data)
        self.assertEqual(errors, [])
        self.assertTrue(any("成本跳变" in w for w in warnings), warnings)

    def test_small_cost_change_no_warn(self):
        self.write_holdings(HK_MD)
        data = {"market": "港股", "positions": [
            {"name": "XL二南方海力士", "code": "07709.HK",
             "qty": 600, "cost": 62.0, "last": 24.0}]}
        _, errors, warnings, _ = self.prepare(data)
        self.assertEqual(errors, [])
        self.assertFalse(any("成本跳变" in w for w in warnings), warnings)


class OrdersTest(Base):
    def test_orders_appear_in_change_record(self):
        self.write_holdings(HK_MD)
        data = {"market": "港股", "account": "盈立证券（港股）",
                "orders": [{"side": "sell", "name": "XL二南方海力士",
                            "code": "07709.HK", "qty": 200, "price": 24.0,
                            "status": "全部成交"}],
                "positions": [{"name": "XL二南方海力士", "code": "07709.HK",
                               "qty": 600, "cost": 71.327, "last": 24.0}]}
        sf = self.snapfile(data)
        hu.main(["--snapshot", sf, "--holdings", str(self.h), "--apply"])
        txt = self.h.read_text(encoding="utf-8")
        self.assertIn("200股@24.0", txt)


if __name__ == "__main__":
    unittest.main()
