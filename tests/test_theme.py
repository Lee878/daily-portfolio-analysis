#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""双主题（Chroma Duality）的契约测试——v2.8.0。

背景：v2.8.0 把报告从"只有浅色"改成"深色默认 + 可切浅色"。这类改动最危险
的地方在于**它不会报错**：主题色改错、脚本位置挪了、控件污染了门禁正则，
产物照样渲染成功、报告照样出得来，只是用户看到的东西不对。

所以本文件只做一件事：把"主题机制必须满足的具体条件"钉成强断言。
每条用例都断言**具体值**（默认主题标识、存储键名、脚本位置、token 实值），
不接受"元素存在"式的弱断言——那种断言在本项目的历史里放过 bug。

覆盖的硬约束：
  * 默认深色 + 首帧无闪烁（脚本必须在 <style> 之前、<body> 之前）
  * 存储键名固定 dpa-theme（改键名 = 用户的选择全部丢失）
  * 切换控件不污染门禁正则（dp- / nw- / ch- 片段、裸方括号、<details>）
  * 深浅两套主题各自实算对比度，正文级 ≥4.5:1
  * 浅色 12 值与 v2.7.0 一字不差（防深色改造误改浅色）
  * 注入元素（横幅 / 页脚 / 徽标）取色走 CSS 变量，不写死浅色值
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

CSS_PATH = REPO / "assets" / "style.css"

# v2.7.0 已验收的浅色 12 值——深色改造不得改动其中任何一个（R-03 防线）。
# 取自 v2.7.0 的 :root 块原值。
V270_LIGHT = {
    "bg": "#faf9f6", "paper": "#ffffff",
    "ink": "#15181d", "ink2": "#454d59",
    "ink3": "#6c727b", "ink4": "#989ea6",
    "rule": "#e2ded4", "rule2": "#eeebe3",
    "rise": "#c0392b", "fall": "#16704a",
    "gold": "#8f6119", "accent": "#1c4b78",
}

