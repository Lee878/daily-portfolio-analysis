#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v2.2.3 修复的回归用例：每条都对应一个实测过的原始缺陷。

覆盖：
  R1 Windows 文件名反斜杠（fetch/gate 两处 safe_name 一致）
  R2 3 列基金表解析（两个解析器结果一致，不再漏场外基金）
  R3 报告切片不被 HTML 属性里的票名带偏
  R4 覆盖率分母不信证据文件里的 planned
  R5 status=verified 但值不是数字 → 拦截
  R6 gate --allow-degraded 真的放行（旧版恒返回 10）
  R7 --report-root 缺省按 holdings 同级推导
  R8 akshare 元 → 亿元/万元 归一
  R9 reuse 复用条目补编号
"""
import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import fetch_data as fd  # noqa: E402
import gate_check as gc  # noqa: E402
import reuse_evidence as re_mod  # noqa: E402
import run_daily as rd  # noqa: E402

THREE_COL_HOLDINGS = """# 持仓档案
## 基金持仓（蚂蚁财富）
| 基金名称 | 金额(元) | 持有收益 |
|---|---|---|
| 华安黄金ETF联接C（000217） | 17,714.72 | -1,751.86 |
| 帮你投 \\| 全球精选100（ADVISORY） | 213.59 | +23.97 |

