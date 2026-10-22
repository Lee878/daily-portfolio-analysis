# -*- coding: utf-8 -*-
"""Brief 版式（v2.7.0）的回归测试：渲染层与门禁的接口契约。

背景：v2.7.0 把"证据徽标"从内联灰方块改成上标脚注，把方括号原文移进
`data-ev` 属性。这个改动看起来纯装饰，实际有三处会**静默**毁掉报告门：

  1. 门禁按 `<div class="card[^"]*">` 认卡片起点。卡片标签多一个属性就匹配
     不上，后续卡片会被并入前一张卡区间，别家标的的证据算到这张卡头上——
     不报错，只是结论错。
  2. 门禁按"行"取 ID 判多空不同源。多空渲染在同一行 → 两边拿到同一批 ID，
     直接判"多空没各引独立来源"。
  3. run_daily 注入横幅/徽标用的是正则全文替换。样式表注释里出现 body
     字样 → 横幅被插进 <style>，CSS 注释提前结束，横幅本身被当 CSS 丢掉。

本文件把这些契约钉死，改版式时不必再逐条人工核对。
"""
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import gate_check as gate  # noqa: E402
import render_report as rr  # noqa: E402
import run_daily as rd  # noqa: E402


DATA = {
    "meta": {
        "h1": "盘后总结与美股前瞻 2026-10-20 周二",
        "title": "测试报告",
        "coverage": "87",
        "coverage_note": "字段级覆盖：必备 12 项命中 10 项。",
    },
    "regime": "大势：反弹不追 [nw-001]，等回踩确认 [dp-001]。",
    "stats": [{"k": "标普500", "v": "7690.73 +0.41%", "cls": "g"},
              {"k": "现货黄金", "v": "约4115 连跌3日", "cls": "r"}],
    "blocks": [
        {"kind": "cards", "h2": "美股持仓｜完整卡片", "cards": [
            {"type": "us", "name": "紫金矿业", "code": "601899.SH · 1500股 成本28.6 · 现价27.4",
             "chg": "+0.97%", "act": "1500股拿住", "act_tag": "持有",
             "concl": "量价共振，持有 [dp-002]。",
             "bull": "铜价上行、净利+123% [nw-002][dp-002]",
             "bear": "金价失守4115、连跌3日 [dp-003][nw-003]",
             "risk": "下方看28/27元 [dp-003]",
             "pos": "站上20日线 [ch-001]",
             "cons": "分歧在铜价持续性 [nw-002]",
             "fals": "跌破27元则减 [dp-003]"},
        ]},
        {"kind": "prose", "h2": "跨报告对账", "paras": ["较今早：反弹不追 [nw-001]"]},
        {"kind": "table", "h2": "操作建议汇总", "rows": [
            {"pos": "紫金矿业", "act": "持有", "cond": "跌破27元", "cls": "r"}]},
    ],
    "sources": [{"label": "上交所", "url": "https://example.com/a"}],
    "sources_note": "行情来自腾讯/新浪适配层。",
}

EV_META = {"601899_SH": {"dp-001": ("P1", "交易所", "https://e.com/1"),
                         "dp-002": ("P1", "交易所", "https://e.com/2"),
                         "dp-003": ("P2", "券商研报", ""),
                         "nw-001": ("P1", "财联社", "https://e.com/n1"),
                         "nw-002": ("P2", "路透", ""),
                         "nw-003": ("P4", "传闻", ""),
                         "ch-001": ("P2", "产业链", "")}}


def render(html_css=None):
    css = (REPO / "assets/style.css").read_text(encoding="utf-8")
    data = {**DATA, "_id_meta": {}, "_id_meta_by_ticker": EV_META}
    return rr.render(data, css)