# 注入元素里不许残留的写死浅色值（AC-28 点名清单）。
# 这些是 v2.7.0 横幅 / 页脚 / 徽标写死的浅色色值，深色底下会糊成一片。
FORBIDDEN_LIGHT_HEX = ("#fdf2f0", "#7d2f28", "#a3261f", "#e2ded4",
                       "#6c727b", "#989ea6", "#8f6119")


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------
def lum(hexcolor):
    """sRGB 相对亮度（WCAG 2.1）。"""
    hexcolor = hexcolor.lstrip("#")
    if len(hexcolor) == 3:
        hexcolor = "".join(c * 2 for c in hexcolor)
    r, g, b = (int(hexcolor[i:i + 2], 16) / 255 for i in (0, 2, 4))

    def f(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def ratio(a, b):
    """对比度 (L1+0.05)/(L2+0.05)。"""
    l1, l2 = lum(a), lum(b)
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


def css_vars(block):
    """从一个 CSS 声明块里抽出颜色变量。"""
    return {n: v for n, v in re.findall(r"--([\w-]+)\s*:\s*(#[0-9a-fA-F]{3,8})", block)}


def theme_blocks(css_text):
    """按**选择器**定位深浅两块（不按块序数取第一个 :root）。

    按块序数取是本项目的经典陷阱：深色放在 :root 时，"第一个 :root" 拿到的是
    深色，浅色对比度校验完全没跑 —— 全绿但什么都没查。
    """
    light_m = re.search(r"^:root\s*\{([^}]*)\}", css_text, re.M)
    dark_m = re.search(r"^\[data-theme=[\"']dark[\"']\]\s*\{([^}]*)\}", css_text, re.M)
    assert light_m, "style.css 缺浅色块 :root { ... }"
    assert dark_m, "style.css 缺深色块 [data-theme=\"dark\"] { ... }"
    return css_vars(light_m.group(1)), css_vars(dark_m.group(1))


# 正文级检查表：前景 × 承载面。paper 是承载面底色变量（仅作 background 用），
# 深色下 paper 比 bg 更亮，ink3 的紧的一侧是 paper —— 只测 bg 会测错对象。
BODY_PAIRS = (
    ("ink", "bg"), ("ink2", "bg"), ("ink3", "bg"),
    ("ink", "paper"), ("ink2", "paper"), ("ink3", "paper"),
    ("rise", "bg"), ("fall", "bg"), ("gold", "bg"), ("accent", "bg"),
)


def _sample_data():
    return {
        "meta": {"h1": "盘后总结 2026-10-20 周二", "title": "主题契约样例",
                  "coverage": "87", "coverage_note": "字段级覆盖：必备 12 项命中 10 项。"},
        "regime": "大势：反弹不追 [nw-001]，等回踩确认 [dp-001]。",
        "stats": [{"k": "标普500", "v": "7690.73 +0.41%", "cls": "g"}],
        "blocks": [
            {"kind": "cards", "h2": "美股持仓｜完整卡片", "cards": [
                {"type": "us", "name": "紫金矿业", "code": "601899.SH · 1500股 成本28.6 · 现价27.4",
                 "chg": "+0.97%", "act": "1500股拿住", "act_tag": "持有",
                 "concl": "量价共振，持有 [dp-002]。",
                 "bull": "铜价上行、净利+123% [nw-002][dp-002]",
                 "bear": "金价失守4115、连跌3日 [dp-003][nw-003]",
                 "risk": "下方看28/27元 [dp-003]",
                 "pos": "站上20日线 [ch-001]",
                 "cons": "分歧在铜价可持续性 [nw-002]",
                 "fals": "跌破27元则减 [dp-003]"}]},
            {"kind": "prose", "h2": "跨报告对账", "paras": ["较今早：反弹不追 [nw-001]"]},
        ],
        "sources": [{"label": "上交所", "url": "https://example.com/a"}],
    }


def render_html(theme=None):
    """渲染一份样例报告。theme=None 时用默认（深色）。"""
    css = CSS_PATH.read_text(encoding="utf-8")
    html = rr.render(_sample_data(), css)
    if theme:
        # 模拟"用户已切到浅色"：只改根元素属性，其余产物字节不动。
        html = html.replace('<html lang="zh" data-theme="dark">',
                            f'<html lang="zh" data-theme="{theme}">', 1)
    return html


def inline_scripts(html):
    """抽出产物里的内联 <script> 体（不含标签本身）。"""
    return [m.group(1) for m in re.finditer(r"<script\b[^>]*>(.*?)</script>", html, re.S)]


# ---------------------------------------------------------------------------
# 1-3 · 默认深色 / 防闪脚本位置 / 存储键名
# ---------------------------------------------------------------------------
class TestThemeDefaultAndScript(unittest.TestCase):
    """默认深色 + 首帧无闪烁 + 存储键名。"""

    def setUp(self):
        self.html = render_html()

    def test_default_theme_is_dark_and_not_light(self):
        """AC-01：根元素主题属性必须是 dark，且产物里没有 light 的默认值。

        强断言两件事：<html> 上确实带 data-theme="dark"；全文不出现
        data-theme="light"（那是"默认浅色"的反面——默认值不能依赖 JS 写入，
        必须是渲染器静态写死）。
        """
        m = re.search(r"<html[^>]*>", self.html)
        self.assertIsNotNone(m, "产物没有 <html> 根标签")
        self.assertIn('data-theme="dark"', m.group(0),
                      f"根元素未静态写死 data-theme=\"dark\"：{m.group(0)}")
        self.assertNotIn('data-theme="light"', self.html,
                         "产物出现 data-theme=\"light\" 默认值——默认值必须静态写死为 dark")

    def test_antiflicker_script_precedes_style_and_body(self):
        """AC-06：内联脚本必须在 <style> 之前、<body> 之前。

        脚本排在 <style> 之后，浏览器会先按 :root 浅色规则解析样式表再执行
        脚本 —— 中间存在一次浅色帧闪动。所以位置不是风格问题，是功能问题。
        """
        scripts = inline_scripts(self.html)
        self.assertTrue(scripts, "产物里没有内联 <script>——防闪脚本丢了")
        body_at = self.html.index("<body")
        style_at = self.html.index("<style")
        for i, s in enumerate(scripts):
            at = self.html.index(s)
            self.assertLess(at, style_at,
                             f"第 {i + 1} 段脚本排在 <style> 之后，会先闪一帧浅色")
            self.assertLess(at, body_at,
                             f"第 {i + 1} 段脚本排在 <body> 之后，首帧主题来不及生效")

    def test_storage_key_is_exactly_dpa_theme(self):
        """AC-04：存储键名必须是 dpa-theme（改键名 = 用户已存的选择全丢）。

        同时守住门禁隔离：键名里不能出现 dp- / nw- / ch- 片段——
        门禁按这些模式统计证据 ID，误计会污染覆盖率。
        """
        scripts = inline_scripts(self.html)
        self.assertTrue(scripts, "产物里没有内联 <script>")
        joined = "\n".join(scripts)
        self.assertIn("localStorage", joined, "脚本里没有 localStorage——主题不会被持久化")
        self.assertIn("'dpa-theme'", joined,
                      "脚本里没有用 'dpa-theme' 这个键名")
        for frag in ("dp-", "nw-", "ch-"):
            self.assertNotIn(frag, joined,
                             f"脚本全文含 {frag} 片段，会被门禁误计为证据 ID")

    def test_single_consolidated_iife(self):
        """主题逻辑必须合并在一段 IIFE 里（蓝图 §3.4）。

        拆成 head 一段 + body 末尾一段：两处逻辑分散，body 那段执行时 head
        那段早已跑完，绑定重复、也让门禁多扫一遍。合成一段后只剩一个入口。
        """
        scripts = inline_scripts(self.html)
        self.assertEqual(len(scripts), 1,
                         f"主题脚本应合并为 1 段，实际 {len(scripts)} 段")
        self.assertIn("(function()", scripts[0], "主题脚本不是 IIFE 形式")


# ---------------------------------------------------------------------------
# 4-6 · 切换控件与门禁隔离
# ---------------------------------------------------------------------------
class TestThemeToggleIsolation(unittest.TestCase):
    """切换控件必须存在、唯一，且不污染门禁。"""

    def setUp(self):
        self.html = render_html()

    def test_toggle_button_exists_exactly_once(self):
        """AC-03：恰有 1 个 id="theme-toggle" 的 <button>，且 type="button"。

        type 必须是 button —— 默认 type 是 submit，点了会提交表单、触发导航，
        主题切换就变成了页面刷新（AC-02 明确要求"不刷新页面"）。
        """
        btns = re.findall(r"<button\b[^>]*id=\"theme-toggle\"[^>]*>", self.html)
        self.assertEqual(len(btns), 1,
                         f"应有且仅有 1 个 id=\"theme-toggle\" 的按钮，实际 {len(btns)} 个")
        tag = btns[0]
        self.assertIn('type="button"', tag, f"切换按钮 type 必须是 button：{tag}")
        self.assertIn('aria-label="切换深浅主题"', tag,
                      f"切换按钮缺 aria-label（纯图标按钮必须有可读名称）：{tag}")
        self.assertIn("class=\"tbtn\"", tag, f"切换按钮缺 tbtn class：{tag}")

    def test_toggle_has_no_visible_text(self):
        """纯图标按钮：剥离标签后可见文本必须为空。

        有可见文字就意味着按钮宽度随主题变化，切换时版式会跳。
        """
        m = re.search(r"<button\b[^>]*id=\"theme-toggle\".*?</button>", self.html, re.S)
        self.assertIsNotNone(m, "找不到 theme-toggle 按钮")
        visible = re.sub(r"<[^>]+>", "", m.group(0)).strip()
        self.assertEqual(visible, "", f"切换按钮不该有可见文本，实际 {visible!r}")

    def test_toggle_and_scripts_do_not_pollute_gate(self):
        """AC-26：控件与脚本全文不含 dp-/nw-/ch-，不含 <details>。

        <details> 尤其致命：门禁靠 <details> 切"信息来源折叠区"，
        控件里多一个 details，报告门的切分就全错位了。
        """
        m = re.search(r"<button\b[^>]*id=\"theme-toggle\".*?</button>", self.html, re.S)
        self.assertIsNotNone(m, "找不到 theme-toggle 按钮")
        btn = m.group(0)
        for frag in ("dp-", "nw-", "ch-"):
            self.assertNotIn(frag, btn, f"切换控件含 {frag} 片段")
        self.assertNotIn("<details", btn, "切换控件含 <details>——会破坏门禁的来源区切分")
        self.assertNotIn("<summary", btn, "切换控件含 <summary>——同上")

        for i, s in enumerate(inline_scripts(self.html)):
            for frag in ("dp-", "nw-", "ch-"):
                self.assertNotIn(frag, s, f"第 {i + 1} 段脚本含 {frag} 片段")
            self.assertNotIn("<details", s, f"第 {i + 1} 段脚本含 <details>")

    def test_no_bare_brackets_in_card_visible_text(self):
        """AC-22：卡片可见文本无裸方括号；data-ev 属性值原样保留。

        证据 ID 靠 data-ev 属性供门禁计数，靠"看不见"供阅读体验。
        两边必须同时成立：属性里留着，正文里不能露。

        作用域是**卡片内**——卡片外的段落（大势 / 跨报告对账）刻意保留原始
        [nw-001] 写法，交给 run_daily 的徽标兜底包成静默上标（脚注序号只在
        卡片内才有对应清单，段落里的编号会指向不存在的条目）。
        """
        body = self.html.split("</head>", 1)[-1]
        ranges = gate._card_ranges(body)
        self.assertTrue(ranges, "产物里没有卡片区间——门禁切分失效，这条断言失去意义")
        for i, (s, e) in enumerate(ranges):
            visible = re.sub(r"<[^>]+>", "", body[s:e])
            for frag in ("[dp-", "[nw-", "[ch-"):
                self.assertNotIn(
                    frag, visible,
                    f"第 {i + 1} 张卡片可见文本里露出裸证据编号 {frag}")
        self.assertIn("data-ev=\"[dp-", self.html,
                      "data-ev 属性里的证据编号丢了——门禁将计不到引用数")


# ---------------------------------------------------------------------------
# 7-11 · CSS 双块与对比度实算
# ---------------------------------------------------------------------------
class TestThemeContrast(unittest.TestCase):
    """深浅两套主题各自实算对比度，正文级必须 ≥4.5:1。"""

    def setUp(self):
        self.css = CSS_PATH.read_text(encoding="utf-8")
        self.light, self.dark = theme_blocks(self.css)

    def test_css_has_both_theme_blocks(self):
        """AC-10：style.css 同时含浅色 :root 块与深色 [data-theme="dark"] 块。"""
        self.assertIn(":root{", self.css.replace(" ", "").replace("\n", "")
                      .replace(":root {", ":root{"), "style.css 缺浅色 :root 块")
        self.assertRegex(self.css, r"\[data-theme=[\"']dark[\"']\]\s*\{",
                         "style.css 缺深色 [data-theme=\"dark\"] 块")
        self.assertTrue(self.light, "浅色块解析为空")
        self.assertTrue(self.dark, "深色块解析为空")

    def test_dark_theme_body_contrast(self):
        """AC-08：深色块正文级全部 ≥4.5:1，且 ink3 on paper ≥4.5:1。"""
        for fg, bg in BODY_PAIRS:
            self.assertIn(fg, self.dark, f"深色块缺变量 --{fg}")
            self.assertIn(bg, self.dark, f"深色块缺变量 --{bg}")
            r = ratio(self.dark[fg], self.dark[bg])
            self.assertGreaterEqual(
                r, 4.5,
                f"深色 --{fg} on --{bg} = {r:.2f}:1 < 4.5:1（{self.dark[fg]} on {self.dark[bg]}）")
        # 单独点名：深色下 paper 比 bg 亮，ink3 的紧的一侧是 paper
        r = ratio(self.dark["ink3"], self.dark["paper"])
        self.assertGreaterEqual(r, 4.5, f"深色 --ink3 on --paper = {r:.2f}:1 < 4.5:1")

    def test_light_theme_body_contrast(self):
        """AC-09：浅色块正文级全部 ≥4.5:1，且 ink3 on paper ≥4.5:1。"""
        for fg, bg in BODY_PAIRS:
            self.assertIn(fg, self.light, f"浅色块缺变量 --{fg}")
            self.assertIn(bg, self.light, f"浅色块缺变量 --{bg}")
            r = ratio(self.light[fg], self.light[bg])
            self.assertGreaterEqual(
                r, 4.5,
                f"浅色 --{fg} on --{bg} = {r:.2f}:1 < 4.5:1（{self.light[fg]} on {self.light[bg]}）")
        r = ratio(self.light["ink3"], self.light["paper"])
        self.assertGreaterEqual(r, 4.5, f"浅色 --ink3 on --paper = {r:.2f}:1 < 4.5:1")

    def test_light_values_match_v270_exactly(self):
        """R-03：浅色 12 值与 v2.7.0 逐一相等（防深色改造误改浅色）。"""
        for name, want in V270_LIGHT.items():
            self.assertIn(name, self.light, f"浅色块缺变量 --{name}")
            self.assertEqual(self.light[name], want,
                             f"浅色 --{name} 被改成了 {self.light[name]}，"
                             f"v2.7.0 原值是 {want}——浅色是已验收的版式基准，不许动")

    def test_warn_vars_exist_in_both_themes_and_pass_contrast(self):
        """AC-59：4 个 --warn-* 变量深浅两块都有取值，且告警前景 on 告警底 ≥4.5:1。

        告警组是独立的一套色：拿 --rise 当告警底色，深色下正文对比度只有
        1.51:1（红底上放浅色字），是典型的反色失败。
        """
        for name in ("warn-bg", "warn-fg", "warn-strong", "warn-rule"):
            self.assertIn(name, self.light, f"浅色块缺 --{name}")
            self.assertIn(name, self.dark, f"深色块缺 --{name}")
        for label, vars_map in (("浅色", self.light), ("深色", self.dark)):
            for fg in ("warn-fg", "warn-strong"):
                r = ratio(vars_map[fg], vars_map["warn-bg"])
                self.assertGreaterEqual(
                    r, 4.5,
                    f"{label} --{fg} on --warn-bg = {r:.2f}:1 < 4.5:1")
        # 变量名集合必须完全对称——只加到一块时，另一块会静默回落到无色
        self.assertEqual(set(self.light), set(self.dark),
                         "深浅两块的变量名集合不一致——差集非空说明某块漏改，"
                         "漏改的那块会悄悄回落到 :root 的浅色值")


# ---------------------------------------------------------------------------
# 12-14 · 注入元素取色 / meta 声明 / 主题切换不重排版式
# ---------------------------------------------------------------------------
class TestThemeInjectedElementsAndMeta(unittest.TestCase):
    """注入元素取色走 CSS 变量；meta 声明与深色 token 实值相等。"""

    def setUp(self):
        self.html = render_html()
        self.css = CSS_PATH.read_text(encoding="utf-8")
        self.light, self.dark = theme_blocks(self.css)

    def test_injected_elements_use_css_vars(self):
        """AC-28：横幅 / 页脚 / 徽标取色一律 var(--...)，不残留写死浅色值。"""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "r.html"
            p.write_text(self.html, encoding="utf-8")
            rd._apply_degrade(p, ["缺口一", "缺口二"], 0.62)
            rd._inject_version_footer(p, 0.62, "PASS")
            text = p.read_text(encoding="utf-8")

        banner = re.search(r"<div id=\"degrade-banner\".*?<!--/degrade-->", text, re.S)
        self.assertIsNotNone(banner, "没找到降级横幅")
        self.assertIn("var(--warn-bg)", banner.group(0),
                      "降级横幅背景未改用 var(--warn-bg)")
        self.assertNotIn("var(--rise)", banner.group(0),
                         "降级横幅背景用了 var(--rise)——那是涨跌语义色，"
                         "深色下当底色对比度只有 1.51:1")

        footer = re.search(r"<footer id=\"daily-version-footer\".*?</footer>", text, re.S)
        self.assertIsNotNone(footer, "没找到版本页脚")
        self.assertIn("var(--ink3)", footer.group(0), "版本页脚未改用 var(--ink3)")

        badge = rd.BADGE_CSS
        self.assertIn("var(--ink4)", badge, "徽标未改用 var(--ink4)")
        self.assertIn("var(--gold)", badge, "徽标未改用 var(--gold)")

        for hexv in FORBIDDEN_LIGHT_HEX:
            self.assertNotIn(hexv, banner.group(0), f"降级横幅残留写死浅色值 {hexv}")
            self.assertNotIn(hexv, footer.group(0), f"版本页脚残留写死浅色值 {hexv}")
            self.assertNotIn(hexv, badge, f"徽标样式残留写死浅色值 {hexv}")

    def test_meta_declarations_match_dark_token(self):
        """AC-07：color-scheme 同时含 dark 与 light；theme-color == 深色 --bg 实值。

        theme-color 要与深色底色 token **逐字相等**（不是"看起来接近"），
        所以这里从 style.css 解析出的 --bg 取期望值，而不是写死一个十六进制。
        """
        cs = re.search(r'<meta name="color-scheme" content="([^"]*)"', self.html)
        self.assertIsNotNone(cs, "缺 meta[name=color-scheme]")
        self.assertIn("dark", cs.group(1), "color-scheme 未声明 dark 支持")
        self.assertIn("light", cs.group(1), "color-scheme 未声明 light 支持")

        tc = re.findall(r'<meta name="theme-color" content="([^"]*)"', self.html)
        self.assertTrue(tc, "缺 meta[name=theme-color]")
        self.assertEqual(tc[0], self.dark["bg"],
                         f"theme-color = {tc[0]}，与深色 --bg 实值 "
                         f"{self.dark['bg']} 不等——地址栏颜色会与实际底色脱节")
        # 单条无 media：两条带 media 的写法会让脚本找不到可改写的目标
        self.assertEqual(len(re.findall(r'<meta name="theme-color"', self.html)), 1,
                         "theme-color 应为单条无 media（多写会导致脚本改写目标歧义）")

    def test_theme_switch_does_not_relayout(self):
        """AC-18：深浅两版产物的卡片结构序列完全一致。

        切换只改根元素上的 data-theme，不该动版式。卡片区间数与标题文本
        逐个相等，才说明主题没碰到结构。
        """
        dark_html = render_html("dark")
        light_html = render_html("light")

        def card_shape(html):
            return re.findall(r'<div class="card[^"]*">', html)

        def titles(html):
            return re.findall(r"<h([1-3])[^>]*>([\s\S]*?)</h\1>", html)

        self.assertTrue(card_shape(dark_html), "深色产物里没有卡片")
        self.assertEqual(card_shape(dark_html), card_shape(light_html),
                         "深浅两版的卡片结构序列不一致——切换主题动了版式")
        self.assertEqual(titles(dark_html), titles(light_html),
                         "深浅两版的标题序列不一致——切换主题动了版式")


if __name__ == "__main__":
    unittest.main()
