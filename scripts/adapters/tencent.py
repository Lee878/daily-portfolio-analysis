#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""腾讯行情适配器（A股 / 港股）。

为什么首选腾讯：
  · 不封 IP，实时价与 K 线可高频取；东财系有频率风控且本机部分域名不通。
  · 一次请求返回 20+ 字段，含项目需要的「量比」，省掉自算。

实测依据（2026-10-22）：见 docs/数据源评估-开源Skill实测-2026-10-22.md

字段索引来自上游 a-stock-data / global-stock-data（Apache-2.0，作者 Simon Lin），
两处易错点照抄并保留注释：
  · A股 vals[44]=流通市值、vals[45]=总市值（曾标反，总股本≠流通股本时差数倍）
  · 港股下标与美股/ A股不同，fields[58]=PB、fields[48/49]=52周高低

统一出口字段（与 fetch_data 内部口径一致）：
  price_last, day_change_pct, volume_ratio, pe_ttm, pb,
  market_cap(亿元), range_52w_pct, high_52w, low_52w, is_stale
"""
from __future__ import annotations

import json
import urllib.request

NAME = "tencent"
MARKETS = ("A股", "港股")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0"

# 沪指数：000300 等不能落到 sz 前缀（会返回空或错票）
_SH_INDEX = {"000300", "000905", "000016", "000688", "000852", "000010"}


def _get(url: str, timeout: int = 12) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _num(s) -> float | None:
    """腾讯空字段常为 "" 或 0；0 对 PE/PB 属无效值，交由调用方按字段语义取舍。"""
    try:
        v = float(str(s).strip())
        return v if v == v else None  # NaN 过滤
    except (TypeError, ValueError):
        return None


def _sh_sz_prefix(code: str) -> str:
    c = str(code).strip().lower()
    if c.startswith(("sh", "sz", "bj")):
        return c
    digits = "".join(ch for ch in c if ch.isdigit())
    if not digits:
        return c
    if digits.startswith("92"):
        return "bj" + digits
    if digits in _SH_INDEX or digits.startswith(("5", "6", "9")):
        return "sh" + digits
    if digits.startswith(("4", "8")):
        return "bj" + digits
    return "sz" + digits


def _hk_prefix(code: str) -> str:
    digits = "".join(ch for ch in str(code) if ch.isdigit())
    return "hk" + digits.zfill(5)


def _range_pct(price, high_52w, low_52w) -> float | None:
    """52 周区间分位：当前价在 [低, 高] 中的位置（0=最低，100=最高）。"""
    if not price or not high_52w or not low_52w:
        return None
    if high_52w <= low_52w:
        return None
    return round((price - low_52w) / (high_52w - low_52w) * 100, 1)


def snapshot(market: str, ticker: str) -> dict:
    """返回统一字段字典；取不到的字段不出现在返回值里（不填 None，方便源链合并）。"""
    code = str(ticker).split(".")[0]
    if market == "港股":
        sym = _hk_prefix(code)
    elif market == "A股":
        sym = _sh_sz_prefix(code)
    else:
        return {}

    raw = _get(f"https://qt.gtimg.cn/q={sym}").decode("gbk", errors="replace")
    if '"' not in raw:
        return {}
    vals = raw.split('"')[1].split("~")

    out: dict = {}
    if market == "A股":
        if len(vals) < 53:
            return {}
        price = _num(vals[3])
        last = _num(vals[4])
        out.update({
            "price_last": price,
            "day_change_pct": _num(vals[32]),
            "volume_ratio": _num(vals[49]) or None,
            "pe_ttm": _num(vals[39]) or None,
            "pb": _num(vals[46]) or None,
            # 腾讯已是「亿元」；44/45 不可互换
            "market_cap": _num(vals[45]) or None,
            "turnover_pct": _num(vals[38]) or None,
            "amount_wan": _num(vals[37]) or None,
        })
        # 僵尸报价：成交量 0 且最新价==昨收，腾讯仍返回 HTTP 200
        amount = _num(vals[37]) or 0
        if price and last and amount == 0 and price == last:
            out["is_stale"] = True
    else:  # 港股，78 字段
        if len(vals) < 76:
            return {}
        price = _num(vals[3])
        high52, low52 = _num(vals[48]), _num(vals[49])
        amt = _num(vals[37])
        out.update({
            "price_last": price,
            "day_change_pct": _num(vals[32]),
            "pe_ttm": _num(vals[39]) or None,
            "pb": _num(vals[58]) or None,
            "market_cap": _num(vals[45]) or None,   # 亿港元
            "high_52w": high52,
            "low_52w": low52,
            # 港股 fields[37] 是港元原值（A股同位置是万元），统一折成万元
            "amount_wan": round(amt / 1e4, 2) if amt else None,
        })
        out["range_52w_pct"] = _range_pct(price, high52, low52)

    if market == "A股" and out.get("high_52w") is None:
        # A股快照无 52 周高低，由 K 线派生（见 kline 调用方）
        pass
    return {k: v for k, v in out.items() if v is not None}


def kline(market: str, ticker: str, days: int = 250) -> list[dict]:
    """前复权日 K。返回 [{date, open, high, low, close, volume}]，按日期升序。"""
    code = str(ticker).split(".")[0]
    sym = _hk_prefix(code) if market == "港股" else _sh_sz_prefix(code)
    adj = "qfq"
    url = (f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
           f"?param={sym},day,,,{int(days)},{adj}")
    payload = json.loads(_get(url).decode("utf-8", errors="replace"))
    if payload.get("code") != 0:
        return []
    node = (payload.get("data") or {}).get(sym) or {}
    # A股前复权键为 qfqday；港股实测为 day（无复权因子）
    rows = node.get("qfqday") or node.get("day") or []
    out = []
    for r in rows:
        if len(r) < 6:
            continue
        # 顺序：日期, 开, 收, 高, 低, 量
        d, o, c, h, lo, v = r[0], _num(r[1]), _num(r[2]), _num(r[3]), _num(r[4]), _num(r[5])
        if c is None:
            continue
        out.append({"date": str(d)[:10], "open": o, "high": h,
                    "low": lo, "close": c, "volume": v or 0})
    out.sort(key=lambda x: x["date"])
    return out