## A股持仓
| 名称 | 代码 | 持仓数量 | 成本价 | 现价 |
|---|---|---|---|---|
| 紫金矿业 | 601899 | 1000 | 28.5 | 31.2 |
"""


class TestR1SafeName(unittest.TestCase):
    def test_backslash_and_windows_chars(self):
        raw = "帮你投 \\-全球精选100（ADVISORY）"
        for mod in (fd, gc):
            name = mod.safe_name(raw)
            self.assertNotIn("\\", name, f"{mod.__name__} 仍保留反斜杠")
            for ch in '*?"<>|':
                self.assertNotIn(ch, name)
        self.assertEqual(fd.safe_name("601899.SH"), "601899_SH")
        self.assertEqual(fd.safe_name(raw), gc.safe_name(raw))


class TestR2FundParsing(unittest.TestCase):
    def test_three_column_fund_table(self):
        hs_gate = gc.parse_holdings(THREE_COL_HOLDINGS)
        hs_fetch = fd.parse_holdings(THREE_COL_HOLDINGS)
        funds_gate = {h["ticker"] for h in hs_gate if h["market"] == "基金"}
        funds_fetch = {h["ticker"] for h in hs_fetch if h["market"] == "基金"}
        self.assertTrue(any("华安黄金" in t for t in funds_gate))
        self.assertEqual(funds_gate, funds_fetch, "两个解析器的基金集合必须一致")

    def test_parsers_agree_on_holdings(self):
        g = {(h["market"], h["ticker"]) for h in gc.parse_holdings(THREE_COL_HOLDINGS)}
        f = {(h["market"], h["ticker"]) for h in fd.parse_holdings(THREE_COL_HOLDINGS)}
        self.assertEqual(g, f, "同一份 holdings.md 两个解析器不得给出不同持仓")


class TestR3SliceSections(unittest.TestCase):
    def test_attribute_names_do_not_hijack_card(self):
        holdings = [
            {"name": "紫金矿业", "ticker": "601899.SH", "market": "A股"},
            {"name": "中芯国际", "ticker": "00981.HK", "market": "港股"},
        ]
        text = (
            '<div class="card"><h3>紫金矿业 <span class="sub">601899.SH</span></h3>'
            '<p class="g">多方：铜价上行 <span class="rb p1" '
            'title="P1 · 中芯国际官方">[nw-001]</span></p>'
            '<p class="r">空方：成本上升 [nw-003]</p></div>'
            '<div class="card"><h3>中芯国际 <span class="sub">00981.HK</span></h3>'
            '<p class="r">空方：扩产折旧 [nw-004]</p></div>'
        )
        sec = gc._slice_sections(text, holdings)
        self.assertIn("[nw-003]", sec.get("601899.SH", ""), "紫金空方行被错切走了")
        self.assertNotIn("[nw-003]", sec.get("00981.HK", ""), "中芯切片混入了紫金内容")


class TestR4CoverageDenominator(unittest.TestCase):
    def test_planned_deletion_cannot_inflate(self):
        ev = {
            "market": "美股", "instrument": "STOCK",
            "planned": {"news": [], "chain": []},      # 恶意/误删 planned
            "data_points": [],
            "news": [
                {"id": "nw-001", "headline": "公司发布新产品线公告",
                 "url": "https://a.com/news/123456", "evidence_level": "P1",
                 "impact": "bullish", "status": "verified"},
                {"id": "nw-002", "headline": "机构下调目标价提示风险",
                 "url": "https://b.com/news/654321", "evidence_level": "P1",
                 "impact": "bearish", "status": "verified"},
            ],
            "chain_notes": [{"id": "ch-001", "evidence_level": "P2",
                             "status": "verified"}],
        }
        pct, _ = gc.coverage(ev, "pre")
        self.assertLess(pct, 0.50, "分母仍取自文件 planned，覆盖率可被刷高")

    def test_expected_plan_per_market(self):
        self.assertEqual(gc.expected_plan({"market": "美股"}, "pre")["flow"],
                         ["put_call_or_inst"])
        self.assertIn("north_south_flow",
                      gc.expected_plan({"market": "A股"}, "pre")["flow"])
        self.assertIn("nav_latest",
                      gc.expected_plan({"market": "基金"}, "pre")["technical"])


class TestR5NumericVerified(unittest.TestCase):
    def test_string_verified_is_blocked(self):
        ev = {"instrument": "STOCK", "market": "A股", "data_points": [
            {"id": "dp-001", "dimension": "flow", "field": "main_net_inflow",
             "value": "暂无数据，稍后补", "status": "verified", "source": "某处"}]}
        problems = gc.validate_authenticity(ev)
        self.assertTrue(any("不是数字" in p for p in problems), problems)

    def test_text_field_allowed(self):
        ev = {"instrument": "FUND", "market": "基金", "data_points": [
            {"id": "dp-001", "dimension": "fundamental", "field": "top_holdings",
             "value": "半导体设备", "status": "verified", "source": "季报"}]}
        self.assertEqual(gc.validate_authenticity(ev), [])


def _degraded_fixture(root: Path):
    """只给价格+新闻+产业链（覆盖率 <50% 但无 problems）的合法降级样本。"""
    ev_dir = root / "evidence"
    ev_dir.mkdir(parents=True, exist_ok=True)
    dps = [{"id": "dp-001", "dimension": "technical", "field": "price_last",
            "label": "最新价", "value": 170, "status": "verified",
            "evidence_level": "P1", "source": "test", "source_url": ""},
           {"id": "dp-002", "dimension": "technical", "field": "day_change_pct",
            "label": "当日涨跌幅%", "value": 0.6, "status": "verified",
            "evidence_level": "P1", "source": "test", "source_url": ""}]
    gaps = []
    for i, (f, dim) in enumerate(
            [("ma5", "technical"), ("pe_ttm", "fundamental"),
             ("main_net_inflow", "flow")], 3):
        dps.append({"id": f"dp-{i:03d}", "dimension": dim, "field": f,
                    "label": f, "value": None, "status": "missing",
                    "evidence_level": "P3", "source": "", "source_url": ""})
        gaps.append(f"{f} 未取到")
    ev = {"schema_version": "1.0", "report_date": "2026-10-21", "session": "pre",
          "ticker": "AAPL", "name": "苹果", "market": "美股", "instrument": "STOCK",
          "data_points": dps,
          "news": [{"id": "nw-001", "headline": "苹果新品发布获市场关注",
                    "url": "https://example.com/news/123456",
                    "evidence_level": "P1", "status": "verified", "impact": "bullish"},
                   {"id": "nw-002", "headline": "机构提示供应链成本上升",
                    "url": "https://reuters.com/article/789012",
                    "evidence_level": "P2", "status": "verified", "impact": "bearish"}],
          "chain_notes": [{"id": "ch-001", "evidence_level": "P2",
                           "status": "verified", "lifecycle": "成熟期"}],
          "gaps": gaps}
    (ev_dir / "2026-10-21_pre_AAPL.json").write_text(
        json.dumps(ev, ensure_ascii=False), encoding="utf-8")
    (root / "holdings.md").write_text(
        "# 持仓\n## 美股持仓\n| 名称 | 代码 | 持仓数量 | 成本价 | 现价 |\n"
        "|---|---|---|---|---|\n| 苹果 | AAPL | 10 | 150 | 170 |\n", encoding="utf-8")
    return root / "holdings.md"


class TestR6AllowDegraded(unittest.TestCase):
    def _args(self, holdings, root, allow):
        return argparse.Namespace(holdings=str(holdings), report_root=str(root),
                                  date="2026-10-21", session="pre",
                                  allow_degraded=allow, no_network=True)

    def test_allow_degraded_returns_pass(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            holdings = _degraded_fixture(root)
            self.assertEqual(rd.do_gate(self._args(holdings, root, False)),
                             rd.EXIT_EV_DEGRADED)
            self.assertEqual(rd.do_gate(self._args(holdings, root, True)),
                             rd.EXIT_PASS, "--allow-degraded 必须放行")


class TestR7PathDefaults(unittest.TestCase):
    def _holdings(self, d):
        h = Path(d) / "holdings.md"
        h.write_text("# 持仓\n## A股持仓\n| 名称 | 代码 | 数量 | 成本 | 现价 |\n"
                     "|---|---|---|---|---|\n| a | 601899 | 1 | 1 | 1 |\n",
                     encoding="utf-8")
        return h

    def test_report_root_prefers_portable_layout(self):
        """便携模式：holdings 同级已有 daily-reports/ 时用它（拷走整个目录即可用）。"""
        with tempfile.TemporaryDirectory() as d:
            h = self._holdings(d)
            (Path(d) / "daily-reports").mkdir()
            root, hh = rd.resolve_paths(argparse.Namespace(holdings=str(h),
                                                           report_root=None))
            self.assertEqual(hh, h)
            self.assertEqual(root, Path(d) / "daily-reports")

    def test_report_root_defaults_to_repo_data_dir(self):
        """标准布局：没有同级 daily-reports 时落在 <仓库>/data/daily-reports。"""
        import paths as paths_mod
        with tempfile.TemporaryDirectory() as d:
            h = self._holdings(d)
            root, _ = rd.resolve_paths(argparse.Namespace(holdings=str(h),
                                                          report_root=None))
            self.assertEqual(root, paths_mod.report_root())


class TestR8Units(unittest.TestCase):
    def test_akshare_units_normalized(self):
        self.assertAlmostEqual(fd._norm_market_cap(7.7784e11), 7778.4, places=1)
        self.assertAlmostEqual(fd._norm_net_inflow(2.4e8), 24000.0, places=1)
        self.assertIn("亿元", fd._field_unit("market_cap", "CNY"))
        self.assertIn("万元", fd._field_unit("main_net_inflow", "CNY"))

    def test_normalized_values_pass_gate(self):
        ev = {"instrument": "STOCK", "market": "A股", "data_points": [
            {"id": "dp-001", "field": "price_last", "value": 29.79,
             "status": "verified", "source": "akshare"},
            {"id": "dp-002", "field": "day_change_pct", "value": -0.43,
             "status": "verified", "source": "akshare"},
            {"id": "dp-003", "field": "market_cap",
             "value": fd._norm_market_cap(7.7784e11),
             "status": "verified", "source": "akshare"},
            {"id": "dp-004", "field": "main_net_inflow",
             "value": fd._norm_net_inflow(2.4e8),
             "status": "verified", "source": "akshare"}]}
        self.assertEqual(gc.validate_authenticity(ev), [])


class TestR9ReuseRenumber(unittest.TestCase):
    def test_appended_points_get_ids(self):
        dst = {"ticker": "X", "session": "noon", "data_points": [
            {"id": "dp-001", "field": "price_last", "value": 1, "status": "verified"}],
            "chain_notes": []}
        src = {"ticker": "X", "session": "pre", "data_points": [
            {"id": "dp-009", "field": "dividend_yield", "value": 2.1,
             "status": "verified", "source": "s"}], "chain_notes": []}
        re_mod.merge(src, dst)
        re_mod.renumber_data_points(dst)
        ids = [p.get("id") for p in dst["data_points"]]
        self.assertTrue(all(ids), f"存在空 ID：{ids}")
        self.assertEqual(ids[0], "dp-001", "已有 ID 不应被重排")
        self.assertEqual(len(set(ids)), len(ids), "ID 不得重复")


class TestR10Preflight(unittest.TestCase):
    """preflight 的两处老 bug：ID 只取到前缀、要求正文手写"多方"。"""

    def setUp(self):
        import preflight as pf
        self.pf = pf

    def test_ids_in_returns_full_ids(self):
        self.assertEqual(self.pf.ids_in("利好 [dp-001] 与 [nw-012]"),
                         ["dp-001", "nw-012"])

    def test_bull_bear_fields_are_enough(self):
        card = {"type": "us", "name": "谷歌-C", "bull": "云AI加速 [nw-001]",
                "bear": "监管扰动 [nw-002]", "concl": "x [dp-001] [dp-002]"}
        problems = []
        self.pf.check_card(card, problems, "pre")
        self.assertFalse([p for p in problems if "缺" in p and "方" in p], problems)

    def test_missing_bull_flagged(self):
        card = {"type": "us", "name": "X", "bear": "风险 [nw-002]"}
        problems = []
        self.pf.check_card(card, problems, "pre")
        self.assertTrue(any("bull" in p for p in problems))


class TestR11BriefSemantics(unittest.TestCase):
    """v2.4.0：关注库缺省**全部深度分析**；只有进 brief 名单的才降级。

    旧版是"深度白名单"（未列出=简列），配错一次就把 7 只美股关注票静默降级了。
    """

    def test_default_is_deep(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(gc.brief_set(Path(d), "post"), set())
            self.assertEqual(fd.load_brief(Path(d), "post"), frozenset())

    def test_explicit_brief_downgrades(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "watchlist_brief.json").write_text(
                json.dumps({"post": ["SNDK"]}), encoding="utf-8")
            self.assertEqual(gc.brief_set(root, "post"), {"SNDK"})
            self.assertEqual(gc.brief_set(root, "pre"), set())
            self.assertEqual(fd.load_brief(root, "post"), frozenset({"SNDK"}))

    def test_cli_override_wins(self):
        import os
        os.environ["DAILY_BRIEF_TICKERS"] = "NVDA, TSM"
        try:
            self.assertEqual(gc.brief_set(Path("."), "post"), {"NVDA", "TSM"})
        finally:
            os.environ.pop("DAILY_BRIEF_TICKERS", None)

    def test_nearest_file_wins_over_config(self):
        """report_root 内的 brief 优先，避免测试/临时目录被真实 config 串扰。"""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "watchlist_brief.json").write_text(
                json.dumps({"post": ["AAPL"]}), encoding="utf-8")
            self.assertEqual(gc.brief_set(root, "post"), {"AAPL"})


    def test_no_dead_tool_names_in_agent_facing_files(self):
        """agent 面向的文件里不许再出现已不存在的工具名。

        v2.6.0 全栈 review 实测：SKILL.md / references / scripts / 定时任务模板里
        散落着 `seed_finance_lookup` 与 `general_search`——这两个工具在当前的
        工具集里根本不存在（行情走 NeoData MCP，新闻走 WebSearch）。
        模型读到这种指令只有两种结果：空转重试，或者编一个"我已查询"。

        只查 agent 真正会读的那几处；`docs/` 里的历史报告与 `.archive/` 是
        存档，允许保留旧名，不算违规。
        """
        root = Path(__file__).resolve().parent.parent
        dead = ("seed_finance_lookup", "general_search")
        targets = [root / "SKILL.md", root / "README.md"]
        for pat in ("references/*.md", "assets/**/*.md", "scripts/*.py"):
            targets.extend(root.glob(pat))

        offenders = []
        for f in targets:
            if not f.is_file():
                continue
            text = f.read_text(encoding="utf-8", errors="replace")
            for name in dead:
                if name in text:
                    offenders.append(f"{f.relative_to(root).as_posix()} → {name}")
        self.assertEqual(
            offenders, [],
            "这些文件还在教模型调用不存在的工具：\n  " + "\n  ".join(offenders),
        )


    def test_prompts_have_no_frozen_channel_or_manual_push(self):
        """三份时段 prompt 不许再出现「邮箱发送」与「手动跑 notify.py」。

        这两种错误都很贵：邮件通道 D-02 已冻结（且 Agent 邮箱 not_bound 发不出），
        手动跑 notify.py 会和 `run_daily report` 的自动推送叠加成两条。
        定时任务只指向这些文件，文件一错，每天错三次。
        """
        root = Path(__file__).resolve().parent.parent
        banned = ("邮箱工具", "config/delivery.json", "notify.py --session")
        offenders = []
        for f in sorted((root / "assets" / "workbuddy-prompts").glob("*.md")):
            text = f.read_text(encoding="utf-8", errors="replace")
            for phrase in banned:
                if phrase in text:
                    offenders.append(f"{f.name} → {phrase}")
        self.assertEqual(offenders, [],
                         "prompt 里还有过期通道指令：\n  " + "\n  ".join(offenders))


if __name__ == "__main__":
    unittest.main()
