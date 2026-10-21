#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
门禁与取证脚本的回归测试。

运行：
  cd scripts
  python -m unittest tests.test_gate -v
  或：python tests/test_gate.py
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import fetch_data as fd  # noqa: E402
import gate_check as gc  # noqa: E402

HOLDINGS_MD = """# 持仓档案
## A股持仓
| 名称 | 代码 | 持仓数量 | 成本价 | 现价 | 市值(元) | 盈亏(元) | 盈亏比例 |
|---|---|---|---|---|---|---|---|
| 紫金矿业 | 601899 | 1000 | 28.5 | 31.2 | 31200 | 2700 | 9.5% |

## 基金持仓
| 基金名称 | 金额(元) | 昨日收益 | 持有收益 |
|---|---|---|---|
| 某混合基金 | 50000 | 12 | 3000 |

## 港股持仓
| 名称 | 代码 | 持仓数量 | 成本价 | 现价 | 市值(港币) | 盈亏(港币) | 盈亏比例 |
|---|---|---|---|---|---|---|---|
| 腾讯控股 | 00700 | 200 | 320 | 380 | 76000 | 12000 | 18.8% |

## 美股持仓
| 名称 | 代码 | 持仓数量 | 成本价 | 现价 | 市值(美元) | 盈亏(美元) | 盈亏比例 |
|---|---|---|---|---|---|---|---|
| 谷歌 | GOOG | 100 | 140 | 170 | 17000 | 3000 | 21.4% |
"""


# 各字段的合理（且彼此不同）测试值，避免用 1.0 占位被真实性门禁拦截
TEST_VALUES = {
    "price_last": 31.2, "day_change_pct": 0.8, "ma5": 30.9, "ma20": 30.2,
    "ma60": 28.6, "range_52w_pct": 62.0, "atr14": 0.9, "volume_ratio": 1.3,
    "pe_ttm": 18.0, "pb": 2.6, "market_cap": 2400.0, "roe": 16.0,
    "revenue_growth_yoy": 12.0, "profit_growth_yoy": 15.0,
    "main_net_inflow": 3.2, "north_south_flow": 5.0,
    "nav_latest": 1.2, "nav_change_pct": 0.3, "nav_position_pct_1y": 40.0,
    "fund_scale_change": 60.0,
}
_SENT = object()


def make_stock_evidence(ticker, name, market, session="pre",
                        price_ok=True, news_ok=True, chain_ok=True,
                        gaps_honest=True, p4_only=False):
    """构造一份（模拟 agent 补证完成后的）股票证据文件内容。"""
    planned = fd.planned_for(market if market != "macro" else "A股", session)
    points, idx = [], 0

    def add(dim, field, status="verified", level="P3", value=_SENT):
        nonlocal idx
        if value is _SENT:
            value = TEST_VALUES.get(field, 1.0)
        idx += 1
        points.append({"id": f"dp-{idx:03d}", "dimension": dim, "field": field,
                       "label": fd.FIELD_LABELS.get(field, field), "value": value,
                       "unit": "", "as_of": "2026-09-20", "source": "test-source",
                       "source_url": "http://example.com/detail/123456",
                       "evidence_level": level,
                       "fetched_by": "script", "status": status})

    for dim, fields in planned.items():
        if dim in ("news", "chain"):
            continue
        for f in fields:
            if f in ("price_last", "day_change_pct") and not price_ok:
                add(dim, f, status="missing", value=None)
            elif f in ("roe", "revenue_growth_yoy", "profit_growth_yoy",
                       "north_south_flow"):
                add(dim, f, status="missing", value=None)  # 模拟财报类未取到
            else:
                add(dim, f)

    if market == "美股":
        # fetch_data 对美股把 flow 计划换成 put_call_or_inst，夹具同步
        add("flow", "put_call_or_inst", value=1.1)

    news = []
    if news_ok:
        news.append({"id": "nw-001", "headline": "公司发布最新季度财报",
                     "url": "http://example.com/detail/123456",
                     "source": "交易所公告", "published_at": "2026-09-19",
                     "evidence_level": "P1", "impact": "bullish",
                     "summary": "营收增长", "status": "verified"})
        if session != "noon":
            news.append({"id": "nw-002", "headline": "机构提示估值回调压力",
                         "url": "https://reuters.com/article/789012",
                         "source": "财新", "published_at": "2026-09-19",
                         "evidence_level": "P2", "impact": "bearish",
                         "summary": "行业景气但估值偏高，机构提示风险",
                         "status": "verified"})
    elif p4_only:
        news.append({"id": "nw-001", "headline": "网传未证实的市场消息",
                     "url": "http://example.com/rumor/345678",
                     "source": "雪球用户", "published_at": "", "evidence_level": "P4",
                     "impact": "bullish", "summary": "传闻", "status": "verified"})

    chain = []
    if chain_ok:
        chain.append({"id": "ch-001", "sector": "测试板块", "claim": "供给偏紧",
                      "lifecycle": "强化期", "sei": 55, "leader_backbone": "健康共振",
                      "evidence_level": "P2", "source": "行业协会",
                      "status": "verified"})

    gaps = []
    if gaps_honest:
        for p in points:
            if p["status"] == "missing":
                gaps.append(f"{p['label']}（{p['field']}）未取到，需 agent 补证")
        gaps.append("需 agent 补新闻")
        gaps.append("需 agent 补产业链")

    return {"schema_version": "1.0", "report_date": "2026-09-20", "session": session,
            "ticker": ticker, "name": name, "market": market,
            "holding": {"quantity": 100, "cost": 10, "last_close_in_holdings": 11},
            "planned": {k: list(v) for k, v in planned.items()},
            "data_points": points, "news": news, "chain_notes": chain, "gaps": gaps}


