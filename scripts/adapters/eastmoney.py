#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""东方财富 push2 适配器（A股 / 港股的资金流与市值兜底）。

本机实测边界（2026-10-22）：
  · push2.eastmoney.com  可用
  · push2his.eastmoney.com  被本机权限层拒绝 → 历史 K 线、日级资金流序列不可用
  · 东财人气榜等其它域名间歇 RemoteDisconnected
因此本适配器**只做快照**，不做历史序列；历史一律走 tencent / baostock。

价格刻意不由本模块提供：f43 是放大整数，小数位随品种变化（基金 3 位、股票 2 位），
用错会差 10 倍。价格统一交给 tencent / sina。
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request

NAME = "eastmoney"
MARKETS = ("A股", "港股")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0"

# 东财有频率风控：逐只标的连续请求会被拒。0.35s 间隔是实测可用的下限。
_MIN_INTERVAL = 0.35
_last_call = [0.0]

# f62 主力净流入(元) / f116 总市值(元) / f117 流通市值(元) / f168 换手率(×100) / f59 价格小数位
_FIELDS = "f57,f58,f59,f62,f116,f117,f168"


def _get_json(url: str, timeout: int = 12) -> dict:
    gap = time.monotonic() - _last_call[0]
    if gap < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - gap)
    _last_call[0] = time.monotonic()
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def _secid(market: str, ticker: str) -> str | None:
    digits = "".join(ch for ch in str(ticker).split(".")[0] if ch.isdigit())
    if not digits:
        return None
    if market == "港股":
        return f"116.{digits.zfill(5)}"
    if market == "A股" and len(digits) == 6:
        return f"{'1' if digits.startswith(('6', '5', '9')) else '0'}.{digits}"
    return None


def snapshot(market: str, ticker: str) -> dict:
    """资金流与市值。

    资金流刻意不走 stock/get 的 f62：实测那里返回 2（而占比 f184=15.78%），
    单位对不上，不能当「元」用。改走 fflow/kline 的 f52（主力净流入，单位元），
    实测 601899 = -345,490,048 元，与成交额量级吻合。
    """
    secid = _secid(market, ticker)
    if not secid:
        return {}

    out: dict = {}
    # ① 市值 / 换手
    url = ("https://push2.eastmoney.com/api/qt/stock/get?"
           + urllib.parse.urlencode({"secid": secid, "fields": "f59,f116,f168"}))
    try:
        d = (_get_json(url) or {}).get("data") or {}
    except Exception:
        d = {}
    if isinstance(d.get("f116"), (int, float)) and d["f116"]:
        out["market_cap"] = round(d["f116"] / 1e8, 2)     # 元 → 亿元
    if isinstance(d.get("f168"), (int, float)):
        out["turnover_pct"] = round(d["f168"] / 100, 2)   # f168 是放大整数

    # ② 主力净流入（最近一个交易日）
    furl = ("https://push2.eastmoney.com/api/qt/stock/fflow/kline/get?"
            + urllib.parse.urlencode({
                "secid": secid, "fields1": "f1,f2,f3,f7",
                "fields2": "f51,f52,f53,f54,f55,f56", "klt": "101", "lmt": "1"}))
    try:
        klines = ((_get_json(furl) or {}).get("data") or {}).get("klines") or []
    except Exception:
        klines = []
    if klines:
        parts = str(klines[-1]).split(",")
        if len(parts) >= 2:
            try:
                out["main_net_inflow"] = round(float(parts[1]) / 1e4, 2)  # 元 → 万元
                out["flow_date"] = parts[0]
            except ValueError:
                pass
    return out
