#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EVALS 辅助：模拟 agent 完成补证后的证据文件状态。

真实流程中，agent 用 seed_finance_lookup / general_search 取数后，
必须把结果按 references/evidence-schema.md 写回 evidence/*.json。
本脚本用**显式标注的虚构数据**演示"补证后的合格形态"，仅用于门禁联调，
产生的一切数字都带 source="SIMULATED-evals"，禁止用于真实报告。

用法：
  python simulate_supplement.py --report-root <daily-reports> --date 2026-09-20 --session pre
"""
import argparse
import json
from pathlib import Path

# 虚构行情（evals 专用）
FAKE_QUOTES = {
    "601899.SH": {"price": 31.68, "chg": 1.2, "ccy": "CNY", "pe": 12.3, "pb": 3.1,
                  "cap": 8.4e11, "flow": 3.2e8},
    "300750.SZ": {"price": 288.5, "chg": -0.8, "ccy": "CNY", "pe": 22.0, "pb": 4.2,
                  "cap": 1.27e12, "flow": -5.1e8},
    "00700.HK": {"price": 382.4, "chg": 0.6, "ccy": "HKD", "pe": 24.0, "pb": 3.6,
                 "cap": 3.55e12, "flow": 4.6e9},
    "GOOG": {"price": 172.3, "chg": 0.9, "ccy": "USD", "pe": 23.5, "pb": 6.8,
             "cap": 2.13e12, "flow": 1.1},
    "AVGO": {"price": 662.0, "chg": -1.5, "ccy": "USD", "pe": 31.0, "pb": 7.2,
             "cap": 3.1e11, "flow": 0.9},
}
FAKE_NAV = {"某沪深300指数基金": (1.215, 0.25), "某医疗混合基金": (0.982, -0.4)}

TECH_FILL = ["price_last", "day_change_pct", "ma5", "ma20", "ma60",
             "range_52w_pct", "atr14", "volume_ratio"]
FUND_FILL = ["pe_ttm", "pb", "market_cap"]
FLOW_NOTE = {"main_net_inflow": "主力净流入", "north_south_flow": "北向/南向资金",
             "put_call_or_inst": "期权PCR/机构动向"}


def supplement_stock(ev):
    q = FAKE_QUOTES.get(ev["ticker"])
    values = {
        "price_last": q["price"], "day_change_pct": q["chg"],
        "ma5": round(q["price"] * 0.99, 2), "ma20": round(q["price"] * 0.96, 2),
        "ma60": round(q["price"] * 0.93, 2), "range_52w_pct": 58.0,
        "atr14": round(q["price"] * 0.02, 2), "volume_ratio": 1.05,
        "pe_ttm": q["pe"], "pb": q["pb"], "market_cap": q["cap"],
        "main_net_inflow": q["flow"],
        "put_call_or_inst": q["flow"],
    }
    for p in ev["data_points"]:
        if p["field"] in values:
            p["status"] = "verified"
            p["value"] = values[p["field"]]
            p["unit"] = q["ccy"]
            p["source"] = "SIMULATED-evals（真实流程用 seed_finance_lookup 回填）"
            p["fetched_by"] = "agent"
    # 新闻（1 条 P1 + 1 条 P2）
    ev["news"] = [
        {"id": "nw-001", "headline": f"{ev['name']}发布最新定期报告",
         "url": "https://example.com/announcement", "source": "交易所公告（SIMULATED）",
         "published_at": ev["report_date"], "evidence_level": "P1",
         "impact": "bullish", "summary": "营收同比增长，经营现金流稳定（虚构）。",
         "status": "verified"},
        {"id": "nw-002", "headline": f"行业媒体报道{ev['name']}所在板块景气度",
         "url": "https://example.com/media", "source": "财新（SIMULATED）",
         "published_at": ev["report_date"], "evidence_level": "P2",
         "impact": "neutral", "summary": "行业需求保持扩张（虚构）。",
         "status": "verified"},
    ]
    ev["chain_notes"] = [
        {"id": "ch-001", "sector": "SIMULATED 板块", "claim": "供给端偏紧、需求扩张",
         "lifecycle": "强化期", "sei": 55, "leader_backbone": "健康共振",
         "evidence_level": "P2", "source": "行业协会公开数据（SIMULATED）",
         "status": "verified"}
    ]
    # 已补齐的项从 gaps 移除；保留财报增速类缺口的诚实披露
    kept = []
    for g in ev["gaps"]:
        if any(f in g for f in ["roe", "revenue_growth", "profit_growth",
                                 "north_south_flow", "ROE", "营收", "净利润"]):
            kept.append(g)
    ev["gaps"] = kept + ["ROE/营收与净利润增速待最新财报原文核对（SIMULATED 保留缺口示范）"]


def supplement_fund(ev):
    nav = FAKE_NAV.get(ev["name"], (1.0, 0.1))
    values = {"nav_latest": nav[0], "nav_change_pct": nav[1],
              "nav_position_pct_1y": 45.0, "fund_scale_change": 2.1,
              "top_holdings": "前十大重仓集中度约 45%（SIMULATED）"}
    for p in ev["data_points"]:
        if p["field"] in values:
            p["status"] = "verified"
            p["value"] = values[p["field"]]
            p["source"] = "SIMULATED-evals（真实流程用平台数据回填）"
            p["fetched_by"] = "agent"
    ev["news"] = [
        {"id": "nw-001", "headline": "基金重仓赛道政策动态",
         "url": "https://example.com/f1", "source": "证监会公告（SIMULATED）",
         "published_at": ev["report_date"], "evidence_level": "P1",
         "impact": "neutral", "summary": "赛道相关政策发布（虚构）。",
         "status": "verified"},
        {"id": "nw-002", "headline": "赛道行业景气跟踪",
         "url": "https://example.com/f2", "source": "证券时报（SIMULATED）",
         "published_at": ev["report_date"], "evidence_level": "P2",
         "impact": "bullish", "summary": "景气度回升（虚构）。",
         "status": "verified"},
    ]
    ev["chain_notes"] = [
        {"id": "ch-001", "sector": "基金重仓赛道", "claim": "赛道处于强化期",
         "lifecycle": "强化期", "sei": 50, "leader_backbone": "健康共振",
         "evidence_level": "P2", "source": "公开研报交叉（SIMULATED）",
         "status": "verified"}
    ]
    ev["gaps"] = ["基金经理变更（manager_change）待平台页面核对（SIMULATED 保留缺口示范）"]


def supplement_macro(ev):
    vals = {"us_index_futures": "纳指期货 +0.3%", "vix": 14.2, "dxy": 103.1,
            "us10y": 4.05, "wti": 72.3, "gold": 2680.0, "btc": 63000.0,
            "vix_now": "VIX 14.2，较5日前 -1.1", "iv_vs_hv": "IV 16% < HV30 21%",
            "event_calendar": "下周 CPI、GOOG 财报", "put_call_ratio": 0.92}
    for p in ev["data_points"]:
        for k, v in vals.items():
            if p["field"] == k:
                p["status"], p["value"], p["source"] = \
                    "verified", v, "SIMULATED-evals（真实流程用 seed_finance_lookup）"
    ev["gaps"] = []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report-root", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--session", default="pre")
    args = ap.parse_args()
    ev_dir = Path(args.report_root) / "evidence"
    for fn in sorted(ev_dir.glob(f"{args.date}_{args.session}_*.json")):
        ev = json.loads(fn.read_text(encoding="utf-8"))
        if ev.get("market") == "macro":
            supplement_macro(ev)
        elif ev.get("market") == "基金":
            supplement_fund(ev)
        else:
            supplement_stock(ev)
        fn.write_text(json.dumps(ev, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"supplemented: {fn.name}")


if __name__ == "__main__":
    main()
