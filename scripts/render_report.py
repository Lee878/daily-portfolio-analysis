#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通用报告渲染器（数据驱动，手机优先）—— v2.4.0

agent 只产出一份紧凑 data.json（纯文字 + 结构化卡片字段，内含证据ID），
本脚本读取 assets/ 里的固定 CSS / 免责文案，套固化的卡片壳与页面骨架。

v2.4.0 视觉层重做：
  - 红涨绿跌（A 股习惯）：涨/多方=红，跌/空方=绿；旧 token g/r/tg/tr 走 CLS_MAP 别名
  - 手机优先：正文 15.5px、常驻顶栏、锚点索引、多空双栏、表格窄屏堆叠
  - 结论优先：结论/多空/风控/操作常显，市场位置/共识/证伪/证据默认折叠
  - 电脑端（>=900px）纯 CSS 自动展开，不需要 JS
  - 每张卡底部生成"证据清单"（ID+级别+来源+链接），替代手机上点不出的 hover

用法：
  python scripts/render_report.py --data <data.json> --out <out.html> \
      --date 2026-10-19 --session pre [--recon-out <recon.md>] [--evidence-dir <dir>]
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

# 允许正文里出现的少量排版标签；其余一律转义
_ALLOWED = ("b", "strong", "em", "i", "u")

ID_RE = re.compile(r"\[(dp|nw|ch)-\d{3}\]")

# 旧 token → 新语义 token（历史 data.json 零迁移）
CLS_MAP = {"g": "up", "r": "down", "tg": "tagup", "tr": "tagdown"}

ACT_CLASS = {"加": "act-add", "减": "act-cut", "持有": "act-hold", "观察": "act-watch"}

# 渲染上下文（id_meta / 锚点去重），由 render() 注入
_CTX = {"id_meta": {}, "anchors": None, "n_cards": 0}


def esc(text):
    """转义 HTML 但保留白名单标签（正文含 < 时不破版）。"""
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


def cls(value, default=""):
    """把旧/新颜色 token 统一成新 token。"""
    v = (value or default or "").strip()
    return CLS_MAP.get(v, v)


def plain(text):
    """去标签取纯文本（用于顶栏摘要）。"""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", str(text or ""))).strip()


def infer_act(text):
    """从操作文字推断动作标签。注意排除否定词："不加仓"不是"加"。"""
    t = str(text or "")
    if re.search(r"(?<!不)(?:减仓|卖出|清仓|止盈|离场|砍仓)", t):
        return "减"
    if re.search(r"(?<!不)(?:加仓|买入|接回|建仓|加回)", t):
        return "加"
    if re.search(r"持有|拿住|不动", t):
        return "持有"
    if re.search(r"观察|等待|等回踩|不追|待验证", t):
        return "观察"
    return "关注"


def act_of(c):
    return str(c.get("act_tag") or infer_act(c.get("act", ""))).strip()


class Anchors:
    """给卡片标题生成唯一锚点 id（TOC 用）。"""

    def __init__(self):
        self.used = set()

    def make(self, c):
        raw = re.split(r"[·\s]", str(c.get("code") or c.get("name") or "card"))[0]
        base = re.sub(r"[^0-9A-Za-z]+", "-", raw).strip("-").lower()
        base = base or "card"
        anchor, i = "c-" + base, 2
        while anchor in self.used:
            anchor = f"c-{base}-{i}"
            i += 1
        self.used.add(anchor)
        return anchor


def load_id_meta(evidence_dir, date, session):
    """从 evidence/*.json 建 ID → (级别, 来源, 链接)，供"证据清单"使用。"""
    meta = {}
    if not evidence_dir:
        return meta
    d = Path(evidence_dir)
    if not d.is_dir():
        return meta
    for f in sorted(d.glob(f"{date}_{session}_*.json")):
        try:
            ev = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        for p in ev.get("data_points", []):
            if p.get("id"):
                meta[p["id"]] = (p.get("evidence_level") or "P3",
                                 p.get("source") or "", p.get("source_url") or "")
        for n in ev.get("news", []):
            if n.get("id"):
                meta[n["id"]] = (n.get("evidence_level") or "P3",
                                 n.get("source") or n.get("headline") or "",
                                 n.get("url") or "")
        for c in ev.get("chain_notes", []):
            if c.get("id"):
                meta[c["id"]] = (c.get("evidence_level") or "P3",
                                 c.get("source") or c.get("sector") or "",
                                 c.get("source_url") or "")
    return meta


# ---------------------------------------------------------------------------
# 固化组件
# ---------------------------------------------------------------------------
def _tag(cls_name, chg):
    return f'<span class="tag {cls(cls_name, "tr")}">{esc(chg)}</span>'


