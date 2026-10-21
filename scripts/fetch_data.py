#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Daily Portfolio Analysis —— 取证脚本（证据门禁 Stage 1）

职责：
  1. 解析 holdings.md 持仓档案
  2. 用 akshare（可选，缺失自动降级）批量拉取行情/估值/资金流/历史K线，
     机械计算 MA / 52周位置 / ATR 等技术指标
  3. 为每只持仓生成符合 references/evidence-schema.md 的证据 JSON
     （拿不到的数据点显式标 missing 并写入 gaps，绝不编造）
  4. 生成宏观共享证据骨架 *_macro.json（新闻、财报、产业链、宏观数据
     必须由 agent 用 seed_finance_lookup / general_search 补证）

用法：
  python fetch_data.py --holdings holdings.md --session pre
  python fetch_data.py --holdings holdings.md --session post --date 2026-09-20
  python fetch_data.py --holdings holdings.md --session noon --no-network
  python fetch_data.py --holdings holdings.md --session quick --tickers AAPL

退出码：
  0 = 证据文件已生成（注意：是否达到门禁标准由 gate_check.py 判定）
  2 = holdings 文件不存在或解析不到任何持仓
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import re
import sys
import traceback
from pathlib import Path

SESSION_LABEL = {"pre": "盘前", "noon": "午间", "post": "盘后", "quick": "快速诊断"}

# ---------------------------------------------------------------------------
# 维度权重（与 evidence-standards.md 保持一致）
# ---------------------------------------------------------------------------
DIM_WEIGHTS = {
    "fundamental": 0.25,
    "technical": 0.20,
    "flow": 0.20,
    "news": 0.20,
    "chain": 0.15,
}

# 股票完整版（pre/post/quick）计划采集点
PLANNED_STOCK_FULL = {
    "technical": ["price_last", "day_change_pct", "ma5", "ma20", "ma60",
                  "range_52w_pct", "atr14", "volume_ratio"],
    "fundamental": ["pe_ttm", "pb", "market_cap", "roe",
                    "revenue_growth_yoy", "profit_growth_yoy"],
    "flow": ["main_net_inflow", "north_south_flow"],
    "news": [],      # 新闻条目，按条数考核
    "chain": [],     # chain_notes，按条数考核
}
# 午间精简版
PLANNED_STOCK_NOON = {
    "technical": ["price_last", "day_change_pct", "ma5", "ma20",
                  "range_52w_pct", "volume_ratio"],
    "fundamental": ["pe_ttm", "pb", "market_cap"],
    "flow": ["main_net_inflow"],
    "news": [],
    "chain": [],
}
# 基金
PLANNED_FUND = {
    "technical": ["nav_latest", "nav_change_pct", "nav_position_pct_1y"],
    "fundamental": ["fund_scale_change", "manager_change", "top_holdings"],
    "flow": [],
    "news": [],
    "chain": [],
}

FIELD_LABELS = {
    "price_last": "最新价", "day_change_pct": "当日涨跌幅%",
    "ma5": "5日均线", "ma20": "20日均线", "ma60": "60日均线",
    "range_52w_pct": "52周价格分位%", "atr14": "ATR14",
    "volume_ratio": "量比/量能变化",
    "pe_ttm": "市盈率TTM", "pb": "市净率", "market_cap": "总市值",
    "roe": "ROE%", "revenue_growth_yoy": "营收同比增速%",
    "profit_growth_yoy": "净利润同比增速%",
    "main_net_inflow": "主力净流入", "north_south_flow": "北向/南向资金",
    "put_call_or_inst": "期权PCR/机构动向",
    "nav_latest": "最新净值", "nav_change_pct": "净值涨跌%",
    "nav_position_pct_1y": "近一年净值分位%",
    "fund_scale_change": "基金规模变化", "manager_change": "基金经理变更",
    "top_holdings": "重仓方向",
}

HARD_REQUIRED = ["price_last", "day_change_pct"]
NEWS_MIN_FULL = 2
NEWS_MIN_NOON = 1
NEWS_MIN_P1P2_FULL = 1
CHAIN_MIN = 1


# ---------------------------------------------------------------------------
# 持仓档案解析
# ---------------------------------------------------------------------------
# 与 gate_check.SECTION_MARKET 保持完全一致：只认"## XX持仓"形式。
# 早期版本还认裸 "## A股"/"## 美股" 等短标题，会与 gate_check 口径不同，
# 导致同一份 holdings.md 解析出两套持仓（见 v2.2.3 修复说明）。
SECTION_MARKET = {
    "A股持仓": "A股",
    "基金持仓": "基金",
    "港股持仓": "港股",
    "美股持仓": "美股",
}