class TestParsing(unittest.TestCase):
    def test_parse_holdings(self):
        hs = fd.parse_holdings(HOLDINGS_MD)
        markets = {(h["market"], h["ticker"]) for h in hs}
        self.assertIn(("A股", "601899.SH"), markets)
        self.assertIn(("港股", "00700.HK"), markets)
        self.assertIn(("美股", "GOOG"), markets)
        self.assertTrue(any(h["market"] == "基金" for h in hs))
        zijin = [h for h in hs if h["ticker"] == "601899.SH"][0]
        self.assertEqual(zijin["quantity"], 1000)
        self.assertAlmostEqual(zijin["cost"], 28.5)

    def test_normalize_ticker(self):
        self.assertEqual(gc.normalize_ticker("601899", "A股"), "601899.SH")
        self.assertEqual(gc.normalize_ticker("300750", "A股"), "300750.SZ")
        self.assertEqual(gc.normalize_ticker("700", "港股"), "00700.HK")
        self.assertEqual(gc.normalize_ticker("aapl", "美股"), "AAPL")

    def test_series_metrics(self):
        rows = [{"date": f"2026-01-{i+1:02d}",
                 "open": 10 + i * 0.1, "high": 10.2 + i * 0.1,
                 "low": 9.9 + i * 0.1, "close": 10 + i * 0.1,
                 "volume": 1000 + i} for i in range(30)]
        m = fd._series_metrics(rows)
        self.assertIsNotNone(m["ma5"])
        self.assertIsNotNone(m["ma20"])
        self.assertIsNone(m["ma60"])  # 数据不足
        self.assertIn(m["range_52w_pct"], (100.0, None))
        self.assertIsNotNone(m["atr14"])

    def test_closed_positions_excluded_and_detected(self):
        md = """# 持仓
## 港股持仓
| 名称 | 代码 | 持仓数量 | 成本价 | 现价 |
|---|---|---|---|---|
| 小米集团-W | 01810.HK | 1400股 | 29.5 | 27.5 |
| ~~希音~~ | 00625.HK | 已清仓 | - | - |

## 美股持仓
| 名称 | 代码 | 持仓数量 | 成本价 | 现价 |
|---|---|---|---|---|
| 谷歌-C | GOOG.US | 25股 | 360 | 350 |
| AMDL | AMDL.US | 已卖出 | - | - |
"""
        for mod in (gc, fd):
            tk = [h["ticker"] for h in mod.parse_holdings(md)]
            self.assertIn("01810.HK", tk)
            self.assertIn("GOOG", tk)
            self.assertNotIn("00625.HK", tk, "删除线清仓标的不得计入持仓")
            self.assertNotIn("AMDL", tk, "状态列写'已卖出'的标的不得计入持仓")
        closed = {(c["ticker"]): c["name"] for c in gc.parse_closed_positions(md)}
        self.assertIn("00625.HK", closed)
        self.assertIn("AMDL", closed)


class GateFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "daily-reports"
        (self.root / "evidence").mkdir(parents=True)
        (self.tmp / "holdings.md").write_text(HOLDINGS_MD, encoding="utf-8")
        self.holdings = gc.parse_holdings(HOLDINGS_MD)
        self.stocks = [h for h in self.holdings if h["market"] != "基金"]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_ev(self, ev, ticker):
        fn = self.root / "evidence" / f"2026-09-20_pre_{gc.safe_name(ticker)}.json"
        fn.write_text(json.dumps(ev, ensure_ascii=False), encoding="utf-8")

    def write_macro(self, options=False):
        points = [{"id": f"dp-{i:03d}", "dimension": "macro", "field": f"m{i}",
                   "label": "m", "value": 1, "unit": "", "as_of": "2026-09-20",
                   "source": "test", "source_url": "http://x", "evidence_level": "P3",
                   "fetched_by": "agent", "status": "verified"} for i in range(1, 6)]
        if options:
            points.append({"id": "dp-006", "dimension": "options", "field": "vix",
                           "label": "VIX", "value": 14, "unit": "", "as_of": "x",
                           "source": "test", "source_url": "http://x",
                           "evidence_level": "P3", "fetched_by": "agent",
                           "status": "verified"})
        macro = {"schema_version": "1.0", "report_date": "2026-09-20",
                 "session": "pre", "ticker": "_macro", "name": "宏观",
                 "market": "macro", "data_points": points, "news": [],
                 "chain_notes": [], "gaps": []}
        (self.root / "evidence" / "2026-09-20_pre_macro.json").write_text(
            json.dumps(macro, ensure_ascii=False), encoding="utf-8")