def chg_dir(chg):
    """从涨跌文本判断方向：红涨绿跌。"""
    m = re.search(r"[-+]?\d+(?:\.\d+)?", str(chg or ""))
    if not m:
        return ""
    try:
        return "down" if float(m.group(0)) < 0 else "up"
    except ValueError:
        return ""


def chg_html(chg):
    d = chg_dir(chg)
    arrow = {"up": "▲", "down": "▼"}.get(d, "")
    return f'<span class="chg {d}">{arrow} {esc(chg)}</span>'


def chead(c, anchor):
    """卡片头：名称 + 代码 + 涨跌（红涨绿跌）+ 动作徽章（手机一行内看完）。"""
    act = act_of(c)
    act_cls = ACT_CLASS.get(act, "")
    return (f'<div class="chead"><h3 id="{anchor}">{esc(c.get("name",""))} '
            f'<span class="sub">{esc(c.get("code",""))}</span></h3>'
            f'{chg_html(c.get("chg",""))}'
            f'<span class="act {act_cls}">{esc(act)}</span></div>')


def fold(title, body_html, open_=False):
    if not body_html:
        return ""
    return (f'<details class="fold"{" open" if open_ else ""}>'
            f'<summary>{esc(title)}</summary>'
            f'<div class="fold-body">{body_html}</div></details>')


def evidence_fold(text, id_meta):
    """卡片底部证据清单：ID + 级别 + 来源 + 可点链接（替代 hover）。"""
    ids, seen = [], set()
    for m in ID_RE.finditer(text or ""):
        i = m.group(0)[1:-1]
        if i not in seen:
            seen.add(i)
            ids.append(i)
    if not ids:
        return ""
    items = []
    for i in ids:
        lv, src, url = id_meta.get(i, ("", "", ""))
        line = f"<b>[{i}]</b>"
        if lv:
            line += f" {esc(lv)}"
        if src:
            line += f" · {esc(src)}"
        if url:
            line += f' · <a href="{_html.escape(url, quote=True)}" target="_blank" rel="noopener">打开来源</a>'
        items.append(f"<li>{line}</li>")
    return fold(f"证据（{len(ids)} 条）", "<ul class='evlist'>" + "".join(items) + "</ul>")


def _bull_bear(c):
    bull, bear = str(c.get("bull") or ""), str(c.get("bear") or "")
    if not bull and not bear:
        return ""
    out = ['<div class="bb">']
    if bull:
        out.append(f'<p class="side bull"><b>多方</b>：{esc(bull)}</p>')
    if bear:
        out.append(f'<p class="side bear"><b>空方</b>：{esc(bear)}</p>')
    out.append("</div>")
    return "\n".join(out)


def _risk_op(c):
    out = []
    if c.get("risk"):
        out.append(f'<p class="riskline"><b>风控</b>：{esc(c["risk"])}</p>')
    if c.get("act"):
        out.append(f'<p class="opline"><b>操作</b>：<span class="actv">{esc(c["act"])}</span></p>')
    return "\n".join(out)


def _card(c, anchor, extra_folds=()):
    """通用卡片壳：结论 → 多空 → 风控/操作 → 折叠细节 → 证据。"""
    body = [chead(c, anchor)]
    if c.get("concl"):
        body.append(f'<p class="concl"><b>结论：</b>{esc(c["concl"])}</p>')
    body.append(_bull_bear(c))
    body.append(_risk_op(c))
    for title, content in extra_folds:
        if content:
            body.append(fold(title, f"<p>{esc(content)}</p>"))
    if c.get("fals"):
        body.append(fold("证伪条件（什么情况说明我错了）", f"<p>{esc(c['fals'])}</p>"))
    text_all = " ".join(str(v) for v in c.values() if isinstance(v, str))
    body.append(evidence_fold(text_all, _CTX["id_meta"]))
    _CTX["n_cards"] += 1
    return '<div class="card">\n' + "\n".join(body) + "\n</div>"


def cn_card(c):
    return _card(c, _CTX["anchors"].make(c), extra_folds=(
        ("市场位置 / 估值 / price-in", c.get("pos", "")),
        ("共识与分歧", c.get("cons", "")),
    ))


def us_card(c):
    return _card(c, _CTX["anchors"].make(c), extra_folds=(
        ("市场位置 / 估值 / price-in", c.get("pos", "")),
        ("共识与分歧", c.get("cons", "")),
    ))


def etf_card(c):
    return _card(c, _CTX["anchors"].make(c), extra_folds=(
        ("跟踪结构 / 每日重置耗损", c.get("top", "")),
    ))


