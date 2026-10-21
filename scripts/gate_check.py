#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Daily Portfolio Analysis —— 门禁校验脚本（证据门禁 Stage 2 / 报告门禁 Stage 3）

两道硬门禁，把"先取证、再思考、后输出"从口号变成机械约束：

  --stage evidence  辩论前运行：
      * 每只持仓必须有证据文件（fetch_data.py 生成、agent 补证）
      * 硬必需：股票 price_last / day_change_pct 必须 verified（基金 nav_latest）
      * 新闻最低条数与 P1/P2 要求、产业链笔记要求
      * 机械计算每只持仓与组合覆盖率（agent 口述无效）
      * missing 点必须在 gaps 中显式披露

  --stage report    报告生成后、present_files 前运行：
      * 每个标的章节的多空论点必须引用证据 ID（[dp-xxx]/[nw-xxx]/[ch-xxx]）
      * 引用的 ID 必须真实存在（防伪造）
      * 报告顶部覆盖率数字必须等于机械值（±3%）
      * 信息来源折叠区、免责声明、缺口披露区块必须存在

退出码：0=PASS  1=FAIL（必须返工）  3=DEGRADED（显式降级声明后可继续）
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402

DIM_WEIGHTS_STOCK = {"fundamental": 0.25, "technical": 0.20, "flow": 0.20,
                     "news": 0.20, "chain": 0.15}
DIM_WEIGHTS_FUND = {"fundamental": 0.40, "technical": 0.30,
                    "news": 0.15, "chain": 0.15}

NEWS_MIN = {"pre": 2, "post": 2, "noon": 1, "quick": 1}
NEWS_P1P2_MIN = {"pre": 1, "post": 1, "noon": 0, "quick": 0}
CHAIN_MIN_STOCK = {"pre": 1, "post": 1, "noon": 1, "quick": 0}

PASS, FAIL, DEGRADED = 0, 1, 3
STATUS_SCORE = {"verified": 1.0, "estimated": 0.5, "missing": 0.0}


# ---------------------------------------------------------------------------
# holdings 解析（与 fetch_data 同构，独立实现以保证单文件可运行）
# ---------------------------------------------------------------------------
SECTION_MARKET = {"A股持仓": "A股", "基金持仓": "基金",
                  "港股持仓": "港股", "美股持仓": "美股"}

# 与 fetch_data 同构的"计划采集点"（v2.2.3 起覆盖率分母由本表重算，
# 不再信任证据文件里可被改写的 planned 字段）
PLANNED_STOCK_FULL = {
    "technical": ["price_last", "day_change_pct", "ma5", "ma20", "ma60",
                  "range_52w_pct", "atr14", "volume_ratio"],
    "fundamental": ["pe_ttm", "pb", "market_cap", "roe",
                    "revenue_growth_yoy", "profit_growth_yoy"],
    "flow": ["main_net_inflow", "north_south_flow"],
}
PLANNED_STOCK_NOON = {
    "technical": ["price_last", "day_change_pct", "ma5", "ma20",
                  "range_52w_pct", "volume_ratio"],
    "fundamental": ["pe_ttm", "pb", "market_cap"],
    "flow": ["main_net_inflow"],
}
PLANNED_FUND = {
    "technical": ["nav_latest", "nav_change_pct", "nav_position_pct_1y"],
    "fundamental": ["fund_scale_change", "manager_change", "top_holdings"],
}

# 这些字段本来就允许是文字（基金/ETF 的描述项），其余命中即要求数值
TEXT_ONLY_FIELDS = {"manager_change", "top_holdings", "put_call_or_inst"}
NUMERIC_FIELDS = {f for plan in (PLANNED_STOCK_FULL, PLANNED_STOCK_NOON, PLANNED_FUND)
                  for fields in plan.values() for f in fields} - TEXT_ONLY_FIELDS


CLOSED_STATUS_RE = re.compile(r"已清仓|清仓|已卖出|已售|已离场|已退市|退市|不再持有|已了结")


def _row_is_closed(name, cells):
    """识别持仓表中已卖出/清仓的行：名称带 Markdown 删除线 ~~~~，或数量/状态列写明清仓。"""
    if "~~" in (name or ""):
        return True
    for c in (cells[2:5] if len(cells) > 2 else []):
        if CLOSED_STATUS_RE.search(c or ""):
            return True
    return False


def _clean_closed_name(n):
    return (n or "").replace("~", "").strip()


def parse_closed_positions(md_text):
    """提取持仓表中已清仓/删除线标的，供报告门拦截'残留持仓卡片'。"""
    closed, mkt = [], None
    for raw in md_text.splitlines():
        line = raw.strip()
        if re.match(r"^##(?!#)", line):
            mkt = None
            for k, v in SECTION_MARKET.items():
                if k in line:
                    mkt = v
                    break
        if not line.startswith("|") or mkt is None:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2 or set("".join(cells)) <= set("-: ") or "名称" in cells[0]:
            continue
        name = cells[0]
        if not _row_is_closed(name, cells):
            continue
        if mkt == "基金":
            closed.append({"name": _clean_closed_name(name),
                           "ticker": _clean_closed_name(name), "market": mkt})
        elif len(cells) > 1 and re.search(r"[A-Za-z0-9]", cells[1]):
            closed.append({"name": _clean_closed_name(name),
                           "ticker": normalize_ticker(cells[1], mkt), "market": mkt})
    seen, uniq = set(), []
    for c in closed:
        if c["ticker"] not in seen:
            seen.add(c["ticker"])
            uniq.append(c)
    return uniq


