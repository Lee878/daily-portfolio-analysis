#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通用报告渲染器（数据驱动，手机优先）—— v2.7.0 Brief 版式

agent 只产出一份紧凑 data.json，本脚本读 assets/style.css / disclaimer.html，
套固化骨架出单文件 HTML。相比 v2.4 的深色卡片版式，本版解决四件实事：

1. **证据不再内联成灰底方块**
   正文里的 `[dp-001]` 换成上标序号 ¹，明细收进卡底"证据"折叠。
   方括号原文并没丢——它移进了所在元素的 `data-ev` 属性，门禁按源码
   正则计数/判多空不同源，肉眼干净，机器照样查得动。

2. **浮动盈亏由脚本算**
   持仓串里的"成本/现价/股数"过去埋在 13px 灰字里且从不计算，
   现在解析成数据显示条，自动算浮盈百分比。

3. **首屏压到必要信息**
   大势段默认 3 行 + 读全文；覆盖率的机器口径说明移到页脚"来源与口径"；
   新增今日动作横滑条与区块目录（原报告 24 屏无任何导航）。

4. **证据按标的分桶**
   每个 evidence 文件的 ID 都从 dp-001 重新编号，旧版用全局 dict 装，
   后写覆盖先写 → 点"来源"跳到别的标的。现按 ticker 分桶。

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

# 旧 token → 语义 token（历史 data.json 零迁移）
CLS_MAP = {"g": "rise", "r": "fall", "tg": "rise", "tr": "fall"}

ACT_CLASS = {"加": "add", "减": "cut", "持有": "hold", "观察": "watch", "关注": "watch"}

# 渲染上下文（证据元信息 / 锚点去重），由 render() 注入
_CTX = {"id_meta": {}, "by_ticker": {}, "anchors": None}


def esc(text):
    """转义 HTML 但保留白名单标签（正文含 < 时不破版）。"""
    s = _html.escape(str(text if text is not None else ""), quote=False)
    for tag in _ALLOWED:
        s = s.replace(f"&lt;{tag}&gt;", f"<{tag}>")
        s = s.replace(f"&lt;/{tag}&gt;", f"</{tag}>")
    s = s.replace("&lt;br&gt;", "<br>").replace("&lt;br /&gt;", "<br>") \
         .replace("&lt;br/&gt;", "<br>")
    return s


def cls(value, default=""):
    """把旧/新颜色 token 统一成语义 token。"""
    v = (value or default or "").strip()
    return CLS_MAP.get(v, v)


def plain(text):
    """去标签取纯文本。"""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", str(text or ""))).strip()


def short_title(t):
    """目录 chip 只留主标题："跨报告对账（核销 10/17）" → "跨报告对账"。"""
    s = re.sub(r"[（(][^)）]*[)）]", "", str(t or "")).strip(" ·|—-")
    return s or str(t or "")


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


# ---------------------------------------------------------------------------
# 证据：脚注编号 + 门禁可见性
# ---------------------------------------------------------------------------
class EvIndex:
    """一张卡片的证据脚注表。

    编号按"字段展示顺序首现"分配，因此正文上标序号与卡底清单顺序天然一致。
    """

    def __init__(self, fields):
        self.n = {}
        for t in fields:
            for m in ID_RE.finditer(str(t or "")):
                i = m.group(0)[1:-1]
                if i not in self.n:
                    self.n[i] = len(self.n) + 1

    def mark(self, text):
        """把正文里的 [dp-001] 换成上标序号，返回 (html, 命中的 ID 列表)。

        命中列表保留重复次数——门禁既数"唯一几个"也数"引用几次"，
        去重会让后者的计数凭空变少。
        """
        hits = []

        def rep(m):
            i = m.group(0)[1:-1]
            hits.append(i)
            return f'<sup class="evm">{self.n.get(i, "?")}</sup>'

        return ID_RE.sub(rep, esc(text)), hits


def data_ev(ids):
    """把 ID 列表写成 data-ev 属性：门禁读源码据此计数，肉眼看不到方括号。"""
    if not ids:
        return ""
    return ' data-ev="' + " ".join(f"[{i}]" for i in ids) + '"'


def load_id_meta(evidence_dir, date, session):
    """从 evidence/*.json 建 ID → (级别, 来源, 链接)。

    注意：各标的文件的 ID 各自从 dp-001 起编号，全局合并会互相覆盖。
    此函数仅作兜底，卡片渲染优先用 load_id_meta_by_ticker 的分桶结果。
    """
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