def fund_card(c):
    return _card(c, _CTX["anchors"].make(c))


def wl_card(c):
    """关注库：现价/目标价/计划/止损一行在前，结论优先，其余折叠。"""
    head = (f'<div class="chead"><h3 id="{_CTX["anchors"].make(c)}">{esc(c.get("name",""))} '
            f'<span class="sub">{esc(c.get("code",""))}</span></h3>'
            f'{chg_html(c.get("chg",""))}'
            f'<span class="act {ACT_CLASS.get(act_of(c), "")}">{esc(act_of(c))}</span></div>')
    meta_line = (f'<p class="mut">现价 {esc(c.get("price",""))} · 目标接回价 {esc(c.get("target",""))}'
                 f' · 计划 {esc(c.get("qty",""))} 股 · 止损 {esc(c.get("stop",""))}'
                 f' · {esc(c.get("dist",""))}</p>')
    body = [head, meta_line]
    if c.get("concl"):
        body.append(f'<p class="concl"><b>结论：</b>{esc(c["concl"])}</p>')
    body.append(_bull_bear(c))
    body.append(_risk_op(c))
    body.append(fold("技术面 / 位置", f"<p>{esc(c.get('pos',''))}</p>" if c.get("pos") else ""))
    body.append(fold("共识与分歧", f"<p>{esc(c.get('cons',''))}</p>" if c.get("cons") else ""))
    body.append(fold("证伪条件", f"<p>{esc(c.get('fals',''))}</p>" if c.get("fals") else ""))
    text_all = " ".join(str(v) for v in c.values() if isinstance(v, str))
    body.append(evidence_fold(text_all, _CTX["id_meta"]))
    _CTX["n_cards"] += 1
    return '<div class="card">\n' + "\n".join(body) + "\n</div>"


def sgov_card(c):
    return _card(c, _CTX["anchors"].make(c))


def advisory_card(c):
    anchor = _CTX["anchors"].make(c)
    note = c.get("note") or "该标的为投顾组合、无公开净值代码，按持仓金额列示，不做个券四层分析、不纳入评分。"
    _CTX["n_cards"] += 1
    return (f'<div class="card"><div class="chead"><h3 id="{anchor}">{esc(c.get("name",""))} '
            f'<span class="sub">{esc(c.get("code",""))}</span></h3>'
            f'<span class="act act-hold">列示</span></div>'
            f'<p class="mut">{esc(note)}</p></div>')


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
    if kind == "warn":
        return f'<div class="warn">{render_paras(b.get("paras", []))}</div>'
    if kind == "buy":
        return f'<div class="buy">{render_paras(b.get("paras", []))}</div>'
    if kind == "sectors":
        out = []
        for s in b.get("items", []):
            c = re.sub(r"[^a-z]", "", str(s.get("cls", "mid")).lower()) or "mid"
            out.append(f'<div class="card sector {c}">{render_paras(s.get("paras", []))}</div>')
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
            c = re.sub(r"[^a-z]", "", str(r.get("cls", "")).lower())
            rows.append(f'<tr><td data-label="持仓/板块">{esc(r.get("pos",""))}</td>'
                        f'<td data-label="动作" class="{c}">{esc(r.get("act",""))}</td>'
                        f'<td data-label="关键条件">{esc(r.get("cond",""))}</td></tr>')
        return "<table>" + "".join(rows) + "</table>"
    if kind == "raw":
        return b.get("html", "")
    return f'<div class="card">{render_paras(b.get("paras", []))}</div>'


def collect_actions(data, limit=4):
    """顶栏"今日动作"：从卡片里抽 名称+动作，最多 limit 条。"""
    out = []
    for b in data.get("blocks", []):
        if b.get("kind") != "cards":
            continue
        for c in b.get("cards", []):
            if c.get("type") == "advisory":
                continue
            name, act = c.get("name"), act_of(c)
            if name and act:
                out.append(f"{plain(name)} {act}")
            if len(out) >= limit:
                return out
    return out