def parse_holdings(md_text):
    holdings, mkt, acct = [], None, None
    for raw in md_text.splitlines():
        line = raw.strip()
        # 只认二级标题 ##（不含 ###）；非持仓章节退出市场上下文
        if re.match(r"^##(?!#)", line):
            mkt, acct = None, None
            for k, v in SECTION_MARKET.items():
                if k in line:
                    mkt, acct = v, line.lstrip("#").strip()
                    break
        if not line.startswith("|") or mkt is None:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2 or set("".join(cells)) <= set("-: ") or "名称" in cells[0]:
            continue
        try:
            if mkt == "基金":
                name = cells[0]
                # 兼容名称被竖线拆开的行（帮你投 | 全球精选100 | 金额）
                if len(cells) >= 3 and _to_float_gate(cells[1]) is None \
                        and _to_float_gate(cells[2]) is not None:
                    name = f"{cells[0]}-{cells[1]}"
                ticker = name
            else:
                name, code = cells[0], cells[1]
                if not name:
                    continue
                if not re.search(r"[A-Za-z0-9]", code):
                    if mkt == "A股":
                        ticker = f"NAME:{name}"
                    else:
                        continue
                else:
                    ticker = normalize_ticker(code, mkt)
            if _row_is_closed(name, cells):
                continue  # 删除线/已清仓标的不再是持仓，禁止取证与生成卡片
            holdings.append({"name": name, "ticker": ticker, "market": mkt,
                             "account": acct or mkt})
        except Exception:
            continue
    seen, uniq = set(), []
    for h in holdings:
        key = (h["market"], h["ticker"])
        if key not in seen and h["name"]:
            seen.add(key)
            uniq.append(h)
    return uniq


def parse_watchlist(md_text):
    """解析 watchlist.md，返回与 parse_holdings 同构的关注标的（带 watchlist 元数据）。

    已接回/已放弃/删除线行跳过；表格列顺序见 watchlist.md。
    """
    items, in_table = [], False
    for raw in md_text.splitlines():
        line = raw.strip()
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
            "watchlist": True,
            "status": status,
            "target_price": _to_float_gate(cells[3]),
            "planned_qty": _to_float_gate(cells[4]),
            "stop_loss": _to_float_gate(cells[6]),
            "added_date": cells[7],
            "wl_logic": cells[9] if len(cells) > 9 else "",
        })
    return items


def _to_float_gate(s):
    try:
        return float(str(s).strip().replace(",", "").replace("%", ""))
    except (ValueError, TypeError):
        return None


def normalize_ticker(code, market):
    code = str(code).strip().upper()
    digits = re.sub(r"\D", "", code)
    if market == "美股":
        # 兼容 GOOG.US / GOOG.OQ；BRK.B / BF.B 这类类别股保留点号
        if "." in code:
            head, tail = code.rsplit(".", 1)
            if tail in ("US", "OQ", "NQ", "N", "PK", "P"):
                return head
        return code
    if market == "基金":
        return code
    if market == "港股":
        return (digits.zfill(5) + ".HK") if digits else code
    if len(digits) == 6:
        # 沪市：6/9 股票、5 开头基金/ETF；深市：0/3 股票、159 基金/ETF
        if digits[0] in ("6", "9", "5"):
            return digits + ".SH"
        if digits[0] in ("0", "3") or digits.startswith("159"):
            return digits + ".SZ"
        return digits + ".BJ"
    return code


def safe_name(ticker):
    """跨平台安全文件名。实现已统一到 paths.safe_name（v2.6.0）。

    这里保留同名入口，是因为证据文件名规则被 gate 与 fetch 同时依赖，
    两处各写一份映射迟早会漂移（曾出现 Windows 反斜杠只在一边被替换）。
    """
    return paths.safe_name(ticker)


# ---------------------------------------------------------------------------
# 覆盖率机械计算
# ---------------------------------------------------------------------------
def expected_plan(ev, session):
    """覆盖率分母（唯一真相）：按 market/instrument/session 机械推导。

    v2.2.3 安全修复：旧版分母直接取证据文件里的 `ev["planned"]`，而该文件
    由 agent 原地写回——只要删掉 planned 里的 technical/fundamental/flow，
    2 条新闻 + 1 条产业链就能拿到 100% 覆盖率。现在分母不再信任文件。
    """
    market = ev.get("market")
    inst = ev.get("instrument")
    if market == "基金" or inst in ("FUND", "ETF", "LEVERAGED_ETP",
                                   "ADVISORY", "CASH_MGMT"):
        return {k: list(v) for k, v in PLANNED_FUND.items()}
    base = PLANNED_STOCK_NOON if session == "noon" else PLANNED_STOCK_FULL
    plan = {k: list(v) for k, v in base.items()}
    if market == "美股":
        plan["flow"] = ["put_call_or_inst"]
    return plan


def dim_score_numeric(ev, dim, planned_fields=None):
    planned = set(planned_fields if planned_fields is not None
                  else ev.get("planned", {}).get(dim, []))
    if not planned:
        return None, {}
    best = {}
    for p in ev.get("data_points", []):
        if p.get("dimension") != dim:
            continue
        f = p.get("field")
        s = STATUS_SCORE.get(p.get("status", "missing"), 0)
        # P4 证据最多算 estimated
        if p.get("evidence_level") == "P4" and s == 1.0:
            s = 0.5
        best[f] = max(best.get(f, 0), s)
    total, got = 0.0, 0.0
    detail = {}
    for f in planned:
        total += 1.0
        s = best.get(f, 0.0)
        got += s
        detail[f] = s
    return (got / total if total else None), detail


def source_family(item):
    """把一条新闻归一到'独立来源族'：优先用 URL 主域名（去 www./端口），否则用来源名。"""
    url = item.get("url", "") or ""
    m = re.match(r"[a-zA-Z][a-zA-Z0-9+.\-]*://([^/#?]+)", url)
    host = (m.group(1) if m else "").lower()
    host = host.split("@")[-1].split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    if host:
        return host
    return (item.get("source", "") or "未知").strip() or "未知"


def _is_article_url(url):
    """判断 URL 是否指向'具体文章/行情页'，用于拦'只填网站首页/栏目页凑数'。"""
    if not url:
        return False
    s = str(url).strip()
    m = re.match(r"[a-zA-Z][a-zA-Z0-9+.\-]*://[^/]+(/[^?#]*)?", s)
    path = (m.group(1) if m else (s if "/" in s else "/" + s)) or "/"
    seg = path.strip("/")
    if not seg:
        return False  # 纯首页 https://host/
    if re.search(r"\d{5,}", seg):
        return True   # 路径含长数字（文章/行情 id）
    last = seg.split("/")[-1]
    if re.search(r"[A-Za-z]", last) and re.search(r"\d", last) and len(last) >= 8:
        return True   # 字母数字混合的长 id（如凤凰 c/8wg3m45e5WN）
    if len(last) >= 14:
        return True
    if re.search(r"/(detail|content|article|post|c|a|p)/[A-Za-z0-9]", seg) and len(seg) >= 10:
        return True
    if "/" not in seg and len(seg) <= 10:
        return False  # 单短词栏目页
    return len(seg) >= 16


