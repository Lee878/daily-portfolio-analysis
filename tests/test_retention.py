#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
留存改造的回归测试（v2.10.3）：
  - fetch 重跑不丢 agent 补的新闻/产业链（news/chain_notes 保护）；
  - report 运行前归档旧产物到 archive 快照（固定名永远最新）；
  - 每次运行追加一行 run-log.csv。

运行：cd scripts && python -m unittest tests.test_retention -v
"""
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import fetch_data  # noqa: E402
import run_daily as rd  # noqa: E402


class PreserveAgentContentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = Path(self.tmp.name) / "2026-10-28_post_MU.json"

    def tearDown(self):
        self.tmp.cleanup()

    def _old_ev(self, news=(), chain=()):
        return {
            "schema_version": "1.0", "report_date": "2026-10-28",
            "session": "post", "ticker": "MU", "name": "美光科技",
            "market": "美股", "instrument": "STOCK", "planned": {},
            "data_points": [], "news": list(news),
            "chain_notes": list(chain), "gaps": [],
        }

    def test_preserves_news_and_chain_notes(self):
        """旧证据里 agent 补的新闻/产业链，重跑 fetch 后必须还在。"""
        old = self._old_ev(
            news=[{"id": "nw-001", "headline": "存储涨价", "impact": "bullish"}],
            chain=[{"id": "ch-001", "sector": "存储"}])
        self.p.write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
        fresh = self._old_ev()  # 脚本重建的骨架：news/chain 为空
        fetch_data._preserve_agent_content(self.p, fresh)
        self.assertEqual(len(fresh["news"]), 1)
        self.assertEqual(len(fresh["chain_notes"]), 1)

    def test_keeps_empty_when_old_empty(self):
        """旧文件 news 为空时，不应把空回填成别的（骨架保持空）。"""
        self.p.write_text(json.dumps(self._old_ev(), ensure_ascii=False),
                          encoding="utf-8")
        fresh = self._old_ev()
        fresh["news"] = []  # 仍为空
        fetch_data._preserve_agent_content(self.p, fresh)
        self.assertEqual(fresh["news"], [])
        self.assertEqual(fresh["chain_notes"], [])

    def test_missing_or_corrupt_file_is_noop(self):
        """旧文件不存在或损坏，保护逻辑不得抛异常。"""
        fresh = self._old_ev()
        fetch_data._preserve_agent_content(self.p, fresh)  # 不存在
        self.p.write_text("{not-valid-json", encoding="utf-8")
        fetch_data._preserve_agent_content(self.p, fresh)  # 损坏
        self.assertEqual(fresh["news"], [])


class SnapshotRunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ev = self.root / "evidence"
        self.ev.mkdir(parents=True)
        self.html = self.root / "2026-10-28-盘后总结-可视化.html"
        self.html.write_text("<html>旧报告</html>", encoding="utf-8")
        self.recon = self.root / "recon-2026-10-28-post.md"
        self.recon.write_text("# 旧对账", encoding="utf-8")
        self.data = self.root / "data-2026-10-28-post.json"
        self.data.write_text('{"meta":{}}', encoding="utf-8")
        (self.ev / "2026-10-28_post_MU.json").write_text('{"ticker":"MU"}', encoding="utf-8")
        (self.ev / "2026-10-28_post_GOOG.json").write_text('{"ticker":"GOOG"}', encoding="utf-8")
        (self.ev / "2026-10-28_pre_MU.json").write_text('{"ticker":"MU-pre"}', encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_snapshot_copies_old_artifacts_and_scoped_evidence(self):
        snap = rd._snapshot_run(self.root, "2026-10-28", "post", "20261028-223000",
                                self.html, self.recon, self.data)
        self.assertTrue((snap / "2026-10-28-盘后总结-可视化.html").exists())
        self.assertTrue((snap / "recon-2026-10-28-post.md").exists())
        self.assertTrue((snap / "data-2026-10-28-post.json").exists())
        # evidence 只复制本次 session 的文件，不复制 pre 的
        ev = snap / "evidence"
        self.assertTrue((ev / "2026-10-28_post_MU.json").exists())
        self.assertTrue((ev / "2026-10-28_post_GOOG.json").exists())
        self.assertFalse((ev / "2026-10-28_pre_MU.json").exists())

    def test_snapshot_tolerates_missing_optional(self):
        """recon/data 为 None 或不存在时，快照不抛异常、仍能归档 HTML。"""
        snap = rd._snapshot_run(self.root, "2026-10-28", "post", "20261028-223001",
                                self.html, None, None)
        self.assertTrue((snap / "2026-10-28-盘后总结-可视化.html").exists())
        self.assertFalse((snap / "recon-2026-10-28-post.md").exists())


class RunLogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _log_rows(self):
        p = self.root / "run-log.csv"
        with open(p, "r", encoding="utf-8-sig", newline="") as f:
            return list(csv.reader(f))

    def test_appends_rows_with_header(self):
        snap = self.root / "archive" / "2026-10-28" / "20261028-223000"
        rd._append_run_log(self.root, "2026-10-28", "20261028-223000", "post",
                           0.834, "PASS", Path("a.html"), Path("r.md"),
                           Path("d.json"), snap)
        rd._append_run_log(self.root, "2026-10-28", "20261028-223005", "post",
                           0.409, "DEGRADED", Path("b.html"), None, None, snap)
        rows = self._log_rows()
        self.assertEqual(len(rows), 3)  # header + 2 行
        self.assertEqual(rows[0][:5], ["date", "run_id", "session", "coverage",
                                       "gate_status"])
        self.assertEqual(rows[1][4], "PASS")
        self.assertIn("83.4%", rows[1][3])
        self.assertEqual(rows[2][4], "DEGRADED")
        self.assertIn("40.9%", rows[2][3])


if __name__ == "__main__":
    unittest.main()
