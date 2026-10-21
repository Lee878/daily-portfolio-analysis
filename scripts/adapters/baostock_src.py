#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""baostock 日线适配器（A股兜底）。

为什么留这一路：纯 socket 协议，不走 HTTP，不读系统代理，
是「东财/腾讯都抽风」时唯一还能出数的通道。代价是需要第三方包（可选依赖）。
未安装时静默跳过，由源链落到下一路。
"""
from __future__ import annotations

NAME = "baostock"
MARKETS = ("A股",)

_state = {"inited": False, "ok": False}


def _ensure_login() -> bool:
    if _state["inited"]:
        return _state["ok"]
    _state["inited"] = True
    try:
        import baostock as bs  # type: ignore
    except ImportError:
        _state["ok"] = False
        return False
    try:
        lg = bs.login()
        _state["ok"] = (getattr(lg, "error_code", "1") == "0")
    except Exception:
        _state["ok"] = False
    return _state["ok"]


def _bs_code(ticker: str) -> str:
    digits = "".join(ch for ch in str(ticker).split(".")[0] if ch.isdigit())
    suffix = ".SH" if digits.startswith(("6", "5", "9")) else ".SZ"
    return ("sh." if suffix == ".SH" else "sz.") + digits


def kline(market: str, ticker: str, days: int = 250) -> list[dict]:
    if market != "A股" or not _ensure_login():
        return []
    import datetime as dt
    import baostock as bs  # type: ignore

    end = dt.date.today()
    # 自然日留足冗余覆盖交易日，多取的由尾部裁剪
    start = end - dt.timedelta(days=int(days * 1.8) + 30)
    try:
        rs = bs.query_history_k_data_plus(
            _bs_code(ticker), "date,open,high,low,close,volume",
            start_date=start.isoformat(), end_date=end.isoformat(),
            frequency="d", adjustflag="2",   # 2 = 前复权
        )
    except Exception:
        return []

    rows = []
    while True:
        try:
            if not rs.next():
                break
            d, o, h, lo, c, v = rs.get_row_data()[:6]
        except Exception:
            break
        try:
            close = float(c)
        except (TypeError, ValueError):
            continue
        rows.append({
            "date": d, "open": float(o or 0), "high": float(h or 0),
            "low": float(lo or 0), "close": close, "volume": float(v or 0),
        })
    rows.sort(key=lambda x: x["date"])
    return rows[-int(days):] if days else rows
