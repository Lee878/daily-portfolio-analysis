#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""辩论输入净化：剥掉证据里会引发「持仓锚定」的字段。

为什么需要
----------
辩论阶段要问的问题是「这家公司现在该不该买」。但只要子代理看到
``holding.cost`` / ``holding.quantity`` / ``account``，它立刻知道
「这是用户已经持有的标的」，随后结论会系统性偏向"继续持有、不必恐慌"。

这不是模型缺陷的偶发现象，是人的处置效应在语言模型上的投影：
RLHF 训练出来的助手天然倾向给"不用慌"的建议。问题在于它不体现在结构上——
报告的证据 ID 一个不少、格式完全合规，门禁查不出来，只有语气和结论方向变了。
所以只能从**输入端**把信息拿掉，而不是在提示词里说"请不要考虑持仓"。

设计约束
--------
- 净化只删字段，不改数字：``data_points`` / ``news`` / ``chain_notes`` 一字不动。
- 幂等：已经是干净输入再跑一次，输出不变。
- 可验证：``--verify`` 递归扫描禁用键，发现任何一个就 exit 1。
  没有这道校验，净化就会变成"看起来剥了、实际漏了"的假绿。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 辩论阶段允许保留的字段（白名单，比黑名单可靠：
# 新加的字段默认不进来，而不是默认漏出去）
KEEP_KEYS = (
    "schema_version", "report_date", "session",
    "ticker", "name", "market", "instrument",
    "data_points", "news", "chain_notes", "gaps",
)

# 禁用键（递归检查用）。命中任意一个即判定净化失败。
FORBIDDEN_KEYS = {
    "holding", "planned", "account",
    "cost", "cost_basis", "avg_cost", "quantity", "position", "positions",
    "pnl", "unrealized", "realized", "profit_loss", "float_pnl",
    "last_close_in_holdings",
    "成本", "持仓", "浮盈", "浮亏", "数量",
}


def sanitize(ev: dict) -> dict:
    """按白名单重建一份干净输入。只保留行情/新闻/产业链/缺口。"""
    return {k: ev[k] for k in KEEP_KEYS if k in ev}


def find_leaks(obj, path: str = "") -> list[str]:
    """递归找出所有禁用键，返回 "a.b.c" 形式的路径列表。"""
    leaks: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            here = f"{path}.{k}" if path else str(k)
            if str(k) in FORBIDDEN_KEYS:
                leaks.append(here)
            leaks.extend(find_leaks(v, here))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            leaks.extend(find_leaks(v, f"{path}[{i}]"))
    return leaks


def sanitize_file(src: Path, out_dir: Path) -> Path:
    ev = json.loads(src.read_text(encoding="utf-8"))
    clean = sanitize(ev)
    leaks = find_leaks(clean)
    if leaks:
        raise SystemExit(f"[debate-input][error] 净化后仍有敏感键：{leaks}")
    ticker = clean.get("ticker") or src.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / f"{ticker}.debate.json"
    dst.write_text(json.dumps(clean, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    return dst


def verify_dir(d: Path) -> int:
    """扫描目录内所有 json，确认没有禁用键漏出去。"""
    bad = 0
    files = sorted(d.glob("*.json"))
    if not files:
        print(f"[debate-input][warn] {d} 下没有 json")
        return 0
    for f in files:
        leaks = find_leaks(json.loads(f.read_text(encoding="utf-8")))
        if leaks:
            bad += 1
            print(f"[debate-input][X] {f.name}: {leaks}")
    if bad:
        print(f"[debate-input] {bad}/{len(files)} 个文件泄漏持仓字段 —— 禁止用于辩论")
        return 1
    print(f"[debate-input] {len(files)} 个文件全部干净 [OK]")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="辩论输入净化")
    ap.add_argument("--evidence", nargs="+", help="证据 JSON 路径（可多个）")
    ap.add_argument("--out", default="data/daily-reports/debate-input",
                    help="净化输出目录")
    ap.add_argument("--verify", help="扫描该目录，确认无禁用键")
    args = ap.parse_args()

    if args.verify:
        return verify_dir(Path(args.verify))
    if not args.evidence:
        ap.print_help()
        return 2
    for e in args.evidence:
        dst = sanitize_file(Path(e), Path(args.out))
        print(f"[debate-input] {Path(e).name} → {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
