#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""数据源适配层：一个出口，多路回退。

设计要点（对应 docs/PRD-日报产品化-v1.0.md FR-13 / FR-14）：
  · 每个数据源一个模块，实现 `snapshot(market, ticker) -> dict` 与/或
    `kline(market, ticker, days) -> list[dict]`，失败就抛异常或返回空，由本层兜。
  · 优先级链在 config/data-sources.json 里声明；文件不存在时用 DEFAULT_CHAIN。
  · **先到先得**：链上第一路给出的非空字段即采用，后续源只补空缺，不覆盖——
    避免「慢源覆盖快源」导致同一份报告里价格来自两个时刻。
  · 每次调用返回 (payload, notes)。notes 记录降级原因，直接进证据 gaps，
    绝不静默吞掉失败。

刻意不做的事：
  · 不改字段单位（各模块已统一为 项目口径：市值亿元 / 资金万元 / 涨跌%）。
  · 不重试到死（每源一次，失败即落下一路），避免单批次卡在某个源上。
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

try:
    import paths  # noqa: E402
except Exception:                                    # 独立调用时的兜底
    paths = None  # type: ignore

from . import baostock_src, cboe, eastmoney, north, sina, tencent  # noqa: E402

SOURCES = {
    "tencent": tencent,
    "sina": sina,
    "eastmoney": eastmoney,
    "baostock": baostock_src,
    "cboe": cboe,
    "north": north,
}

# 快照链只放「一次请求拿一批字段」的源。cboe（1.9MB）与 north（单独口径）
# 不进默认链，按需单独调用，否则每只票都要拖 2MB。
DEFAULT_SNAPSHOT_CHAIN = {
    "A股": ["tencent", "eastmoney"],
    "港股": ["tencent", "eastmoney"],
    "美股": ["sina"],
}
DEFAULT_KLINE_CHAIN = {
    "A股": ["tencent", "baostock"],
    "港股": ["tencent"],
    "美股": ["sina"],
}

_CFG_CACHE: dict | None = None

# 链终止条件：这些字段齐了才停，只看价格会漏掉后续源的独有字段
# （tencent 给价格与估值，但主力净流入只有 eastmoney 有）
_CORE_FIELDS = ("price_last", "day_change_pct", "pe_ttm", "pb",
                "market_cap", "main_net_inflow")


def load_config() -> dict:
    """读 config/data-sources.json；不存在/损坏时回默认（不因配置缺失而停摆）。"""
    global _CFG_CACHE
    if _CFG_CACHE is not None:
        return _CFG_CACHE
    cfg: dict = {}
    if paths is not None:
        p = paths.config_dir() / "data-sources.json"
        if p.exists():
            try:
                cfg = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                cfg = {}
    _CFG_CACHE = cfg
    return cfg


def reset_config_cache() -> None:
    """测试用：改完配置后强制重读。"""
    global _CFG_CACHE
    _CFG_CACHE = None


def _chain(kind: str, market: str) -> list[str]:
    cfg = load_config()
    table = cfg.get(kind) or {}
    seq = table.get(market)
    if isinstance(seq, list) and seq:
        return [s for s in seq if s in SOURCES]
    default = DEFAULT_SNAPSHOT_CHAIN if kind == "snapshot" else DEFAULT_KLINE_CHAIN
    return list(default.get(market, []))


def enabled(name: str) -> bool:
    src = (load_config().get("sources") or {}).get(name) or {}
    return bool(src.get("enabled", True))


def snapshot(market: str, ticker: str) -> tuple[dict, list[str]]:
    """按链取快照字段，先到先得。返回 (fields, notes)。"""
    merged: dict = {}
    notes: list[str] = []
    for name in _chain("snapshot", market):
        if not enabled(name):
            notes.append(f"{name}: 已禁用")
            continue
        mod = SOURCES[name]
        try:
            got = mod.snapshot(market, ticker) or {}
        except Exception as e:
            notes.append(f"{name}: {type(e).__name__}")
            continue
        if not got:
            notes.append(f"{name}: 无数据")
            continue
        for k, v in got.items():
            if merged.get(k) is None and v is not None:
                merged[k] = v
        if all(merged.get(f) is not None for f in _CORE_FIELDS):
            break
    return merged, notes


def kline(market: str, ticker: str, days: int = 250) -> tuple[list[dict], list[str]]:
    """按链取日 K；第一个非空结果即返回。"""
    notes: list[str] = []
    for name in _chain("kline", market):
        if not enabled(name):
            notes.append(f"{name}: 已禁用")
            continue
        mod = SOURCES[name]
        fn = getattr(mod, "kline", None)
        if fn is None:
            continue
        try:
            rows = fn(market, ticker, days) or []
        except Exception as e:
            notes.append(f"{name}: {type(e).__name__}")
            continue
        if rows:
            return rows, notes
        notes.append(f"{name}: 空结果")
    return [], notes


def north_flow() -> tuple[float | None, list[str]]:
    """北向资金（万元）。单独出口，因为它不属于任何单只标的。"""
    if not enabled("north"):
        return None, ["north: 已禁用"]
    try:
        v = north.north_flow()
    except Exception as e:
        return None, [f"north: {type(e).__name__}"]
    if v is None:
        return None, ["north: 无数据"]
    return v, []


def option_pcr(ticker: str) -> tuple[dict, list[str]]:
    """美股期权 PCR（文本口径）。单独出口，避免拖慢普通快照。"""
    if not enabled("cboe"):
        return {}, ["cboe: 已禁用"]
    try:
        got = cboe.snapshot("美股", ticker) or {}
    except Exception as e:
        return {}, [f"cboe: {type(e).__name__}"]
    return got, ([] if got else ["cboe: 无数据"])


def describe() -> dict:
    """自检用：当前生效的源与链。"""
    cfg = load_config()
    return {
        "config_found": bool(cfg),
        "sources": {n: enabled(n) for n in SOURCES},
        "snapshot_chain": {m: _chain("snapshot", m)
                           for m in ("A股", "港股", "美股")},
        "kline_chain": {m: _chain("kline", m) for m in ("A股", "港股", "美股")},
    }


__all__ = ["SOURCES", "snapshot", "kline", "north_flow", "option_pcr",
           "describe", "load_config", "reset_config_cache", "enabled"]
