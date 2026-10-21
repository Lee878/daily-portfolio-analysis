#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""新浪行情适配器（美股）。

上游 global-stock-data 的实测结论（Apache-2.0，作者 Simon Lin）：
  · 实时行情 36 字段，含 52 周高低与 PE，比东财快且不受本机代理影响
  · 日 K 可回溯到 1984 年，但 `num` 参数实际不生效——传 5 仍返回全历史，
    必须自己取尾部，否则会把 1999 年的收盘价当成今天的。
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request

NAME = "sina"
MARKETS = ("美股",)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0"
REFERER = "https://finance.sina.com.cn/"


def _get(url: str, timeout: int = 12) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": REFERER})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("gbk", errors="replace")


def _num(s) -> float | None:
    try:
        v = float(str(s).strip())
        return v if v == v else None
    except (TypeError, ValueError):
        return None


def snapshot(market: str, ticker: str) -> dict:
    if market != "美股":
        return {}
    sym = str(ticker).strip().upper().split(".")[0]
    if not re.fullmatch(r"[A-Z][A-Z.\-]{0,6}", sym):
        return {}
    # 新浪的 gb_ 前缀要求小写，且点号类别股用 . 连接（BRK.B → gb_brk.b）
    text = _get(f"https://hq.sinajs.cn/list=gb_{sym.lower()}")
    m = re.search(r'"(.+)"', text)
    if not m:
        return {}
    f = m.group(1).split(",")
    if len(f) < 30:
        return {}

    price = _num(f[1])
    high52, low52 = _num(f[8]), _num(f[9])
    mcap = _num(f[12])
    out = {
        "price_last": price,
        "day_change_pct": _num(f[2]),
        "open": _num(f[5]),
        "high": _num(f[6]),
        "low": _num(f[7]),
        "high_52w": high52,
        "low_52w": low52,
        "prev_close": _num(f[26]),
        "volume": _num(f[10]),
        "eps": _num(f[13]),
        "pe_ttm": _num(f[14]) or None,
        # 新浪给的是美元原值，项目统一用「亿美元」
        "market_cap": round(mcap / 1e8, 2) if mcap else None,
    }
    if price and high52 and low52 and high52 > low52:
        out["range_52w_pct"] = round((price - low52) / (high52 - low52) * 100, 1)
    return {k: v for k, v in out.items() if v is not None}


def kline(market: str, ticker: str, days: int = 250) -> list[dict]:
    if market != "美股":
        return []
    sym = str(ticker).strip().upper().split(".")[0]
    url = ("https://stock.finance.sina.com.cn/usstock/api/jsonp.php/var/"
           "US_MinKService.getDailyK?" + urllib.parse.urlencode(
               {"symbol": sym, "num": max(int(days) * 2, 260)}))
    text = _get(url, timeout=20)
    m = re.search(r"\((\[.+\])\)", text, re.S)
    if not m:
        return []
    try:
        items = json.loads(m.group(1))
    except json.JSONDecodeError:
        return []
    rows = []
    for it in items:
        c = _num(it.get("c"))
        if not c:
            continue
        rows.append({
            "date": str(it.get("d"))[:10],
            "open": _num(it.get("o")),
            "high": _num(it.get("h")),
            "low": _num(it.get("l")),
            "close": c,
            "volume": _num(it.get("v")) or 0,
        })
    rows.sort(key=lambda x: x["date"])
    # num 参数不可靠，靠尾部裁剪保证「最近 N 天」
    return rows[-int(days):] if days else rows