def _to_float(s):
    if s is None:
        return None
    s = str(s).strip().replace(",", "").replace("%", "")
    if s in ("", "-", "--", "N/A", "nan", "None"):
        return None
    try:
        v = float(s)
        return None if math.isnan(v) else v
    except ValueError:
        return None


def _to_qty(s):
    """数量列可能带中文单位：4,500份 / 1,400股。"""
    if s is None:
        return None
    t = re.sub(r"[份股张口手]", "", str(s).strip())
    return _to_float(t)


# --- 量纲归一（v2.2.3）------------------------------------------------------
# akshare 返回的"总市值/主力净流入"单位是【元】，而门禁区间与人工补证
# 一律用【亿元/万元】。不归一会出现"紫金矿业市值 7.78e11 被判疑似伪造"。
def _norm_market_cap(v):
    try:
        return None if v is None else round(float(v) / 1e8, 2)
    except (TypeError, ValueError):
        return None


def _norm_net_inflow(v):
    try:
        return None if v is None else round(float(v) / 1e4, 2)
    except (TypeError, ValueError):
        return None


def _field_unit(field, currency):
    if field == "market_cap":
        return f"亿元({currency})"
    if field in ("main_net_inflow", "north_south_flow"):
        return f"万元({currency})"
    return currency


def normalize_ticker(code: str, market: str) -> str:
    """归一化为 601899.SH / 00700.HK / AAPL 形式。"""
    code = str(code).strip().upper()
    if market == "美股":
        # 兼容 GOOG.US / GOOG.OQ 等券商写法；BRK.B / BF.B 这类类别股保留点号
        if "." in code:
            head, tail = code.rsplit(".", 1)
            if tail in ("US", "OQ", "NQ", "N", "PK", "P"):
                return head
        return code
    if market == "基金":
        return code
    digits = re.sub(r"\D", "", code)
    if market == "港股":
        if digits:
            return digits.zfill(5) + ".HK"
        return code
    if market == "A股":
        if len(digits) == 6:
            # 沪市：6/9 股票、68 科创板、5 开头基金/ETF、11/13 可转债
            if digits[0] in ("6", "9", "5") or digits.startswith("68"):
                suffix = ".SH"
            # 深市：0/3 股票、159 基金/ETF、12 可转债
            elif digits[0] in ("0", "3") or digits.startswith("159"):
                suffix = ".SZ"
            else:
                suffix = ".BJ"
            return digits + suffix
        return code
    # 兜底：按数字猜
    if len(digits) == 6:
        return normalize_ticker(digits, "A股")
    if digits and len(digits) <= 5 and code == digits:
        return digits.zfill(5) + ".HK"
    return code


CLOSED_STATUS_RE = re.compile(r"已清仓|清仓|已卖出|已售|已离场|已退市|退市|不再持有|已了结")


def _row_is_closed(name, cells):
    """名称带 Markdown 删除线 ~~~~，或数量/状态列写明清仓/已卖出，即视为已清仓，不再是持仓。"""
    if "~~" in (name or ""):
        return True
    for c in (cells[2:5] if len(cells) > 2 else []):
        if CLOSED_STATUS_RE.search(c or ""):
            return True
    return False


def parse_holdings(md_text: str):
    """解析 holdings.md，返回 [{name,ticker,market,account,quantity,cost,last}]。"""
    holdings = []
    current_market = None
    current_account = None
    for raw_line in md_text.splitlines():
        line = raw_line.strip()
        # 只认二级标题 ##（不含 ###），避免子标题干扰
        if re.match(r"^##(?!#)", line):
            matched_market = None
            for key, mkt in SECTION_MARKET.items():
                if key in line:
                    matched_market = mkt
                    current_account = line.lstrip("#").strip()
                    break
            # 非持仓章节（账户总览/持仓变动记录等）：退出市场上下文，
            # 其表格行不得被当成持仓
            current_market = matched_market
        if not line.startswith("|") or current_market is None:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        # 基金表常见只有 3 列（名称|金额|收益），不能要求 4 列（v2.2.3 修复：
        # 旧版 <4 会把整段场外基金漏掉，导致证据门"缺少证据文件"必 FAIL）
        if len(cells) < 2:
            continue
        # 表头/分隔行跳过
        if set("".join(cells)) <= set("-: ") or "名称" in cells[0] or "基金名称" in cells[0]:
            continue
        try:
            if current_market == "基金":
                if len(cells) < 2:
                    continue
                name = cells[0]
                # 兼容"帮你投 | 全球精选100 | 215.49 ..."这类名称被竖线拆开的行
                if _to_float(cells[1]) is None and len(cells) >= 3 \
                        and _to_float(cells[2]) is not None:
                    name = f"{cells[0]}-{cells[1]}"
                ticker = name  # 基金可能无代码，用名称做键
                quantity = cost = last = None
                amount = _to_float(cells[1])
            else:
                name, code = cells[0], cells[1]
                if not name:
                    continue
                if not re.search(r"[A-Za-z0-9]", code):
                    # 代码缺失（如持仓表中写"-"的场内ETF）：不丢标的，
                    # 用 NAME:<名称> 占位；取数跳过，由 agent 按名称补证/补代码
                    if current_market == "A股":
                        ticker = f"NAME:{name}"
                    else:
                        continue
                else:
                    ticker = normalize_ticker(code, current_market)
                quantity = _to_qty(cells[2]) if len(cells) > 2 else None
                cost = _to_float(cells[3]) if len(cells) > 3 else None
                last = _to_float(cells[4]) if len(cells) > 4 else None
                amount = _to_float(cells[5]) if len(cells) > 5 else None
            if _row_is_closed(name, cells):
                continue  # 删除线/已清仓标的不再取证
            holdings.append({
                "name": name,
                "ticker": ticker,
                "market": current_market,
                "account": current_account or current_market,
                "quantity": quantity,
                "cost": cost,
                "last": last,
            })
        except Exception:
            continue
    # 去重（同一代码可能在变动记录等表中重复）
    seen, uniq = set(), []
    for h in holdings:
        key = (h["market"], h["ticker"])
        if key in seen or not h["name"]:
            continue
        seen.add(key)
        uniq.append(h)
    return uniq


