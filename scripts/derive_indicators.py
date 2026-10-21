#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从日 K 线派生证据门要求的三个指标（NeoData MCP 不直接提供）。

证据门的 technical 维度要 8 个字段，MCP 能直接给 5 个（price_last /
day_change_pct / ma5 / ma20 / ma60），剩下三个必须自己算：

  - atr14        真实波幅 14 日均值（止损与仓位依据）
  - range_52w_pct 现价在近 52 周高低区间中的位置（0=最低，100=最高）
  - volume_ratio 量比 = 当日成交量 / 前 5 日均量

为什么要单独写脚本：这三个都是"差一位小数就影响止损"的量，靠心算或
目测会出错，而报告门不校验数值对错（只校验有没有）。把算法固化在这里，
agent 只负责搬数，不负责算数。

输入（两种，自动识别）：
  1. NeoData `quote_and_kline` 的完整返回 JSON（含 result[].kline_list）
  2. 纯 K 线数组：[{"trade_date": "...", "open": ..., "close": ..., ...}]

用法：
  python scripts/derive_indicators.py --mcp mcp_quote.json
  python scripts/derive_indicators.py --kline kline.json --out derived.json
  python scripts/derive_indicators.py --selftest

输出：JSON（stdout 或 --out），字段名与证据门的 field 一一对应。
算不出的字段输出 null 并在 notes 里说明原因，绝不填假数。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 52 周按 250 个交易日计（交易所年均约 244-250 日）
WEEKS_52_BARS = 250
ATR_PERIOD = 14
VOLUME_BASE_BARS = 5
# MCP 在非交易时段会用这些字符串占位，必须先剔掉，否则 float() 直接崩
_NULL_TOKENS = {"", "-", "—", "未开盘", "None", "null", "nan"}


def _num(v):
    """把 MCP 的字符串数字转 float；占位符与脏值返回 None。"""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if s in _NULL_TOKENS:
        return None
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def _extract_bars(payload):
    """从两种输入里取出 K 线数组，统一成 [{trade_date, open, high, low, close, volume, pct_change}]。"""
    raw = payload
    # 形态一：MCP 完整返回
    if isinstance(payload, dict) and isinstance(payload.get("result"), list):
        bars = []
        for item in payload["result"]:
            for row in item.get("kline_list") or []:
                bars.append(row)
        raw = bars
    if not isinstance(raw, list):
        raise ValueError("输入既不是 MCP 返回（含 result[]），也不是 K 线数组")

    out = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        # MCP 会在长区间里插入"省略中间历史行情"标记行，close 是 "-" 但
        # trade_date 是 "2026-09-01 ~ 2026-09-12"，不能当成一根真实 K 线
        day_raw = row.get("trade_date") or row.get("trading_date") or row.get("date")
        if isinstance(day_raw, str) and ("~" in day_raw or "省略" in day_raw):
            continue
        if isinstance(row.get("open"), str) and "省略" in row["open"]:
            continue
        close = _num(row.get("close"))
        # 未开盘/停牌行：收盘价是占位符，整行丢弃
        if close is None:
            continue
        day = row.get("trade_date") or row.get("trading_date") or row.get("date")
        if isinstance(day, int):  # MCP technical 返回 20261008 这种整数
            day = f"{day // 10000:04d}-{day // 100 % 100:02d}-{day % 100:02d}"
        out.append({
            "trade_date": str(day),
            "open": _num(row.get("open")),
            "high": _num(row.get("high")),
            "low": _num(row.get("low")),
            "close": close,
            "volume": _num(row.get("volume")),
            "pct_change": _num(row.get("pct_change")),
        })
    # MCP 返回新→旧，统一成旧→新，均线/ATR 都依赖方向
    out.sort(key=lambda b: b["trade_date"])
    return out


def _ma(closes, n):
    if len(closes) < n:
        return None
    return round(sum(closes[-n:]) / n, 4)