def load_id_meta_by_ticker(evidence_dir, date, session):
    """按标的文件分桶：{tag(如 601899_SH): {id: (级别, 来源, 链接)}}。

    必须分桶——全局 dict 会让后写覆盖先写，点"来源"跳到别的标的上。
    """
    out = {}
    if not evidence_dir:
        return out
    d = Path(evidence_dir)
    if not d.is_dir():
        return out
    prefix = f"{date}_{session}_"
    for f in sorted(d.glob(prefix + "*.json")):
        try:
            ev = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
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
        out[f.stem[len(prefix):]] = m
    return out


def pick_bucket(by_ticker, code):
    """用卡片 code 首段匹配标的文件："601899.SH · 紫金" → 601899_SH。"""
    if not by_ticker:
        return {}
    head = re.split(r"[·\s]", str(code or ""))[0].strip().rstrip(".")
    if not head:
        return {}
    key = head.replace(".", "_")
    if key in by_ticker:
        return by_ticker[key]
    if head in by_ticker:
        return by_ticker[head]
    for t in by_ticker:
        if t.startswith(key + "_") or t.startswith(head):
            return by_ticker[t]
    return {}


# ---------------------------------------------------------------------------
# 持仓解读：成本 / 现价 / 浮动盈亏（脚本算，不靠模型口算）
# ---------------------------------------------------------------------------
def parse_position(code):
    """从 code 串抠出仓位信息："GOOG · 28股 成本357.577 · 现价340.16"。"""
    s = str(code or "")
    out = {"tail": "", "shares": "", "cost": "", "last": "", "pnl": "", "pnl_cls": ""}
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
    rest = s
    for p in (r"·?\s*成本\s*[\d,\.]+", r"·?\s*现价\s*[\d,\.]+", r"·?\s*\d+\s*股"):
        rest = re.sub(p, "", rest)
    out["tail"] = rest.strip(" ·")
    return out


def data_bar(pairs):
    pairs = [(k, v, c) for k, v, c in pairs if v not in (None, "")]
    if not pairs:
        return ""
    cells = "".join(
        f'<div class="dcell"><span class="dk">{esc(k)}</span>'
        f'<span class="dv {c}">{esc(v)}</span></div>' for k, v, c in pairs)
    return f'<div class="dbar">{cells}</div>'


def position_bar(pos):
    cells = []
    if pos["cost"]:
        cells.append(("成本", pos["cost"], ""))
    if pos["last"]:
        cells.append(("现价", pos["last"], ""))
    if pos["pnl"]:
        cells.append(("浮动", pos["pnl"], pos["pnl_cls"]))
    elif pos["shares"]:
        cells.append(("持仓", f"{pos['shares']} 股", ""))
    return data_bar(cells)


def split_stat(v):
    """'7690.73 +0.41%' → ('7690.73','+0.41%','rise')
       '约4115 连跌3日' → ('约4115','连跌3日','fall')
       数值与状态词分开，窄屏才不会被挤断行。"""
    s = str(v or "").strip()
    m = re.match(r"^(.+?)\s*([+-]\d+(?:\.\d+)?%)\s*$", s)
    if m:
        d = "fall" if m.group(2).startswith("-") else "rise"
        return m.group(1), m.group(2), d
    m = re.match(r"^(约?[\d,]+(?:\.\d+)?)\s*(?=[^\d.,])(.+)$", s)
    if m:
        tail = m.group(2)
        d = "fall" if "跌" in tail else ("rise" if "涨" in tail else "")
        return m.group(1), tail, d
    return s, "", ""


def chg_dir(chg):
    m = re.search(r"[-+]?\d+(?:\.\d+)?", str(chg or ""))
    if not m:
        return ""
    try:
        return "fall" if float(m.group(0)) < 0 else "rise"
    except ValueError:
        return ""


# ---------------------------------------------------------------------------
# 固化组件
# ---------------------------------------------------------------------------
def fold(label, body_html, count=""):
    if not body_html:
        return ""
    tag = f"<em>{esc(count)}</em>" if count else ""
    return (f'<details class="fold"><summary>{esc(label)}{tag}</summary>'
            f'<div class="fb">{body_html}</div></details>')


