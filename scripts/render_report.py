#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用报告渲染器（数据驱动，替代每轮手写 builder）。

agent 只产出一份紧凑 data.json（纯文字 + 结构化卡片字段，内含证据ID），
本脚本读取 assets/ 里的固定 CSS / 免责文案，套固化的卡片壳与页面骨架，
产出与旧版同结构 HTML。agent 不写 CSS、不写卡片函数、不写骨架、不写免责。

用法：
  python3 render_report.py --data <data.json> --out <out.html> \
      --date 2026-10-19 --session pre [--recon-out <recon.md>]

data.json 结构见 assets/data-schema.md。门禁仍由 gate_check.py 机械校验，
本渲染器不放松任何报告门规则。
"""
import argparse
import html as _html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402

ASSETS = paths.ASSETS

# 允许正文里出现的少量排版标签；其余一律转义（v2.2.3）
_ALLOWED = ("b", "strong", "em", "i", "u")


def esc(text):
    """转义 HTML 但保留白名单标签。

    旧版直接把 data.json 文本插进 HTML：正文出现 "R<支撑" 这类小于号会被浏览器
    当标签吞掉；来源 URL 里的引号还能截断 href。这里统一转义后只放行 <b>/<br> 等。
    """
    s = _html.escape(str(text if text is not None else ""), quote=False)
    for tag in _ALLOWED:
        s = s.replace(f"&lt;{tag}&gt;", f"<{tag}>")
        s = s.replace(f"&lt;/{tag}&gt;", f"</{tag}>")
    s = s.replace("&lt;br&gt;", "<br>").replace("&lt;br /&gt;", "<br>") \
         .replace("&lt;br/&gt;", "<br>")
    return s


def _ids(text):
    """正文里的 [dp/nw/ch-xxx] 原样保留（徽标由 run_daily 统一包裹），其余转义。"""
    return esc(text)


# ---------------------------------------------------------------------------
# 固化卡片壳（结构固定，文字由 data.json 填入；报告门要求的多方/空方标注、
# 结论/市场位置/共识/风控/操作/证伪字段全部保留）
# ---------------------------------------------------------------------------
def _tag(cls, chg):
    return f'<span class="tag {cls}">{chg}</span>'


def cn_card(c):
    return f"""<div class="card">
<h3>{esc(c['name'])} <span class="sub">{esc(c['code'])}</span>{_tag(c.get('tagcls','tr'), esc(c['chg']))}</h3>
<p><b>结论：</b>{_ids(c.get('concl',''))}</p>
<p><b>市场位置/估值：</b>{_ids(c.get('pos',''))}</p>
<p class="g">多方：{_ids(c.get('bull',''))}</p>
<p class="r">空方：{_ids(c.get('bear',''))}</p>
<p class="mut">共识与分歧：{_ids(c.get('cons',''))}</p>
<p><b>风控：</b>{_ids(c.get('risk',''))}</p>
<p><b>操作：</b><span class="b">{_ids(c.get('act',''))}</span></p>
<p class="mut">证伪：{_ids(c.get('fals',''))}</p></div>"""


def us_card(c):
    return f"""<div class="card">
<h3>{esc(c['name'])} <span class="sub">{esc(c['code'])}</span>{_tag(c.get('tagcls','tr'), esc(c['chg']))}</h3>
<p><b>结论：</b>{_ids(c.get('concl',''))}</p>
<p><b>市场位置：</b>{_ids(c.get('pos',''))}</p>
<p class="g">多方：{_ids(c.get('bull',''))}</p>
<p class="r">空方：{_ids(c.get('bear',''))}</p>
<p class="mut">共识与分歧：{_ids(c.get('cons',''))}</p>
<p><b>风控：</b>{_ids(c.get('risk',''))}</p>
<p><b>操作：</b><span class="b">{_ids(c.get('act',''))}</span></p>
<p class="mut">证伪：{_ids(c.get('fals',''))}</p></div>"""


def etf_card(c):
    return f"""<div class="card">
<h3>{esc(c['name'])} <span class="sub">{esc(c['code'])}</span>{_tag(c.get('tagcls','tr'), esc(c['chg']))}</h3>
<p><b>结论：</b>{_ids(c.get('concl',''))}</p>
<p><b>跟踪/结构：</b>{_ids(c.get('top',''))}</p>
<p class="g">多方：{_ids(c.get('bull',''))}</p>
<p class="r">空方：{_ids(c.get('bear',''))}</p>
<p><b>操作：</b><span class="b">{_ids(c.get('act',''))}</span></p>
<p class="mut">证伪：{_ids(c.get('fals',''))}</p></div>"""


def fund_card(c):
    return f"""<div class="card">
