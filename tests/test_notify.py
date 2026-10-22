#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bark 通知与「机械告警接线」的回归测试（不联网）。

覆盖：
  N1 单元测试环境下必须自动闭嘴（否则跑测试会把手机刷屏）
  N2 DAILY_NO_NOTIFY 环境变量同样能闭嘴
  N3 --no-notify 时 run_daily 不调用推送
  N4 FAIL 走 alert（timeSensitive），PASS/DEGRADED 走 notify_report
  N5 推送抛异常不得影响出报告
"""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import notify  # noqa: E402
import run_daily as rd  # noqa: E402


class FakeNotify:
    """替身：记录调用，不碰网络。"""

    def __init__(self):
        self.calls = []

    def alert(self, session, reason, detail=""):
        self.calls.append(("alert", session, reason))
        return True, "已发送(假)"

    def notify_report(self, session, coverage, degraded, summary="", problems=0, read_url=""):
        self.calls.append(("notify_report", session, round(coverage, 1), degraded, problems))
        return True, "已发送(假)"


class BoomNotify(FakeNotify):
    def alert(self, session, reason, detail=""):
        raise RuntimeError("模拟推送崩了")

    def notify_report(self, *a, **kw):
        raise RuntimeError("模拟推送崩了")


class Args:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


class SuppressTests(unittest.TestCase):
    def test_suppressed_under_unittest(self):
        """测试进程里 _suppressed() 必须给非空原因。"""
        self.assertIn("单元测试", notify._suppressed())

    def test_send_is_noop_when_suppressed(self):
        ok, msg = notify.send("t", "b")
        self.assertFalse(ok)
        self.assertIn("抑制", msg)

    def test_env_var_suppresses(self):
        os.environ["DAILY_NO_NOTIFY"] = "1"
        try:
            self.assertIn("DAILY_NO_NOTIFY", notify._suppressed())
        finally:
            os.environ.pop("DAILY_NO_NOTIFY", None)


class WiringTests(unittest.TestCase):
    def setUp(self):
        self._real = sys.modules.get("notify")
        self.fake = FakeNotify()
        sys.modules["notify"] = self.fake

    def tearDown(self):
        if self._real is not None:
            sys.modules["notify"] = self._real
        else:
            sys.modules.pop("notify", None)

    def test_no_notify_flag_skips_push(self):
        rd._notify(Args(no_notify=True), "pre", "PASS", coverage=90.0)
        self.assertEqual(self.fake.calls, [])

    def test_pass_goes_to_notify_report(self):
        rd._notify(Args(no_notify=False), "post", "PASS", coverage=87.5, summary="持有为主")
        self.assertEqual(self.fake.calls, [("notify_report", "post", 87.5, False, 0)])

    def test_degraded_is_marked_degraded(self):
        rd._notify(Args(no_notify=False), "pre", "DEGRADED", coverage=57.1, problems=42)
        self.assertEqual(self.fake.calls, [("notify_report", "pre", 57.1, True, 42)])

    def test_fail_goes_to_alert(self):
        rd._notify(Args(no_notify=False), "post", "FAIL", reason="取证脚本失败")
        self.assertEqual(self.fake.calls, [("alert", "post", "取证脚本失败")])


class ExceptionSafetyTests(unittest.TestCase):
    def test_push_exception_never_raises(self):
        """推送崩了也必须静默放过——绝不能因为通知失败而丢掉报告。"""
        real = sys.modules.get("notify")
        sys.modules["notify"] = BoomNotify()
        try:
            rd._notify(Args(no_notify=False), "pre", "FAIL", reason="x")   # 不应抛
        finally:
            if real is not None:
                sys.modules["notify"] = real
            else:
                sys.modules.pop("notify", None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