class TestEvidenceGate(GateFixture):
    def test_full_evidence_passes(self):
        for h in self.stocks:
            self.write_ev(make_stock_evidence(h["ticker"], h["name"], h["market"]),
                          h["ticker"])
        self.write_macro()
        # 基金给一份合格证据
        fund = [h for h in self.holdings if h["market"] == "基金"][0]
        ev = make_stock_evidence(fund["ticker"], fund["name"], "基金")
        ev["data_points"] = [
            {"id": "dp-001", "dimension": "technical", "field": "nav_latest",
             "label": "净值", "value": 1.2, "unit": "", "as_of": "x", "source": "test",
             "source_url": "http://x", "evidence_level": "P3", "fetched_by": "agent",
             "status": "verified"},
            {"id": "dp-002", "dimension": "technical", "field": "nav_change_pct",
             "label": "涨跌", "value": 0.3, "unit": "", "as_of": "x", "source": "test",
             "source_url": "http://x", "evidence_level": "P3", "fetched_by": "agent",
             "status": "verified"}]
        ev["planned"] = {k: list(v) for k, v in fd.PLANNED_FUND.items()}
        self.write_ev(ev, fund["ticker"])
        r = gc.check_evidence(self.root, "2026-09-20", "pre", self.holdings)
        self.assertEqual(r["exit_code"], gc.PASS, r["problems"])

    def test_missing_price_blocks(self):
        for h in self.stocks:
            self.write_ev(
                make_stock_evidence(h["ticker"], h["name"], h["market"], price_ok=False),
                h["ticker"])
        r = gc.check_evidence(self.root, "2026-09-20", "pre", self.stocks)
        self.assertEqual(r["exit_code"], gc.FAIL)
        self.assertTrue(any("硬必需" in p for p in r["problems"]))

    def test_missing_news_blocks(self):
        for h in self.stocks:
            self.write_ev(
                make_stock_evidence(h["ticker"], h["name"], h["market"], news_ok=False),
                h["ticker"])
        r = gc.check_evidence(self.root, "2026-09-20", "pre", self.stocks)
        self.assertEqual(r["exit_code"], gc.FAIL)
        self.assertTrue(any("有效新闻" in p for p in r["problems"]))

    def test_p4_news_counts_as_insufficient(self):
        for h in self.stocks:
            self.write_ev(
                make_stock_evidence(h["ticker"], h["name"], h["market"],
                                   news_ok=False, p4_only=True),
                h["ticker"])
        r = gc.check_evidence(self.root, "2026-09-20", "pre", self.stocks)
        self.assertEqual(r["exit_code"], gc.FAIL)
        self.assertTrue(any("P1/P2" in p for p in r["problems"]))

    def test_same_source_family_blocks(self):
        for h in self.stocks:
            ev = make_stock_evidence(h["ticker"], h["name"], h["market"])
            # 第二条新闻改成与第一条同域名、同来源（同源转载凑数）
            ev["news"][1]["url"] = "http://example.com/detail/111111"
            ev["news"][1]["source"] = "交易所公告"
            self.write_ev(ev, h["ticker"])
        r = gc.check_evidence(self.root, "2026-09-20", "pre", self.stocks)
        self.assertTrue(any("独立来源族" in p for p in r["problems"]),
                        r["problems"])

    def test_missing_bearish_impact_blocks(self):
        for h in self.stocks:
            ev = make_stock_evidence(h["ticker"], h["name"], h["market"])
            ev["news"][1]["impact"] = "bullish"  # 两条全看多，无看空
            self.write_ev(ev, h["ticker"])
        r = gc.check_evidence(self.root, "2026-09-20", "pre", self.stocks)
        self.assertTrue(
            any("看多(bullish)与看空(bearish)" in p for p in r["problems"]),
            r["problems"])

    def test_missing_chain_blocks(self):
        for h in self.stocks:
            self.write_ev(
                make_stock_evidence(h["ticker"], h["name"], h["market"], chain_ok=False),
                h["ticker"])
        r = gc.check_evidence(self.root, "2026-09-20", "pre", self.stocks)
        self.assertEqual(r["exit_code"], gc.FAIL)
        self.assertTrue(any("chain_notes" in p for p in r["problems"]))

    def test_hidden_gap_blocks(self):
        """missing 点未写入 gaps → 必须阻断（防隐瞒缺口）。"""
        for h in self.stocks:
            self.write_ev(
                make_stock_evidence(h["ticker"], h["name"], h["market"],
                                   gaps_honest=False),
                h["ticker"])
        r = gc.check_evidence(self.root, "2026-09-20", "pre", self.stocks)
        self.assertEqual(r["exit_code"], gc.FAIL)
        self.assertTrue(any("gaps" in p for p in r["problems"]))

    def test_low_coverage_degraded(self):
        for h in self.stocks:
            ev = make_stock_evidence(h["ticker"], h["name"], h["market"])
            # 把大量点改成 missing 且诚实披露 → 低覆盖
            for p in ev["data_points"]:
                if p["field"] not in ("price_last", "day_change_pct"):
                    p["status"] = "missing"
                    p["value"] = None
            ev["gaps"] = [f"{p['label']}（{p['field']}）未取到"
                          for p in ev["data_points"] if p["status"] == "missing"]
            ev["gaps"] += ["需 agent 补新闻", "需 agent 补产业链"]
            self.write_ev(ev, h["ticker"])
        r = gc.check_evidence(self.root, "2026-09-20", "pre", self.stocks)
        # v2.2.3：低覆盖一律 DEGRADED（3），是否放行由调用方 --allow-degraded 决定；
        # 旧版直接改判 FAIL，导致文档里的退出码 11 永远走不到。
        self.assertEqual(r["exit_code"], gc.DEGRADED)
        r2 = gc.check_evidence(self.root, "2026-09-20", "pre", self.stocks,
                               allow_degraded=True)
        self.assertEqual(r2["exit_code"], gc.DEGRADED)
        # 单独验证覆盖率判定函数：
        low_ev = make_stock_evidence("TEST.SH", "测试", "A股")
        for p in low_ev["data_points"]:
            if p["field"] not in ("price_last", "day_change_pct"):
                p["status"] = "missing"
                p["value"] = None
        pct, _ = gc.coverage(low_ev, "pre")
        self.assertLess(pct, 0.50)

    # 期权/VIX/IV/PCR 板块已彻底移除：盘后不再强制 options 维度证据，故删除原
    # test_post_requires_options（旧断言"无期权证据则FAIL"已失效）。


