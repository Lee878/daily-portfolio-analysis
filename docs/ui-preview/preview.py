#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UI 重设计样张生成器（一次性，不参与生产流程）

读真实 data.json，用两套视觉语言各出一份 HTML，供选定方向。
共享的信息架构改进：
  1. 正文剥离证据徽标 → 收进卡底折叠（可追溯性不丢）
  2. 从 code 解析 成本/现价/股数 → 自动算浮盈，做成三格数据条
  3. 首屏压成 4 层：日期带 / Regime 大字 / 指数网格 / 今日动作横滑
  4. 覆盖率机器说明收进折叠
  5. 卡片按动作给左侧状态条，扫一眼能找出"要动手的"
"""
import html as _html
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

ALLOWED = ("b", "strong", "em", "i", "u")
ID_RE = re.compile(r"\[(dp|nw|ch)-\d{3}\]")
CLS_MAP = {"g": "rise", "r": "fall", "tg": "rise", "tr": "fall"}
ACT_CLASS = {"加": "add", "减": "cut", "持有": "hold", "观察": "watch", "关注": "watch"}


def esc(t):
    s = _html.escape(str(t if t is not None else ""), quote=False)
    for tag in ALLOWED:
        s = s.replace(f"&lt;{tag}&gt;", f"<{tag}>").replace(f"&lt;/{tag}&gt;", f"</{tag}>")
    return s


def strip_ids(text):
    """剥离正文证据 ID，返回 (干净文本, 去重 ID 列表)。"""
    raw = str(text or "")
    ids, seen = [], set()
    for m in ID_RE.finditer(raw):
        i = m.group(0)[1:-1]
        if i not in seen:
            seen.add(i)
            ids.append(i)
    clean = ID_RE.sub("", raw)
    clean = re.sub(r"[ \t]{2,}", " ", clean)
    clean = re.sub(r"\s+([。，；、）])", r"\1", clean)
    clean = re.sub(r"（\s*）", "", clean)
    return clean.strip(), ids


def short_title(t):
    """目录 chip 只留主标题，括号里的补充说明移到完整 h2 里。"""
    s = re.sub(r"[（(][^)）]*[)）]", "", str(t or "")).strip(" ·|—-")
    return s or str(t or "")


def cls_of(v, default=""):
    return CLS_MAP.get((v or default or "").strip(), (v or default or "").strip())


def infer_act(text):
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


# ---------------------------------------------------------------------------
# 从 code 字段抠出"我的仓位"信息：GOOG · 28股 成本357.577 · 现价340.16
# ---------------------------------------------------------------------------
def parse_position(code):
    s = str(code or "")
    out = {"name_tail": "", "shares": "", "cost": "", "last": "", "pnl": "", "pnl_cls": ""}
    m = re.search(r"成本\s*([\d,]+\.?\d*)", s)
    if m:
        out["cost"] = m.group(1).replace(",", "")
    m = re.search(r"现价\s*([\d,]+\.?\d*)", s)
    if m:
        out["last"] = m.group(1).replace(",", "")
    m = re.search(r"(\d+)\s*股", s)
    if m:
        out["shares"] = m.group(1)
    if out["cost"] and out["last"]:
        try:
            c, l = float(out["cost"]), float(out["last"])
            if c > 0:
                pct = (l / c - 1) * 100
                out["pnl"] = f"{pct:+.2f}%"
                out["pnl_cls"] = "rise" if pct > 0 else ("fall" if pct < 0 else "")
        except ValueError:
            pass
    # 名称前段（"GOOG"）+ 其余残余
    rest = s
    for p in (r"·?\s*成本\s*[\d,\.]+", r"·?\s*现价\s*[\d,\.]+", r"·?\s*\d+\s*股"):
        rest = re.sub(p, "", rest)
    out["name_tail"] = rest.strip(" ·")
    return out


def split_stat(v):
    """'7690.73 +0.41%' → ('7690.73','+0.41%','rise')
       '约4115 连跌3日'   → ('约4115','连跌3日','fall')
       状态词单独成行才不会被数值挤断。"""
    s = str(v or "").strip()
    m = re.match(r"^(.+?)\s*([+-]\d+(?:\.\d+)?%)\s*$", s)
    if m:
        d = "fall" if m.group(2).startswith("-") else "rise"
        return m.group(1), m.group(2), d
    m = re.match(r"^(约?[\d,]+(?:\.\d+)?)\s*(.+)$", s)
    if m:
        tail = m.group(2)
        d = ""
        if "跌" in tail:
            d = "fall"
        elif "涨" in tail:
            d = "rise"
        return m.group(1), tail, d
    return s, "", ""


# ---------------------------------------------------------------------------
# 卡片
# ---------------------------------------------------------------------------
def data_bar(pos):
    """三格数据条：成本 / 现价 / 浮盈。没成本信息就不出。"""
    if not (pos["cost"] or pos["last"]):
        return ""
    cells = []
    if pos["cost"]:
        cells.append(f'<div class="dcell"><span class="dk">成本</span>'
                     f'<span class="dv">{esc(pos["cost"])}</span></div>')
    if pos["last"]:
        cells.append(f'<div class="dcell"><span class="dk">现价</span>'
                     f'<span class="dv">{esc(pos["last"])}</span></div>')
    if pos["pnl"]:
        cells.append(f'<div class="dcell"><span class="dk">浮动</span>'
                     f'<span class="dv {pos["pnl_cls"]}">{esc(pos["pnl"])}</span></div>')
    elif pos["shares"]:
        cells.append(f'<div class="dcell"><span class="dk">持仓</span>'
                     f'<span class="dv">{esc(pos["shares"])} 股</span></div>')
    return '<div class="dbar">' + "".join(cells) + "</div>"


def fold(label, body, count=""):
    if not body:
        return ""
    tag = f'<em>{count}</em>' if count else ""
    return (f'<details class="fold"><summary>{esc(label)}{tag}</summary>'
            f'<div class="fb">{body}</div></details>')


def load_meta_by_ticker(ev_dir, date, session):
    """按标的文件分桶：{tag: {id: (级别, 来源, 链接)}}。

    必须分桶——每个 evidence 文件的 ID 都从 dp-001 重新编号，全局 dict 会让
    后写覆盖先写，点"来源"就跳到别的标的上。
    """
    out = {}
    d = Path(ev_dir)
    if not d.is_dir():
        return out
    prefix = f"{date}_{session}_"
    for f in sorted(d.glob(prefix + "*.json")):
        try:
            ev = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        tag = f.stem[len(prefix):]
        m = {}
        for p in ev.get("data_points", []):
            if p.get("id"):
                m[p["id"]] = (p.get("evidence_level") or "P3",
                              p.get("source") or "", p.get("source_url") or "")
        for n in ev.get("news", []):
            if n.get("id"):
                m[n["id"]] = (n.get("evidence_level") or "P3",
                              n.get("source") or n.get("headline") or "",
                              n.get("url") or "")
        for cn in ev.get("chain_notes", []):
            if cn.get("id"):
                m[cn["id"]] = (cn.get("evidence_level") or "P3",
                               cn.get("source") or cn.get("sector") or "",
                               cn.get("source_url") or "")
        out[tag] = m
    return out


def pick_bucket(by_tag, code):
    """用卡片 code 首段匹配标的文件："01810 · 小米" → 01810_HK。"""
    if not by_tag:
        return {}
    head = re.split(r"[·\s]", str(code or ""))[0].strip()
    if not head:
        return {}
    if head in by_tag:
        return by_tag[head]
    for t in by_tag:
        if t.startswith(head + "_") or head in t:
            return by_tag[t]
    return {}


def chead(c, anchor):
    act = act_of(c)
    pos = parse_position(c.get("code"))
    chg = str(c.get("chg") or "")
    chg_clean = re.sub(r"^\d{1,2}/\d{1,2}\s*", "", chg).strip() or chg
    d = ""
    mm = re.search(r"[-+]?\d+(?:\.\d+)?", chg_clean)
    if mm:
        d = "fall" if float(mm.group(0)) < 0 else "rise"
    arrow = {"rise": "▲", "fall": "▼"}.get(d, "")
    sub = pos["name_tail"] or str(c.get("code") or "")
    return (f'<header class="chead">'
            f'<div class="cl"><h3 id="{anchor}">{esc(c.get("name",""))}</h3>'
            f'<span class="cc">{esc(sub)}</span></div>'
            f'<div class="cr"><span class="chg {d}">{arrow}{esc(chg_clean)}</span>'
            f'<span class="act {ACT_CLASS.get(act,"")}">{esc(act)}</span></div>'
            f'</header>')


def bull_bear(c):
    bull, bear = strip_ids(c.get("bull"))[0], strip_ids(c.get("bear"))[0]
    if not bull and not bear:
        return ""
    out = ['<div class="bb">']
    if bull:
        out.append(f'<div class="side bull"><span class="sl">多方</span><p>{esc(bull)}</p></div>')
    if bear:
        out.append(f'<div class="side bear"><span class="sl">空方</span><p>{esc(bear)}</p></div>')
    out.append("</div>")
    return "".join(out)


def risk_op(c):
    out = []
    if c.get("risk"):
        out.append(f'<div class="kv risk"><span class="kl">风控</span>'
                   f'<p>{esc(strip_ids(c["risk"])[0])}</p></div>')
    if c.get("act"):
        out.append(f'<div class="kv op"><span class="kl">操作</span>'
                   f'<p>{esc(strip_ids(c["act"])[0])}</p></div>')
    return "".join(out)


def evidence_block(all_ids, id_meta, idx):
    if not all_ids:
        return ""
    items = []
    for i in all_ids:
        lv, src, url = id_meta.get(i, ("", "", ""))
        line = f'<span class="eid">{i}</span>'
        if lv:
            line += f'<span class="elv">{esc(lv)}</span>'
        if src:
            line += f'<span class="esrc">{esc(src)}</span>'
        if url:
            line += f'<a href="{_html.escape(url, quote=True)}" target="_blank" rel="noopener">来源</a>'
        items.append(f"<li>{line}</li>")
    p4 = sum(1 for i in all_ids if id_meta.get(i, ("",))[0] == "P4")
    count = f"{len(all_ids)} 条" + (f" · {p4} 待补" if p4 else "")
    return fold("证据", "<ul class='ev'>" + "".join(items) + "</ul>", count)


def card(c, anchor, by_tag, extra=()):
    id_meta = pick_bucket(by_tag, c.get("code"))
    pos = parse_position(c.get("code"))
    act = act_of(c)
    if c.get("type") == "advisory":
        return (f'<article class="card ref"><header class="chead">'
                f'<div class="cl"><h3 id="{anchor}">{esc(c.get("name",""))}</h3>'
                f'<span class="cc">{esc(pos["name_tail"] or c.get("code",""))}</span></div></header>'
                f'<p class="note">{esc(c.get("note") or "投顾组合，无公开净值代码，按持仓金额列示，不纳入评分。")}</p>'
                f'</article>')

    body = [chead(c, anchor), data_bar(pos)]
    all_ids = []
    if c.get("concl"):
        t, ids = strip_ids(c["concl"])
        all_ids += ids
        body.append(f'<p class="concl">{esc(t)}</p>')
    body.append(bull_bear(c))
    for k in ("bull", "bear", "risk", "act"):
        all_ids += strip_ids(c.get(k))[1]
    body.append(risk_op(c))

    folds = []
    for label, key in extra:
        t, ids = strip_ids(c.get(key))
        all_ids += ids
        if t:
            folds.append(fold(label, f"<p>{esc(t)}</p>"))
    t, ids = strip_ids(c.get("fals"))
    all_ids += ids
    if t:
        folds.append(fold("证伪条件", f"<p>{esc(t)}</p>"))
    for k in ("pos", "cons", "top"):
        all_ids += strip_ids(c.get(k))[1]
    if folds or all_ids:
        body.append('<div class="folds">' + "".join(folds) + evidence_block(all_ids, id_meta, 0) + "</div>")
    return f'<article class="card act-{ACT_CLASS.get(act,"")}">' + "".join(body) + "</article>"


def wl_card(c, anchor, by_tag):
    """关注库：一行关键数据在最上，其余折叠。"""
    id_meta = pick_bucket(by_tag, c.get("code"))
    head = (f'<header class="chead"><div class="cl"><h3 id="{anchor}">{esc(c.get("name",""))}</h3>'
            f'<span class="cc">{esc(c.get("code",""))}</span></div></header>')
    bar = ('<div class="dbar">'
           + "".join(f'<div class="dcell"><span class="dk">{esc(k)}</span>'
                     f'<span class="dv">{esc(c.get(v,""))}</span></div>'
                     for k, v in (("现价", "price"), ("目标", "target"),
                                  ("计划", "qty"), ("止损", "stop")) if c.get(v))
           + "</div>")
    body = [head, bar]
    all_ids = []
    if c.get("concl"):
        t, ids = strip_ids(c["concl"])
        all_ids += ids
        body.append(f'<p class="concl">{esc(t)}</p>')
    body.append(bull_bear(c))
    body.append(risk_op(c))
    for k in ("bull", "bear", "risk", "act", "pos", "cons", "fals", "dist"):
        all_ids += strip_ids(c.get(k))[1]
    folds = []
    for label, key in (("技术面 / 位置", "pos"), ("共识与分歧", "cons"), ("证伪条件", "fals")):
        t, _ = strip_ids(c.get(key))
        if t:
            folds.append(fold(label, f"<p>{esc(t)}</p>"))
    if folds or all_ids:
        body.append('<div class="folds">' + "".join(folds) + evidence_block(all_ids, id_meta, 0) + "</div>")
    return f'<article class="card act-{ACT_CLASS.get(act_of(c),"")}">' + "".join(body) + "</article>"


EXTRA = {
    "cn": (("市场位置 / 估值", "pos"), ("共识与分歧", "cons")),
    "us": (("市场位置 / 估值", "pos"), ("共识与分歧", "cons")),
    "etf": (("跟踪结构 / 重置耗损", "top"),),
    "fund": (), "sgov": (),
}


class Anchors:
    def __init__(self):
        self.used = set()

    def make(self, c):
        raw = re.split(r"[·\s]", str(c.get("code") or c.get("name") or "card"))[0]
        base = re.sub(r"[^0-9A-Za-z]+", "-", raw).strip("-").lower() or "card"
        a, i = "c-" + base, 2
        while a in self.used:
            a = f"c-{base}-{i}"
            i += 1
        self.used.add(a)
        return a


# ---------------------------------------------------------------------------
def render(data, theme_label):
    meta = data.get("meta", {})
    by_tag = data.get("_by_tag", {})
    anc = Anchors()
    cov = meta.get("coverage", "--")

    parts = [f'<div class="page"><div class="wrap">']

    # ---- 首屏 ----
    date_txt = str(meta.get("h1", ""))
    m = re.search(r"(\d{4}-\d{2}-\d{2})\s*(周[一二三四五六日])?", date_txt)
    dstr = f"{m.group(1)} {m.group(2) or ''}".strip() if m else ""
    sess = "盘后" if "盘后" in date_txt else ("午间" if "午" in date_txt else "盘前")
    head = date_txt.replace(dstr, "").strip(" ·") or theme_label

    parts.append(f'''<header class="hero">
  <div class="hmeta"><span class="hdate">{esc(dstr)}</span>
    <span class="hdot">·</span><span class="hsess">{esc(sess)}</span>
    <span class="cov" title="机械门禁计算的字段覆盖率">覆盖 {esc(cov)}%</span></div>
  <h1>{esc(head)}</h1>''')

    regime, _ = strip_ids(data.get("regime"))
    if regime:
        # 大势判断常写 300-500 字，直接铺开会占满首屏。
        # 只露 3 行，点开看全文（纯 CSS，无 JS）。
        parts.append(f'<details class="rfold"><summary>'
                     f'<p class="regime clamp">{esc(regime)}</p>'
                     f'<span class="rmore">读全文</span></summary>'
                     f'<p class="regime full">{esc(regime)}</p></details>')

    if data.get("stats"):
        cells = []
        for s in data["stats"]:
            v, delta, d = split_stat(s.get("v"))
            k = cls_of(s.get("cls"))
            cells.append(f'<div class="stat"><div class="srow"><span class="sv {k or d}">{esc(v)}</span>'
                         + (f'<span class="sd {d or k}">{esc(delta)}</span>' if delta else "")
                         + '</div>'
                         + f'<span class="sk">{esc(s.get("k",""))}</span></div>')
        parts.append('<div class="stats">' + "".join(cells) + "</div>")

    # 今日动作横滑：全部持仓的动作，一眼看全组合
    acts = []
    for b in data.get("blocks", []):
        if b.get("kind") != "cards":
            continue
        for c in b.get("cards", []):
            if c.get("type") == "advisory":
                continue
            a = act_of(c)
            if c.get("name"):
                acts.append((esc(c["name"]), ACT_CLASS.get(a, ""), esc(a)))
    if acts:
        chips = "".join(f'<li class="a-{cl}"><b>{n}</b><span>{a}</span></li>' for n, cl, a in acts)
        parts.append(f'<div class="actionbar"><div class="ablab">今日动作</div>'
                     f'<ul class="ablist">{chips}</ul></div>')

    # 覆盖率的机器口径说明属于"资料"，不属于首屏——放到底部来源区
    note = meta.get("coverage_note", "")

    # 区块目录：手机一页约 2-3 屏，纯滚动找标的太慢
    sections = [(i, b["h2"]) for i, b in enumerate(data.get("blocks", [])) if b.get("h2")]
    if len(sections) >= 3:
        chips = "".join(f'<a href="#sec-{i}" title="{_html.escape(str(t), quote=True)}">'
                        f'{esc(short_title(t))}</a>' for i, t in sections)
        parts.append(f'<nav class="toc" aria-label="区块目录">{chips}</nav>')

    # ---- 正文 ----
    for bi, b in enumerate(data.get("blocks", [])):
        kind = b.get("kind", "card")
        if b.get("h2"):
            parts.append(f'<h2 id="sec-{bi}">{esc(b["h2"])}</h2>')

        if kind == "cards":
            for c in b.get("cards", []):
                ctype = c.get("type")
                a = anc.make(c)
                if ctype == "wl":
                    parts.append(wl_card(c, a, by_tag))
                elif ctype in EXTRA:
                    parts.append(card(c, a, by_tag, EXTRA[ctype]))
                else:
                    parts.append(card(c, a, by_tag))
        elif kind == "warn":
            ps = "".join(f"<p>{esc(strip_ids(p)[0])}</p>" for p in b.get("paras", []))
            parts.append(f'<div class="alert warn">{ps}</div>')
        elif kind == "buy":
            ps = "".join(f"<p>{esc(strip_ids(p)[0])}</p>" for p in b.get("paras", []))
            parts.append(f'<div class="alert buy">{ps}</div>')
        elif kind == "sectors":
            cells = []
            for s in b.get("items", []):
                c = re.sub(r"[^a-z]", "", str(s.get("cls", "mid")).lower()) or "mid"
                ps = "".join(f"<p>{esc(strip_ids(p)[0])}</p>" for p in s.get("paras", []))
                cells.append(f'<div class="sector s-{c}">{ps}</div>')
            parts.append('<div class="sectors">' + "".join(cells) + "</div>")
        elif kind == "table":
            rows = ['<tr><th>持仓 / 板块</th><th>动作</th><th>关键条件</th></tr>']
            for r in b.get("rows", []):
                c = re.sub(r"[^a-z]", "", str(r.get("cls", "")).lower())
                rows.append(f'<tr><td data-l="持仓/板块">{esc(r.get("pos",""))}</td>'
                            f'<td data-l="动作" class="{cls_of(c)}">{esc(r.get("act",""))}</td>'
                            f'<td data-l="关键条件">{esc(r.get("cond",""))}</td></tr>')
            parts.append('<div class="tbl"><table>' + "".join(rows) + "</table></div>")
        elif kind == "raw":
            parts.append(b.get("html", ""))
        else:
            ps = "".join(f"<p>{esc(strip_ids(p)[0])}</p>" for p in b.get("paras", []))
            if ps:
                parts.append(f'<div class="prose">{ps}</div>')

    # ---- 来源 / 页脚 ----
    src = ['<details class="fold src"><summary>数据来源与口径<em>%d 条</em></summary><div class="fb">'
           % len([s for s in data.get("sources", []) if s.get("url")])]
    if note:
        src.append(f'<p class="cnote"><b>覆盖率口径</b>：{esc(note)}</p>')
    if data.get("sources_note"):
        src.append(f'<p>{esc(data["sources_note"])}</p>')
    for i, s in enumerate([x for x in data.get("sources", []) if x.get("url")], 1):
        label = s.get("label") or s.get("url")
        src.append(f'<p>{i}. <a href="{_html.escape(s["url"], quote=True)}" '
                   f'target="_blank" rel="noopener">{esc(label)}</a></p>')
    src.append("</div></details>")
    parts.append("".join(src))

    foot = (REPO / "assets" / "disclaimer.html").read_text(encoding="utf-8").strip()
    parts.append(f'<footer class="foot">{foot}</footer>')
    parts.append("</div></div>")
    return "\n".join(parts)


def main():
    src = REPO / "data/daily-reports/post_2026-10-20_data.json"
    data = json.loads(src.read_text(encoding="utf-8"))

    ev_dir = REPO / "data/daily-reports/evidence"
    by_tag = load_meta_by_ticker(ev_dir, "2026-10-20", "post")
    data["_by_tag"] = by_tag
    total = sum(len(m) for m in by_tag.values())
    print(f"证据分桶：{len(by_tag)} 个标的 / {total} 条")

    body = render(data, "持仓日报")
    for name, title in (("a-terminal", "A · Terminal 深色"),
                        ("b-brief", "B · Brief 浅色")):
        css = (HERE / f"{name}.css").read_text(encoding="utf-8")
        dark = name.startswith("a")
        page = (f'<!doctype html><html lang="zh"><head><meta charset="utf-8">'
                f'<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
                f'<meta name="color-scheme" content="{"dark" if dark else "light"}">'
                f'<meta name="theme-color" content="{"#0a0d12" if dark else "#faf9f6"}">'
                f'<title>{title}</title><style>{css}</style></head><body>{body}</body></html>')
        out = HERE / f"{name}-preview.html"
        out.write_text(page, encoding="utf-8")
        print(f"生成 {out}  {round(len(page.encode())/1024,1)} KB")


if __name__ == "__main__":
    main()