def _atr14(bars, period=ATR_PERIOD):
    """ATR14：TR = max(高-低, |高-昨收|, |低-昨收|)，取最近 period 日均值。"""
    if len(bars) < period + 1:
        return None
    trs = []
    for i in range(len(bars) - period, len(bars)):
        cur, prev = bars[i], bars[i - 1]
        high, low, prev_close = cur["high"], cur["low"], prev["close"]
        if high is None or low is None:
            prev_close = prev["close"]
            trs.append(abs(cur["close"] - prev_close))
            continue
        prev_close = prev["close"]
        trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    return round(sum(trs) / len(trs), 4)


def _range_52w_pct(bars, close):
    """现价在近 52 周区间的位置：0=贴最低，100=贴最高。"""
    window = bars[-WEEKS_52_BARS:]
    highs = [b["high"] for b in window if b["high"] is not None]
    lows = [b["low"] for b in window if b["low"] is not None]
    if not highs or not lows:
        highs = [b["close"] for b in window]
        lows = highs
    hi, lo = max(highs), min(lows)
    if hi <= lo:
        return None
    return round((close - lo) / (hi - lo) * 100, 2)


def _volume_ratio(bars):
    """量比 = 当日量 / 前 5 日均量（不含当日）。"""
    if len(bars) < VOLUME_BASE_BARS + 1:
        return None
    today = bars[-1]["volume"]
    base = [b["volume"] for b in bars[-VOLUME_BASE_BARS - 1:-1]
            if b["volume"] is not None]
    if today is None or not base:
        return None
    avg = sum(base) / len(base)
    if avg <= 0:
        return None
    return round(today / avg, 3)


def _merge(bars_list):
    """合并多段 K 线：按交易日去重后升序。MCP 单次返回会被截断，
    长区间（如取满 52 周）必须分几段取再合并。"""
    seen = {}
    for bars in bars_list:
        for b in bars:
            seen[b["trade_date"]] = b  # 同一天以最后一段为准（复权口径一致时无差别）
    return [seen[k] for k in sorted(seen)]


def derive(bars):
    """返回证据门的 technical 字段字典 + 说明。"""
    notes = []
    closes = [b["close"] for b in bars]
    last = bars[-1]

    atr = _atr14(bars)
    if atr is None:
        notes.append(f"K 线不足 {ATR_PERIOD + 1} 根，atr14 算不出")

    rng = _range_52w_pct(bars, last["close"])
    if rng is None:
        notes.append("区间高低点相同或缺失，range_52w_pct 算不出")
    elif len(bars) < WEEKS_52_BARS:
        notes.append(f"只有 {len(bars)} 根 K 线（<{WEEKS_52_BARS}），"
                     "range_52w_pct 按现有区间算，非完整 52 周")

    vr = _volume_ratio(bars)
    if vr is None:
        notes.append(f"K 线不足 {VOLUME_BASE_BARS + 1} 根，volume_ratio 算不出")

    pct = last["pct_change"]
    if pct is None:
        prev = bars[-2]["close"] if len(bars) >= 2 else None
        pct = round((last["close"] / prev - 1) * 100, 2) if prev else None
        if pct is None:
            notes.append("缺前收价，day_change_pct 算不出")

    return {
        "as_of": last["trade_date"],
        "bars_used": len(bars),
        "price_last": round(last["close"], 4),
        "day_change_pct": pct,
        "ma5": _ma(closes, 5),
        "ma20": _ma(closes, 20),
        "ma60": _ma(closes, 60),
        "range_52w_pct": rng,
        "atr14": atr,
        "volume_ratio": vr,
        "notes": notes,
    }