def chead(c, anchor, pos):
    act = act_of(c)
    chg = str(c.get("chg") or "")
    chg_clean = re.sub(r"^\d{1,2}/\d{1,2}\s*", "", chg).strip() or chg
    d = chg_dir(chg_clean)
    arrow = {"rise": "▲", "fall": "▼"}.get(d, "")
    sub = pos["tail"] or str(c.get("code") or "")
    return ('<div class="chead"><div class="cl">'
            f'<h3 id="{anchor}">{esc(c.get("name", ""))}</h3>'
            f'<span class="cc">{esc(sub)}</span></div>'
            f'<div class="cr"><span class="chg {d}">{arrow}{esc(chg_clean)}</span>'
            f'<span class="act {ACT_CLASS.get(act, "")}">{esc(act)}</span></div></div>')


def _side(label, key, text, idx, used):
    """多空一行。data-ev 把该行引用的 ID 留在源码里，多空不同源由此判定。"""
    html_text, hits = idx.mark(text)
    used.extend(hits)
    return (f'<div class="side {key}"{data_ev(hits)}>'
            f'<span class="sl">{label}</span><p>{html_text}</p></div>')


def bull_bear(c, idx, used):
    bull, bear = str(c.get("bull") or ""), str(c.get("bear") or "")
    if not bull and not bear:
        return ""
    out = ['<div class="bb">']
    if bull:
        out.append(_side("多方", "bull", bull, idx, used))
    if bear:
        out.append(_side("空方", "bear", bear, idx, used))
    out.append("</div>")
    # 多空必须各占一行：门禁按行取 ID，同行会让两边拿到同一批 ID
    return "\n".join(out)


def risk_op(c, idx, used):
    out = []
    for key, label, field in (("risk", "风控", "risk"), ("op", "操作", "act")):
        text = str(c.get(field) or "")
        if not text:
            continue
        html_text, hits = idx.mark(text)
        used.extend(hits)
        out.append(f'<div class="kv {key}"{data_ev(hits)}>'
                   f'<span class="kl">{label}</span><p>{html_text}</p></div>')
    return "".join(out)


def evidence_block(idx, id_meta):
    """卡底证据清单：上标序号 → 编号 / 级别 / 来源 / 可点链接。"""
    if not idx.n:
        return ""
    items, p4 = [], 0
    for i in sorted(idx.n, key=idx.n.get):
        lv, src, url = id_meta.get(i, ("", "", ""))
        if lv == "P4":
            p4 += 1
        line = (f'<span class="enum">{idx.n[i]}</span>'
                f'<span class="eid">{esc(i)}</span>')
        if lv:
            line += f'<span class="elv">{esc(lv)}</span>'
        if src:
            line += f'<span class="esrc">{esc(src)}</span>'
        if url:
            line += (f'<a href="{_html.escape(url, quote=True)}" '
                     f'target="_blank" rel="noopener">来源</a>')
        items.append(f"<li>{line}</li>")
    count = f"{len(idx.n)} 条" + (f" · {p4} 待补" if p4 else "")
    return fold("证据", "<ul class='ev'>" + "".join(items) + "</ul>", count)


# ---------------------------------------------------------------------------
# 卡片
# ---------------------------------------------------------------------------
EXTRA_FIELDS = {
    "cn": (("市场位置 / 估值", "pos"), ("共识与分歧", "cons")),
    "us": (("市场位置 / 估值", "pos"), ("共识与分歧", "cons")),
    "etf": (("跟踪结构 / 每日重置耗损", "top"),),
}


def _card_fields(c, extra):
    keys = ["concl", "bull", "bear", "risk", "act"]
    keys += [k for _, k in extra]
    keys += ["fals"]
    return [str(c.get(k) or "") for k in keys]