def parse_watchlist(md_text: str):
    """解析 watchlist.md，返回与 parse_holdings 同构的关注标的（带 watchlist 元数据）。

    已接回/已放弃/删除线行跳过；表格列顺序见 watchlist.md。
    """
    items, in_table = [], False
    for raw_line in md_text.splitlines():
        line = raw_line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        joined = "".join(cells)
        if "目标接回价" in joined and "代码" in joined:
            in_table = True  # 表头
            continue
        if not in_table or set(joined) <= set("-: ") or "名称" in cells[0]:
            continue
        if len(cells) < 9:
            continue
        name, code, market, status = cells[0], cells[1], cells[2], cells[8]
        if name.startswith("~~") or "已接回" in status or "已放弃" in status:
            continue
        if not re.search(r"[A-Za-z0-9]", code):
            continue
        items.append({
            "name": name,
            "ticker": normalize_ticker(code, market),
            "market": market,
            "account": "关注库",
            "quantity": _to_qty(cells[4]),   # 计划股数
            "cost": _to_float(cells[3]),     # 目标接回价
            "last": None,
            "watchlist": True,
            "target_price": _to_float(cells[3]),
            "planned_qty": _to_qty(cells[4]),
            "est_amount": _to_float(cells[5]),
            "stop_loss": _to_float(cells[6]),
            "added_date": cells[7],
            "status": status,
            "wl_logic": cells[9] if len(cells) > 9 else "",
        })
    return items


# ---------------------------------------------------------------------------
# 技术指标（纯标准库）
# ---------------------------------------------------------------------------
def _ma(closes, n):
    if len(closes) < n:
        return None
    return round(sum(closes[-n:]) / n, 4)


def _range_position(closes, n=252):
    window = closes[-n:] if len(closes) >= n else closes
    if len(window) < 10:
        return None
    lo, hi = min(window), max(window)
    if hi == lo:
        return None
    return round((closes[-1] - lo) / (hi - lo) * 100, 1)


def _atr(highs, lows, closes, n=14):
    if len(closes) < n + 1:
        return None
    trs = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    if len(trs) < n:
        return None
    return round(sum(trs[-n:]) / n, 4)


def _series_metrics(rows):
    """rows: list of dict(date,open,high,low,close,volume)，按日期升序。"""
    if not rows:
        return {}
    rows = sorted(rows, key=lambda r: r["date"])
    closes = [r["close"] for r in rows]
    highs = [r["high"] for r in rows]
    lows = [r["low"] for r in rows]
    vols = [r["volume"] for r in rows]
    last = closes[-1]
    prev = closes[-2] if len(closes) >= 2 else None
    out = {
        "price_last": round(last, 4),
        "day_change_pct": round((last - prev) / prev * 100, 2) if prev else None,
        "ma5": _ma(closes, 5),
        "ma20": _ma(closes, 20),
        "ma60": _ma(closes, 60),
        "range_52w_pct": _range_position(closes),
        "atr14": _atr(highs, lows, closes),
    }
    if len(vols) >= 6 and sum(vols[-6:-1]) > 0:
        out["volume_ratio"] = round(vols[-1] / (sum(vols[-6:-1]) / 5), 2)
    return out