def render(data, css):
    meta = data.get("meta", {})
    _CTX["id_meta"] = data.get("_id_meta", {})
    _CTX["anchors"] = Anchors()
    _CTX["n_cards"] = 0

    # 覆盖率：必须是整数百分比（门禁正则只认整数，run_daily 还会校准）
    try:
        cov = int(round(float(meta.get("coverage", "0"))))
    except (TypeError, ValueError):
        cov = _html.escape(str(meta.get("coverage", "--")))

    actions = collect_actions(data)
    regime_short = plain(data.get("regime", ""))[:32]

    parts = ['<!doctype html><html lang="zh"><head><meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">',
             '<meta name="color-scheme" content="dark">',
             '<meta name="theme-color" content="#0d1117">',
             f"<title>{_html.escape(str(meta.get('title', '报告')))}</title>",
             f"<style>{css}</style></head><body><div class=\"wrap\">"]

    # 常驻顶栏：Regime + 覆盖率 + 今日动作
    tb = ['<div class="topbar"><div class="tb-row">',
          f'<span class="tb-regime">{esc(regime_short or meta.get("h1", "报告"))}</span>',
          f'<span class="tb-cov">覆盖 {cov}%</span></div>']
    if actions:
        tb.append(f'<div class="tb-actions">今日：{esc(" · ".join(actions))}</div>')
    tb.append("</div>")
    parts.append("".join(tb))

    parts.append(f"<h1>{esc(meta.get('h1',''))}</h1>")
    if meta.get("sub"):
        parts.append(f'<div class="sub">{esc(meta["sub"])}</div>')

    parts.append(f'<div class="banner" style="margin-top:12px"><b>数据覆盖率 {cov}% · 机械门禁计算</b>'
                 f'<br><span class="mut">{esc(meta.get("coverage_note",""))}</span></div>')

    if data.get("stats"):
        cells = []
        for s in data["stats"]:
            cells.append(f'<div class="stat"><div class="v {cls(s.get("cls"))}">{esc(s.get("v",""))}</div>'
                         f'<div class="k">{esc(s.get("k",""))}</div></div>')
        parts.append('<div class="stats">' + "".join(cells) + "</div>")

    if data.get("regime"):
        parts.append(f'<div class="regime">{esc(data["regime"])}</div>')

    # 先渲染区块（此时才产生锚点），再补 TOC —— 用占位符回填
    body_parts = []
    for b in data.get("blocks", []):
        if b.get("h2"):
            body_parts.append(f"<h2>{esc(b['h2'])}</h2>")
        body_parts.append(render_block(b))

    # render_block 已经把锚点写进 h3；这里按卡片顺序收集 h3 id
    anchors = re.findall(r'<h3 id="([^"]+)"', "".join(body_parts))
    names = [plain(c.get("name", "")) for b in data.get("blocks", [])
             if b.get("kind") == "cards" for c in b.get("cards", [])]
    if len(anchors) >= 3 and len(anchors) == len(names):
        chips = "".join(f'<a href="#{a}">{esc(n)}</a>' for n, a in zip(names, anchors))
        parts.append(f'<nav class="toc">{chips}</nav>')

    parts.extend(body_parts)

    src = ['<details class="src"><summary><b>信息来源（点击展开）</b></summary>']
    if data.get("sources_note"):
        src.append(f"<p>{esc(data['sources_note'])}</p>")
    for i, s in enumerate(data.get("sources", []), 1):
        url = str(s.get("url", "") or "")
        if not url:
            continue
        label = s.get("label", "") or url
        src.append(f'<p>{i}. <a href="{_html.escape(url, quote=True)}" '
                   f'target="_blank" rel="noopener">{esc(label)}</a></p>')
    src.append("</details>")
    parts.append("\n".join(src))

    parts.append(f'<div class="foot">{(ASSETS / "disclaimer.html").read_text(encoding="utf-8").strip()}</div>')
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
            def clean(t):
                return re.sub(r"\[[^\]]*\]", "", t or "").strip()
            lines.append(f"- **{c.get('name','')}** 操作：{clean(c.get('act',''))}")
            if c.get("risk"):
                lines.append(f"  - 风控：{clean(c['risk'])}")
            if c.get("fals"):
                lines.append(f"  - 证伪：{clean(c['fals'])}")
    Path(out_path).write_text("\n".join(lines), encoding="utf-8")


def main():
    paths.ensure_utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--session", required=True)
    ap.add_argument("--recon-out")
    ap.add_argument("--evidence-dir", help="证据目录（生成每张卡的证据清单）")
    args = ap.parse_args()

    data = json.loads(Path(args.data).read_text(encoding="utf-8"))
    data.setdefault("meta", {})["date"] = args.date
    data["meta"]["session"] = args.session
    if args.evidence_dir:
        data["_id_meta"] = load_id_meta(args.evidence_dir, args.date, args.session)
    css = (ASSETS / "style.css").read_text(encoding="utf-8")
    html = render(data, css)
    Path(args.out).write_text(html, encoding="utf-8")
    if args.recon_out:
        write_recon_summary(data, args.recon_out)
    print("rendered:", args.out)


if __name__ == "__main__":
    main()