def _card(c, anchor, extra=()):
    pos = parse_position(c.get("code"))
    idx = EvIndex(_card_fields(c, extra) + [str(c.get("dist") or "")])
    id_meta = pick_bucket(_CTX["by_ticker"], c.get("code")) or _CTX["id_meta"]
    used = []

    body = [chead(c, anchor, pos), position_bar(pos)]

    if c.get("concl"):
        text, hits = idx.mark(c["concl"])
        used.extend(hits)
        body.append(f'<p class="concl"{data_ev(hits)}>{text}</p>')

    body.append(bull_bear(c, idx, used))
    body.append(risk_op(c, idx, used))

    folds = []
    for label, key in extra:
        if c.get(key):
            text, hits = idx.mark(c[key])
            used.extend(hits)
            folds.append(fold(label, f"<p{data_ev(hits)}>{text}</p>"))
    if c.get("fals"):
        text, hits = idx.mark(c["fals"])
        used.extend(hits)
        folds.append(fold("证伪条件", f"<p{data_ev(hits)}>{text}</p>"))

    left = [i for i in idx.n if i not in set(used)]
    if folds or idx.n:
        # 未渲染字段里若也带 ID，兜底挂在这个容器行上（不可挂到 <div class="card">：
        # 门禁按 `<div class="card[^"]*">` 认卡片起点，多一个属性就匹配不上，
        # 会让后续卡片被并入前一张卡区间，把别家标的的证据算到这张卡上）。
        line_cls = ' class="folds"' + data_ev(left) if left else ' class="folds"'
        body.append(f'<div{line_cls}>' + "\n".join(folds)
                    + evidence_block(idx, id_meta) + "</div>")

    act = act_of(c)
    cls_act = ACT_CLASS.get(act, "")
    cls_str = f' class="card {cls_act}"' if cls_act else ' class="card"'
    # 每个论点元素独占一行：门禁按"行"取 ID 判定多空是否各引独立来源，
    # 拼成一行会让多空拿到同一批 ID，直接判失败。
    return f'<div{cls_str}>' + "\n".join(body) + "</div>"


def cn_card(c):
    return _card(c, _CTX["anchors"].make(c), EXTRA_FIELDS["cn"])


def us_card(c):
    return _card(c, _CTX["anchors"].make(c), EXTRA_FIELDS["us"])


def etf_card(c):
    return _card(c, _CTX["anchors"].make(c), EXTRA_FIELDS["etf"])


def fund_card(c):
    return _card(c, _CTX["anchors"].make(c))


def sgov_card(c):
    return _card(c, _CTX["anchors"].make(c))


def advisory_card(c):
    anchor = _CTX["anchors"].make(c)
    note = c.get("note") or "该标的为投顾组合、无公开净值代码，按持仓金额列示，不做个券四层分析、不纳入评分。"
    pos = parse_position(c.get("code"))
    return ('<div class="card ref"><div class="chead"><div class="cl">'
            f'<h3 id="{anchor}">{esc(c.get("name", ""))}</h3>'
            f'<span class="cc">{esc(pos["tail"] or c.get("code", ""))}</span></div>'
            f'<div class="cr"><span class="act hold">列示</span></div></div>'
            f'<p class="note">{esc(note)}</p></div>')


def wl_card(c):
    """关注库：现价/目标/计划/止损做成数据条，其余折叠。"""
    anchor = _CTX["anchors"].make(c)
    extra = (("技术面 / 位置", "pos"), ("共识与分歧", "cons"), ("证伪条件", "fals"))
    idx = EvIndex(_card_fields(c, extra) + [str(c.get("dist") or "")])
    id_meta = pick_bucket(_CTX["by_ticker"], c.get("code")) or _CTX["id_meta"]
    used = []

    head = ('<div class="chead"><div class="cl">'
            f'<h3 id="{anchor}">{esc(c.get("name", ""))}</h3>'
            f'<span class="cc">{esc(c.get("code", ""))}</span></div>'
            f'<div class="cr"><span class="act {ACT_CLASS.get(act_of(c), "")}">'
            f'{esc(act_of(c))}</span></div></div>')
    bar = data_bar([("现价", c.get("price"), ""), ("目标", c.get("target"), ""),
                    ("计划", c.get("qty"), ""), ("止损", c.get("stop"), "")])
    body = [head, bar]

    if c.get("concl"):
        text, hits = idx.mark(c["concl"])
        used.extend(hits)
        body.append(f'<p class="concl"{data_ev(hits)}>{text}</p>')
    body.append(bull_bear(c, idx, used))
    body.append(risk_op(c, idx, used))

    folds = []
    for label, key in extra:
        if c.get(key):
            text, hits = idx.mark(c[key])
            used.extend(hits)
            folds.append(fold(label, f"<p{data_ev(hits)}>{text}</p>"))
    left = [i for i in idx.n if i not in set(used)]
    if folds or idx.n:
        line_cls = ' class="folds"' + data_ev(left) if left else ' class="folds"'
        body.append(f'<div{line_cls}>' + "\n".join(folds)
                    + evidence_block(idx, id_meta) + "</div>")

    cls_act = ACT_CLASS.get(act_of(c), "")
    cls_str = f' class="card {cls_act}"' if cls_act else ' class="card"'
    return f'<div{cls_str}>' + "\n".join(body) + "</div>"