class TestReportGate(GateFixture):
    def _good_evidence(self):
        ids_by_ticker = {}
        for h in self.stocks:
            ev = make_stock_evidence(h["ticker"], h["name"], h["market"])
            self.write_ev(ev, h["ticker"])
            ids = [p["id"] for p in ev["data_points"][:6]]
            ids += [n["id"] for n in ev["news"]] + [c["id"] for c in ev["chain_notes"]]
            ids_by_ticker[h["ticker"]] = ids
        return ids_by_ticker

    def _report_text(self, ids_by_ticker, coverage_pct=80, refs=True,
                     fake_id=False, with_sources=True, with_disclaimer=True,
                     with_uncertainty=True):
        chunks = [f"# 盘前报告\n数据覆盖率 {coverage_pct}%\n"]
        for h in self.stocks:
            ids = ids_by_ticker.get(h["ticker"], [])
            chunks.append(f"## {h['name']}（{h['ticker']}）")
            if refs:
                for i in range(4):
                    use = ids[i % len(ids)]
                    if fake_id and i == 0:
                        use = "dp-999"
                    chunks.append(f"- 多方论点{i+1}：理由陈述 [{use}]")
                chunks.append(f"- 空方论点1：风险陈述 [{ids[(4) % len(ids)]}]")
                chunks.append(f"- 空方论点2：另一风险 [{ids[(5) % len(ids)]}]")
        if with_uncertainty:
            chunks.append("## 我不确定的是\n- 部分财报数据待验证")
        if with_sources:
            chunks.append(
                "<details><summary>信息来源</summary>"
                "http://example.com/detail/123456\n"
                "http://example.com/article/789012\n"
                "http://example.com/news/345678\n"
                "http://example.com/post/901234\n</details>")
        if with_disclaimer:
            chunks.append("免责声明：本报告不构成投资建议，风险自担。")
        return "\n".join(chunks)

    def test_good_report_passes(self):
        ids_map = self._good_evidence()
        text = self._report_text(ids_map)
        rf = self.root / "report.md"
        rf.write_text(text, encoding="utf-8")
        r = gc.check_report(self.root, "2026-09-20", "pre", self.stocks, rf)
        self.assertEqual(r["exit_code"], gc.PASS, r["problems"])

    def test_no_refs_blocks(self):
        ids_map = self._good_evidence()
        rf = self.root / "report.md"
        rf.write_text(self._report_text(ids_map, refs=False), encoding="utf-8")
        r = gc.check_report(self.root, "2026-09-20", "pre", self.stocks, rf)
        self.assertEqual(r["exit_code"], gc.FAIL)
        self.assertTrue(any("证据引用" in p for p in r["problems"]))

    def test_fake_id_blocks(self):
        ids_map = self._good_evidence()
        rf = self.root / "report.md"
        rf.write_text(self._report_text(ids_map, fake_id=True), encoding="utf-8")
        r = gc.check_report(self.root, "2026-09-20", "pre", self.stocks, rf)
        self.assertEqual(r["exit_code"], gc.FAIL)
        self.assertTrue(any("不存在的 ID" in p for p in r["problems"]))

    def test_coverage_mismatch_blocks(self):
        ids_map = self._good_evidence()
        rf = self.root / "report.md"
        rf.write_text(self._report_text(ids_map, coverage_pct=99), encoding="utf-8")
        r = gc.check_report(self.root, "2026-09-20", "pre", self.stocks, rf)
        self.assertTrue(any("覆盖率" in p for p in r["problems"]))

    def test_missing_sources_and_disclaimer_blocks(self):
        ids_map = self._good_evidence()
        rf = self.root / "report.md"
        rf.write_text(self._report_text(
            ids_map, with_sources=False, with_disclaimer=False,
            with_uncertainty=False), encoding="utf-8")
        r = gc.check_report(self.root, "2026-09-20", "pre", self.stocks, rf)
        joined = "\n".join(r["problems"])
        self.assertIn("信息来源", joined)
        self.assertIn("免责", joined)
        self.assertIn("缺口披露", joined)

    def test_closed_position_card_blocked(self):
        ids_map = self._good_evidence()
        text = self._report_text(ids_map) + \
            "\n## AMDL（已清仓）（AMDL）\n- 已了结，不操作 [dp-001]\n"
        rf = self.root / "report.md"
        rf.write_text(text, encoding="utf-8")
        closed = [{"name": "AMDL", "ticker": "AMDL"}]
        r = gc.check_report(self.root, "2026-09-20", "pre", self.stocks, rf,
                            closed=closed)
        self.assertTrue(any("已清仓标的" in p for p in r["problems"]),
                        r["problems"])

    def test_closed_position_inline_mention_allowed(self):
        ids_map = self._good_evidence()
        text = self._report_text(ids_map) + \
            "\n跨报告对账：AMDL 已于 9/18 清仓，本期不再列持仓卡片。\n"
        rf = self.root / "report.md"
        rf.write_text(text, encoding="utf-8")
        closed = [{"name": "AMDL", "ticker": "AMDL"}]
        r = gc.check_report(self.root, "2026-09-20", "pre", self.stocks, rf,
                            closed=closed)
        self.assertFalse(any("已清仓标的" in p for p in r["problems"]),
                         r["problems"])

    def test_bull_bear_same_source_blocks(self):
        ids_map = self._good_evidence()
        text = self._report_text(ids_map)
        # 把空方论点引用改成与多方完全相同的 ID（空方照抄多方来源）
        text = text.replace("[dp-005]", "[dp-001]").replace("[dp-006]", "[dp-002]")
        rf = self.root / "report.md"
        rf.write_text(text, encoding="utf-8")
        r = gc.check_report(self.root, "2026-09-20", "pre", self.stocks, rf)
        self.assertTrue(any("独立于多方" in p for p in r["problems"]),
                        r["problems"])

    def test_missing_bull_bear_block_blocks(self):
        ids_map = self._good_evidence()
        text = self._report_text(ids_map).replace("空方论点", "补充论点")
        rf = self.root / "report.md"
        rf.write_text(text, encoding="utf-8")
        r = gc.check_report(self.root, "2026-09-20", "pre", self.stocks, rf)
        self.assertTrue(any("对立" in p for p in r["problems"]), r["problems"])


