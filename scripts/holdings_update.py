#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""holdings_update.py —— 从「规范化快照 JSON」安全更新 config/holdings.md

这是「丢截图 → 更新持仓」流程的后半段（工程化部分）：
    视觉读图（agent 干） → 快照 JSON → 本脚本：校验 → 比对 → 备份 → 写回 → 记变动

四条硬保证：
  1. 校验不通过绝不写 —— 防止 OCR 把 6 看成 8 这类错误污染持仓
  2. 写前必备份，可 --restore 还原
  3. 快照里没出现的持仓**绝不自动清仓**，只标「待确认」
  4. 默认 dry-run 只打印变更；--apply 才真正写入

用法：
    python scripts/holdings_update.py --snapshot snap.json              # 预览（默认）
    python scripts/holdings_update.py --snapshot snap.json --apply      # 写回
    python scripts/holdings_update.py --snapshot snap.json --apply --mark-cleared 09988.HK
    python scripts/holdings_update.py --list-backups
    python scripts/holdings_update.py --restore <backup.md>

退出码：0 正常 / 1 校验错误或写入失败 / 2 输入缺失
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import sys
from pathlib import Path

# 复用 fetch_data 的解析口径，保证「更新」与「取数」永远一致
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_data  # noqa: E402

MARKETS = ("A股", "基金", "港股", "美股")

HEADER = {
    "A股": "| 名称 | 代码 | 持仓数量 | 成本价 | 现价 | 市值(元) | 盈亏(元) | 盈亏比例 |",
    "港股": "| 名称 | 代码 | 持仓数量 | 成本价 | 现价 | 市值(港币) | 盈亏(港币) | 盈亏比例 |",
    "美股": "| 名称 | 代码 | 持仓数量 | 成本价 | 现价 | 市值(美元) | 盈亏(美元) | 盈亏比例 |",
    "基金": "| 基金名称 | 金额(元) | 持有收益 |",
}
SEP = {
    "A股": "|---|---|---|---|---|---|---|---|",
    "港股": "|---|---|---|---|---|---|---|---|",
    "美股": "|---|---|---|---|---|---|---|---|",
    "基金": "|---|---|---|",
}
SECTION_KEY = {v: k for k, v in fetch_data.SECTION_MARKET.items()}  # 市场 -> "A股持仓"

CODE_RE = {
    "A股": re.compile(r"^\d{6}\.(SH|SZ|BJ)$"),
    "港股": re.compile(r"^\d{4,5}\.HK$"),
    "美股": re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$"),
}