CARD_FN = {
    "cn": cn_card, "us": us_card, "etf": etf_card, "fund": fund_card,
    "wl": wl_card, "sgov": sgov_card, "advisory": advisory_card,
}


# ---------------------------------------------------------------------------
# 区块渲染
# ---------------------------------------------------------------------------
def render_paras(paras):
    return "".join(f"<p>{esc(p)}</p>" for p in paras)


def render_block(b):
    kind = b.get("kind", "card")
    if kind == "warn":
        return f'<div class="alert warn">{render_paras(b.get("paras", []))}</div>'
    if kind == "buy":
        return f'<div class="alert buy">{render_paras(b.get("paras", []))}</div>'
    if kind == "sectors":
        out = []
        for s in b.get("items", []):
            c = re.sub(r"[^a-z]", "", str(s.get("cls", "mid")).lower()) or "mid"
            out.append(f'<div class="card sector s-{c}">'
                       f'{render_paras(s.get("paras", []))}</div>')
        return "\n".join(out)
    if kind == "cards":
        out = []
        for c in b.get("cards", []):
            fn = CARD_FN.get(c.get("type"))
            if fn:
                out.append(fn(c))
        return "\n".join(out)
    if kind == "table":
        rows = ["<tr><th>持仓 / 板块</th><th>动作</th><th>关键条件</th></tr>"]
        for r in b.get("rows", []):
            rows.append(f'<tr><td data-l="持仓 / 板块">{esc(r.get("pos", ""))}</td>'
                        f'<td data-l="动作" class="{cls(r.get("cls"))}">{esc(r.get("act", ""))}</td>'
                        f'<td data-l="关键条件">{esc(r.get("cond", ""))}</td></tr>')
        return '<div class="tbl"><table>' + "".join(rows) + "</table></div>"
    if kind == "raw":
        return b.get("html", "")
    return f'<div class="prose">{render_paras(b.get("paras", []))}</div>'


def collect_actions(data):
    """今日动作条：把全部持仓的动作横滑排开，一眼看全组合。"""
    out = []
    for b in data.get("blocks", []):
        if b.get("kind") != "cards":
            continue
        for c in b.get("cards", []):
            if c.get("type") == "advisory" or not c.get("name"):
                continue
            act = act_of(c)
            out.append((plain(c["name"]), ACT_CLASS.get(act, ""), act))
    return out