# 数值型字段的合理区间（min, max）；量纲随字段，越界即视为伪造/错误
FIELD_RANGES = {
    "day_change_pct": (-22, 22), "nav_change_pct": (-22, 22),
    "range_52w_pct": (0, 100), "nav_position_pct_1y": (0, 100),
    "volume_ratio": (0, 30), "pe_ttm": (-2000, 2000), "pb": (0, 200),
    "roe": (-100, 300), "revenue_growth_yoy": (-99, 900),
    "profit_growth_yoy": (-99, 900),
    "main_net_inflow": (-1e7, 1e7), "north_south_flow": (-1e7, 1e7),
}
# 量纲不同、正常情况下绝不应取相同数值的字段（用于抓'多个字段全=1.0'占位）
DISTINCT_SCALE_FIELDS = {
    "price_last", "nav_latest", "pe_ttm", "pb", "market_cap",
    "ma5", "ma20", "ma60", "atr14"}


def _price_bounds(instrument, field):
    if field == "price_last":
        if instrument == "STOCK":
            return (1.5, 1e8)
        if instrument in ("ETF", "FUND"):
            return (0.15, 60)
        if instrument == "LEVERAGED_ETP":
            return (0.1, 1e6)
    if field == "nav_latest":
        return (0.08, 1e6)
    if field in ("ma5", "ma20", "ma60"):
        return (0.08, 1e8)
    if field == "market_cap":
        return (0.5, 1e6)          # 亿元口径；0.5 亿以下多为壳/微型股，上限 100 万亿
    if field == "atr14":
        return (0.01, 1e8)
    return None


def validate_authenticity(ev):
    """证据真实性校验：拦占位值/缺来源/量纲冲突/越界数值。返回 problems 列表。

    设计目标：脚本网络不通、agent 只能手工补证时，禁止用 1.0 等占位值把
    '字段非空'糊弄过去；取不到就必须留 missing。
    """
    problems = []
    instrument = ev.get("instrument")
    dps = ev.get("data_points", [])

    # 0) verified 的数值型字段必须真的是数字（v2.2.3）
    #    旧版只按 status 计分，填 "暂无数据，稍后补" 这种字符串也能拿满分。
    for p in dps:
        if p.get("status") != "verified":
            continue
        v = p.get("value")
        if p.get("field") in NUMERIC_FIELDS and (isinstance(v, bool)
                                                or not isinstance(v, (int, float))):
            problems.append(
                f"数据点 {p.get('id')}（{p.get('field')}）status=verified 但值不是数字"
                f"（{v!r}）——数值字段请填数字，文字说明放 note 字段；"
                f"确实只有定性信息时把 status 降为 estimated 或 missing")

    num = [p for p in dps if p.get("status") == "verified"
           and isinstance(p.get("value"), (int, float)) and not isinstance(p["value"], bool)]

    # 1) verified 数值必须注明来源
    for p in num:
        if not str(p.get("source", "")).strip():
            problems.append(
                f"verified 数据点 {p.get('id')}（{p.get('field')}）缺少 source"
                f"——真实数据必须注明可追溯来源，无来源的数值按占位处理")

    # 2) 跨字段同值（量纲不同却完全相等，典型占位）
    bucket = {}
    for p in num:
        f = p.get("field")
        if f in DISTINCT_SCALE_FIELDS:
            bucket.setdefault(round(float(p["value"]), 4), set()).add(f)
    for v, fs in bucket.items():
        if len(fs) >= 3:
            problems.append(
                f"多个量纲不同的字段 {sorted(fs)} 取值完全相同（={v}）"
                f"——这是占位值的典型特征（如全填1.0），禁止按 verified 计分")

    # 3) 价格/净值/均线/市值的合理性
    for p in num:
        f, v = p.get("field"), float(p["value"])
        b = _price_bounds(instrument, f)
        if b and not (b[0] <= v <= b[1]):
            problems.append(
                f"数据点 {p.get('id')}（{f}）={v} 超出合理区间 {b}，疑似错误/占位")
        r = FIELD_RANGES.get(f)
        if r and not (r[0] <= v <= r[1]):
            problems.append(
                f"数据点 {p.get('id')}（{f}）={v} 超出合理区间 [{r[0]},{r[1]}]")
    return problems


def news_score(ev, session):
    news = [n for n in ev.get("news", []) if n.get("status", "verified") != "missing"]
    valid = []
    for n in news:
        if not (n.get("url") and n.get("evidence_level") in ("P1", "P2", "P3")):
            continue
        headline = str(n.get("headline", "")).strip()
        if len(headline) < 8 or not _is_article_url(n.get("url")):
            continue  # 无标题或只填首页/栏目页，不计入有效新闻
        valid.append(n)
    p1p2 = [n for n in valid if n.get("evidence_level") in ("P1", "P2")]
    need = NEWS_MIN.get(session, 2)
    score = min(len(valid) / need, 1.0) if need else 1.0
    return score, {"valid": len(valid), "p1p2": len(p1p2),
                   "need": need, "p1p2_need": NEWS_P1P2_MIN.get(session, 1),
                   "families": sorted({source_family(n) for n in valid}),
                   "impacts": {n.get("impact") for n in valid}}


def instrument_for(h):
    """与 fetch_data.instrument_for 同构的独立副本（单文件可运行）。"""
    market, name = h.get("market", ""), h.get("name", "") or ""
    ticker = h.get("ticker", "") or ""
    if market == "基金":
        if re.search(r"帮你投|投顾|全球精选", name):
            return "ADVISORY"
        return "FUND"
    # 现金管理类（短债/货币 ETF，如 SGOV）：净值稳定在 100 附近，仅列示、不做四层分析
    if re.search(r"SGOV|现金管理|0-3月国债|国债ETF|货币基金|短债", name):
        return "CASH_MGMT"
    if re.search(r"GraniteShare|XL二|南方.*(?:杠杆|反向|2x|两倍)|每日杠杆|每日反向|2x|2X",
                 name):
        return "LEVERAGED_ETP"
    if "ETF" in name.upper() or ticker.startswith("NAME:"):
        return "ETF"
    digits = re.sub(r"\D", "", ticker)
    if market == "A股" and (digits.startswith(("51", "56", "58")) or digits.startswith("159")):
        return "ETF"
    return "STOCK"


