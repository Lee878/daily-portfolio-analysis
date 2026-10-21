#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_daily 物理门禁管道的回归测试：
  - 双门 PASS 才在 HTML 注入 daily-gate 签名；
  - 报告门 FAIL 时 do_report 删除产物并返回退出码 12；
  - 证据门 FAIL 时不运行 builder（返回 10）。

运行：cd scripts && python -m unittest tests.test_run_daily -v
"""
import argparse
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gate_check as gc  # noqa: E402
import run_daily as rd   # noqa: E402

HOLDINGS_MD = """# 持仓档案
## 美股持仓
| 名称 | 代码 | 持仓数量 | 成本价 | 现价 |
|---|---|---|---|---|
| 苹果 | AAPL | 10 | 150 | 170 |
"""

GOOD_HTML = """<html><head><title>t</title></head><body>
<h2>苹果 AAPL</h2>
<p>价格 [dp-001] 涨跌 [dp-002] 均线 [dp-003] [dp-004]，估值 [dp-009] [dp-010]</p>
<p>多方：业绩与资金支撑，成长 [dp-013] [dp-014]，资金 [dp-015]，利好公告 [nw-001]，产业链 [ch-001]</p>
<p>空方：估值偏高、获利回吐，机构风险提示 [nw-002] [dp-010]，需求担忧 [dp-005]</p>
<p>数据覆盖率 100% 机械计算</p>
<details><summary>信息来源</summary>
http://example.com/detail/123456
http://example.com/article/789012
http://example.com/news/345678
http://example.com/post/901234
</details>
<p>我不确定的是：无</p>
<p>免责：不构成投资建议，风险自担。</p>
</body></html>"""

BAD_HTML = "<html><title>bad</title><body>无引用 无覆盖率</body></html>"


def _evidence_dict():
    vals = {
        "price_last": 170, "day_change_pct": 0.6, "ma5": 168, "ma20": 165,
        "ma60": 160, "range_52w_pct": 70, "atr14": 3.2, "volume_ratio": 1.2,
        "pe_ttm": 28, "pb": 9, "market_cap": 30000, "roe": 15,
        "revenue_growth_yoy": 10, "profit_growth_yoy": 12,
        "put_call_or_inst": 1.1}
    dim_of = {}
    for _d, _fs in (("technical", ["price_last", "day_change_pct", "ma5", "ma20",
                                   "ma60", "range_52w_pct", "atr14", "volume_ratio"]),
                    ("fundamental", ["pe_ttm", "pb", "market_cap", "roe",
                                     "revenue_growth_yoy", "profit_growth_yoy"]),
                    ("flow", ["put_call_or_inst"])):
        for _f in _fs:
            dim_of[_f] = _d
    dps = []
    for i, f in enumerate(vals, 1):
        dps.append({"id": f"dp-{i:03d}", "dimension": dim_of.get(f, "x"), "field": f,
                    "value": vals[f], "status": "verified", "evidence_level": "P3",
                    "source": "test-source",
                    "source_url": "http://example.com/detail/123456"})
    return {
        "schema_version": "1.0", "report_date": "2026-09-21", "session": "pre",
        "ticker": "AAPL", "name": "苹果", "market": "美股", "instrument": "STOCK",
        "planned": {}, "data_points": dps,
        "news": [
            {"id": "nw-001", "headline": "苹果AI业务获市场看好",
             "url": "http://example.com/detail/123456", "evidence_level": "P1",
             "status": "verified", "impact": "bullish"},
            {"id": "nw-002", "headline": "机构提示估值回调风险",
             "url": "https://reuters.com/article/789012", "evidence_level": "P2",
             "status": "verified", "impact": "bearish"}],
        "chain_notes": [
            {"id": "ch-001", "evidence_level": "P2", "status": "verified",
             "lifecycle": "加速期"}],
        "gaps": [],
    }


class RunDailyPipeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ev = self.root / "evidence"
        self.ev.mkdir(parents=True, exist_ok=True)
        self.holdings = self.root / "holdings.md"
        self.holdings.write_text(HOLDINGS_MD, encoding="utf-8")
        self.html = self.root / "r.html"
        (self.ev / "2026-09-21_pre_AAPL.json").write_text(
            __import__("json").dumps(_evidence_dict(), ensure_ascii=False),
            encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _args(self, builder):
        return argparse.Namespace(
            holdings=str(self.holdings), report_root=str(self.root),
            date="2026-09-21", session="pre", allow_degraded=False,
            builder=builder, html=str(self.html), no_network=False)

    def _make_builder(self, content):
        p = self.root / "b.py"
        p.write_text(
            "from pathlib import Path\n"
            f"Path(r'''{self.html}''').write_text({content!r}, encoding='utf-8')\n",
            encoding="utf-8")
        return str(p)

    def test_good_report_gets_signature(self):
        rc = rd.do_report(self._args(self._make_builder(GOOD_HTML)))
        self.assertEqual(rc, rd.EXIT_PASS)
        self.assertTrue(self.html.exists())
        self.assertIn('name="daily-gate"', self.html.read_text(encoding="utf-8"))

    def test_bad_report_is_deleted(self):
        rc = rd.do_report(self._args(self._make_builder(BAD_HTML)))
        self.assertEqual(rc, rd.EXIT_RP_FAIL)
        self.assertFalse(self.html.exists(), "报告门 FAIL 必须物理删除不合格 HTML")

    def test_evidence_gate_blocks_builder(self):
        # 删掉证据 → 证据门 FAIL，builder 不应被运行（产物不出现）
        (self.ev / "2026-09-21_pre_AAPL.json").unlink()
        rc = rd.do_report(self._args(self._make_builder(GOOD_HTML)))
        self.assertEqual(rc, rd.EXIT_EV_FAIL)
        self.assertFalse(self.html.exists(), "证据门 FAIL 时禁止生成报告")

    def test_signature_is_single_even_if_rerun(self):
        self._prep_html()
        rd._inject_signature(self.html, "2026-09-21", "pre", 0.9)
        rd._inject_signature(self.html, "2026-09-21", "pre", 0.9)
        self.assertEqual(
            self.html.read_text(encoding="utf-8").count('name="daily-gate"'), 1)

    def _prep_html(self):
        self.html.write_text("<html><title>x</title></html>", encoding="utf-8")
        return self.html

    def test_banner_synced_to_mechanical_value(self):
        self.html.write_text(
            "<html><head></head><body>数据覆盖率 70% 机械计算</body></html>",
            encoding="utf-8")
        changed = rd._sync_coverage_banner(self.html, 0.834)
        self.assertEqual(changed, 1)
        text = self.html.read_text(encoding="utf-8")
        self.assertIn("数据覆盖率 83%", text)
        self.assertNotIn("70%", text)

    def test_render_badges_wraps_bare_ids(self):
        self.html.write_text(
            "<html><head></head><body><p>利好 [nw-001] 与 [dp-001]</p></body></html>",
            encoding="utf-8")
        n = rd._render_badges(self.html, self.root, "2026-09-21", "pre")
        self.assertEqual(n, 2)
        text = self.html.read_text(encoding="utf-8")
        self.assertIn('class="rb', text)
        self.assertIn(".rb", text, "应注入徽标 CSS")
        stripped = __import__("re").sub(r'<span class="rb[^>]*>.*?</span>', "", text)
        self.assertNotIn("[nw-001]", stripped)
        self.assertNotIn("[dp-001]", stripped)

    def test_render_badges_protects_existing(self):
        self.html.write_text(
            '<html><head></head><body><span class="b p1" title="x">[nw-001]</span>'
            "</body></html>", encoding="utf-8")
        n = rd._render_badges(self.html, self.root, "2026-09-21", "pre")
        self.assertEqual(n, 0, "已渲染的 span.b 徽标不应被二次包裹")
        self.assertNotIn('class="rb', self.html.read_text(encoding="utf-8"))

    def test_gate_constants_distinct(self):
        self.assertEqual(gc.PASS, 0)
        self.assertNotEqual(rd.EXIT_EV_FAIL, rd.EXIT_RP_FAIL)


if __name__ == "__main__":
    unittest.main()
