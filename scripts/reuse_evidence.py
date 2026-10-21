#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
同日证据增量复用（省 token）。

pre 建当日全量底库；noon/post 只补"当日增量"（实时行情、当日新闻、新公告），
慢变量（财报/估值/ROE/产业链）从同日早一时段证据复用，不重复搜索、不重复取证。

用法：
  python3 reuse_evidence.py --report-root <daily-reports> --date <YYYY-MM-DD> \
      --from-session pre --to-session noon

只合并"不变项"：
  - chain_notes（产业链/生命周期/SEI，当日不变）
  - data_points 中 status=verified 的慢变量（pe/pb/market_cap/roe/营收利润增速/52周分位）
不合并：实时行情（price_last/day_change_pct/MA/ATR/量比）、news（必须当日新）、宏观行情。
被复用的条目加 "reused_from" 标记，便于对账，不改变证据门判定。
"""
import argparse
import json
import re
from pathlib import Path

# 慢变量字段（当日基本不变，可复用）；行情/技术波动字段不在此列
SLOW_FIELDS = {
    "pe_ttm", "pb", "market_cap", "roe",
    "revenue_growth_yoy", "profit_growth_yoy", "range_52w_pct",
    "dividend_yield", "gross_margin", "net_margin",
}


def load(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def merge(src, dst):
    """把 src 的不变项合并进 dst（原地改 dst dict），返回复用条数。

    慢变量 dp 按 field 回填 dst 已有的同字段槽位（沿用 dst 的 ID，避免编号冲突）；
    dst 没有该 field 槽位时才追加，追加条目 id 置空，交给统一编号。
    """
    n = 0
    # 产业链笔记复用（dst 通常无 chain 槽位，直接追加；按 id 去重）
    existing_ch = {c.get("id") for c in dst.get("chain_notes", [])}
    for c in src.get("chain_notes", []):
        if c.get("id") and c["id"] not in existing_ch:
            c = dict(c)
            c["reused_from"] = src.get("session")
            dst.setdefault("chain_notes", []).append(c)
            n += 1
    # 慢变量 data_points 复用（仅 verified）：按 field 回填
    for p in src.get("data_points", []):
        if p.get("status") != "verified" or p.get("field") not in SLOW_FIELDS:
            continue
        slot = next((d for d in dst.get("data_points", [])
                     if d.get("field") == p.get("field")
                     and d.get("status") != "verified"), None)
        if slot is not None:
            slot.update({
                "value": p.get("value"),
                "source": p.get("source", ""),
                "source_url": p.get("source_url", ""),
                "evidence_level": p.get("evidence_level", "P3"),
                "fetched_by": "script",
                "status": "verified",
                "reused_from": src.get("session"),
            })
            n += 1
            continue
        # 无槽位且该 field 未 verified：追加（id 置空，避免冲突）
        if any(d.get("field") == p.get("field") and d.get("status") == "verified"
               for d in dst.get("data_points", [])):
            continue
        p = dict(p)
        p["id"] = ""
        p["reused_from"] = src.get("session")
        dst.setdefault("data_points", []).append(p)
        n += 1
    return n


def renumber_data_points(dst):
    """给 id 为空的 data_point 补编号（v2.2.3）。

    旧版追加条目 id 留空且无人重编号，docstring 承诺的"交给统一编号"实际不存在，
    导致复用来的字段无法在报告里引用。编号只补空的，不动已有 ID，避免打断
    已写好的引用。
    """
    used = {d.get("id") for d in dst.get("data_points", []) if d.get("id")}
    nums = []
    for i in used:
        m = re.fullmatch(r"dp-(\d+)", str(i))
        if m:
            nums.append(int(m.group(1)))
    nxt = max(nums) + 1 if nums else 1
    changed = 0
    for d in dst.get("data_points", []):
        if d.get("id"):
            continue
        while f"dp-{nxt:03d}" in used:
            nxt += 1
        d["id"] = f"dp-{nxt:03d}"
        used.add(d["id"])
        nxt += 1
        changed += 1
    return changed


def main():
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--report-root", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--from-session", required=True)
    ap.add_argument("--to-session", required=True)
    args = ap.parse_args()

    ev_dir = Path(args.report_root) / "evidence"

    def load_session(session):
        out = {}
        for p in ev_dir.glob(f"{args.date}_{session}_*.json"):
            d = load(p)
            if d and d.get("ticker"):
                out[d["ticker"]] = p
        return out

    src_files = load_session(args.from_session)
    total = 0
    for dst_path in ev_dir.glob(f"{args.date}_{args.to_session}_*.json"):
        dst = load(dst_path)
        if not dst or not dst.get("ticker"):
            continue
        src_path = src_files.get(dst["ticker"])
        src = load(src_path) if src_path else None
        if not src:
            continue
        n = merge(src, dst)
        if n:
            renumber_data_points(dst)
            dst_path.write_text(
                json.dumps(dst, ensure_ascii=False, indent=2), encoding="utf-8")
            total += n
            print(f"[reuse] {dst.get('name')} 复用 {n} 条（{args.from_session}→{args.to_session}）")
    print(f"[reuse] 完成，共复用 {total} 条慢变量/产业链；实时行情与当日新闻仍需新补。")


if __name__ == "__main__":
    main()