def is_fund_like(ev):
    return ev.get("market") == "基金" or ev.get("instrument") in (
        "ETF", "LEVERAGED_ETP", "FUND", "CASH_MGMT")


_OLD_DEPTH_WARNED = False


def brief_set(report_root, session):
    """返回本时段**只做简列**的关注标的（降级名单）。

    v2.4.0 语义反转：旧版 watchlist_depth.json 是"深度白名单"，未列出=简列；
    现在缺省 = **全部深度分析**，只有明确写进 watchlist_brief.json 的才降级。
    这样"我关注的票"默认都被认真分析，不会再因为名单配错被静默降级。
    探测顺序：单次 --brief 覆盖 > report_root 邻近（测试夹具）> config/。
    """
    global _OLD_DEPTH_WARNED
    brief = paths.brief_tickers(session, extra_dirs=(report_root,
                                                    Path(report_root).parent))
    if not brief and not _OLD_DEPTH_WARNED:
        old = paths.config_dir() / "watchlist_depth.json"
        if old.exists():
            print("[gate][warn] 检测到旧 watchlist_depth.json：语义已改为 "
                  "watchlist_brief.json（缺省=全部深度分析），旧文件不再生效，可删除")
            _OLD_DEPTH_WARNED = True
    return brief



def chain_score(ev, session):
    if is_fund_like(ev):
        need = 1
    else:
        need = CHAIN_MIN_STOCK.get(session, 1)
    notes = [c for c in ev.get("chain_notes", [])
             if c.get("status", "verified") != "missing"
             and c.get("evidence_level") in ("P1", "P2", "P3")]
    if need == 0:
        return 1.0 if notes else None, {"valid": len(notes), "need": 0}
    return min(len(notes) / need, 1.0), {"valid": len(notes), "need": need}


def coverage(ev, session):
    is_fund = is_fund_like(ev)
    weights = DIM_WEIGHTS_FUND if is_fund else DIM_WEIGHTS_STOCK
    plan = expected_plan(ev, session)
    parts, used_w, detail = [], 0.0, {}
    for dim, w in weights.items():
        if dim == "news":
            s, d = news_score(ev, session)
        elif dim == "chain":
            s, d = chain_score(ev, session)
        else:
            s, d = dim_score_numeric(ev, dim, plan.get(dim, []))
        if s is None:
            continue
        parts.append((dim, s, w))
        used_w += w
        detail[dim] = {"score": round(s, 3), **d}
    pct = round(sum(s * w for _, s, w in parts) / used_w, 4) if used_w else 0.0
    return pct, detail