class TestGateContract(unittest.TestCase):
    """渲染产物必须仍然"可被门禁读懂"——否则版式一改，门禁就瞎了。"""

    def setUp(self):
        self.html = render()

    def test_card_tags_match_gate_start_regex(self):
        """卡片开标签必须能被 `_CARD_START_RE` 认出来。

        认不出来 → 卡片区间错位 → 证据归属串到别家标的（不报错，结论错）。
        """
        cards = re.findall(r'<div class="card[^"]*"[^>]*>', self.html)
        self.assertTrue(cards, "没有渲染出任何卡片")
        for tag in cards:
            self.assertRegex(tag, gate._CARD_START_RE.pattern,
                             f"卡片标签不匹配门禁起始正则：{tag}")

    def test_bull_and_bear_on_separate_lines_with_own_ids(self):
        """多空必须各占一行且各带自己的 ID——门禁按行判"不同源"。"""
        bull = [L for L in self.html.splitlines() if "多方" in L]
        bear = [L for L in self.html.splitlines() if "空方" in L]
        self.assertEqual(len(bull), 1)
        self.assertEqual(len(bear), 1)
        b_ids = set(m.group(0) for m in gate.ID_RE.finditer(bull[0]))
        r_ids = set(m.group(0) for m in gate.ID_RE.finditer(bear[0]))
        self.assertTrue(b_ids and r_ids, "多空行里没有证据 ID，门禁会判缺论点")
        self.assertTrue(b_ids - r_ids, "多空引用完全同源，门禁会判失败")
        self.assertTrue(r_ids - b_ids, "多空引用完全同源，门禁会判失败")

    def test_ids_stay_countable_but_invisible(self):
        """卡片内：方括号留在源码（门禁计数），但看不见；卡片外保留原始徽标。

        非卡片正文（大势/对账段落）不编号——脚注序号在卡片里才有对应清单，
        段落里编号会指向不存在的条目，所以那里保留 [nw-001] 交给
        run_daily 的徽标兜底包成静默上标。
        """
        self.assertGreaterEqual(len(gate.ID_RE.findall(self.html)), 6,
                                "总引用次数不足，门禁会判证据不足")
        card = rr._card(DATA["blocks"][0]["cards"][0], "c-test",
                        rr.EXTRA_FIELDS["us"])
        self.assertGreaterEqual(len(gate.ID_RE.findall(card)), 6,
                                "卡片源码里的证据引用数不对，门禁会判不足")
        visible = re.sub(r"<[^>]+>", "", card)
        self.assertNotIn("[dp-", visible, "卡片可见文本里还有裸方括号")
        self.assertNotIn("[nw-", visible, "卡片可见文本里还有裸方括号")

    def test_every_superscript_has_evidence_entry(self):
        """上标序号必须都能在卡底"证据"清单里找到对应行。"""
        nums = set(re.findall(r'class="evm">(\d+)</sup>', self.html))
        rows = set(re.findall(r'class="enum">(\d+)</span>', self.html))
        self.assertTrue(nums)
        self.assertEqual(nums, rows, "上标序号与证据清单条目对不上")

    def test_coverage_banner_anchor_present(self):
        """`数据覆盖率 X%` 是 run_daily 机械校准的锚点，不能丢。"""
        self.assertRegex(self.html, r"数据覆盖率\s*\d{1,3}\s*%")
        self.assertIn("<h1>", self.html)


class TestPositionMath(unittest.TestCase):
    """浮动盈亏由脚本算——这是原版最大的可读性损失（有成本却不算盈亏）。"""

    def test_pnl_from_code_string(self):
        pos = rr.parse_position("601899.SH · 1500股 成本28.6 · 现价27.4")
        self.assertEqual(pos["cost"], "28.6")
        self.assertEqual(pos["last"], "27.4")
        self.assertEqual(pos["shares"], "1500")
        self.assertEqual(pos["pnl"], "-4.20%")
        self.assertEqual(pos["pnl_cls"], "fall")

    def test_pnl_positive_and_neutral(self):
        self.assertEqual(rr.parse_position("X · 10股 成本100 · 现价110")["pnl"], "+10.00%")
        self.assertEqual(rr.parse_position("X · 10股 成本100 · 现价100")["pnl"], "+0.00%")
        self.assertEqual(rr.parse_position("无仓位信息")["pnl"], "")

    def test_bad_numbers_do_not_raise(self):
        self.assertEqual(rr.parse_position("成本 · 现价")["pnl"], "")


class TestStatSplit(unittest.TestCase):
    """指数格：数值与状态词分开，窄屏才不会被挤断。"""

    def test_percent_and_state_word(self):
        self.assertEqual(rr.split_stat("7690.73 +0.41%"), ("7690.73", "+0.41%", "rise"))
        v, tail, d = rr.split_stat("约4115 连跌3日")
        self.assertEqual((v, tail, d), ("约4115", "连跌3日", "fall"))

    def test_plain_value(self):
        self.assertEqual(rr.split_stat("4130"), ("4130", "", ""))