# ---------------------------------------------------------------------------
# akshare 取数（任何失败都降级为 missing，由 gaps 显式披露）
# ---------------------------------------------------------------------------
class MarketDataFetcher:
    def __init__(self, network=True):
        self.network = network
        self.ak = None
        self.a_spot = None      # A股全市场快照，只拉一次
        self.hk_spot = None
        self.errors = []
        if network:
            try:
                import akshare as ak  # type: ignore
                self.ak = ak
            except ImportError:
                self.errors.append("未安装 akshare，脚本只生成取证骨架；行情/财务需 agent 补证")

    def _safe(self, fn, *args, **kwargs):
        if self.ak is None:
            return None
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            msg = f"{getattr(fn, '__name__', 'akshare_call')} 失败: {type(e).__name__}: {e}"
            if msg not in self.errors:
                self.errors.append(msg)
            return None

    # -- A 股 ---------------------------------------------------------------
    def _a_spot_row(self, digits6):
        if self.a_spot is None:
            self.a_spot = self._safe(self.ak.stock_zh_a_spot_em)
        if self.a_spot is None:
            return None
        try:
            hit = self.a_spot[self.a_spot["代码"] == digits6]
            return hit.iloc[0] if len(hit) else None
        except Exception:
            return None

    def _a_hist(self, digits6):
        end = dt.date.today()
        start = end - dt.timedelta(days=420)
        df = self._safe(
            self.ak.stock_zh_a_hist,
            symbol=digits6, period="daily",
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"), adjust="qfq",
        )
        return self._hist_rows(df, cn=True)

    def _a_flow(self, digits6):
        market = "sh" if digits6.startswith(("6", "9")) else "sz"
        df = self._safe(self.ak.stock_individual_fund_flow, stock=digits6, market=market)
        if df is None or len(df) == 0:
            return None
        try:
            row = df.iloc[-1]
            col = "主力净流入-净额" if "主力净流入-净额" in df.columns else df.columns[-2]
            return _to_float(row[col])
        except Exception:
            return None

    def fetch_a(self, ticker):
        digits6 = ticker.split(".")[0]
        points, gaps = [], []
        if self.ak is None:
            return points, gaps
        rows = self._a_hist(digits6)
        metrics = _series_metrics(rows) if rows else {}
        spot = self._a_spot_row(digits6)
        spot_map = {}
        if spot is not None:
            def g(name):
                try:
                    return spot[name]
                except Exception:
                    return None
            spot_map = {
                "price_last": _to_float(g("最新价")),
                "day_change_pct": _to_float(g("涨跌幅")),
                "volume_ratio": _to_float(g("量比")),
                "pe_ttm": _to_float(g("市盈率-动态")),
                "pb": _to_float(g("市净率")),
                # akshare 的"总市值"单位是元，统一折成亿元（与门禁/人工补证一致）
                "market_cap": _norm_market_cap(_to_float(g("总市值"))),
            }
        # 快照优先，历史指标补充
        merged = dict(metrics)
        for k, v in spot_map.items():
            if v is not None:
                merged[k] = v
        for field, value in merged.items():
            points.append(self._dp(field, value, "P3",
                                   "akshare:stock_zh_a_spot_em/hist",
                                   _field_unit(field, "CNY")))
        flow = self._a_flow(digits6)
        if flow is not None:
            # 单位元 → 万元（门禁区间按万元设定）
            points.append(self._dp("main_net_inflow", _norm_net_inflow(flow), "P3",
                                   "akshare:stock_individual_fund_flow",
                                   _field_unit("main_net_inflow", "CNY")))
        return points, gaps

    # -- 港股 ---------------------------------------------------------------
    def _hk_spot_row(self, digits5):
        if self.hk_spot is None:
            self.hk_spot = self._safe(self.ak.stock_hk_spot_em)
        if self.hk_spot is None:
            return None
        try:
            hit = self.hk_spot[self.hk_spot["代码"].astype(str).str.zfill(5) == digits5]
            return hit.iloc[0] if len(hit) else None
        except Exception:
            return None

    def _hk_hist(self, digits5):
        end = dt.date.today()
        start = end - dt.timedelta(days=420)
        df = self._safe(
            self.ak.stock_hk_hist,
            symbol=digits5, period="daily",
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"), adjust="qfq",
        )
        return self._hist_rows(df, cn=True)

    def fetch_hk(self, ticker):
        digits5 = ticker.split(".")[0].zfill(5)
        points = []
        if self.ak is None:
            return points, []
        rows = self._hk_hist(digits5)
        metrics = _series_metrics(rows) if rows else {}
        spot = self._hk_spot_row(digits5)
        if spot is not None:
            def g(name):
                try:
                    return spot[name]
                except Exception:
                    return None
            for field, col in [("price_last", "最新价"), ("day_change_pct", "涨跌幅"),
                               ("volume_ratio", "量比"), ("pe_ttm", "市盈率"),
                               ("pb", "市净率"), ("market_cap", "总市值")]:
                v = _to_float(g(col))
                if field == "market_cap":
                    v = _norm_market_cap(v)   # 港元 → 亿港元
                if v is not None:
                    metrics[field] = v
        for field, value in metrics.items():
            points.append(self._dp(field, value, "P3",
                                   "akshare:stock_hk_spot_em/hist",
                                   _field_unit(field, "HKD")))
        return points, []

    # -- 美股 ---------------------------------------------------------------
    def _us_hist(self, symbol):
        # 新浪源（SKILL 已验证），失败再试 yfinance；yfinance 不依赖 akshare
        rows = []
        if self.ak is not None:
            df = self._safe(self.ak.stock_us_daily, symbol=symbol, adjust="qfq")
            rows = self._hist_rows(df, cn=False)
        if rows:
            return rows
        try:
            import yfinance as yf  # type: ignore
            end = dt.date.today()
            start = end - dt.timedelta(days=420)
            t = yf.Ticker(symbol)
            df = t.history(start=start, end=end)
            out = []
            for idx, r in df.iterrows():
                out.append({"date": idx.strftime("%Y-%m-%d"),
                            "open": float(r["Open"]), "high": float(r["High"]),
                            "low": float(r["Low"]), "close": float(r["Close"]),
                            "volume": float(r["Volume"])})
            return out
        except Exception as e:
            if "yfinance" not in "".join(self.errors):
                self.errors.append(f"美股K线获取失败（akshare/yfinance 均不可用）: {e}")
            return []

    def fetch_us(self, ticker):
        # v2.2.3：不再因 akshare 缺失直接返回空——yfinance 独立可用
        rows = self._us_hist(ticker)
        metrics = _series_metrics(rows) if rows else {}
        points = [self._dp(k, v, "P3", "akshare:stock_us_daily/yfinance", "USD")
                  for k, v in metrics.items()]
        return points, []

    # -- 共用 ---------------------------------------------------------------
    @staticmethod
    def _dp(field, value, level, source, unit):
        return {
            "id": "",  # 组装时统一编号
            "dimension": _DIM_OF_FIELD.get(field, "fundamental"),
            "field": field,
            "label": FIELD_LABELS.get(field, field),
            "value": value,
            "unit": unit,
            "as_of": dt.date.today().isoformat(),
            "source": source,
            "source_url": "",
            "evidence_level": level,
            "fetched_by": "script",
            "status": "verified" if value is not None else "missing",
        }

    @staticmethod
    def _hist_rows(df, cn):
        if df is None or len(df) == 0:
            return []
        try:
            if cn:
                col = {"date": "日期", "open": "开盘", "high": "最高",
                       "low": "最低", "close": "收盘", "volume": "成交量"}
            else:
                cols = {c.lower(): c for c in df.columns}
                col = {"date": cols.get("date", "date"),
                       "open": cols.get("open", "open"),
                       "high": cols.get("high", "high"),
                       "low": cols.get("low", "low"),
                       "close": cols.get("close", "close"),
                       "volume": cols.get("volume", "volume")}
            rows = []
            for _, r in df.iterrows():
                rows.append({
                    "date": str(r[col["date"]])[:10],
                    "open": _to_float(r[col["open"]]),
                    "high": _to_float(r[col["high"]]),
                    "low": _to_float(r[col["low"]]),
                    "close": _to_float(r[col["close"]]),
                    "volume": _to_float(r[col["volume"]]) or 0,
                })
            return [r for r in rows if r["close"] is not None]
        except Exception:
            return []