# ---------------------------------------------------------------------------
# Stage evidence
# ---------------------------------------------------------------------------
def check_evidence(report_root, date, session, holdings, allow_degraded=False):
    ev_dir = report_root / "evidence"
    problems, warnings_all, cards = [], [], []
    coverages = []
    brief = brief_set(report_root, session)

    for h in holdings:
        fn = ev_dir / f"{date}_{session}_{safe_name(h['ticker'])}.json"
        if not fn.exists():
            problems.append(f"[{h['name']}] 缺少证据文件 {fn.name}（先跑 fetch_data.py 并完成补证）")
            continue
        try:
            ev = json.loads(fn.read_text(encoding="utf-8"))
        except Exception as e:
            problems.append(f"[{h['name']}] 证据文件无法解析: {e}")
            continue

        inst0 = instrument_for(h)
        # 投顾组合 / 现金管理：仅列示，豁免个券硬必需/新闻/产业链，覆盖率按 1.0
        if inst0 in ("ADVISORY", "CASH_MGMT"):
            lab = "PASS-投顾组合仅列示" if inst0 == "ADVISORY" else "PASS-现金管理仅列示"
            cards.append((h["name"], h["ticker"], 1.0, lab, {}))
            coverages.append(1.0)
            continue

        # 简列关注（watchlist 但不在深度名单）：只要求真实现价，进关注库总览表，
        # 不强制多空新闻/产业链/基本面，不计入组合覆盖率
        if h.get("watchlist") and h["ticker"] in brief:
            by_field = {p.get("field"): p for p in ev.get("data_points", [])}
            for f in ("price_last", "day_change_pct"):
                p = by_field.get(f)
                if not p or p.get("status") != "verified":
                    problems.append(
                        f"[{h['name']}] 简列关注硬必需 {f} 未 verified"
                        f"——关注库总览表需要真实现价")
            problems.extend(f"[{h['name']}] {x}"
                            for x in validate_authenticity(ev))
            cards.append((h["name"], h["ticker"], 0.0, "BRIEF-关注库仅列示", {}))
            continue

        warns = []
        is_fund = h["market"] == "基金" or ev.get("instrument") in (
            "ETF", "LEVERAGED_ETP", "FUND")
        hard = ["nav_latest"] if is_fund else ["price_last", "day_change_pct"]
        by_field = {p.get("field"): p for p in ev.get("data_points", [])}
        for f in hard:
            p = by_field.get(f)
            if not p or p.get("status") != "verified":
                problems.append(f"[{h['name']}] 硬必需数据点 {f} 未 verified"
                                f"——连价格都没有，禁止进入辩论")

        # 真实性/防伪：占位值、缺来源、量纲冲突、越界数值
        problems.extend(f"[{h['name']}] {x}" for x in validate_authenticity(ev))

        pct, detail = coverage(ev, session)
        coverages.append(pct)

        # 新闻条数 / P1P2
        ns, nd = news_score(ev, session)
        if nd["valid"] < nd["need"]:
            problems.append(f"[{h['name']}] 有效新闻 {nd['valid']} 条，"
                            f"最低要求 {nd['need']} 条（须带可访问 URL；P4 传闻不算）")
        if nd["p1p2"] < nd["p1p2_need"]:
            problems.append(f"[{h['name']}] 缺少 P1/P2 级新闻"
                            f"（公告/财报/权威媒体），现有新闻级别不足")

        # 独立来源族：股票完整版（pre/post）至少 2 个不同域名/媒体，禁止多条同源于一处
        instrument = instrument_for(h)
        fam_need = 1 if (is_fund or instrument in ("FUND", "ADVISORY")
                         or session not in ("pre", "post")) else 2
        if len(nd["families"]) < fam_need:
            problems.append(
                f"[{h['name']}] 有效新闻仅来自 {len(nd['families'])} 个独立来源族"
                f"（{', '.join(nd['families']) or '无'}），股票完整版至少 {fam_need} 个"
                f"不同来源（按域名/媒体计），禁止多条新闻同源于一处或互相转载凑数")

        # 强制反面证据：股票完整版必须同时有看多与看空的新闻，只搜一边禁止进入辩论
        if (not is_fund and instrument not in ("FUND", "ADVISORY")
                and session in ("pre", "post")):
            impacts = {i for i in nd["impacts"] if i}
            if "bullish" not in impacts or "bearish" not in impacts:
                problems.append(
                    f"[{h['name']}] 证据必须同时包含看多(bullish)与看空(bearish)的新闻，"
                    f"现有立场 {sorted(impacts) or '无'}——只搜利好或只搜利空都无法做强制"
                    f"多空辩论，请补独立的反面证据（估值/行业/技术面风险或催化）")

        # 产业链
        cs, cd = chain_score(ev, session)
        if cd["need"] and cd["valid"] < cd["need"]:
            problems.append(f"[{h['name']}] 缺少产业链笔记 chain_notes"
                            f"（{cd['valid']}/{cd['need']}，需含生命周期判断与来源）")

        # missing 必须在 gaps 披露
        gaps_text = "\n".join(ev.get("gaps", []))
        for p in ev.get("data_points", []):
            if p.get("status") == "missing":
                f, label = p.get("field", ""), p.get("label", "")
                if f and f not in gaps_text and label not in gaps_text:
                    problems.append(f"[{h['name']}] 数据点 {f} 为 missing 但未写入 gaps"
                                    f"——缺口必须显式披露")

        # P4 提示
        p4 = [p.get("id") for p in ev.get("data_points", [])
              if p.get("evidence_level") == "P4"]
        p4 += [n.get("id") for n in ev.get("news", [])
               if n.get("evidence_level") == "P4"]
        if p4:
            warns.append(f"含 P4 弱证据 {len(p4)} 条（{', '.join(filter(None,p4))}），"
                         f"不得作为论点唯一支撑")

        # 覆盖率等级
        if pct < 0.50:
            level = "FAIL"
        elif pct < 0.70:
            level = "WARN-只给定性判断"
            warns.append("覆盖率 50-69%：只给定性判断，禁止给精确评分/具体仓位数字")
        else:
            level = "PASS"
        cards.append((h["name"], h["ticker"], pct, level, detail))
        warnings_all.extend(f"[{h['name']}] {w}" for w in warns)

    # macro 文件
    macro_fn = ev_dir / f"{date}_{session}_macro.json"
    if session in ("pre", "post"):
        if not macro_fn.exists():
            msg = "缺少宏观证据文件 *_macro.json"
            (problems if session == "post" else warnings_all).append(msg)
        # 期权/VIX/IV/PCR 板块已按用户要求彻底移除：盘后不再强制 options 维度证据

    combo = round(sum(coverages) / len(coverages), 4) if coverages else 0.0
    hard_fail = bool(problems)
    # brief 关注卡片覆盖率按设计记 0.0（仅列示、不深度分析），不得触发低覆盖降级
    low_cov = any(c[2] < 0.50 for c in cards
                  if not str(c[3]).startswith("BRIEF"))

    if hard_fail:
        code = FAIL
        verdict = "FAIL"
    elif low_cov:
        # v2.2.3：低覆盖一律标 DEGRADED（退出码 3），由调用方决定是否放行。
        # 旧版在未加 --allow-degraded 时直接改判 FAIL，导致 run_daily 文档里的
        # 退出码 11（需显式降级）永远走不到，--allow-degraded 在 gate 子命令上失效。
        code = DEGRADED
        verdict = ("DEGRADED（需报告顶部挂数据不足横幅，只给定性判断）" if allow_degraded
                   else "DEGRADED（存在覆盖率<50%的标的；补证后重跑，或加 --allow-degraded 显式降级）")
    else:
        code = PASS
        verdict = "PASS"

    return {"stage": "evidence", "verdict": verdict, "exit_code": code,
            "combo_coverage": combo, "cards": cards,
            "problems": problems, "warnings": warnings_all}


# ---------------------------------------------------------------------------
# Stage report
# ---------------------------------------------------------------------------
ID_RE = re.compile(r"\[(dp|nw|ch)-\d{3}\]")
SECTION_HEAD_RE = re.compile(r"(?:^|\n)#{1,4}\s*([^\n]+)|"
                             r"<h[1-4][^>]*>(.*?)</h[1-4]>|"
                             r"class=\"[^\"]*card-title[^\"]*\"[^>]*>(.*?)<",
                             re.S)


def _name_pattern(nm):
    """构造名称/代码匹配正则。

    纯 ASCII 代码/短 ticker（如 KO、MU、BE）必须加词边界，否则会误命中
    其它单词的子串——典型 KO（可口可乐）命中 KOSPI，把 KOSPI 所在卡片的
    证据 ID 错切给可口可乐。含中文的名称（如 闪迪、美光科技）仍按普通
    子串匹配，中文相邻字符不构成词边界问题。
    """
    if re.fullmatch(r"[A-Za-z0-9.\-]+", nm):
        return re.compile(r"(?<![A-Za-z0-9])" + re.escape(nm) + r"(?![A-Za-z0-9])")
    return re.compile(re.escape(nm))


_CARD_START_RE = re.compile(r'<div class="card(?![^"]*sector)[^"]*">', re.I)
_TAG_RE = re.compile(r"<[^>]+>")
_TITLE_RE = re.compile(r"<h([1-3])[^>]*>([\s\S]*?)</h\1>", re.I)


def _plain(html_text):
    """去掉标签与属性，只留可见文字（属性里的票名不应参与归属判定）。"""
    return _TAG_RE.sub(" ", html_text or "")


def _card_ranges(text):
    """按 div 深度配对，返回完整卡片区间 [(start, end)]（跳过 sector 卡）。"""
    starts = [m.start() for m in _CARD_START_RE.finditer(text)]
    ranges = []
    for i, s in enumerate(starts):
        limit = starts[i + 1] if i + 1 < len(starts) else len(text)
        depth, end = 0, limit
        for tm in re.finditer(r"<div\b|</div>", text[s:limit]):
            if tm.group(0) == "</div>":
                depth -= 1
                if depth <= 0:
                    end = s + tm.end()
                    break
            else:
                depth += 1
        ranges.append((s, end))
    return ranges