def render(data, css):
    meta = data.get("meta", {})
    _CTX["id_meta"] = data.get("_id_meta", {})
    _CTX["by_ticker"] = data.get("_id_meta_by_ticker", {})
    _CTX["anchors"] = Anchors()

    # 覆盖率：整数百分比（门禁正则只认整数，run_daily 还会机械校准）
    try:
        cov = int(round(float(meta.get("coverage", "0"))))
    except (TypeError, ValueError):
        cov = _html.escape(str(meta.get("coverage", "--")))

    parts = ['<!doctype html><html lang="zh"><head><meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">',
             '<meta name="color-scheme" content="light">',
             '<meta name="theme-color" content="#faf9f6">',
             f"<title>{_html.escape(str(meta.get('title', '报告')))}</title>",
             f"<style>{css}</style></head><body><div class=\"wrap\">"]

    # ---- 报头 ----
    date_txt = str(meta.get("h1", ""))
    m = re.search(r"(\d{4}-\d{2}-\d{2})\s*(周[一二三四五六日])?", date_txt)
    dstr = f"{m.group(1)} {m.group(2) or ''}".strip() if m else ""
    sess = "盘后" if "盘后" in date_txt else ("午间" if "午" in date_txt else "盘前")
    head = date_txt.replace(dstr, "").strip(" ·") or "持仓日报"

    parts.append(f'<header class="hero"><div class="hmeta">'
                 f'<span class="hdate">{esc(dstr)}</span>'
                 f'<span class="hdot">·</span><span>{esc(sess)}</span>'
                 f'<span class="cov" title="机械门禁计算的字段覆盖率">覆盖 {cov}%</span>'
                 f'</div><h1>{esc(head)}</h1>')

    # 大势段常写三四百字，铺开会占满首屏：默认 3 行 + 读全文。
    # 这里的证据引用保留原始 [nw-001]（由 run_daily 兜底包成静默上标）：
    # 脚注序号只在卡片内有对应清单，段落里编号会指向不存在的条目。
    if data.get("regime"):
        text = esc(data["regime"])
        parts.append(f'<details class="rfold"><summary>'
                     f'<p class="regime clamp">{text}</p>'
                     f'<span class="rmore">读全文</span></summary>'
                     f'<p class="regime full">{text}</p></details>')
    parts.append("</header>")

    if data.get("stats"):
        cells = []
        for s in data["stats"]:
            v, delta, d = split_stat(s.get("v"))
            k = cls(s.get("cls"))
            # 只有"带百分比的涨跌幅"才给数值染色；"约4115 连跌3日"这类状态词
            # 若也染绿，金价本身会被读成"跌"，语义就错了。
            v_cls = k or (d if delta.endswith("%") else "")
            cells.append(f'<div class="stat"><div class="srow">'
                         f'<span class="sv {v_cls}">{esc(v)}</span>'
                         + (f'<span class="sd {d or k}">{esc(delta)}</span>' if delta else "")
                         + f'</div><span class="sk">{esc(s.get("k", ""))}</span></div>')
        parts.append('<div class="stats">' + "".join(cells) + "</div>")

    actions = collect_actions(data)
    if actions:
        chips = "".join(f'<li class="a-{c}"><b>{esc(n)}</b><span>{esc(a)}</span></li>'
                        for n, c, a in actions)
        parts.append('<div class="actionbar"><div class="ablab">今日动作</div>'
                     f'<ul class="ablist">{chips}</ul></div>')

    # 区块目录：整份报告二十来屏，没有导航就得硬滑
    sections = [(i, b["h2"]) for i, b in enumerate(data.get("blocks", [])) if b.get("h2")]
    if len(sections) >= 3:
        chips = "".join(f'<a href="#sec-{i}" title="{_html.escape(str(t), quote=True)}">'
                        f'{esc(short_title(t))}</a>' for i, t in sections)
        parts.append(f'<nav class="toc" aria-label="区块目录">{chips}</nav>')

    for bi, b in enumerate(data.get("blocks", [])):
        if b.get("h2"):
            parts.append(f'<h2 id="sec-{bi}">{esc(b["h2"])}</h2>')
        parts.append(render_block(b))

    # ---- 来源与口径 ----
    # 覆盖率机器口径说明属于"资料"，放这里而不是首屏；
    # "数据覆盖率 X%" 字面必须保留，run_daily 依此锚点做机械校准。
    src = ['<details class="fold src"><summary>数据来源与口径'
           f'<em>{len([s for s in data.get("sources", []) if s.get("url")])} 条</em>'
           '</summary><div class="fb">']
    src.append(f'<p class="cnote"><b>数据覆盖率 {cov}%</b> · 机械门禁计算：'
               f'{esc(meta.get("coverage_note", ""))}</p>')
    if data.get("sources_note"):
        src.append(f"<p>{esc(data['sources_note'])}</p>")
    for i, s in enumerate([x for x in data.get("sources", []) if x.get("url")], 1):
        label = s.get("label") or s.get("url")
        src.append(f'<p>{i}. <a href="{_html.escape(s["url"], quote=True)}" '
                   f'target="_blank" rel="noopener">{esc(label)}</a></p>')
    src.append("</div></details>")
    parts.append("".join(src))

    parts.append(f'<footer class="foot">'
                 f'{(ASSETS / "disclaimer.html").read_text(encoding="utf-8").strip()}'
                 f'</footer>')
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
        data["_id_meta_by_ticker"] = load_id_meta_by_ticker(
            args.evidence_dir, args.date, args.session)
    css = (ASSETS / "style.css").read_text(encoding="utf-8")
    Path(args.out).write_text(render(data, css), encoding="utf-8")
    if args.recon_out:
        write_recon_summary(data, args.recon_out)
    print("rendered:", args.out)


if __name__ == "__main__":
    main()