<h3>{esc(c['name'])} <span class="sub">{esc(c['code'])}</span>{_tag(c.get('tagcls','tr'), esc(c['chg']))}</h3>
<p><b>结论：</b>{_ids(c.get('concl',''))}</p>
<p class="g">多方：{_ids(c.get('bull',''))}</p>
<p class="r">空方：{_ids(c.get('bear',''))}</p>
<p><b>操作：</b><span class="b">{_ids(c.get('act',''))}</span></p></div>"""


def wl_card(c):
    dist = c.get('dist', '')
    head = (f"{esc(c['name'])} <span class='sub'>{esc(c['code'])}</span>"
            f"{_tag(c.get('tagcls','ty'), esc(c['chg']))}")
    price_line = (f"<p class='mut'>现价 {esc(c.get('price',''))} / 目标接回价 {esc(c.get('target',''))}"
                  f" · 计划 {esc(c.get('qty',''))} 股 · 止损 {esc(c.get('stop',''))} · {esc(dist)}</p>")
    return f"""<div class="card">
<h3>{head}</h3>
{price_line}
<p><b>结论：</b>{_ids(c.get('concl',''))}</p>
<p><b>技术面/位置：</b>{_ids(c.get('pos',''))}</p>
<p class="g">多方：{_ids(c.get('bull',''))}</p>
<p class="r">空方：{_ids(c.get('bear',''))}</p>
<p class="mut">共识：{_ids(c.get('cons',''))}</p>
<p><b>操作：</b><span class="b">{_ids(c.get('act',''))}</span></p>
<p class="mut">证伪：{_ids(c.get('fals',''))}</p></div>"""


def sgov_card(c):
    return f"""<div class="card">
<h3>{c['name']} <span class="sub">{c['code']}</span>{_tag(c.get('tagcls','ty'), esc(c['chg']))}</h3>
<p><b>结论：</b>{_ids(c.get('concl',''))}</p>
<p class="g">多方：{_ids(c.get('bull',''))}</p>
<p class="r">空方：{_ids(c.get('bear',''))}</p>
<p><b>操作：</b><span class="b">{_ids(c.get('act',''))}</span></p></div>"""


def advisory_card(c):
    return f"""<div class="card">