def _earliest_holder(plain_text, holdings):
    """在文本里找位置最靠前的持仓名/代码，返回 ticker（避免被后续提及的票抢走）。"""
    best = None
    for h in holdings:
        for nm in (h["name"], h["ticker"], h["ticker"].split(".")[0]):
            if not nm:
                continue
            m = _name_pattern(nm).search(plain_text)
            if m and (best is None or m.start() < best[0]):
                best = (m.start(), h["ticker"])
    return best[1] if best else None


def _slice_sections(text, holdings):
    """把报告切成 {ticker: 章节文本}。

    v2.2.3：优先按卡片边界切，再在"去标签纯文本"里认标的。旧版按名称出现位置
    直接切原文，会命中 HTML 属性里的票名（如徽标 title="P1 · 中芯国际官方"），
    把紫金卡片的空方整行算给中芯国际——既可能误杀（空方 0 ID），也可能误放
    （相邻卡片的引用灌进薄卡片）。CHANGELOG 2026-10-20 只加了词边界，没解决
    "在标签属性里匹配"这个根。
    """
    sections, consumed = {}, []
    for s, e in _card_ranges(text):
        block = text[s:e]
        consumed.append((s, e))
        title = _TITLE_RE.search(block)
        head = _plain(title.group(2)) if title else ""
        tk = _earliest_holder(head, holdings) or _earliest_holder(_plain(block), holdings)
        if tk:
            sections[tk] = sections.get(tk, "") + block

    # 兜底：总览表/对账/新闻清单等非卡片区域，仍按位置切给"没有卡片"的标的
    # （先把卡片区间与所有标签挖空，避免把卡片内引用算到这些标的上）
    rest = [h for h in holdings if h["ticker"] not in sections]
    if rest:
        chars = list(text)
        for s, e in consumed:
            for i in range(s, min(e, len(chars))):
                chars[i] = " "
        masked = _TAG_RE.sub(lambda m: " " * len(m.group(0)), "".join(chars))
        marks = []
        for h in rest:
            for nm in (h["name"], h["ticker"], h["ticker"].split(".")[0]):
                if not nm:
                    continue
                for m in _name_pattern(nm).finditer(masked):
                    marks.append((m.start(), h["ticker"]))
        marks.sort()
        for i, (pos, tk) in enumerate(marks):
            end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
            sections[tk] = sections.get(tk, "") + text[pos:end]
    return sections


