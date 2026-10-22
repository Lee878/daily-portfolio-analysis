#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
提交前预校验（preflight）：渲染前对 data.json 做静态自查，提前拦住最常见的
报告门失败点，避免跑到 report 才被删 HTML、返工重写。

不替代 gate_check（那是权威门禁）；这里只给 agent 一份快速自查清单。
退出码 0=可继续，1=先修下列问题。

用法：
  python3 preflight.py --data <data.json> --session pre [--holdings <holdings.md>]
"""
import argparse
import re
import sys
from pathlib import Path

ID_RE = re.compile(r"\[(dp|nw|ch)-\d{3}\]")   # 与 gate_check.ID_RE 对齐（v2.2.3）
HOME_URL = re.compile(r"^https?://[^/]+/?$")


def ids_in(text):
    """返回完整证据编号（如 dp-001）。

    旧版用 ID_RE.findall：正则带捕获组时 findall 只返回组内容（dp/nw/ch），
    于是"唯一 ID 数"永远≤3，自查结论全是错的。
    """
    return [m.group(0).strip("[]") for m in ID_RE.finditer(text or "")]


def collect_card_text(c):
    return " ".join(str(v) for v in c.values() if isinstance(v, str))


def check_card(c, problems, session):
    ctype = c.get("type")
    name = c.get("name", "?")
    # 完整股票：多空双栏 + 多空不同源 + ID 数量
    if ctype in ("cn", "us"):
        full = collect_card_text(c)
        # 渲染器会自动加"多方：/空方："前缀，这里只要求字段非空，
        # 否则 agent 会被迫在正文里再写一遍，产出"多方：多方："（历史报告就出现过）
        if not str(c.get("bull", "")).strip():
            problems.append(f"[{name}] 缺 bull（多方）字段")
        if not str(c.get("bear", "")).strip():
            problems.append(f"[{name}] 缺 bear（空方）字段")
        bull_ids = set(ids_in(c.get("bull", "")))
        bear_ids = set(ids_in(c.get("bear", "")))
        # 多空不同源（各自独有证据）仅完整版 pre/post 强制；noon/quick 放宽
        if session in ("pre", "post"):
            if bull_ids and bull_ids - bear_ids == set():
                problems.append(f"[{name}] 多方缺少对方没有的独立证据ID（多空不同源）")
            if bear_ids and bear_ids - bull_ids == set():
                problems.append(f"[{name}] 空方缺少对方没有的独立证据ID（多空不同源）")
        all_ids = ids_in(full)
        # 引用阈值与 gate_check 一致：完整版 4/6，noon/quick 2/3
        min_ids, min_refs = (4, 6) if session in ("pre", "post") else (2, 3)
        if len(set(all_ids)) < min_ids:
            problems.append(f"[{name}] 章节内唯一证据ID <{min_ids}（现 {len(set(all_ids))}）")
        if len(all_ids) < min_refs:
            problems.append(f"[{name}] 证据引用总次数 <{min_refs}（现 {len(all_ids)}）")
    # 关注库：到价二选一，未到价禁喊买
    if ctype == "wl":
        try:
            price, target = float(c.get("price", 0)), float(c.get("target", 0))
        except (TypeError, ValueError):
            price, target = 0, 0
        act = c.get("act", "")
        if price and target and price <= target:
            if ("可接回" not in act) and ("先别接" not in act):
                problems.append(f"[{name}] 已到价，act 须给'可接回清单'或喊'先别接'")
        else:
            if ("可接回" in act or "买入" in act):
                problems.append(f"[{name}] 未到价，禁止喊可接回/买入")


def main():
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--session", default="pre")
    ap.add_argument("--holdings")
    args = ap.parse_args()

    import json
    data = json.loads(Path(args.data).read_text(encoding="utf-8"))
    problems = []

    # 覆盖率横幅
    if not str(data.get("meta", {}).get("coverage", "")):
        problems.append("meta.coverage 缺失（横幅覆盖率）")

    # 遍历 blocks 里的卡片
    for b in data.get("blocks", []):
        if b.get("kind") == "cards":
            for c in b.get("cards", []):
                check_card(c, problems, args.session)

    # 来源折叠
    sources = data.get("sources", [])
    need = 4 if args.session in ("pre", "post") else 3
    if len(sources) < need:
        problems.append(f"信息来源 {len(sources)} 条 < {need}（{args.session} 要求）")
    for s in sources:
        u = s.get("url", "")
        if HOME_URL.match(u):
            problems.append(f"来源是首页/栏目页，须具体文章页：{u}")

    # 缺口披露
    full_text = json.dumps(data, ensure_ascii=False)
    if not re.search(r"我不确定|数据缺口|待验证|gaps|缺口", full_text, re.I):
        problems.append("缺缺口披露（须含'我不确定/gaps/待验证/数据缺口'）")

    if problems:
        print("[preflight] 发现问题，先修再 report：")
        for p in problems:
            print("  [X]", p)
        sys.exit(1)
    print("[preflight] 静态自查通过，可继续跑 report。")
    sys.exit(0)


if __name__ == "__main__":
    main()
