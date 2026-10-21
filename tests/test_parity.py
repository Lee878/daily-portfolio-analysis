# -*- coding: utf-8 -*-
"""跨模块口径一致性测试。

背景：`holdings.md` 被两套独立实现解析——`fetch_data.parse_holdings`（取证侧）
与 `gate_check.parse_holdings`（门禁侧）。两边一旦对同一行得出不同结论，
就会出现「取证认为持有、门禁认为已清仓」这类无解问题，且现象是
覆盖率莫名下降，极难定位。

这里不强行合并两份实现（风格差异大、合并风险高于收益），而是用同一份
样本同时喂给两边，**断言结论一致**。任何一边改动导致漂移，这里立刻红。
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import fetch_data as fd  # noqa: E402
import gate_check as gc  # noqa: E402

SAMPLE = """# 持仓明细

## 账户总览

| 账户 | 总资产 |
|---|---|
| A股 | 100000 |

## A股持仓（券商）

| 名称 | 代码 | 数量 | 成本 | 现价 | 市值 |
|---|---|---|---|---|---|
| 紫金矿业 | 601899 | 1,000 | 20.00 | 28.87 | 28,870 |
| 鼎龙股份 | 300054 | 500 | 30.00 | 58.20 | 29,100 |
| ~~清仓股~~ | 600000 | 0 | 8.00 | 9.00 | 0 |

## 基金持仓（场外）

| 基金名称 | 金额 | 收益 |
|---|---|---|
| 华安黄金ETF联接C（000217） | 5000 | 120 |
| 华夏恒生科技ETF联接(QDII)C（013403，定投） | 3000 | -80 |

## 港股持仓

| 名称 | 代码 | 数量 | 成本 | 现价 | 市值 |
|---|---|---|---|---|---|
| 腾讯控股 | 00700 | 100 | 400.00 | 393.80 | 39,380 |

## 美股持仓

| 名称 | 代码 | 数量 | 成本 | 现价 | 市值 |
|---|---|---|---|---|---|
| 英伟达 | NVDA | 10 | 180.00 | 221.52 | 2,215 |
"""


class TestParseParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a = fd.parse_holdings(SAMPLE)
        cls.b = gc.parse_holdings(SAMPLE)

    def test_same_count(self):
        self.assertEqual(len(self.a), len(self.b),
                         "两套解析器得出的持仓数量必须一致")

    def test_same_ticker_and_market(self):
        ka = sorted((h["market"], str(h["ticker"])) for h in self.a)
        kb = sorted((h["market"], str(h["ticker"])) for h in self.b)
        self.assertEqual(ka, kb, "同一标的在两套解析器下必须得到相同 (market, ticker)")

    def test_closed_row_excluded_on_both(self):
        names = [h["name"] for h in self.a] + [h["name"] for h in self.b]
        self.assertFalse(any("清仓股" in n for n in names),
                         "删除线标记的已清仓标的不得进入持仓")

    def test_fund_rows_kept(self):
        # 基金表只有 3 列，旧版 fetch 曾因「要求 ≥4 列」整段漏掉，
        # 导致门禁「缺少证据文件」必 FAIL
        funds_a = [h for h in self.a if h["market"] == "基金"]
        funds_b = [h for h in self.b if h["market"] == "基金"]
        self.assertEqual(len(funds_a), 2)
        self.assertEqual(len(funds_b), 2)

    def test_markets_covered(self):
        markets = {h["market"] for h in self.a}
        self.assertEqual(markets, {"A股", "基金", "港股", "美股"})


class TestTickerNormalizeParity(unittest.TestCase):
    CASES = [
        ("601899", "A股"), ("300054", "A股"), ("688981", "A股"),
        ("00700", "港股"), ("700", "港股"),
        ("NVDA", "美股"), ("BRK.B", "美股"),
    ]

    def test_same_normalization(self):
        for code, market in self.CASES:
            with self.subTest(code=code, market=market):
                self.assertEqual(fd.normalize_ticker(code, market),
                                 gc.normalize_ticker(code, market),
                                 f"{code}/{market} 归一化结果不一致")


class TestSafeNameParity(unittest.TestCase):
    def test_same_output(self):
        for ticker in ["601899.SH", "帮你投 | 全球精选100", "00700.HK", "A/B:C"]:
            with self.subTest(ticker=ticker):
                self.assertEqual(fd.safe_name(ticker), gc.safe_name(ticker))


if __name__ == "__main__":
    unittest.main()
