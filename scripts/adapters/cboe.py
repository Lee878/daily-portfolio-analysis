#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CBOE 期权链适配器（美股），用于补 `put_call_or_inst`。

上游 global-stock-data 的实测结论：CBOE 官方延迟行情，零鉴权，
cdn.cboe.com 会 307 跳到 cdn-api.cboe.com（必须跟随重定向，urllib 默认会跟）。

出口只给两个比值，不落原始链（1.9 MB，没必要进证据文件）：
  pcr_volume  成交量 put/call
  pcr_oi      持仓量 put/call
"""
from __future__ import annotations

import json
import re
import urllib.request

NAME = "cboe"
MARKETS = ("美股",)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0"
_URL = "https://cdn.cboe.com/api/global/delayed_quotes/options/{t}.json"
_OSI_RE = re.compile(r"^([A-Z][A-Z.]*?)(\d{6})([CP])(\d{8})$")


def _get_json(url: str, timeout: int = 25) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:   # 默认跟随 307
        return json.loads(r.read().decode("utf-8", errors="replace"))


def chain_stats(ticker: str) -> dict:
    sym = str(ticker).strip().upper().split(".")[0]
    try:
        payload = _get_json(_URL.format(t=sym))
    except Exception:
        return {}
    opts = ((payload or {}).get("data") or {}).get("options") or []

    call_v = put_v = call_oi = put_oi = 0.0
    for o in opts:
        m = _OSI_RE.match(str(o.get("option", "")))
        if not m:
            continue
        side = m.group(3)
        vol = o.get("volume") or 0
        oi = o.get("open_interest") or 0
        if not isinstance(vol, (int, float)):
            vol = 0
        if not isinstance(oi, (int, float)):
            oi = 0
        if side == "C":
            call_v += vol
            call_oi += oi
        else:
            put_v += vol
            put_oi += oi

    out: dict = {}
    if call_v > 0:
        out["pcr_volume"] = round(put_v / call_v, 2)
    if call_oi > 0:
        out["pcr_oi"] = round(put_oi / call_oi, 2)
    out["contracts"] = len(opts)
    return out


def snapshot(market: str, ticker: str) -> dict:
    """给源链用的统一出口：只回 put_call_or_inst（文本口径，门禁按文本字段处理）。"""
    if market != "美股":
        return {}
    s = chain_stats(ticker)
    if not s:
        return {}
    parts = []
    if "pcr_volume" in s:
        parts.append(f"期权PCR(成交量) {s['pcr_volume']}")
    if "pcr_oi" in s:
        parts.append(f"PCR(持仓量) {s['pcr_oi']}")
    if not parts:
        return {}
    return {"put_call_or_inst": "；".join(parts), "contracts": s.get("contracts", 0)}