_DIM_OF_FIELD = {}
for _dim, _fields in list(PLANNED_STOCK_FULL.items()) + list(PLANNED_FUND.items()):
    for _f in _fields:
        _DIM_OF_FIELD[_f] = _dim
_DIM_OF_FIELD.update({"price_last": "technical", "day_change_pct": "technical",
                      "put_call_or_inst": "flow"})


# ---------------------------------------------------------------------------
# 证据文件组装
# ---------------------------------------------------------------------------
def planned_for(market, session):
    if market == "基金":
        return PLANNED_FUND
    if session == "noon":
        return PLANNED_STOCK_NOON
    return PLANNED_STOCK_FULL


def instrument_for(holding):
    """识别证券类型：FUND 场外基金 / ETF 场内基金 / LEVERAGED_ETP 杠杆反向产品 / STOCK 个股。

    场内 ETF 与杠杆 ETP 没有个股 PE/ROE，统一走基金（净值/跟踪标的）口径。
    """
    market, name, ticker = holding["market"], holding.get("name", ""), holding["ticker"]
    if market == "基金":
        # 投顾组合/帮你投：无单独净值代码，不做个券深度分析
        if re.search(r"帮你投|投顾|全球精选", name):
            return "ADVISORY"
        return "FUND"
    # 现金管理类（短债/货币 ETF，如 SGOV）：净值稳定在 100 附近，仅列示
    if re.search(r"SGOV|现金管理|0-3月国债|国债ETF|货币基金|短债", name):
        return "CASH_MGMT"
    if re.search(r"GraniteShare|XL二|南方.*(?:杠杆|反向|2x|两倍)|每日杠杆|每日反向|2x|2X",
                 name):
        return "LEVERAGED_ETP"
    if "ETF" in name.upper() or ticker.startswith("NAME:"):
        return "ETF"
    # A股场内基金代码号段：沪市 51/56/58 开头，深市 159 开头
    digits = re.sub(r"\D", "", ticker)
    if market == "A股" and (digits.startswith(("51", "56", "58")) or digits.startswith("159")):
        return "ETF"
    return "STOCK"