def check_report(report_root, date, session, holdings, report_file,
                 combo_coverage_override=None, closed=None):
    problems, warnings_out = [], []
    wl_info = {}  # ticker → watchlist 元数据 + verified 现价
    text = Path(report_file).read_text(encoding="utf-8", errors="ignore")
    ev_dir = report_root / "evidence"
    brief = brief_set(report_root, session)

    # 只装载当前在册持仓 + macro 的证据文件；已清仓标的的旧证据一律忽略
    # （既不计入覆盖率，也不提供 ID），从源头消除"已卖标的还在报告里"。
    expected_files = {ev_dir / f"{date}_{session}_{safe_name(h['ticker'])}.json"
                      for h in holdings}
    expected_files.add(ev_dir / f"{date}_{session}_macro.json")

    # 装载证据 ID
    id_level, id_exists = {}, set()
    coverages = []
    # brief 关注标的不进组合覆盖率（与证据门口径一致），否则其低覆盖会拉低 combo
    brief_tickers = {h["ticker"] for h in holdings
                     if h.get("watchlist") and h["ticker"] in brief}
    for f in sorted(expected_files):
        if not f.exists():
            continue
        try:
            ev = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        for p in ev.get("data_points", []):
            if p.get("id"):
                id_exists.add(p["id"])
                id_level[p["id"]] = p.get("evidence_level")
        for n in ev.get("news", []):
            if n.get("id"):
                id_exists.add(n["id"])
                id_level[n["id"]] = n.get("evidence_level")
        for c in ev.get("chain_notes", []):
            if c.get("id"):
                id_exists.add(c["id"])
                id_level[c["id"]] = c.get("evidence_level")
        if (ev.get("market") not in (None, "macro")
                and ev.get("ticker", "_") != "_macro"
                and ev.get("ticker") not in brief_tickers
                and ev.get("instrument") not in ("ADVISORY", "CASH_MGMT")):
            pct, _ = coverage(ev, session)
            coverages.append(pct)
        if ev.get("watchlist"):
            wl_price = next(
                (p.get("value") for p in ev.get("data_points", [])
                 if p.get("field") == "price_last" and p.get("status") == "verified"),
                None)
            wl_info[ev.get("ticker")] = dict(ev["watchlist"], price=wl_price)
    combo = combo_coverage_override or (round(sum(coverages) / len(coverages), 4)
                                        if coverages else None)

    sections = _slice_sections(text, holdings)
    min_ids = 2 if session == "noon" else 4
    min_refs = 3 if session == "noon" else 6
    for h in holdings:
        inst_h = instrument_for(h)
        is_brief_wl = bool(h.get("watchlist")) and h["ticker"] in brief
        if inst_h in ("ADVISORY", "CASH_MGMT") or is_brief_wl:
            # 投顾/现金仅列示；简列关注只在关注库总览表，均不要求独立章节
            continue
        body = sections.get(h["ticker"], "")
        if not body:
            problems.append(f"[{h['name']}] 报告中找不到该标的章节")
            continue
        ids = set(m.group(0).strip("[]") for m in ID_RE.finditer(body))
        fake = [i for i in ids if i not in id_exists]
        if fake:
            problems.append(f"[{h['name']}] 引用了证据文件中不存在的 ID：{', '.join(fake)}")
        if len(ids) < min_ids:
            problems.append(f"[{h['name']}] 章节内唯一证据引用 {len(ids)} 个，"
                            f"最低 {min_ids} 个（多空论点必须挂 [dp/nw/ch-xxx]）")
        if len(ID_RE.findall(body)) < min_refs:
            problems.append(f"[{h['name']}] 证据引用总次数 {len(ID_RE.findall(body))}，"
                            f"最低 {min_refs} 次")
        # 禁止靠同一编号反复堆砌刷引用次数（用 finditer 取完整编号，
        # findall 因 ID_RE 含捕获组只会返回前缀 dp/nw/ch）
        _freq = {}
        for _m in ID_RE.finditer(body):
            _rid = _m.group(0)
            _freq[_rid] = _freq.get(_rid, 0) + 1
        for rid, n in _freq.items():
            if n >= 5:
                problems.append(f"[{h['name']}] 编号 {rid} 在卡片内重复出现 {n} 次"
                                f"——禁止靠重复同一编号凑引用次数")
        # P4 唯一支撑：逐行检查
        p4_only_lines = 0
        for line in body.splitlines():
            line_ids = [m.group(0).strip("[]") for m in ID_RE.finditer(line)]
            if len(line_ids) == 1 and id_level.get(line_ids[0]) == "P4":
                p4_only_lines += 1
        if p4_only_lines > 2:
            problems.append(f"[{h['name']}] 有 {p4_only_lines} 条论点仅靠 P4 弱证据支撑，"
                            f"必须降级为线索或补证")

        # 多空不同源（完整版 pre/post）：多方与空方必须各有独立证据，禁止照抄同一 ID
        if session in ("pre", "post") and instrument_for(h) not in ("FUND", "ADVISORY"):
            bull_ids, bear_ids = set(), set()
            for line in body.splitlines():
                line_ids = {m.group(0).strip("[]") for m in ID_RE.finditer(line)}
                if re.search(r"多方|多头", line):
                    bull_ids |= line_ids
                if re.search(r"空方|空头", line):
                    bear_ids |= line_ids
            if not bull_ids or not bear_ids:
                problems.append(
                    f"[{h['name']}] 章节内找不到明确标注'多方/多头'与'空方/空头'的对立"
                    f"论点区块（多方 {len(bull_ids)} 个ID / 空方 {len(bear_ids)} 个ID）")
            else:
                if not (bull_ids - bear_ids):
                    problems.append(
                        f"[{h['name']}] 多方论点没有任何独立于空方的证据——多空必须各引"
                        f"不同来源，禁止多方照抄空方同源 ID")
                if not (bear_ids - bull_ids):
                    problems.append(
                        f"[{h['name']}] 空方论点没有任何独立于多方的证据（引用全是多方同源 "
                        f"ID），必须补独立的反面来源")

    # 关注库（watchlist）：到价标红+执行清单 / 未到价禁喊买 / 满4周重评估 / 价值陷阱可否决
    for h in holdings:
        if not h.get("watchlist"):
            continue
        body = sections.get(h["ticker"], "")
        meta = wl_info.get(h["ticker"], {})
        price, target = meta.get("price"), meta.get("target_buy_price")
        at_target = (price is not None and target is not None and price <= target)
        says_buy = re.search(r"可接回|建议买入|建议接回|到价可|可买入", body)
        says_block = re.search(r"先别接|价值陷阱|不要接|暂不接|暂不买入|降级|待验证", body)

        is_brief_wl = h["ticker"] in brief

        if is_brief_wl:
            # 简列关注：未到价禁喊买；到价须在总览表标红并提示进入目标区（不强制完整清单）
            if not at_target and says_buy:
                problems.append(
                    f"[{h['name']}] 现价 {price} 尚未到目标接回价 {target}，"
                    f"简列关注不得提前喊'可接回/买入'")
            if at_target and not re.search(r"目标区|已到价|到价|进入", body):
                problems.append(
                    f"[{h['name']}] 现价 {price} 已进入目标接回价 {target}，"
                    f"关注库总览表须标红并提示'已进入目标区·待深度评估'")
            continue

        if at_target:
            if not says_buy and not says_block:
                problems.append(
                    f"[{h['name']}] 现价 {price} 已到目标接回价 {target}，报告必须二选一："
                    f"给'可接回'执行清单，或明确喊'先别接'并挂证据说明（价值陷阱否决）")
            if says_buy:
                qty = meta.get("planned_qty")
                miss_el = []
                if qty is not None and str(int(qty)) not in body:
                    miss_el.append(f"接回股数 {int(qty)}")
                if "止损" not in body:
                    miss_el.append("止损位")
                if "证伪" not in body:
                    miss_el.append("证伪条件")
                if miss_el:
                    problems.append(
                        f"[{h['name']}] 到价执行清单缺少：{', '.join(miss_el)}"
                        f"——须含接回股数/止损/证伪，用户确认即可执行")
        else:
            if says_buy:
                problems.append(
                    f"[{h['name']}] 现价 {price} 尚未到目标接回价 {target}，"
                    f"不得提前喊'可接回/买入'（可做专家分析、提示接近低点）")
            added = meta.get("added_date")
            try:
                overdue = (dt.date.fromisoformat(date)
                           - dt.date.fromisoformat(added)).days >= 28
            except Exception:
                overdue = False
            if overdue and not re.search(r"重新评估|重定|重新设定|重新审视", body):
                problems.append(
                    f"[{h['name']}] 自 {added} 已满 4 周仍未到价，报告须提示"
                    f"'重新评估、重定低位目标价'（不删除条目）")

    # 已清仓标的不得作为独立卡片/章节出现（允许在对账正文一句话提及）
    for c in (closed or []):
        kws = {c.get("ticker", ""), c.get("ticker", "").split(".")[0],
               c.get("name", "")}
        kws = {k for k in kws if k and len(k) >= 2}
        hit = None
        for kw in kws:
            pat = re.compile(
                r"(?:^|\n)#{1,4}[^\n]*" + re.escape(kw) +
                r"|<h[1-4]\b[^>]*>[\s\S]{0,160}?" + re.escape(kw) +
                r"|card-title[^>]*>[\s\S]{0,160}?" + re.escape(kw), re.I)
            m = pat.search(text)
            if m:
                hit = kw
                break
        if hit:
            problems.append(
                f"报告包含已清仓标的「{c['name']}」的独立卡片/章节（命中 {hit}）："
                f"已卖出标的不得生成持仓卡片，最多在跨报告对账里用一句话说明，"
                f"请删除该卡片（持仓表中它应以 ~~~~删除线 或'已清仓'标注）")

    # 覆盖率横幅
    if combo is not None:
        m = re.search(r"数据覆盖率[^0-9]{0,12}(\d{1,3})\s*%", text)
        if not m:
            problems.append("报告缺少'数据覆盖率 X%'横幅（数值必须取自 gate_check 机械计算）")
        elif abs(int(m.group(1)) - round(combo * 100)) > 3:
            problems.append(f"报告自报覆盖率 {m.group(1)}% 与机械值 "
                            f"{round(combo*100)}% 偏差超过 3 个百分点——禁止口述覆盖率")

    # 非法/格式错误的证据编号（如 [dp-vix]、[dp-1]）：ID_RE 不匹配它们，
    # 若不主动拦截就会成为漏网的"伪引用"
    ALL_BRACKET_RE = re.compile(r"\[([A-Za-z0-9][A-Za-z0-9._\-]*)\]")
    for tok in set(ALL_BRACKET_RE.findall(text)):
        if re.match(r"(dp|nw|ch)-", tok) and not re.match(r"(dp|nw|ch)-\d{3}$", tok):
            problems.append(f"报告出现非法/格式错误的证据编号 [{tok}]"
                            f"（正确格式 [dp/nw/ch-三位数字]，如 [dp-001]）")

    # 信息来源 / 免责 / 缺口披露
    if not re.search(r"<details|信息来源|数据来源|参考来源", text):
        problems.append("报告末尾缺少信息来源折叠区（<details>）")
    else:
        src_zone = "\n".join(re.findall(r"<details[\s\S]*?</details>", text))
        if not src_zone:
            msrc = re.search(r"(?:信息来源|数据来源|参考来源)[\s\S]{0,6000}", text)
            src_zone = msrc.group(0) if msrc else ""
        art = sorted({u for u in re.findall(r"https?://[^\s\"'<>)）]+", src_zone)
                      if _is_article_url(u)})
        need_art = 3 if session == "noon" else 4
        if len(art) < need_art:
            problems.append(f"信息来源折叠区仅 {len(art)} 条具体文章/行情链接，"
                            f"至少 {need_art} 条（网站首页/栏目页不算，须能点开的具体出处）")
    if not re.search(r"免责|不构成投资建议|风险自担", text):
        problems.append("报告缺少免责声明")
    if session != "quick" and not re.search(r"我不确定|数据缺口|待验证|gaps", text, re.I):
        problems.append("报告缺少缺口披露区块（'我不确定的是'/数据缺口）")

    code = FAIL if problems else PASS
    return {"stage": "report", "verdict": "FAIL" if problems else "PASS",
            "exit_code": code, "combo_coverage": combo,
            "problems": problems, "warnings": warnings_out}


