#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""北向资金适配器（同花顺沪深股通当日分时）。

补的是 NeoData 取不到的那个缺口：`north_south_flow`。
单位口径：上游给「亿元」，本项目统一「万元」，出口已换算。

只取「当日累计净买入」，不做历史序列——历史需要另一个域名的日频接口，
本机尚未验证，不在此臆造。
"""
from __future__ import annotations

import json
import urllib.request

NAME = "north"
MARKETS = ("A股",)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0"
_URL = "https://data.hexin.cn/market/hsgtApi/method/dayChart/"


def _last_valid(seq):
    for v in reversed(seq or []):
        if isinstance(v, (int, float)):
            return float(v)
    return None


def north_flow() -> float | None:
    """沪股通 + 深股通当日累计净买入（万元）。取不到返回 None，绝不填 0。"""
    try:
        req = urllib.request.Request(_URL, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=12) as r:
            d = json.loads(r.read().decode("utf-8", errors="replace"))
    except Exception:
        return None
    hgt = _last_valid(d.get("hgt"))
    sgt = _last_valid(d.get("sgt"))
    if hgt is None and sgt is None:
        return None
    total_yi = (hgt or 0.0) + (sgt or 0.0)
    return round(total_yi * 1e4, 2)