def build_evidence(holding, session, fetcher, date_str, depth=None):
    depth = depth or frozenset()
    market = holding["market"]
    instrument = instrument_for(holding)
    # 场外基金、场内 ETF、杠杆/反向 ETP、现金管理一律走基金（净值/跟踪标的）口径
    advisory = instrument == "ADVISORY"
    cash_mgmt = instrument == "CASH_MGMT"
    fund_like = market == "基金" or instrument in (
        "ETF", "LEVERAGED_ETP", "FUND", "ADVISORY", "CASH_MGMT")
    # 简列关注：watchlist 但不在深度名单，只取现价、不要求多空新闻/产业链
    brief_wl = bool(holding.get("watchlist")) and holding["ticker"] not in depth
    if fund_like:
        planned = {k: list(v) for k, v in PLANNED_FUND.items()}
    else:
        planned = {k: list(v) for k, v in planned_for(market, session).items()}
        # 美股个股资金面维度用期权/机构动向，A股/港股用主力资金与南北向
        if market == "美股" and "flow" in planned:
            planned["flow"] = ["put_call_or_inst"]
    points, gaps = [], []

    if holding["ticker"].startswith("NAME:"):
        gaps.append(f"标的 {holding['name']} 在 holdings.md 中缺证券代码，"
                    f"脚本无法取数：请补 6 位代码后重跑，或由 agent 按名称用 "
                    f"seed_finance_lookup/general_search 补证")
    elif market == "基金":
        gaps.append("场外基金无实时行情，需 agent 用 seed_finance_lookup/平台数据补净值与持仓")
    elif fund_like:
        # 场内 ETF / 杠杆 ETP：取交易价格，映射为净值口径，其余技术点保留供报告引用
        if market == "A股":
            raw, gaps = fetcher.fetch_a(holding["ticker"])
        elif market == "港股":
            raw, gaps = fetcher.fetch_hk(holding["ticker"])
        else:
            raw, gaps = fetcher.fetch_us(holding["ticker"])
        for p in raw:
            points.append(p)
            if p["field"] == "price_last":
                q = dict(p); q["field"] = "nav_latest"
                q["label"] = FIELD_LABELS["nav_latest"]; points.append(q)
            if p["field"] == "day_change_pct":
                q = dict(p); q["field"] = "nav_change_pct"
                q["label"] = FIELD_LABELS["nav_change_pct"]; points.append(q)
        if instrument == "LEVERAGED_ETP":
            gaps.append("杠杆/反向 ETP 无个股基本面：fund_scale_change 填产品规模、"
                        "top_holdings 填跟踪标的与杠杆倍数，ROE/营收增速等不适用")
    elif market == "A股":
        points, gaps = fetcher.fetch_a(holding["ticker"])
    elif market == "港股":
        points, gaps = fetcher.fetch_hk(holding["ticker"])
    elif market == "美股":
        points, gaps = fetcher.fetch_us(holding["ticker"])

    # 按计划点补 missing 骨架（保证 gate 能逐项核对，也给 agent 明确待补清单）
    have_fields = {p["field"] for p in points}
    for dim, fields in planned.items():
        if dim in ("news", "chain"):
            continue
        for f in fields:
            if f not in have_fields:
                points.append({
                    "id": "", "dimension": dim, "field": f,
                    "label": FIELD_LABELS.get(f, f), "value": None,
                    "unit": "", "as_of": date_str, "source": "",
                    "source_url": "", "evidence_level": "P3",
                    "fetched_by": "agent", "status": "missing",
                })
                gaps.append(f"{FIELD_LABELS.get(f, f)}（{f}）未取到，需 agent 补证")

    # 统一编号
    for i, p in enumerate(points, 1):
        p["id"] = f"dp-{i:03d}"

    evidence = {
        "schema_version": "1.0",
        "report_date": date_str,
        "session": session,
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "ticker": holding["ticker"],
        "name": holding["name"],
        "market": market,
        "instrument": instrument,
        "account": holding["account"],
        "holding": {
            "quantity": holding["quantity"],
            "cost": holding["cost"],
            "last_close_in_holdings": holding["last"],
        },
        "planned": {k: list(v) for k, v in planned.items()},
        "data_points": points,
        "news": [],
        "chain_notes": [],
        "gaps": sorted(set(gaps)),
    }
    if advisory:
        evidence["gaps"].append(
            "投顾组合（帮你投/全球精选）无公开净值代码，仅按持仓金额列示，不做个券四层分析")
    elif cash_mgmt:
        evidence["gaps"].append(
            "现金管理工具（短债/货币ETF，如 SGOV）：净值稳定在 100 附近，"
            "仅按持仓金额列示，不做个券四层分析")
    elif brief_wl:
        evidence["gaps"].append(
            "简列关注：仅取现价用于关注库总览表，不做深度多空新闻/产业链取证；"
            "到价会在总览表标红并提示，需深度分析时把代码加入 watchlist_depth.json")
    else:
        news_min = NEWS_MIN_NOON if session == "noon" else NEWS_MIN_FULL
        evidence["gaps"].append(
            f"需 agent 补新闻至少 {news_min} 条（完整版至少 1 条 P1/P2，须带可访问 URL）")
        evidence["gaps"].append("需 agent 补产业链/赛道判断至少 1 条 chain_note（生命周期/SEI/中军龙头）")
    if holding.get("watchlist"):
        evidence["watchlist"] = {
            "target_buy_price": holding.get("target_price"),
            "planned_qty": holding.get("planned_qty"),
            "stop_loss": holding.get("stop_loss"),
            "added_date": holding.get("added_date"),
            "status": holding.get("status"),
        }
        if not brief_wl:
            evidence["gaps"].append(
                "关注库标的：需专家多维分析（K线/成交量等技术面 + 利好利空新闻，"
                "≥2 独立来源族、含多空），展示现价/目标接回价/距目标价%/距高点回撤%；"
                "未到价不得喊买入，到价给执行清单或喊'先别接'")
    return evidence