# ---------------------------------------------------------------- 工具
def _num(v):
    """宽松转数字；拿不到返回 None。"""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "").replace("%", "")
    if s in ("", "-", "--", "N/A", "nan", "None"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _fmt_qty(q):
    if q is None:
        return "-"
    q = float(q)
    return f"{int(round(q)):,}股" if abs(q - round(q)) < 1e-9 else f"{q:,}"


def _row_ticker(cells, market):
    """从现有表格行里取 ticker（与 fetch_data.parse_holdings 口径一致）。"""
    if market == "基金":
        name = cells[0] if cells else ""
        if len(cells) >= 3 and _num(cells[1]) is None and _num(cells[2]) is not None:
            name = f"{cells[0]}-{cells[1]}"
        return name
    if len(cells) < 2:
        return None
    code = cells[1]
    if not re.search(r"[A-Za-z0-9]", code or ""):
        return None
    return fetch_data.normalize_ticker(code, market)


# ---------------------------------------------------------------- 快照
def load_snapshot(path: Path):
    d = json.loads(path.read_text(encoding="utf-8"))
    for k in ("market", "positions"):
        if k not in d:
            raise ValueError(f"快照缺少必填字段: {k}")
    if d["market"] not in MARKETS:
        raise ValueError(f"market 必须是 {MARKETS} 之一，收到 {d['market']!r}")
    if not isinstance(d["positions"], list) or not d["positions"]:
        raise ValueError("positions 必须是非空数组")
    return d


def _derive(p, market):
    """补全可由基础字段推导的派生值（市值/盈亏/盈亏比例）。"""
    if market == "基金":
        return
    qty, cost, last = _num(p.get("qty")), _num(p.get("cost")), _num(p.get("last"))
    if _num(p.get("market_value")) is None and qty is not None and last is not None:
        p["market_value"] = qty * last
    if _num(p.get("pnl")) is None and qty is not None and cost is not None and last is not None:
        p["pnl"] = (last - cost) * qty
    if _num(p.get("pnl_pct")) is None and cost and last is not None:
        p["pnl_pct"] = (last - cost) / cost * 100


def validate_snapshot(snap):
    """返回 (errors, warnings)。errors 阻断写入，warnings 仅提示。"""
    market = snap["market"]
    errors, warnings = [], []
    seen = {}

    for i, p in enumerate(snap["positions"], 1):
        tag = f"#{i} {p.get('name') or '(无名)'}"
        name = (p.get("name") or "").strip()
        if not name:
            errors.append(f"{tag}: 名称为空")
            continue

        if market == "基金":
            amt = _num(p.get("amount"))
            if amt is None or amt <= 0:
                errors.append(f"{tag}: 基金金额缺失或非正 ({p.get('amount')!r})")
            p["code"] = name  # 基金无代码，以名称作键
            if name in seen:
                errors.append(f"{tag}: 基金名称重复（{name}）")
            seen[name] = True
            continue

        code = (p.get("code") or "").strip()
        if not code:
            errors.append(f"{tag}: 缺少代码")
            ticker = None
        else:
            ticker = fetch_data.normalize_ticker(code, market)
            if market in CODE_RE and not CODE_RE[market].match(ticker):
                warnings.append(f"{tag}: 代码格式可疑 {code!r} → {ticker!r}")
        if ticker:
            if ticker in seen:
                errors.append(f"{tag}: 代码重复（{ticker}）")
            seen[ticker] = True
        p["ticker"] = ticker

        qty = _num(p.get("qty"))
        if qty is None or qty <= 0:
            errors.append(f"{tag}: 数量缺失或非正 ({p.get('qty')!r})")
            continue

        cost, last = _num(p.get("cost")), _num(p.get("last"))
        if cost is None:
            warnings.append(f"{tag}: 缺成本价，成本类判断会不准")
        if last is None:
            warnings.append(f"{tag}: 缺现价，市值无法交叉校验")

        # 交叉校验：数量 × 现价 ≈ 市值（这是抓 OCR 数字错最有效的一条）
        mv = _num(p.get("market_value"))
        if mv is not None and last is not None:
            expect = qty * last
            if expect > 0:
                rel = abs(mv - expect) / expect
                if rel > 0.03:
                    errors.append(
                        f"{tag}: 市值对不上 —— 数量×现价={expect:,.2f}，快照市值={mv:,.2f}（差 {rel:.1%}）"
                    )
                elif rel > 0.01:
                    warnings.append(f"{tag}: 市值有 {rel:.1%} 偏差（可能含费用/四舍五入）")

        # 盈亏 ≈ (现价-成本)×数量
        pnl = _num(p.get("pnl"))
        if pnl is not None and cost is not None and last is not None:
            expect = (last - cost) * qty
            if abs(pnl - expect) > max(2.0, 0.02 * abs(expect)):
                warnings.append(
                    f"{tag}: 盈亏对不上 —— 推算 {expect:+,.2f}，快照 {pnl:+,.2f}"
                )

        # 盈亏比例一致性
        pct = _num(p.get("pnl_pct"))
        if pct is not None and cost and last is not None and cost > 0:
            expect_pct = (last - cost) / cost * 100
            if abs(pct - expect_pct) > 1.0:
                warnings.append(f"{tag}: 盈亏比例对不上 —— 推算 {expect_pct:+.2f}%，快照 {pct:+.2f}%")

    return errors, warnings


# ---------------------------------------------------------------- 比对
def check_cost_jumps(snap, current_md_text, threshold=0.15):
    """成本相对现有档案跳变超阈值 → 告警（不阻断）。卖出不改成本基础，跳变多为口径差异或读错。"""
    market = snap["market"]
    if market == "基金":
        return []
    cur = {h["ticker"]: h for h in fetch_data.parse_holdings(current_md_text) if h["market"] == market}
    warns = []
    for p in snap["positions"]:
        tk = p.get("ticker") or p.get("code")
        if not tk or tk not in cur:
            continue
        old, new = cur[tk].get("cost"), _num(p.get("cost"))
        if old and new and old > 0:
            rel = abs(new - old) / old
            if rel > threshold:
                warns.append(
                    f"{p.get('name')} {tk}: 成本跳变 {old:.3f} → {new:.3f}（{rel:.0%}）"
                    f"——卖出/减仓不改变成本基础，请核对券商口径后确认"
                )
    return warns


def diff_snapshot(snap, current_md_text):
    """返回按类别归好的变更字典。只在该 market 范围内比对。"""
    market = snap["market"]
    cur_all = fetch_data.parse_holdings(current_md_text)
    cur = {h["ticker"]: h for h in cur_all if h["market"] == market}

    snap_map = {}
    for p in snap["positions"]:
        tk = p.get("ticker") or p.get("code") or p.get("name")
        snap_map[tk] = p

    out = {"added": [], "qty": [], "cost": [], "price": [], "amount": [],
           "unchanged": [], "missing": [], "market": market}
    for tk, p in snap_map.items():
        if tk not in cur:
            out["added"].append(p)
            continue
        c = cur[tk]
        if market == "基金":
            a0, a1 = c.get("amount"), _num(p.get("amount"))
            if a0 is not None and a1 is not None and abs(a0 - a1) > 0.005:
                out["amount"].append((c, p, a0, a1))
            else:
                out["unchanged"].append(p)
            continue
        q0, q1 = c.get("quantity"), _num(p.get("qty"))
        c0, c1 = c.get("cost"), _num(p.get("cost"))
        l0, l1 = c.get("last"), _num(p.get("last"))
        touched = False
        if q0 is not None and q1 is not None and abs(q0 - q1) > 1e-9:
            out["qty"].append((c, p, q0, q1)); touched = True
        if c0 is not None and c1 is not None and abs(c0 - c1) > 0.0005:
            out["cost"].append((c, p, c0, c1)); touched = True
        if l0 is not None and l1 is not None and abs(l0 - l1) > 0.0005:
            out["price"].append((c, p, l0, l1)); touched = True
        if not touched:
            out["unchanged"].append(p)

    # 现有持仓但快照里没出现 —— 只报告，绝不自动清仓
    for tk, h in cur.items():
        if tk not in snap_map:
            out["missing"].append(h)
    return out


def _has_change(d):
    return bool(d["added"] or d["qty"] or d["cost"] or d["price"] or d["amount"])


# ---------------------------------------------------------------- 渲染
def render_report(snap, d, errors, warnings):
    L = []
    L.append("=== 快照校验 ===")
    if errors:
        L.append(f"❌ {len(errors)} 项错误（会阻断写入）")
        for e in errors:
            L.append(f"   - {e}")
    else:
        L.append("✅ 无阻断错误")
    if warnings:
        L.append(f"⚠️  {len(warnings)} 项提醒")
        for w in warnings:
            L.append(f"   - {w}")

    L.append("")
    acct = snap.get("account") or snap.get("broker") or ""
    L.append(f"=== 变更清单（{d['market']} · {acct} · {snap.get('as_of', '—')}）===")

    if d["added"]:
        L.append("🆕 新增持仓")
        for p in d["added"]:
            L.append(f"   + {p['name']} {p.get('ticker') or p.get('code') or ''}  "
                     f"{_fmt_qty(_num(p.get('qty')))}")
    if d["qty"]:
        L.append("✏️  数量变化")
        for c, p, q0, q1 in d["qty"]:
            L.append(f"   - {p['name']} {p.get('ticker')}  {_fmt_qty(q0)} → {_fmt_qty(q1)}"
                     f"（{q1 - q0:+,.0f}）")
    if d["cost"]:
        L.append("✏️  成本变化")
        for c, p, c0, c1 in d["cost"]:
            L.append(f"   - {p['name']} {p.get('ticker')}  {c0:.3f} → {c1:.3f}")
    if d["price"]:
        L.append("💲 现价更新")
        for c, p, l0, l1 in d["price"]:
            L.append(f"   - {p['name']} {p.get('ticker')}  {l0:.3f} → {l1:.3f}")
    if d["amount"]:
        L.append("💲 金额变化")
        for c, p, a0, a1 in d["amount"]:
            L.append(f"   - {p['name']}  {a0:,.2f} → {a1:,.2f}（{a1 - a0:+,.2f}）")
    if d["unchanged"]:
        L.append(f"⏸️  未变：{len(d['unchanged'])} 只")
    if d["missing"]:
        L.append("❓ 截图未包含（保持原样，不自动清仓）")
        for h in d["missing"]:
            L.append(f"   - {h['name']} {h['ticker']}  {_fmt_qty(h.get('quantity'))}  "
                     f"→ 若已卖出，请加 --mark-cleared {h['ticker']}")
    orders = snap.get("orders") or []
    if orders:
        L.append("📋 成交订单（来自快照 orders）")
        for o in orders:
            side = "卖出" if str(o.get("side", "")).lower() in ("sell", "卖", "卖出") else "买入"
            L.append(f"   - {side} {o.get('name', '')} {o.get('code', '')} "
                     f"{o.get('qty', '')}股 @{o.get('price', '')}（{o.get('status', '')}）")
    if not _has_change(d):
        L.append("（无任何持仓变动）")
    return "\n".join(L)


# ---------------------------------------------------------------- 写回
def _sub_num(text, key, value, plus=False):
    """把「key：<数字>」里的数字换成 value，单位/括号说明等其余文字原样保留。"""
    if value is None:
        return text
    pat = re.compile(rf"({re.escape(key)}\s*[：:]\s*)([+\-]?[\d,]+(?:\.\d+)?)")
    new = f"{value:+,.2f}" if plus else f"{value:,.2f}"
    return pat.sub(lambda m: m.group(1) + new, text, count=1)


def _sub_pct(text, key, value):
    if value is None:
        return text
    pat = re.compile(rf"({re.escape(key)}\s*[：:]\s*)([\d.]+)\s*%")
    return pat.sub(lambda m: m.group(1) + f"{value:g}%", text, count=1)


def _sync_overview_row(md_text, account, totals):
    """按 account 精确匹配「账户总览」行，更新净资产与总盈亏两列。"""
    lines = md_text.splitlines()
    for i, ln in enumerate(lines):
        if not ln.strip().startswith("|") or "账户" not in ln or "总资产" not in ln:
            continue
        j = i + 1
        while j < len(lines) and lines[j].strip().startswith("|---"):
            j += 1
        while j < len(lines) and lines[j].strip().startswith("|"):
            cells = [c.strip() for c in lines[j].strip().strip("|").split("|")]
            if cells and cells[0] == account and len(cells) >= 4:
                cur = (totals.get("currency") or "").strip()
                na, pnl = totals.get("net_assets"), totals.get("pnl")
                if na is not None:
                    cells[2] = f"{na:,.2f} {cur}".strip()
                if pnl is not None:
                    cells[3] = f"{pnl:+,.2f} {cur}".strip()
                lines[j] = "| " + " | ".join(cells) + " |"
                return "\n".join(lines)
            j += 1
        break
    return md_text


def _sync_section_summary(md_text, market, totals):
    """更新分节里的「净资产 / 总资产」汇总行，只换数字，措辞与说明原样保留。"""
    key = SECTION_KEY[market]
    lines = md_text.splitlines()
    start = end = None
    for i, ln in enumerate(lines):
        if re.match(rf"^##(?!#)\s*{re.escape(key)}", ln.strip()):
            start = i
            continue
        if start is not None and i > start and re.match(r"^##(?!#)", ln.strip()):
            end = i
            break
    if start is None:
        return md_text
    if end is None:
        end = len(lines)

    for i in range(start, end):
        s = lines[i]
        if s.strip().startswith("|"):
            continue
        if re.search(r"净资产\s*[：:]", s):
            s = _sub_num(s, "净资产", totals.get("net_assets"))
            s = _sub_num(s, "持仓盈亏", totals.get("pnl"), plus=True)
            s = _sub_num(s, "今日盈亏", totals.get("today_pnl"), plus=True)
            lines[i] = s
        elif re.search(r"总资产\s*[：:]", s):
            s = _sub_num(s, "总资产", totals.get("net_assets"))
            s = _sub_pct(s, "仓位", totals.get("position_pct"))
            s = _sub_num(s, "总盈亏", totals.get("pnl"), plus=True)
            lines[i] = s
    return "\n".join(lines)


def _sync_totals(md_text, snap):
    """快照带 totals 时，同步账户总览行与分节汇总行；不带则原样返回。"""
    totals = snap.get("totals") or {}
    if not totals:
        return md_text
    md = md_text
    account = (snap.get("account") or "").strip()
    if account:
        md = _sync_overview_row(md, account, totals)
    md = _sync_section_summary(md, snap["market"], totals)
    return md


def _replace_section_table(md_text, market, snap, cleared=()):
    """把 market 分节里的持仓表重写为快照内容；已清仓行、非表格注释原样保留。"""
    key = SECTION_KEY[market]
    lines = md_text.splitlines()
    start = end = None
    for i, ln in enumerate(lines):
        if re.match(rf"^##(?!#)\s*{re.escape(key)}", ln.strip()):
            start = i
            continue
        if start is not None and i > start and re.match(r"^##(?!#)", ln.strip()):
            end = i
            break
    if start is None:
        raise ValueError(f"holdings.md 里找不到分节「## {key}」")
    if end is None:
        end = len(lines)

    # 分节内定位表格块
    tbl_rows = [i for i in range(start, end) if lines[i].strip().startswith("|")]
    if not tbl_rows:
        raise ValueError(f"「{key}」分节里没有表格，无法写入")

    header_i = tbl_rows[0]
    # 数据行 = 表头与分隔行之后的连续 | 行
    data_start = header_i + 2 if len(tbl_rows) >= 2 else header_i + 1
    data_idx = [i for i in tbl_rows if i >= data_start]

    # 现有行：保留已清仓行；其余按 ticker 映射替换
    snap_map = {}
    for p in snap["positions"]:
        tk = p.get("ticker") or p.get("code") or p.get("name")
        snap_map[tk] = p

    kept, seen = [], set()
    for i in data_idx:
        raw = lines[i].strip()
        cells = [c.strip() for c in raw.strip("|").split("|")]
        if fetch_data._row_is_closed(cells[0] if cells else "", cells):
            kept.append(raw)
            continue
        tk = _row_ticker(cells, market)
        if tk in snap_map:
            kept.append(_fmt_row(market, snap_map[tk])); seen.add(tk)
        elif tk in cleared:
            kept.append(_fmt_closed_row(cells, market)); 
        else:
            kept.append(raw)  # 快照未包含 → 原样保留（不清仓）

    for tk, p in snap_map.items():
        if tk not in seen:
            kept.append(_fmt_row(market, p))

    new_block = [HEADER[market], SEP[market]] + kept
    if data_idx:
        tail = lines[data_idx[-1] + 1:]
    else:
        after = header_i + (2 if len(tbl_rows) >= 2 else 1)
        tail = lines[after:]
    replaced = lines[:header_i] + new_block + tail
    return "\n".join(replaced) + ("\n" if md_text.endswith("\n") else "")


def _fmt_row(market, p):
    name = p.get("name", "")
    if market == "基金":
        amt = _num(p.get("amount"))
        pnl = _num(p.get("pnl"))
        amt_s = f"{amt:,.2f}" if amt is not None else "-"
        if pnl is None:
            return f"| {name} | {amt_s} | - |"
        return f"| {name} | {amt_s} | {pnl:+,.2f} |"
    code = p.get("code", "")
    qty = _fmt_qty(_num(p.get("qty")))
    cost = _num(p.get("cost"))
    last = _num(p.get("last"))
    mv = _num(p.get("market_value"))
    pnl = _num(p.get("pnl"))
    pct = _num(p.get("pnl_pct"))
    return ("| {n} | {c} | {q} | {co} | {la} | {mv} | {pn} | {pc} |").format(
        n=name, c=code, q=qty,
        co=f"{cost:.3f}" if cost is not None else "-",
        la=f"{last:.3f}" if last is not None else "-",
        mv=f"{mv:,.2f}" if mv is not None else "-",
        pn=f"{pnl:+,.2f}" if pnl is not None else "-",
        pc=f"{pct:+.2f}%" if pct is not None else "-",
    )


def _fmt_closed_row(cells, market):
    """把某行标成已清仓（加删除线 + 状态），保留其余信息。"""
    if market == "基金":
        return f"| ~~{cells[0]}~~ | 已赎回 | - |"
    name = cells[0].replace("~~", "")
    code = cells[1] if len(cells) > 1 else "-"
    return f"| ~~{name}~~ | {code} | 已清仓 | - | - | - | - | 用户确认卖出 |"


def _touch_updated_line(md_text, now, note):
    pat = re.compile(r"^>\s*最后更新：.*$", re.M)
    repl = f"> 最后更新：{now}（{note}）"
    if pat.search(md_text):
        return pat.sub(repl, md_text, count=1)
    return md_text


def _append_change_record(md_text, now, d, snap, cleared):
    date = now[:10]
    bits = []
    for o in (snap.get("orders") or []):
        side = "卖出" if str(o.get("side", "")).lower() in ("sell", "卖", "卖出") else "买入"
        bits.append(f"{side} {o.get('name', '')}{o.get('code', '')} "
                    f"{o.get('qty', '')}股@{o.get('price', '')}")
    for p in d["added"]:
        bits.append(f"新增 {p['name']}{p.get('ticker') or ''} {_fmt_qty(_num(p.get('qty')))}")
    for c, p, q0, q1 in d["qty"]:
        bits.append(f"{p['name']} {q0:.0f}→{q1:.0f}股")
    for c, p, c0, c1 in d["cost"]:
        bits.append(f"{p['name']}成本{c0:.3f}→{c1:.3f}")
    for c, p, a0, a1 in d["amount"]:
        bits.append(f"{p['name']}金额{a0:,.0f}→{a1:,.0f}")
    for h in d["missing"]:
        bits.append(f"{h['name']}未在截图出现(待确认)")
    for tk in cleared:
        bits.append(f"{tk} 标清仓")
    if bits:
        content = "；".join(bits)
    elif snap.get("totals"):
        content = "账户汇总更新（无持仓变动）"
    else:
        content = "无变动"
    acct = snap.get("account") or snap.get("broker") or ""
    note = f"{acct} {snap.get('as_of', '')} 截图；快照更新".strip()

    row = f"| {date} | {content} | 见上表 | {note} |"
    # 追加到「持仓变动更新记录」表末尾
    m = re.search(r"^##\s*持仓变动更新记录.*$", md_text, re.M)
    if not m:
        return md_text + "\n\n## 持仓变动更新记录\n\n| 日期 | 变动内容 | 变动后持仓 | 备注 |\n|---|---|---|---|\n" + row + "\n"
    tail = md_text[m.end():]
    last_tbl = None
    for mm in re.finditer(r"(?m)^\|.*\|\s*$", tail):
        last_tbl = mm
    if last_tbl is None:
        insert_at = m.end()
        return md_text[:insert_at] + "\n\n| 日期 | 变动内容 | 变动后持仓 | 备注 |\n|---|---|---|---|\n" + row + md_text[insert_at:]
    abs_pos = m.end() + last_tbl.end()
    return md_text[:abs_pos] + "\n" + row + md_text[abs_pos:]


def apply_update(holdings_path: Path, snap, d, cleared):
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    md = holdings_path.read_text(encoding="utf-8")

    # 1) 备份
    bdir = holdings_path.parent / ".holdings-backup"
    bdir.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = bdir / f"holdings-{stamp}.md"
    shutil.copy2(holdings_path, backup)

    # 2) 重写表格
    md2 = _replace_section_table(md, snap["market"], snap, cleared)
    # 2.5) 快照带 totals 时，同步账户总览 / 分节汇总行
    md2 = _sync_totals(md2, snap)
    # 3) 更新时间戳 + 变动记录
    md2 = _touch_updated_line(md2, now, f"{snap.get('account','')}截图更新".strip())
    md2 = _append_change_record(md2, now, d, snap, cleared)
    holdings_path.write_text(md2, encoding="utf-8")
    return backup


# ---------------------------------------------------------------- CLI
def main(argv=None):
    ap = argparse.ArgumentParser(description="从快照 JSON 安全更新 holdings.md")
    ap.add_argument("--snapshot", help="规范化快照 JSON 路径")
    ap.add_argument("--holdings", default="config/holdings.md")
    ap.add_argument("--apply", action="store_true", help="真正写回（默认只预览）")
    ap.add_argument("--force", action="store_true", help="忽略阻断错误强行写（危险）")
    ap.add_argument("--mark-cleared", nargs="*", default=[], help="显式把这些 ticker 标为已清仓")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出比对结果")
    ap.add_argument("--list-backups", action="store_true")
    ap.add_argument("--restore", help="从备份文件还原 holdings.md")
    args = ap.parse_args(argv)

    hpath = Path(args.holdings)
    if args.list_backups:
        bdir = hpath.parent / ".holdings-backup"
        for f in sorted(bdir.glob("holdings-*.md")) if bdir.exists() else []:
            print(f.name)
        return 0
    if args.restore:
        shutil.copy2(args.restore, hpath)
        print(f"已从备份还原 → {hpath}")
        return 0

    if not args.snapshot:
        print("缺少 --snapshot（或用 --list-backups / --restore）", file=sys.stderr)
        return 2
    if not hpath.exists():
        print(f"holdings 文件不存在: {hpath}", file=sys.stderr)
        return 2

    try:
        snap = load_snapshot(Path(args.snapshot))
    except Exception as e:  # noqa: BLE001
        print(f"快照读取失败: {e}", file=sys.stderr)
        return 2

    for p in snap["positions"]:
        _derive(p, snap["market"])

    errors, warnings = validate_snapshot(snap)
    md = hpath.read_text(encoding="utf-8")
    warnings += check_cost_jumps(snap, md)
    d = diff_snapshot(snap, md)
    cleared = set(args.mark_cleared or [])

    if args.json:
        print(json.dumps({
            "market": d["market"],
            "errors": errors, "warnings": warnings,
            "added": [p.get("ticker") or p.get("name") for p in d["added"]],
            "qty": [{"ticker": p.get("ticker"), "from": q0, "to": q1} for _, p, q0, q1 in d["qty"]],
            "cost": [{"ticker": p.get("ticker"), "from": c0, "to": c1} for _, p, c0, c1 in d["cost"]],
            "price": [{"ticker": p.get("ticker"), "from": l0, "to": l1} for _, p, l0, l1 in d["price"]],
            "amount": [{"ticker": p.get("ticker") or p.get("name"), "from": a0, "to": a1} for _, p, a0, a1 in d["amount"]],
            "missing": [h["ticker"] for h in d["missing"]],
            "changed": _has_change(d),
        }, ensure_ascii=False, indent=2))
    else:
        print(render_report(snap, d, errors, warnings))

    if errors and not args.force:
        print("\n⛔ 有阻断错误，未写入。修正快照后重跑（或 --force 强行，风险自负）。", file=sys.stderr)
        return 1

    if not args.apply:
        if _has_change(d) or cleared or _sync_totals(md, snap) != md:
            print("\n⚠️  这是预览，未写入。确认无误后加 --apply 写回。")
        return 0

    if not _has_change(d) and not cleared and _sync_totals(md, snap) == md:
        print("\n✅ 无变动，无需写入。")
        return 0

    backup = apply_update(hpath, snap, d, cleared)
    print(f"\n💾 已备份 → {backup}")
    print(f"✅ 已写回 → {hpath}")
    print("📝 已追加变动记录")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
