# -*- coding: utf-8 -*-
"""derive_indicators 的回归测试。

这三个指标（atr14 / range_52w_pct / volume_ratio）不在 MCP 里，只能自算。
算错的后果是止损位和仓位建议跟着错，而报告门只校验"有没有值"、不校验
"值对不对"，所以必须靠这里的确定性用例兜住。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import derive_indicators as di  # noqa: E402


def _bars(n=25, start=101.0, step=1.0):
    """构造 n 根单边上涨的 K 线：第 i 根 close = start + i*step。"""
    out = []
    for i in range(n):
        close = start + i * step
        out.append({
            "trade_date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}",
            "open": close - 0.5,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1000 + i * 100,
            "pct_change": 1.0,
        })
    return out


class TestExtract(unittest.TestCase):
    def test_drops_not_open_rows(self):
        raw = [{"trade_date": "2026-10-22", "open": "未开盘", "high": "-",
                "low": "-", "close": "-", "volume": "-"}] + _bars(5)
        self.assertEqual(len(di._extract_bars(raw)), 5)

    def test_drops_ellipsis_marker(self):
        """MCP 截断时插入的"省略中间历史行情"行不能当 K 线。"""
        raw = [{"trade_date": "2026-09-01 ~ 2026-09-12",
                "open": "省略中间历史行情，不包含任何具体数值，禁止根据该标记推断、补全或参与计算",
                "high": "-", "low": "-", "close": "-", "volume": "-"}] + _bars(4)
        self.assertEqual(len(di._extract_bars(raw)), 4)

    def test_parses_mcp_envelope(self):
        payload = {"status": "success",
                   "result": [{"code": "601899.SH", "kline_list": _bars(3)}]}
        bars = di._extract_bars(payload)
        self.assertEqual(len(bars), 3)
        self.assertEqual(bars[-1]["close"], 103.0)

    def test_sorts_ascending(self):
        """MCP 返回新→旧，必须翻正，否则 ATR/均线全错。"""
        raw = list(reversed(_bars(4)))
        bars = di._extract_bars(raw)
        self.assertLess(bars[0]["trade_date"], bars[-1]["trade_date"])

    def test_merge_dedupes(self):
        a = di._extract_bars(_bars(15))
        b = di._extract_bars(_bars(25)[10:])
        self.assertEqual(len(di._merge([a, b])), 25)

    def test_rejects_non_kline(self):
        with self.assertRaises(ValueError):
            di._extract_bars({"foo": "bar"})


class TestDerive(unittest.TestCase):
    def test_ma_insufficient_returns_none(self):
        got = di.derive(_bars(25))
        self.assertIsNotNone(got["ma5"])
        self.assertIsNotNone(got["ma20"])
        self.assertIsNone(got["ma60"], "25 根 K 线不应算出 MA60")

    def test_ma_values(self):
        got = di.derive(_bars(6))  # close = 101..106
        self.assertAlmostEqual(got["ma5"], (102 + 103 + 104 + 105 + 106) / 5, places=4)
        self.assertEqual(got["price_last"], 106.0)

    def test_range_52w(self):
        # 首根 low=100，末根 high=126，收 125 → (125-100)/(126-100)
        got = di.derive(_bars(25))
        self.assertAlmostEqual(got["range_52w_pct"],
                               round((125 - 100) / (126 - 100) * 100, 2), places=2)

    def test_range_notes_when_short(self):
        got = di.derive(_bars(25))
        self.assertTrue(any("非完整 52 周" in n or "<250" in n for n in got["notes"]))

    def test_volume_ratio(self):
        # 末根量 3400，前 5 根 2900..3300 均值 3100
        got = di.derive(_bars(25))
        self.assertAlmostEqual(got["volume_ratio"], round(3400 / 3100, 3), places=3)

    def test_atr_positive(self):
        got = di.derive(_bars(25))
        self.assertGreater(got["atr14"], 0)
        # 每根 TR = max(2, |high-prev_close|=2, |low-prev_close|=0) = 2
        self.assertAlmostEqual(got["atr14"], 2.0, places=4)

    def test_atr_needs_period_plus_one(self):
        self.assertIsNone(di.derive(_bars(14))["atr14"])

    def test_all_missing_when_too_short(self):
        got = di.derive(_bars(2))
        self.assertIsNone(got["atr14"])
        self.assertIsNone(got["volume_ratio"])
        self.assertIsNone(got["ma5"])

    def test_no_fake_numbers(self):
        """算不出的字段必须是 None，不能是 0（0 会被门禁当成有效数值）。"""
        got = di.derive(_bars(2))
        for k in ("ma5", "ma20", "ma60", "atr14", "volume_ratio"):
            self.assertIsNone(got[k], f"{k} 算不出时必须是 None 而不是 0")


if __name__ == "__main__":
    unittest.main()