WATCHLIST_MD = """# 关注库（Watchlist）

## 关注标的

| 名称 | 代码 | 市场 | 目标接回价 | 计划股数 | 预计金额 | 止损价(-15%) | 加入日期 | 状态 | 逻辑/备注 |
|---|---|---|---|---|---|---|---|---|---|
| Lumentum（老馒头） | LITE | 美股 | 850 | 4 | 3400 | 722.5 | 2026-09-24 | 等待 | 高位卖出，等回调接回 |
| 美光科技 | MU | 美股 | 950 | 4 | 3800 | 807.5 | 2026-09-24 | 等待 | 存储周期，等回调 |
"""


def make_watchlist_evidence(price, target=850, stop=722.5, added="2026-09-24"):
    flds = ["price_last", "day_change_pct", "ma5", "ma20", "ma60", "range_52w_pct",
            "atr14", "volume_ratio", "pe_ttm", "pb", "market_cap", "roe",
            "revenue_growth_yoy", "profit_growth_yoy", "put_call_or_inst"]
    _dim = {f: d for d, fs in (
        ("technical", ["price_last", "day_change_pct", "ma5", "ma20", "ma60",
                       "range_52w_pct", "atr14", "volume_ratio"]),
        ("fundamental", ["pe_ttm", "pb", "market_cap", "roe",
                         "revenue_growth_yoy", "profit_growth_yoy"]),
        ("flow", ["main_net_inflow", "north_south_flow", "put_call_or_inst"]),
    ) for f in fs}
    dps = [{"id": f"dp-{i:03d}", "dimension": _dim.get(f, "x"), "field": f, "label": f,
            "value": 1, "unit": "", "as_of": "2026-09-24", "source": "test",
            "source_url": "http://example.com", "evidence_level": "P3",
            "fetched_by": "script", "status": "verified"}
           for i, f in enumerate(flds, 1)]
    dps[0]["value"] = price
    return {"schema_version": "1.0", "report_date": "2026-09-24", "session": "post",
            "ticker": "LITE", "name": "Lumentum（老馒头）", "market": "美股",
            "instrument": "STOCK", "account": "关注库", "data_points": dps,
            "news": [
                {"id": "nw-001", "headline": "光通信需求持续向好",
                 "url": "https://reuters.com/article/abc12345",
                 "source": "路透", "evidence_level": "P1", "impact": "bullish",
                 "status": "verified"},
                {"id": "nw-002", "headline": "当前估值明显偏高",
                 "url": "https://seekingalpha.com/article/67890",
                 "source": "SeekingAlpha",
                 "evidence_level": "P2", "impact": "bearish", "status": "verified"}],
            "chain_notes": [{"id": "ch-001", "sector": "光通信", "lifecycle": "加速期",
                             "evidence_level": "P2", "status": "verified"}],
            "watchlist": {"target_buy_price": target, "planned_qty": 4,
                          "stop_loss": stop, "added_date": added, "status": "等待"},
            "gaps": ["无"]}


