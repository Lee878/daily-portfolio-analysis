#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""debate_input 净化的回归测试。

净化本身是「防持仓锚定」的唯一机械防线，一旦静默失效，
辩论阶段会重新看到 holding.cost，结论回偏而没有任何报错 —— 所以这里重点测「不泄漏」。
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import debate_input as di  # noqa: E402

FULL = {
    "schema_version": "1",
    "report_date": "2026-10-22",
    "session": "pre",
    "ticker": "002156.SZ",
    "name": "通富微电",
    "market": "A",
    "instrument": "STOCK",
    "account": "A股持仓（中国银河证券）",
    "holding": {"quantity": 1000, "cost": 52.3, "last_close_in_holdings": 47.31},
    "planned": {"technical": ["price_last"]},
    "data_points": [{"id": "dp-001", "key": "price_last", "value": 47.67}],
    "news": [{"id": "nw-001", "title": "AMD 上调指引"}],
    "chain_notes": [{"id": "ch-001", "note": "强化期"}],
    "gaps": ["main_net_inflow 未取到"],
}


class SanitizeTests(unittest.TestCase):
    def test_strips_holding_and_account(self):
        clean = di.sanitize(FULL)
        for k in ("holding", "account", "planned"):
            self.assertNotIn(k, clean, f"净化后仍含 {k}")

    def test_keeps_evidence_intact(self):
        """数据本体一个不能少、一个不能改 —— 净化只删字段，不动数字。"""
        clean = di.sanitize(FULL)
        self.assertEqual(clean["data_points"], FULL["data_points"])
        self.assertEqual(clean["news"], FULL["news"])
        self.assertEqual(clean["chain_notes"], FULL["chain_notes"])
        self.assertEqual(clean["gaps"], FULL["gaps"])

    def test_no_leak_after_sanitize(self):
        self.assertEqual(di.find_leaks(di.sanitize(FULL)), [])

    def test_find_leaks_detects_nested(self):
        """嵌套在列表里的 cost 也必须被抓到——只看顶层是典型的假绿。"""
        leaky = {"data_points": [{"id": "dp-1", "meta": {"cost": 1}}]}
        self.assertTrue(di.find_leaks(leaky))

    def test_find_leaks_detects_chinese_keys(self):
        self.assertTrue(di.find_leaks({"data_points": [{"成本": 52.3}]}))

    def test_sanitize_file_then_verify_dir(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            src = d / "ev.json"
            src.write_text(json.dumps(FULL, ensure_ascii=False), encoding="utf-8")
            out = d / "out"
            dst = di.sanitize_file(src, out)
            self.assertTrue(dst.exists())
            self.assertEqual(di.verify_dir(out), 0)

    def test_verify_dir_catches_leak(self):
        """把带 holding 的文件冒充成净化产物，verify 必须拦住。"""
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "bad.json").write_text(json.dumps(FULL, ensure_ascii=False),
                                        encoding="utf-8")
            self.assertEqual(di.verify_dir(d), 1)

    def test_idempotent(self):
        once = di.sanitize(FULL)
        twice = di.sanitize(once)
        self.assertEqual(once, twice)


if __name__ == "__main__":
    unittest.main(verbosity=2)