class TestInjectionHelpers(unittest.TestCase):
    """注入类操作必须避开 style/script 内部——这里真的踩过。"""

    def test_sub_outside_tags_keeps_attributes_intact(self):
        text = ('<p data-ev="[dp-001]">正文 [dp-001] 引用</p>'
                '<div class="x" title="[dp-002]"></div>')
        out = rd._sub_outside_tags(gate.ID_RE, lambda m: "<b>X</b>", text)
        self.assertIn('data-ev="[dp-001]"', out, "属性里的 ID 被改写了")
        self.assertIn('title="[dp-002]"', out, "属性里的 ID 被改写了")
        self.assertIn("<b>X</b> 引用", out, "正文里的 ID 没有被替换")

    def test_inject_into_body_skips_style_comment(self):
        text = ('<html><head><style>/* 插在 <body> 之后 */\n.b{color:red}</style>'
                '</head><body><p>x</p></body></html>')
        out = rd._inject_into_body(text, "<div>BANNER</div>")
        self.assertLess(out.index("</style>"), out.index("BANNER"),
                        "横幅被插进了样式表内部")
        self.assertIn("<body><div>BANNER</div><p>x</p>", out)

    def test_style_css_has_no_angle_bracket_tag_in_comments(self):
        """样式表注释里不许出现 <tag> 字样：注入正则会把它们当真的标签。"""
        css = (REPO / "assets/style.css").read_text(encoding="utf-8")
        for block in re.findall(r"/\*.*?\*/", css, re.S):
            self.assertIsNone(
                re.search(r"<(?!/)[a-zA-Z][\w-]*[^>]*>", block),
                f"CSS 注释里出现了尖括号标签，会被注入正则命中：{block[:60]}")


class TestThemeIdCountStable(unittest.TestCase):
    """主题改造不得让门禁的证据引用计数漂移。

    深浅两版是同一份 data.json 的两次渲染，主题只改根元素上的 data-theme。
    门禁按 `[dp|nw|ch-xxx]` 计数，计数一变就说明有人在版式里动了证据引用
    ——这类改动不报错，只是结论错（多空同源、引用不足、重复凑数）。
    """

    def test_dark_and_light_products_have_equal_gate_id_counts(self):
        """AC-21：深浅两版产物的门禁 ID 计数完全相等。"""
        dark = render()
        light = dark.replace('<html lang="zh" data-theme="dark">',
                             '<html lang="zh" data-theme="light">', 1)
        self.assertNotEqual(dark, light, "深浅两版产物应只有主题属性不同")

        for label, html in (("深色", dark), ("浅色", light)):
            ids = gate.ID_RE.findall(html)
            self.assertGreaterEqual(len(ids), 6,
                                    f"{label}版证据引用总数不足，门禁会判证据不足")
            self.assertEqual(
                sorted(ids), sorted(gate.ID_RE.findall(
                    light if label == "深色" else dark)),
                f"{label}版与其他版本的证据 ID 序列不一致——主题改造动了证据引用")

    def test_injected_elements_take_color_from_css_vars(self):
        """AC-28：注入元素取色来源是 var(--...)，不残留写死浅色值。

        写死的浅色值叠到深色页面上会糊成一片（深红字对深底对比度 1.5:1），
        用户根本看不见告警。断言的是"取色来源"，不是"看起来对不对"。
        """
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "r.html"
            p.write_text(render(), encoding="utf-8")
            rd._apply_degrade(p, ["缺口一", "缺口二"], 0.62)
            rd._inject_version_footer(p, 0.62, "PASS")
            text = p.read_text(encoding="utf-8")

        banner = re.search(r'<div id="degrade-banner".*?<!--/degrade-->', text, re.S)
        self.assertIsNotNone(banner, "没找到降级横幅")
        footer = re.search(r'<footer id="daily-version-footer".*?</footer>', text, re.S)
        self.assertIsNotNone(footer, "没找到版本页脚")

        for label, blob in (("降级横幅", banner.group(0)),
                            ("版本页脚", footer.group(0)),
                            ("证据徽标", rd.BADGE_CSS)):
            for hexv in ("#fdf2f0", "#7d2f28", "#a3261f", "#e2ded4",
                         "#6c727b", "#989ea6", "#8f6119"):
                self.assertNotIn(hexv, blob,
                                 f"{label}残留写死浅色值 {hexv}——深色主题下会看不见")
        self.assertIn("var(--warn-bg)", banner.group(0),
                      "降级横幅背景未改用 var(--warn-bg)")
        self.assertIn("var(--ink3)", footer.group(0),
                      "版本页脚未改用 var(--ink3)")
        self.assertIn("var(--ink4)", rd.BADGE_CSS,
                      "证据徽标未改用 var(--ink4)")


class TestEvidenceBucket(unittest.TestCase):
    """证据按标的分桶：全局 dict 会让后写覆盖先写，来源链接指错标的。"""

    def test_pick_bucket_by_ticker_head(self):
        by = {"601899_SH": {"dp-001": ("P1", "a", "")},
              "00981_HK": {"dp-001": ("P1", "b", "")}}
        self.assertEqual(rr.pick_bucket(by, "601899.SH · 紫金")["dp-001"][1], "a")
        self.assertEqual(rr.pick_bucket(by, "00981.HK · 中芯")["dp-001"][1], "b")
        self.assertEqual(rr.pick_bucket(by, "无匹配"), {})


if __name__ == "__main__":
    unittest.main()