def build_macro_skeleton(session, date_str):
    macro_fields = [
        ("us_index_futures", "美股三大指数/期货"),
        ("vix", "VIX 恐慌指数"),
        ("dxy", "美元指数"),
        ("us10y", "美债10年收益率"),
        ("wti", "WTI原油"),
        ("gold", "黄金"),
        ("btc", "比特币"),
    ]
    points = [{
        "id": f"dp-{i:03d}", "dimension": "macro", "field": f,
        "label": label, "value": None, "unit": "", "as_of": date_str,
        "source": "", "source_url": "", "evidence_level": "P3",
        "fetched_by": "agent", "status": "missing",
    } for i, (f, label) in enumerate(macro_fields, 1)]
    gaps = ["宏观数据需 agent 用 seed_finance_lookup/general_search 补证"]
    return {
        "schema_version": "1.0", "report_date": date_str, "session": session,
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "ticker": "_macro", "name": "宏观共享证据", "market": "macro",
        "data_points": points, "news": [], "chain_notes": [], "gaps": gaps,
    }


def safe_name(ticker):
    """把 ticker/基金名转成跨平台安全文件名。

    v2.2.3：补上 Windows 非法字符（反斜杠 / 通配符 / 引号 / 竖线）。
    Markdown 表格里 `帮你投 \\| 全球精选100` 转义后 cells[0] 含反斜杠，
    Linux 上合法、Windows 上是路径分隔符，旧版会直接 FileNotFoundError。
    只增加替换、不改变原有 . / : 的映射，历史证据文件名保持兼容。
    """
    out = str(ticker)
    for ch in (".", "/", ":", chr(92), "*", "?", '"', "<", ">", "|"):
        out = out.replace(ch, "_")
    return out


def ensure_utf8_stdout():
    """Windows 控制台/计划任务默认 GBK，打印 ✗/✅ 会 UnicodeEncodeError 中断流程。

    统一把 stdout/stderr 切到 UTF-8（极端环境退化为替换字符，绝不抛异常）。
    """
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def load_depth(base_dir, session):
    """读取 watchlist_depth.json，返回本 session 深度关注 ticker 集合。"""
    p = Path(base_dir) / "watchlist_depth.json"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return frozenset(str(t) for t in d.get(session, []))
    except Exception:
        return frozenset()


