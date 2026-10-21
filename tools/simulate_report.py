#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EVALS 辅助：从证据文件生成一份"合规样例报告"（Markdown）。

演示报告门的三条硬规则：
  1. 每条多空论点都挂真实存在的证据 ID（[dp-xxx]/[nw-xxx]/[ch-xxx]）
  2. 顶部覆盖率数字直接取自 gate_check 的机械计算，禁止自报
  3. 含信息来源折叠区、免责声明、缺口披露

内容为 SIMULATED 虚构，仅用于门禁联调。

用法：
  python simulate_report.py --report-root <daily-reports> --holdings holdings.md \
      --date 2026-09-20 --session pre --out report.md
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import gate_check as gc  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report-root", required=True)
    ap.add_argument("--holdings", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--session", default="pre")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    root = Path(args.report_root)
    holdings = gc.parse_holdings(Path(args.holdings).read_text(encoding="utf-8"))
    coverages, evs = [], {}
    for h in holdings:
        fn = root / "evidence" / f"{args.date}_{args.session}_{gc.safe_name(h['ticker'])}.json"
        ev = json.loads(fn.read_text(encoding="utf-8"))
        evs[h["ticker"]] = ev
        pct, _ = gc.coverage(ev, args.session)
        coverages.append(pct)
    combo = round(sum(coverages) / len(coverages) * 100)

    lines = ["# 盘前持仓报告（SIMULATED 合规样例）",
             f"数据覆盖率 {combo}%（数值由 gate_check 机械计算，禁止人工修改）",
             ""]
    for h in holdings:
        ev = evs[h["ticker"]]
        ids = [p["id"] for p in ev["data_points"] if p["status"] == "verified"]
        ids += [n["id"] for n in ev.get("news", [])]
        ids += [c["id"] for c in ev.get("chain_notes", [])]
        lines.append(f"## {h['name']}（{h['ticker']}）")
        lines.append("**一句话结论**：持有观望，置信度中（SIMULATED）。")
        lines.append("")
        lines.append("**多方**")
        lines.append(f"1. 基本面与估值具备支撑 [{ids[0]}][{ids[1]}]")
        lines.append(f"2. 最新公告释放积极信号 [{ids[-3] if len(ids)>2 else ids[0]}]")
        lines.append(f"3. 产业链供给偏紧、板块处于强化期 [{ids[-1]}]")
        lines.append("**空方**")
        lines.append(f"1. 短期量能一般，追高性价比不足 [{ids[2] if len(ids)>2 else ids[0]}]")
        lines.append(f"2. 财报增速类数据仍有缺口，需防预期差 [{ids[-2] if len(ids)>3 else ids[0]}]")
        if ev.get("gaps"):
            lines.append("**待验证缺口**：" + "；".join(ev["gaps"][:2]))
        lines.append("")

    lines += [
        "## 我不确定的是",
        "- 财报增速类数据点尚未完成原文核对（见各标的 gaps）。",
        "",
        "<details><summary>信息来源（SIMULATED）</summary>",
        "交易所公告、公司 IR、财新/证券时报、seed_finance_lookup 行情；完整 URL 见 evidence/*.json",
        "</details>",
        "",
        "免责声明：本报告仅为研究分析与决策参考，不构成投资建议，不承诺收益，风险自担。",
    ]
    Path(args.out).write_text("\n".join(lines), encoding="utf-8")
    print(f"report written: {args.out}（覆盖率横幅 {combo}%）")


if __name__ == "__main__":
    main()
