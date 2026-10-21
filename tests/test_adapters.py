# -*- coding: utf-8 -*-
"""数据源适配层与降级交付的回归测试（全离线，不联网）。

为什么必须离线：适配层一旦联网才能测，CI 就会因为某个行情源抽风而红，
最后大家开始忽略红色——门禁就废了。这里只测纯函数与文件级行为，
真实取数由 docs/数据源评估 里的实测矩阵负责。

覆盖的坑（都是实际踩过的）：
  · 000300 是沪指数，不能落 sz 前缀（落错会返回空或错票）
  · 920xxx 是北交所新号段，必须先于 9x 判断
  · 港股 5 位补零
  · 东财 secid 前缀：沪 1 / 深 0 / 港股 116
  · 降级横幅重复调用不能叠加
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import adapters  # noqa: E402
import notify  # noqa: E402
import run_daily  # noqa: E402
from adapters import cboe, eastmoney, tencent  # noqa: E402


class TestTencentPrefix(unittest.TestCase):
    def test_a_share(self):
        self.assertEqual(tencent._sh_sz_prefix("601899"), "sh601899")
        self.assertEqual(tencent._sh_sz_prefix("000001"), "sz000001")
        self.assertEqual(tencent._sh_sz_prefix("300054"), "sz300054")

    def test_sh_index_not_sz(self):
        # 000300 沪深300 属沪市，落 sz 会拿到空数据
        self.assertEqual(tencent._sh_sz_prefix("000300"), "sh000300")

    def test_bj_before_9x(self):
        # 92 开头是北交所新号段，不能按 9x 判成沪市
        self.assertEqual(tencent._sh_sz_prefix("920982"), "bj920982")
        self.assertEqual(tencent._sh_sz_prefix("830799"), "bj830799")

    def test_hk_pad(self):
        self.assertEqual(tencent._hk_prefix("700"), "hk00700")
        self.assertEqual(tencent._hk_prefix("00700.HK"), "hk00700")


class TestRangePct(unittest.TestCase):
    def test_mid(self):
        self.assertEqual(tencent._range_pct(15, 20, 10), 50.0)

    def test_bounds(self):
        self.assertEqual(tencent._range_pct(20, 20, 10), 100.0)
        self.assertEqual(tencent._range_pct(10, 20, 10), 0.0)

    def test_invalid(self):
        self.assertIsNone(tencent._range_pct(15, 10, 20))   # 高低颠倒
        self.assertIsNone(tencent._range_pct(0, 20, 10))     # 无价
        self.assertIsNone(tencent._range_pct(15, 20, 20))    # 区间为 0


class TestEastmoneySecid(unittest.TestCase):
    def test_a_share(self):
        self.assertEqual(eastmoney._secid("A股", "601899.SH"), "1.601899")
        self.assertEqual(eastmoney._secid("A股", "002156.SZ"), "0.002156")

    def test_hk(self):
        self.assertEqual(eastmoney._secid("港股", "00700.HK"), "116.00700")

    def test_us_not_supported(self):
        # 美股故意不支持：secid 前缀 105/106 靠猜会取错票
        self.assertIsNone(eastmoney._secid("美股", "NVDA"))


class TestChainConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._old = os.environ.get("DAILY_CONFIG_DIR")
        os.environ["DAILY_CONFIG_DIR"] = self.tmp
        adapters.reset_config_cache()

    def tearDown(self):
        if self._old is None:
            os.environ.pop("DAILY_CONFIG_DIR", None)
        else:
            os.environ["DAILY_CONFIG_DIR"] = self._old
        adapters.reset_config_cache()

    def test_default_chain_without_config(self):
        self.assertEqual(adapters._chain("snapshot", "A股"), ["tencent", "eastmoney"])
        self.assertEqual(adapters._chain("kline", "A股"), ["tencent", "baostock"])
        self.assertEqual(adapters._chain("kline", "美股"), ["sina"])

    def test_config_overrides_chain(self):
        p = Path(self.tmp) / "data-sources.json"
        p.write_text(json.dumps({"kline": {"A股": ["baostock"]}}), encoding="utf-8")
        adapters.reset_config_cache()
        self.assertEqual(adapters._chain("kline", "A股"), ["baostock"])

    def test_unknown_source_is_dropped(self):
        p = Path(self.tmp) / "data-sources.json"
        p.write_text(json.dumps({"kline": {"A股": ["nope", "baostock"]}}), encoding="utf-8")
        adapters.reset_config_cache()
        self.assertEqual(adapters._chain("kline", "A股"), ["baostock"])

    def test_broken_config_falls_back(self):
        p = Path(self.tmp) / "data-sources.json"
        p.write_text("{not json", encoding="utf-8")
        adapters.reset_config_cache()
        # 配置坏了退回默认链，而不是整批停摆
        self.assertEqual(adapters._chain("snapshot", "港股"), ["tencent", "eastmoney"])

    def test_disable_source(self):
        p = Path(self.tmp) / "data-sources.json"
        p.write_text(json.dumps({"sources": {"tencent": {"enabled": False}}}),
                     encoding="utf-8")
        adapters.reset_config_cache()
        self.assertFalse(adapters.enabled("tencent"))
        self.assertTrue(adapters.enabled("sina"))


class TestOsiParse(unittest.TestCase):
    def test_parse(self):
        m = cboe._OSI_RE.match("NVDA261021C00120000")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "NVDA")
        self.assertEqual(m.group(3), "C")

    def test_reject_garbage(self):
        self.assertIsNone(cboe._OSI_RE.match("NOT-AN-OPTION"))


class TestDegradeBanner(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.html = Path(self.tmp) / "r.html"
        self.html.write_text(
            '<!doctype html><html><head><title>t</title></head>'
            '<body><div class="wrap"><h1>报告</h1></div></body></html>',
            encoding="utf-8")

    def test_banner_inserted_at_top(self):
        n = run_daily._apply_degrade(self.html, ["缺新闻", "覆盖率低"], 0.57)
        text = self.html.read_text(encoding="utf-8")
        self.assertEqual(n, 2)
        self.assertIn('id="degrade-banner"', text)
        self.assertIn("数据不全", text)
        # 必须在 <body> 之后、正文之前
        self.assertLess(text.index("degrade-banner"), text.index("<h1>"))

    def test_idempotent(self):
        run_daily._apply_degrade(self.html, ["a"], 0.5)
        run_daily._apply_degrade(self.html, ["b"], 0.5)
        text = self.html.read_text(encoding="utf-8")
        self.assertEqual(text.count('id="degrade-banner"'), 1)

    def test_more_than_eight_collapsed(self):
        run_daily._apply_degrade(self.html, [f"问题{i}" for i in range(12)], 0.3)
        text = self.html.read_text(encoding="utf-8")
        self.assertIn("另有 4 项", text)

    def test_html_escaped(self):
        run_daily._apply_degrade(self.html, ["<script>x</script>"], 0.5)
        text = self.html.read_text(encoding="utf-8")
        self.assertNotIn("<script>x</script>", text)


class TestNotifyBody(unittest.TestCase):
    def test_degraded_first_line_says_gap(self):
        title, subtitle, body = notify._fmt_report_body("post", 57.1, True, "动作：持有", 42)
        self.assertIn("盘后", title)
        self.assertIn("数据不全", subtitle)
        self.assertTrue(body.startswith("数据不全"))

    def test_pass_has_no_warning(self):
        _t, subtitle, body = notify._fmt_report_body("pre", 92.0, False, "", 0)
        self.assertNotIn("⚠", subtitle)
        self.assertTrue(body.startswith("数据完整"))

    def test_body_length_capped(self):
        _t, _s, body = notify._fmt_report_body("pre", 90, False, "x" * 2000, 0)
        self.assertLessEqual(len(body), notify.MAX_BODY)


if __name__ == "__main__":
    unittest.main()