def main():
    ensure_utf8_stdout()
    ap = argparse.ArgumentParser(description="持仓证据取证脚本（证据门禁 Stage 1）")
    ap.add_argument("--holdings", required=False, help="holdings.md 路径")
    ap.add_argument("--session", choices=list(SESSION_LABEL), default="pre")
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--report-root", help="证据输出根目录，默认 holdings 同级 daily-reports/")
    ap.add_argument("--tickers", default="", help="只处理部分标的，逗号分隔（快速诊断用）")
    ap.add_argument("--no-network", action="store_true", help="不调用 akshare，只生成取证骨架")
    args = ap.parse_args()

    holdings_path = None
    candidates = []
    if args.holdings:
        candidates.append(Path(args.holdings))
    env = os.environ.get("DAILY_HOLDINGS")
    if env:
        candidates.append(Path(env))
    candidates += [
        Path("holdings.md"),
        Path("/home/user/Doubao/chats/38441678557998594/holdings.md"),
    ]
    for c in candidates:
        if c.exists():
            holdings_path = c
            break
    if holdings_path is None:
        print("[error] 找不到 holdings.md，请用 --holdings 指定路径")
        sys.exit(2)

    md_text = holdings_path.read_text(encoding="utf-8")
    holdings = parse_holdings(md_text)
    if not holdings:
        print(f"[error] {holdings_path} 中未解析到任何持仓（请检查表格是否符合模板）")
        sys.exit(2)

    # 关注库：仅纳入"接下来要开盘市场"对应标的（pre→A股/港股，post→美股），
    # noon/quick 不自动纳入；与持仓合并去重（持仓在前）。
    wl_markets = {"pre": {"A股", "港股"}, "post": {"美股"}}.get(args.session, set())
    wl_path = holdings_path.parent / "watchlist.md"
    watchlist = []
    if wl_markets and wl_path.exists():
        watchlist = [w for w in parse_watchlist(wl_path.read_text(encoding="utf-8"))
                     if w["market"] in wl_markets]
    merged, mseen = [], set()
    for h in holdings + watchlist:
        key = (h["market"], h["ticker"])
        if key in mseen:
            continue
        mseen.add(key)
        merged.append(h)
    holdings = merged

    # 午间只聚焦 A股/港股（午后要操作的市场）；场外基金净值午间不更新、美股仅隔夜背景，均不展开卡片
    if args.session == "noon":
        holdings = [h for h in holdings if h["market"] in {"A股", "港股"}]

    if args.tickers:
        wanted = {t.strip().upper() for t in args.tickers.split(",") if t.strip()}
        holdings = [h for h in holdings
                    if h["ticker"].upper() in wanted or h["name"] in wanted]

    report_root = Path(args.report_root) if args.report_root \
        else holdings_path.parent / "daily-reports"
    ev_dir = report_root / "evidence"
    ev_dir.mkdir(parents=True, exist_ok=True)

    print(f"[fetch] holdings={holdings_path}")
    print(f"[fetch] session={args.session}({SESSION_LABEL[args.session]}) "
          f"标的数={len(holdings)} network={not args.no_network}")

    fetcher = MarketDataFetcher(network=not args.no_network)
    depth = load_depth(holdings_path.parent, args.session)
    written = []
    for h in holdings:
        ev = build_evidence(h, args.session, fetcher, args.date, depth=depth)
        out = ev_dir / f"{args.date}_{args.session}_{safe_name(h['ticker'])}.json"
        out.write_text(json.dumps(ev, ensure_ascii=False, indent=2), encoding="utf-8")
        verified = sum(1 for p in ev["data_points"] if p["status"] == "verified")
        total = len(ev["data_points"])
        written.append(out)
        print(f"  - {h['name']:<12} {h['ticker']:<10} "
              f"脚本已验证 {verified}/{total} 个数据点 → {out.name}")

    # 宏观骨架（quick 时段不需要）
    if args.session != "quick":
        macro = build_macro_skeleton(args.session, args.date)
        mout = ev_dir / f"{args.date}_{args.session}_macro.json"
        mout.write_text(json.dumps(macro, ensure_ascii=False, indent=2), encoding="utf-8")
        written.append(mout)
        print(f"  - 宏观证据骨架 → {mout.name}")

    if fetcher.errors:
        print("\n[warn] 取数过程中的降级（已写入 gaps，不影响骨架生成）:")
        for e in dict.fromkeys(fetcher.errors):
            print(f"  · {e}")

    print(f"\n[next] 1) agent 补证（新闻/财报/产业链/宏观，写回上述 JSON）")
    print(f"       2) python gate_check.py --report-root {report_root} "
          f"--date {args.date} --session {args.session} --stage evidence")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