def _selftest():
    """用确定性数据验算，防止改坏了没人发现。"""
    # 构造 25 根走势已知的 K 线
    bars = []
    price = 100.0
    for i in range(25):
        price += 1.0
        bars.append({
            "trade_date": f"2026-09-{i + 1:02d}" if i < 30 else "",
            "open": price - 0.5, "high": price + 1.0, "low": price - 1.0,
            "close": price, "volume": 1000 + i * 100, "pct_change": 1.0,
        })
    got = derive(bars)
    assert got["price_last"] == 125.0, got["price_last"]
    assert got["ma5"] == round((121 + 122 + 123 + 124 + 125) / 5, 4), got["ma5"]
    assert got["ma20"] is not None
    assert got["ma60"] is None, "25 根 K 线不应算出 MA60"
    assert got["atr14"] is not None and got["atr14"] > 0
    # 首根 close=101、low=100，末根 high=126 → (125-100)/(126-100)
    assert got["range_52w_pct"] == round((125 - 100) / (126 - 100) * 100, 2), \
        got["range_52w_pct"]
    # 当日量 3400，前 5 日均量 (2900+3000+3100+3200+3300)/5 = 3100
    assert got["volume_ratio"] == round(3400 / 3100, 3), got["volume_ratio"]

    # 占位行必须被剔除：混入"未开盘"不应对结果产生任何影响
    dirty = [{"trade_date": "2026-10-22", "open": "未开盘", "high": "-",
              "low": "-", "close": "-", "volume": "-"}] + bars
    got2 = derive(_extract_bars(dirty))
    assert got2["price_last"] == got["price_last"], "未开盘行未被剔除"
    assert got2["bars_used"] == 25

    # MCP 的"省略中间历史行情"标记行：既不能当 K 线，也不能参与计算
    truncated = [{"trade_date": "2026-09-01 ~ 2026-09-12",
                  "open": "省略中间历史行情，不包含任何具体数值，禁止根据该标记推断、补全或参与计算",
                  "high": "-", "low": "-", "close": "-",
                  "pct_change": "-", "volume": "-"}]
    got3 = derive(_extract_bars(truncated + bars))
    assert got3["bars_used"] == 25, f"省略行未被剔除：{got3['bars_used']}"

    # 多段合并：同一交易日重复取到只应保留一根
    seg_a = _extract_bars(bars[:15])
    seg_b = _extract_bars(bars[10:])
    merged = _merge([seg_a, seg_b])
    assert len(merged) == 25, f"合并去重失败：{len(merged)}"
    assert derive(merged)["price_last"] == got["price_last"]
    print("[selftest] OK —— 派生指标算法、占位行剔除、省略行剔除、多段合并均正确")


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    ap = argparse.ArgumentParser(
        description="从日 K 线派生 atr14 / range_52w_pct / volume_ratio / 均线")
    ap.add_argument("--mcp", action="append",
                    help="NeoData quote_and_kline 的完整返回 JSON（可重复，多段合并）")
    ap.add_argument("--kline", action="append",
                    help="纯 K 线数组 JSON（可重复，多段合并）")
    ap.add_argument("--out", help="输出文件（默认打印到 stdout）")
    ap.add_argument("--ticker", default="", help="写进结果的标的代码，便于对账")
    ap.add_argument("--selftest", action="store_true", help="跑内置验算")
    args = ap.parse_args()

    if args.selftest:
        _selftest()
        return 0
    if not (args.mcp or args.kline):
        ap.error("必须给 --mcp 或 --kline（或用 --selftest）")

    segments = []
    for src in list(args.mcp or []) + list(args.kline or []):
        p = Path(src)
        if not p.exists():
            print(f"[error] 文件不存在：{p}", file=sys.stderr)
            return 2
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[error] {p.name} JSON 解析失败：{e}", file=sys.stderr)
            return 2
        try:
            segments.append(_extract_bars(payload))
        except ValueError as e:
            print(f"[error] {p.name}: {e}", file=sys.stderr)
            return 2

    bars = _merge(segments)
    if not bars:
        print("[error] 没有任何有效 K 线（全是未开盘/停牌占位）", file=sys.stderr)
        return 2

    result = derive(bars)
    result["ticker"] = args.ticker
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"[derive] 已写出 {args.out}（{result['bars_used']} 根 K 线）")
        for n in result["notes"]:
            print(f"  ! {n}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
