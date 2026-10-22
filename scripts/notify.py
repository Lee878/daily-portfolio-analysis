#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bark 通知与告警（PRD FR-03 / FR-04 / FR-11）。

分工明确：Bark 只负责「叫醒」，正文只放 3-5 行摘要，全文点链接去 App 看。
（Bark 通知栏放不下整份报告，硬塞等于把关键结论截断在通知里。）

配置 `config/notify.json`（不入库）：
    {
      "enabled": true,
      "bark_key": "你的设备 key",
      "bark_endpoint": "https://api.day.app",
      "read_url_base": "",          // 报告在 App 中的可访问前缀，留空则不带链接
      "quiet_hours": ["23:00", "07:30"]
    }

用法：
    python scripts/notify.py --session post --status PASS --coverage 87.5 --summary "..."
    python scripts/notify.py --session post --status FAIL --reason "取数全失败"
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402

SESSION_CN = {"pre": "盘前", "noon": "午间", "post": "盘后", "quick": "快诊"}
MAX_BODY = 400           # Bark 通知正文上限，超出会被截断
GROUP = "持仓日报"


def load_conf() -> dict:
    p = paths.config_dir() / "notify.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _in_quiet_hours(conf: dict, now: dt.datetime | None = None) -> bool:
    qh = conf.get("quiet_hours") or []
    if len(qh) != 2:
        return False
    now = now or dt.datetime.now()
    cur = now.strftime("%H:%M")
    start, end = qh
    return start <= cur or cur < end if start > end else (start <= cur < end)


def _suppressed() -> str:
    """返回非空字符串表示当前不该真发推送。

    两个场景必须闭嘴：
    1. 单元测试——测试会大量走失败路径，真发会把手机刷屏；
    2. 批处理/离线回放——设 `DAILY_NO_NOTIFY=1` 即可。
    """
    if os.environ.get("DAILY_NO_NOTIFY", "").strip().lower() in ("1", "true", "yes", "on"):
        return "已抑制（DAILY_NO_NOTIFY）"
    if "unittest" in sys.modules:
        return "已抑制（单元测试环境）"
    return ""


def send(title: str, body: str, subtitle: str = "", url: str = "",
         level: str = "active", sound: str = "", force: bool = False) -> tuple[bool, str]:
    """发一条 Bark 通知。返回 (是否发出, 说明)。失败绝不抛异常打断主流程。"""
    sup = _suppressed()
    if sup:
        return False, sup
    conf = load_conf()
    if not conf.get("enabled"):
        return False, "未启用（config/notify.json 里 enabled=false）"
    key = str(conf.get("bark_key") or "").strip()
    if not key:
        return False, "缺 bark_key"
    if not force and _in_quiet_hours(conf):
        return False, "处于静默时段"

    endpoint = str(conf.get("bark_endpoint") or "https://api.day.app").rstrip("/")
    payload = {
        "device_key": key,
        "title": title[:60],
        "body": body[:MAX_BODY],
        "group": GROUP,
        "level": level,
    }
    if subtitle:
        payload["subtitle"] = subtitle[:60]
    if sound:
        payload["sound"] = sound
    if url:
        payload["url"] = url

    req = urllib.request.Request(
        endpoint + "/push",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            raw = r.read().decode("utf-8", errors="replace")
        ok = '"code":200' in raw.replace(" ", "")
        return ok, ("已发送" if ok else f"服务端返回异常: {raw[:120]}")
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        return False, f"发送失败: {type(e).__name__}"


def _fmt_report_body(session: str, coverage: float, degraded: bool,
                     summary: str, problems: int) -> tuple[str, str]:
    """组装标题/副标题/正文。降级版必须在第一行说明缺什么。"""
    title = f"持仓日报 · {SESSION_CN.get(session, session)}"
    if degraded:
        subtitle = f"⚠ 数据不全 · 覆盖 {coverage:.0f}%"
        head = f"数据不全（{problems} 项缺口），结论仅作参考。"
    else:
        subtitle = f"覆盖 {coverage:.0f}%"
        head = "数据完整。"
    lines = [head]
    if summary:
        lines.append(summary[:260])
    lines.append("全文点开看。")
    return title, subtitle, "\n".join(lines)


def notify_report(session: str, coverage: float, degraded: bool,
                  summary: str = "", problems: int = 0,
                  read_url: str = "") -> tuple[bool, str]:
    title, subtitle, body = _fmt_report_body(session, coverage, degraded, summary, problems)
    conf = load_conf()
    url = read_url or str(conf.get("read_url_base") or "")
    return send(title, body, subtitle=subtitle, url=url,
                level="passive" if session == "noon" else "active",
                sound="" if session == "noon" else "bell")


def alert(session: str, reason: str, detail: str = "") -> tuple[bool, str]:
    """批次失败告警：不受静默时段限制（PRD FR-05 例外）。"""
    body = (detail or reason)[:300] + "\n报告可能未生成，请打开 App 核对。"
    return send(f"⚠ 日报异常 · {SESSION_CN.get(session, session)}", body,
                subtitle=reason[:50], level="timeSensitive", sound="alarm", force=True)


def main() -> int:
    paths.ensure_utf8_stdout()
    ap = argparse.ArgumentParser(description="Bark 通知")
    ap.add_argument("--session", default="pre", choices=list(SESSION_CN))
    ap.add_argument("--status", default="PASS", choices=["PASS", "DEGRADED", "FAIL"])
    ap.add_argument("--coverage", type=float, default=0.0, help="覆盖率百分比，如 87.5")
    ap.add_argument("--summary", default="", help="正文摘要（今日动作/到价提醒）")
    ap.add_argument("--problems", type=int, default=0, help="缺口项数")
    ap.add_argument("--read-url", default="", help="App 内可打开的链接")
    ap.add_argument("--reason", default="", help="FAIL 时的失败原因")
    ap.add_argument("--dry-run", action="store_true", help="只打印，不发送")
    args = ap.parse_args()

    if args.status == "FAIL":
        if args.dry_run:
            print("[dry-run] alert:", args.session, args.reason or args.summary)
            return 0
        ok, msg = alert(args.session, args.reason or "批次失败", args.summary)
    else:
        degraded = args.status == "DEGRADED"
        if args.dry_run:
            title, subtitle, body = _fmt_report_body(
                args.session, args.coverage, degraded, args.summary, args.problems)
            print(f"[dry-run] {title} | {subtitle}\n{body}")
            return 0
        ok, msg = notify_report(args.session, args.coverage, degraded,
                                args.summary, args.problems, args.read_url)
    print(("[notify] " + msg))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