# ---------------------------------------------------------------------------
def ensure_utf8_stdout():
    """Windows 控制台/计划任务默认 GBK，打印符号会 UnicodeEncodeError。

    旧版在 GBK 下失败路径连 problems 都打不出来（退出码还会变 1），
    等于把门禁的反馈闭环掐断。实现统一到 paths.ensure_utf8_stdout。
    """
    paths.ensure_utf8_stdout()


def render(result):
    print("=" * 64)
    print(f"门禁阶段：{result['stage']}  结论：{result['verdict']}")
    if result.get("combo_coverage") is not None:
        print(f"组合机械覆盖率：{round(result['combo_coverage']*100, 1)}%")
    print("=" * 64)
    for name, tk, pct, level, _ in result.get("cards", []):
        print(f"  {name:<10} {tk:<10} 覆盖率 {round(pct*100,1):>5}%  {level}")
    if result["problems"]:
        print(f"\n阻断项（{len(result['problems'])}）：")
        for p in result["problems"]:
            print(f"  [X] {p}")
    if result["warnings"]:
        print(f"\n警告（{len(result['warnings'])}）：")
        for w in result["warnings"]:
            print(f"  [!] {w}")
    if not result["problems"] and not result["warnings"]:
        print("\n全部检查通过。")
    print("=" * 64)


def main():
    ensure_utf8_stdout()
    ap = argparse.ArgumentParser(description="证据/报告门禁校验")
    ap.add_argument("--report-root", required=True)
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--session", choices=["pre", "noon", "post", "quick"], default="pre")
    ap.add_argument("--stage", choices=["evidence", "report"], required=True)
    ap.add_argument("--holdings", help="holdings.md 路径（默认 report-root 上级）")
    ap.add_argument("--report-file", help="stage=report 时的报告 md/html 文件")
    ap.add_argument("--allow-degraded", action="store_true",
                    help="覆盖率过低时允许显式降级放行（报告必须挂横幅）")
    ap.add_argument("--json", action="store_true", help="机器可读输出")
    args = ap.parse_args()

    report_root = Path(args.report_root)
    holdings_path = paths.resolve_holdings(args.holdings)
    if holdings_path is None:
        print("[error] 找不到 holdings.md（config/holdings.md 或 --holdings 指定）")
        sys.exit(2)
    md_text = holdings_path.read_text(encoding="utf-8")
    holdings = parse_holdings(md_text)
    if not holdings:
        print("[error] holdings.md 未解析到持仓")
        sys.exit(2)
    closed = parse_closed_positions(md_text)

    # 关注库：仅纳入"接下来要开盘市场"对应标的（pre→A股/港股，post→美股），
    # noon/quick 不纳入；与持仓合并去重（持仓在前）。
    wl_markets = {"pre": {"A股", "港股"}, "post": {"美股"}}.get(args.session, set())
    wl_path = paths.watchlist_path(holdings_path)
    watchlist = []
    if wl_markets and wl_path:
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

    # 午间只聚焦 A股/港股持仓；基金/美股午间不展开卡片
    if args.session == "noon":
        holdings = [h for h in holdings if h["market"] in {"A股", "港股"}]

    if args.stage == "evidence":
        result = check_evidence(report_root, args.date, args.session,
                                holdings, args.allow_degraded)
    else:
        if not args.report_file or not Path(args.report_file).exists():
            print("[error] --stage report 需要指定存在的 --report-file")
            sys.exit(2)
        result = check_report(report_root, args.date, args.session,
                              holdings, args.report_file, closed=closed)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        render(result)
    if (result.get("exit_code") == DEGRADED and args.stage == "evidence"
            and args.allow_degraded):
        print("[gate] 已显式 --allow-degraded：放行（报告须挂'数据不足'横幅）")
        sys.exit(0)
    sys.exit(result["exit_code"])


if __name__ == "__main__":
    main()