_WL_ANA = ("## Lumentum LITE\n"
           "多方：技术企稳 [dp-001][dp-003]，需求向好 [nw-001][ch-001]\n"
           "空方：估值偏高 [dp-009][dp-010]，竞争风险 [nw-002]\n"
           "现价 {p}，专家分析：")


def _wl_report(body):
    return ("# 美股关注库\n" + body +
            "\n数据覆盖率 100%\n"
            "<details><summary>来源</summary>"
            "http://example.com/detail/123456\n"
            "http://example.com/article/789012\n"
            "http://example.com/news/345678\n"
            "http://example.com/post/901234\n</details>\n"
            "免责：不构成投资建议\n我不确定：无\n")


class TestWatchlist(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "evidence").mkdir(parents=True)
        # v2.4.0 语义反转：brief 里是"要降级"的名单；留空 = 全部深度分析
        (self.root / "watchlist_brief.json").write_text(
            json.dumps({"pre": [], "noon": [], "post": []}),
            encoding="utf-8")
        self.lite = gc.parse_watchlist(WATCHLIST_MD)[0]

    def tearDown(self):
        self.tmp.cleanup()

    def _check(self, price, body, added="2026-09-24"):
        (self.root / "evidence" / "2026-09-24_post_LITE.json").write_text(
            json.dumps(make_watchlist_evidence(price, added=added), ensure_ascii=False),
            encoding="utf-8")
        rf = self.root / "r.md"
        rf.write_text(_wl_report(body), encoding="utf-8")
        return gc.check_report(self.root, "2026-09-24", "post", [self.lite], str(rf))

    def test_parse_watchlist(self):
        for parser in (fd.parse_watchlist, gc.parse_watchlist):
            items = parser(WATCHLIST_MD)
            self.assertEqual([i["ticker"] for i in items], ["LITE", "MU"])
            lite = items[0]
            self.assertEqual(lite["target_price"], 850)
            self.assertEqual(lite["planned_qty"], 4)
            self.assertAlmostEqual(lite["stop_loss"], 722.5)
            self.assertTrue(lite.get("watchlist"))

    def test_below_target_analysis_passes(self):
        r = self._check(937, _WL_ANA.format(p=937) + "未到目标850，继续等待，暂不买入。")
        self.assertEqual(r["exit_code"], gc.PASS, r["problems"])

    def test_buy_call_before_target_fails(self):
        r = self._check(937, _WL_ANA.format(p=937) + "可接回 4股。")
        self.assertTrue(any("尚未到目标" in p for p in r["problems"]))

    def test_at_target_full_checklist_passes(self):
        r = self._check(800, _WL_ANA.format(p=800)
                        + "已到目标850，可接回 4 股，止损722.5，证伪：跌破700。")
        self.assertEqual(r["exit_code"], gc.PASS, r["problems"])

    def test_at_target_no_checklist_fails(self):
        r = self._check(800, _WL_ANA.format(p=800) + "已到价。")
        self.assertTrue(any("必须二选一" in p for p in r["problems"]))

    def test_four_week_no_reassess_fails(self):
        r = self._check(937, _WL_ANA.format(p=937) + "继续等待。", added="2026-08-20")
        self.assertTrue(any("满 4 周" in p for p in r["problems"]))

    def test_four_week_reassess_passes(self):
        r = self._check(937, _WL_ANA.format(p=937)
                        + "建议重新评估、重定低位目标价。", added="2026-08-20")
        self.assertEqual(r["exit_code"], gc.PASS, r["problems"])

    def test_at_target_value_trap_block_passes(self):
        r = self._check(800, _WL_ANA.format(p=800)
                        + "已到价但先别接：财报暴雷，疑似价值陷阱，降级待验证。")
        self.assertEqual(r["exit_code"], gc.PASS, r["problems"])