<h3>{c['name']} <span class="sub">{c['code']}</span><span class="tag ty">ADVISORY</span></h3>
<p class="mut">{esc(c.get('note','该标的为投顾组合、无公开净值代码，按持仓金额列示，不做个券四层分析、不纳入评分。'))}</p>
</div>"""


CARD_FN = {
    "cn": cn_card, "us": us_card, "etf": etf_card, "fund": fund_card,
    "wl": wl_card, "sgov": sgov_card, "advisory": advisory_card,
}


# ---------------------------------------------------------------------------
# 区块渲染
# ---------------------------------------------------------------------------
def render_paras(paras):
    return "\n".join(f"<p>{esc(p)}</p>" for p in paras)


def render_block(b):
    kind = b.get("kind", "card")
    if kind == "card":
        return f'<div class="card">{render_paras(b.get("paras", []))}</div>'
    if kind == "warn":
        return f'<div class="warn">{render_paras(b.get("paras", []))}</div>'
    if kind == "buy":
        return f'<div class="buy">{render_paras(b.get("paras", []))}</div>'
    if kind == "sectors":
        out = []
        for s in b.get("items", []):
            cls = re.sub(r"[^a-z]", "", str(s.get("cls", "mid")).lower()) or "mid"
            out.append(f'<div class="card sector {cls}">{render_paras(s.get("paras", []))}</div>')
        return "\n".join(out)
    if kind == "cards":
        out = []
        for c in b.get("cards", []):
            fn = CARD_FN.get(c.get("type"))
            if fn:
                out.append(fn(c))
        return "\n".join(out)
    if kind == "table":
        rows = ["<tr><th>持仓/板块</th><th>动作</th><th>关键条件</th></tr>"]
        for r in b.get("rows", []):
            cls = re.sub(r"[^a-z]", "", str(r.get("cls", "")).lower())
            rows.append(f"<tr><td>{esc(r.get('pos',''))}</td>"
                        f"<td class='{cls}'>{esc(r.get('act',''))}</td>"
                        f"<td>{esc(r.get('cond',''))}</td></tr>")
        return "<table>" + "".join(rows) + "</table>"
    if kind == "raw":
        return b.get("html", "")
    return f'<div class="card">{render_paras(b.get("paras", []))}</div>'


def render(data, css):
    meta = data.get("meta", {})
    parts = []
    parts.append(f"<!doctype html><html lang=\"zh\"><head><meta charset=\"utf-8\">")
    parts.append('<meta name="viewport" content="width=device-width,initial-scale=1">')
    parts.append(f"<title>{_html.escape(str(meta.get('title','报告')))}</title>"
                 f"<style>{css}</style></head><body><div class=\"wrap\">")
    parts.append(f"<h1>{esc(meta.get('h1',''))}</h1>")
    if meta.get("sub"):
        parts.append(f'<div class="sub">{esc(meta["sub"])}</div>')
    # 覆盖率横幅（数字必须是整数百分比，门正则只认整数；run_daily 还会机械校准）
    try:
        cov = int(round(float(meta.get("coverage", "0"))))
    except (TypeError, ValueError):
        cov = _html.escape(str(meta.get("coverage", "--")))
    parts.append(f'<div class="banner"><b>数据覆盖率 {cov}% · 机械门禁计算</b><br>'
                 f'<span class="mut">{esc(meta.get("coverage_note",""))}</span></div>')
    # 宏观统计小卡
    if data.get("stats"):
        cells = []
        for s in data["stats"]:
            cls = re.sub(r"[^a-z]", "", str(s.get("cls", "")).lower())
            cells.append(f'<div class="stat"><div class="v {cls}">{esc(s.get("v",""))}</div>'
                         f'<div class="k">{esc(s.get("k",""))}</div></div>')
        parts.append('<div class="stats">' + "".join(cells) + "</div>")
    # Regime 条
    if data.get("regime"):
        parts.append(f'<div class="regime">{esc(data["regime"])}</div>')
    # 顺序区块
    for b in data.get("blocks", []):
        if b.get("h2"):
            parts.append(f"<h2>{esc(b['h2'])}</h2>")
        parts.append(render_block(b))
    # 信息来源折叠区
    src = ['<details><summary><b>信息来源（点击展开）</b></summary>']
    if data.get("sources_note"):
        src.append(f"<p>{esc(data['sources_note'])}</p>")
    for i, s in enumerate(data.get("sources", []), 1):
        url = str(s.get("url", "") or "")
        label = s.get("label", "") or url
        if not url:
            continue
        src.append(f'<p>{i}. <a href="{_html.escape(url, quote=True)}">{esc(label)}</a></p>')
    src.append("</details>")
    parts.append("\n".join(src))
    # 固定免责
    parts.append(f'<div class="foot">{(ASSETS/"disclaimer.html").read_text(encoding="utf-8").strip()}</div>')
    parts.append("</div></body></html>")
    return "\n".join(parts)


def write_recon_summary(data, out_path):
    """落盘紧凑对账摘要：下一轮只读这份，不读整份报告。"""
    lines = [f"# 对账摘要 {data.get('meta',{}).get('date','')} {data.get('meta',{}).get('session','')}", ""]
    for b in data.get("blocks", []):
        if b.get("h2") and ("对账" in b["h2"]):
            lines += [f"## {b['h2']}"] + [f"- {p}" for p in b.get("paras", [])]
    lines.append("")
    lines.append("## 各持仓上轮建议/止损/证伪")
    for b in data.get("blocks", []):
        if b.get("kind") != "cards":
            continue
        for c in b.get("cards", []):
            if c.get("type") in ("advisory", "sgov"):
                continue
            clean = lambda t: re.sub(r"\[[^\]]*\]", "", t or "").strip()
            lines.append(f"- **{c.get('name','')}** 操作：{clean(c.get('act',''))}")
            if c.get("risk"):
                lines.append(f"  - 风控：{clean(c['risk'])}")
            if c.get("fals"):
                lines.append(f"  - 证伪：{clean(c['fals'])}")
    Path(out_path).write_text("\n".join(lines), encoding="utf-8")


def main():
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--session", required=True)
    ap.add_argument("--recon-out")
    args = ap.parse_args()

    data = json.loads(Path(args.data).read_text(encoding="utf-8"))
    data.setdefault("meta", {})["date"] = args.date
    data["meta"]["session"] = args.session
    css = (ASSETS / "style.css").read_text(encoding="utf-8")
    html = render(data, css)
    Path(args.out).write_text(html, encoding="utf-8")
    if args.recon_out:
        write_recon_summary(data, args.recon_out)
    print("rendered:", args.out)


if __name__ == "__main__":
    main()