SRC_BLOCK = ("<details><summary>信息来源</summary>"
             "http://example.com/detail/123456\n"
             "https://reuters.com/article/789012\n"
             "http://example.com/news/345678\n"
             "http://example.com/post/901234\n</details>")


class TestAntiFraud(GateFixture):
    """锁定 2026-09-29 事故：占位值/非法编号/空信息源必须被门禁拦截。"""

    def _prep_good_evidence(self):
        ids = {}
        for h in self.stocks:
            ev = make_stock_evidence(h["ticker"], h["name"], h["market"])
            self.write_ev(ev, h["ticker"])
            ids[h["ticker"]] = ([p["id"] for p in ev["data_points"][:6]]
                                + [n["id"] for n in ev["news"]]
                                + [c["id"] for c in ev["chain_notes"]])
        return ids

    def _report(self, ids, details_block, extra_line=""):
        chunks = ["# 盘前报告\n数据覆盖率 80%\n"]
        for h in self.stocks:
            L = ids[h["ticker"]]
            chunks.append(f"## {h['name']}（{h['ticker']}）")
            chunks.append(f"多方：成长与资金 [{L[0]}] [{L[1]}] [{L[2]}] [nw-001]")
            chunks.append(f"空方：估值与风险 [{L[3]}] [{L[4]}] [nw-002]")
            if extra_line:
                chunks.append(extra_line)
        chunks.append("## 我不确定的是\n- 部分数据待验证")
        chunks.append(details_block)
        chunks.append("免责声明：不构成投资建议，风险自担。")
        return "\n".join(chunks)

    def test_placeholder_values_and_missing_source_fail(self):
        for h in self.stocks:
            ev = make_stock_evidence(h["ticker"], h["name"], h["market"])
            for p in ev["data_points"]:
                if p["status"] == "verified":
                    p["value"] = 1.0      # 全填占位 1.0
                    p["source"] = ""      # 且无来源
            self.write_ev(ev, h["ticker"])
        r = gc.check_evidence(self.root, "2026-09-20", "pre", self.stocks)
        self.assertEqual(r["exit_code"], gc.FAIL)
        self.assertTrue(any("完全相同" in p or "source" in p for p in r["problems"]),
                        r["problems"])

    def test_homepage_only_news_url_fails(self):
        for h in self.stocks:
            ev = make_stock_evidence(h["ticker"], h["name"], h["market"])
            for n in ev["news"]:
                n["url"] = "http://example.com/"   # 只给网站首页
            self.write_ev(ev, h["ticker"])
        r = gc.check_evidence(self.root, "2026-09-20", "pre", self.stocks)
        self.assertEqual(r["exit_code"], gc.FAIL)
        self.assertTrue(any("有效新闻" in p for p in r["problems"]))

    def test_illegal_id_token_fails(self):
        ids = self._prep_good_evidence()
        text = self._report(ids, SRC_BLOCK, extra_line="多方补充：市场传闻 [dp-vix]")
        rf = self.root / "r.md"
        rf.write_text(text, encoding="utf-8")
        r = gc.check_report(self.root, "2026-09-20", "pre", self.stocks, rf)
        self.assertEqual(r["exit_code"], gc.FAIL)
        self.assertTrue(any("非法" in p for p in r["problems"]), r["problems"])

    def test_empty_details_no_article_links_fails(self):
        ids = self._prep_good_evidence()
        text = self._report(ids, '<details><summary>信息来源</summary>SEC</details>')
        rf = self.root / "r.md"
        rf.write_text(text, encoding="utf-8")
        r = gc.check_report(self.root, "2026-09-20", "pre", self.stocks, rf)
        self.assertEqual(r["exit_code"], gc.FAIL)
        self.assertTrue(any("具体文章" in p for p in r["problems"]), r["problems"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
