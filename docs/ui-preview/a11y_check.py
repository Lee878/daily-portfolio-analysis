#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WCAG 2.1 对比度校验：assets/style.css 的浅色 / 深色双主题实算。

规则：
  正文 (<18.66px 粗体 / <24px 常规)  >= 4.5:1  (AA)
  大字 (>=24px 或 >=18.66px 粗体)     >= 3.0:1  (AA Large)
  装饰性（发丝线、计数角标）            不作硬性要求，仅提示

================================================================================
【矩阵增列规则 —— 改动本文件前必读】
================================================================================
1) 每个「文字色 × 承载面」组合，只要存在真实引用路径（即该文字色可能落在
   该承载面上），即须列入 CHECKS；
   **不得按「数值相近 / 信息重复 / 看着冗余」判冗余**。

2) 为什么必须做参数空间穷举而不能手挑：同一份 CSS 里，「哪个承载面更紧」
   会随主题反转。--paper 在浅色下比 --bg 更亮（深字更难读），在深色下比
   --bg 更暗（浅字更好读），于是同一个文字色的紧侧在两套主题间左右互换：

       文字色   浅色紧侧     深色紧侧
       ink3     bg (4.61)    paper (5.88)  <-- 只测 bg 就会漏掉深色的 paper 侧
       ink      bg (16.90)   paper (14.64)
       ink2     bg (8.11)    paper (9.34)
       rise     bg (5.17)    paper (6.19)
       fall     bg (5.78)    paper (6.81)
       gold     bg (5.13)    paper (8.89)
       accent   bg (8.57)    paper (6.85)

   只测一侧 = 另一侧失守时脚本照样 exit 0。
   **单个反例不成立 != 覆盖成立**：判断「某组合是否已被别的组合覆盖」必须
   做参数空间穷举，不能拿一个反例的成败代替覆盖性证明。

3) 承载面的含义与真实引用路径（assets/style.css + scripts/run_daily.py 实测）：
     --bg        body 底色，全局承载面
     --paper     .actionbar 底色（横条），内含 .ablab / .ablist / .a-add /
                 .a-cut / .a-watch
     --warn-bg   降级横幅底色（run_daily.py 行内样式），内含 warn-fg / warn-strong
     --warn-rule 降级横幅 1px 下边框**描边色**（非文字承载面，仅作描边对照）
   --bg / --paper 上对全部文字色做**完整交叉**（10 个前景色 × 2 个承载面），
   因为页面上任何文字色都可能被放到这两个底色上，漏一格就是漏测。

4) 条件触发规则（--warn-rule 对照组）：
   告警四件套里 --warn-rule 起初在 assets/style.css 中无任何引用点（0 处），
   故当时不列 ("warn-fg", "warn-rule") 是对的。
   但 scripts/run_daily.py 的降级横幅已用 `border-bottom:1px solid var(--warn-rule)`
   作描边 —— **触发条件已成立**，故 ("warn-fg","warn-rule") 与
   ("warn-strong","warn-rule") 必须列入（实算 浅 5.70/4.61，深 6.78/6.05，均达标）。
   若将来 run_daily.py 改为不再用 var(--warn-rule) 作描边，这两组可撤；
   若改为用它承载文字（如 background:var(--warn-rule)），必须保持本组在列。

5) 完整性自检（防「删行假绿」）：CHECKS 由下面的 TEXT_FG / LINE_FG 派生，
   并与 EXPECTED_PAIRS 这份**独立枚举**逐对核对。少一对就 exit 1 并点名缺哪对 ——
   这样「从矩阵里删掉 ink3/paper 让它变绿」会当场暴露，而不是悄悄放过。

防「假绿」设计（本次改造的核心）：
  1. 变量块用花括号配对扫描提取，**不**用 split("}", 1) —— 块内嵌套花括号
     （@media / :is() 等）会被静默截错，导致变量解析不全而对比度校验假绿。
  2. 浅色与深色两块**分别实算**；任一块找不到、解析为空或变量数不足，
     一律 exit 1 —— 绝不把「解析失败」当成「没发现问题」放过。
  3. 检查矩阵引用的变量在任一主题中缺失 -> 同样 exit 1（无法验证即不通过）。
  4. 矩阵不完整（缺对 / 多对）-> exit 1（无法证明覆盖即不通过）。
  5. 注释先剥除，注释里的变量声明不参与计算，避免误计。

用法：
  python docs/ui-preview/a11y_check.py                 # 读仓库内 assets/style.css
  python docs/ui-preview/a11y_check.py path/to.css     # 指定 CSS 文件
  python docs/ui-preview/a11y_check.py --json          # 机器可读输出
"""
import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

# 脚本位于 <repo>/docs/ui-preview/，上溯三级到 repo 根（不硬编码绝对路径）
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CSS = REPO_ROOT / "assets" / "style.css"

LIGHT_SELECTOR = ":root"
DARK_SELECTOR = '[data-theme="dark"]'

MIN_VARS = 10          # 单个主题块至少应解析出的颜色变量数，低于此判为解析失败
BODY_MIN = 4.5         # 正文级门槛（WCAG AA）
LARGE_MIN = 3.0        # 大字级 / 装饰性参考门槛（WCAG AA Large）

# ----------------------------------------------------------------------
# 单一事实源：文字前景色 × 承载面
# ----------------------------------------------------------------------
# 承载面标签前缀（拼在用途前，拼出可读的「用途」列）
SURFACE_LABEL = {
    "bg": "",
    "paper": "纸面·",
    "warn-bg": "告警块·",
    "warn-rule": "告警描边·",
}

# (前景变量, 用途, 是否正文级, 可落承载面)
# 「可落承载面」按上文第 3) 条确定：
#   --bg / --paper 上做完整交叉（页面上任何文字色都可能被放到这两个底色上）
#   --warn-bg / --warn-rule 只给真正走告警四件套的告警文字色
TEXT_FG = [
    ("ink",         "正文",        True,  ("bg", "paper")),
    ("ink2",        "次级正文",     True,  ("bg", "paper")),
    ("ink3",        "辅助标签",     True,  ("bg", "paper")),
    ("ink4",        "装饰（计数）",  False, ("bg", "paper")),
    ("rise",        "涨（数值）",    True,  ("bg", "paper")),
    ("fall",        "跌（数值）",    True,  ("bg", "paper")),
    ("gold",        "提示/提醒",     True,  ("bg", "paper")),
    ("accent",      "链接",         True,  ("bg", "paper")),
    ("warn-fg",     "告警文字",     True,  ("bg", "paper", "warn-bg", "warn-rule")),
    ("warn-strong", "告警强调",     True,  ("bg", "paper", "warn-bg", "warn-rule")),
]

# 纯装饰的线色（发丝线 / 次线），不承载文字，只提示
LINE_FG = [
    ("rule",  "发丝线（装饰）", False, ("bg", "paper")),
    ("rule2", "次线（装饰）",   False, ("bg", "paper")),
]

# 独立枚举的期望组合对 —— 与派生结果交叉核对，防止「删行假绿」。
# 增删 CHECKS 时必须同步这里，否则完整性自检会 exit 1 点名缺哪对。
EXPECTED_PAIRS = frozenset({
    ("ink", "bg"), ("ink", "paper"),
    ("ink2", "bg"), ("ink2", "paper"),
    ("ink3", "bg"), ("ink3", "paper"),
    ("ink4", "bg"), ("ink4", "paper"),
    ("rise", "bg"), ("rise", "paper"),
    ("fall", "bg"), ("fall", "paper"),
    ("gold", "bg"), ("gold", "paper"),
    ("accent", "bg"), ("accent", "paper"),
    ("warn-fg", "bg"), ("warn-fg", "paper"),
    ("warn-fg", "warn-bg"), ("warn-fg", "warn-rule"),
    ("warn-strong", "bg"), ("warn-strong", "paper"),
    ("warn-strong", "warn-bg"), ("warn-strong", "warn-rule"),
    ("rule", "bg"), ("rule", "paper"),
    ("rule2", "bg"), ("rule2", "paper"),
})


def build_checks():
    """由 TEXT_FG / LINE_FG 派生 (前景, 背景, 用途, 是否正文级) 检查表。"""
    checks = []
    for fg, use, is_body, surfaces in TEXT_FG + LINE_FG:
        for bg in surfaces:
            checks.append((fg, bg, SURFACE_LABEL.get(bg, "") + use, is_body))
    return checks


CHECKS = build_checks()


def lum(hexcolor):
    hexcolor = hexcolor.lstrip("#")
    if len(hexcolor) == 3:
        hexcolor = "".join(c * 2 for c in hexcolor)
    r, g, b = (int(hexcolor[i:i + 2], 16) / 255 for i in (0, 2, 4))
    def f(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def ratio(a, b):
    l1, l2 = lum(a), lum(b)
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


# --------------------------------------------------------------------------
# CSS 解析
# --------------------------------------------------------------------------
def strip_comments(txt):
    """剥除 CSS 注释（尊重字符串字面量），注释里的变量声明不参与计算。"""
    out = []
    i, n = 0, len(txt)
    while i < n:
        ch = txt[i]
        if ch in "\"'":
            quote = ch
            out.append(ch)
            i += 1
            while i < n:
                out.append(txt[i])
                if txt[i] == "\\":
                    if i + 1 < n:
                        out.append(txt[i + 1])
                        i += 2
                        continue
                elif txt[i] == quote:
                    i += 1
                    break
                i += 1
            continue
        if ch == "/" and i + 1 < n and txt[i + 1] == "*":
            end = txt.find("*/", i + 2)
            i = n if end < 0 else end + 2
            out.append(" ")
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def extract_block(txt, selector):
    """按 selector 定位 CSS 块，用花括号配对扫描返回块内完整内容。

    不能用 split("}", 1) —— 块内嵌套花括号会被截错。
    花括号不配对（文件被截断）时返回 ""，交由调用方按解析失败处理。
    """
    blocks = extract_all_blocks(txt, selector)
    return blocks[0] if blocks else ""


def extract_all_blocks(txt, selector):
    """返回该 selector 命中的所有块的完整内容（同一选择器可多次定义）。"""
    blocks = []
    pattern = re.compile(re.escape(selector) + r"\s*\{")
    pos = 0
    while True:
        m = pattern.search(txt, pos)
        if not m:
            break
        i = m.end()          # 指向匹配到的 '{' 之后
        depth = 1
        out = []
        n = len(txt)
        closed = False
        while i < n:
            ch = txt[i]
            if ch == "{":
                depth += 1
                out.append(ch)
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    closed = True
                    i += 1
                    break
                out.append(ch)
            else:
                out.append(ch)
            i += 1
        if not closed:
            # 花括号不配对：视为解析失败，不返回半截内容
            return []
        blocks.append("".join(out))
        pos = i
    return blocks


def vars_from_block(block):
    """从块内容解析出颜色变量（仅 hex 颜色值；字体族等非颜色变量不计）。

    只认 3 位与 6 位 hex —— 4/5/7/8 位（含 #rgba / #rrggbbaa）不是本脚本
    判定体系内的色值，一律不收，避免下游 lum() 按错误长度取值而崩溃。
    """
    return dict(re.findall(
        r"--([\w-]+)\s*:\s*(#[0-9a-fA-F]{6}(?![0-9a-fA-F])|#[0-9a-fA-F]{3}(?![0-9a-fA-F]))",
        block))


def theme_vars(txt, selector):
    """返回 (变量字典, 命中块数)；未命中返回 ({}, 0)。"""
    blocks = extract_all_blocks(txt, selector)
    if not blocks:
        return {}, 0
    merged = {}
    for b in blocks:
        merged.update(vars_from_block(b))
    return merged, len(blocks)


# --------------------------------------------------------------------------
# 表格排版（中文全角对齐）
# --------------------------------------------------------------------------
def _dw(s):
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def _pad(s, width):
    return s + " " * max(1, width - _dw(s))


def _rpad(s, width):
    return " " * max(1, width - _dw(s)) + s


# --------------------------------------------------------------------------
# 检查
# --------------------------------------------------------------------------
def run_theme(label, selector, v, out_lines):
    """跑一套主题的比值表，返回 (失败项列表, 行数据)。"""
    lines = out_lines
    lines.append("")
    lines.append("=" * 78)
    lines.append(f"{label}主题（选择器 {selector}｜解析到 {len(v)} 个颜色变量）")
    lines.append("=" * 78)
    lines.append(_pad("用途", 22) + _pad("前景", 14) + _pad("背景", 12)
                 + _rpad("比值", 8) + "  " + _pad("级别", 6) + "判定")
    lines.append("-" * 78)

    bad = []
    rows = []
    for fg, bg, use, is_body in CHECKS:
        if fg not in v or bg not in v:
            missing = [x for x in (fg, bg) if x not in v]
            lines.append(_pad(use, 22) + _pad("缺变量 " + "/".join(missing), 46)
                         + _rpad("-", 8) + "  " + _pad("—", 6) + "✗ 变量缺失")
            bad.append({"use": use, "fg": fg, "bg": bg, "ratio": None,
                        "reason": "变量缺失: " + "/".join(missing)})
            rows.append({"use": use, "fg": fg, "bg": bg, "fg_value": v.get(fg),
                         "bg_value": v.get(bg), "ratio": None, "body": is_body,
                         "verdict": "变量缺失"})
            continue
        r = ratio(v[fg], v[bg])
        if is_body:
            if r >= BODY_MIN:
                mark, verdict = "✓", "AA 正文"
            elif r >= LARGE_MIN:
                mark, verdict = "✗", "仅达大字级，未过 AA 正文"
            else:
                mark, verdict = "✗", "不达标"
        else:
            if r >= LARGE_MIN:
                mark, verdict = "✓", "装饰 OK"
            else:
                mark, verdict = "·", "装饰（不阻塞）"
        lines.append(_pad(use, 22)
                     + _pad(f"{fg} {v[fg]}", 14)
                     + _pad(f"{bg} {v[bg]}", 12)
                     + _rpad(f"{r:.2f}", 8) + "  "
                     + _pad("正文" if is_body else "装饰", 6)
                     + f"{mark} {verdict}")
        if is_body and r < BODY_MIN:
            bad.append({"use": use, "fg": fg, "bg": bg, "ratio": round(r, 2),
                        "reason": f"{r:.2f} < {BODY_MIN}"})
        rows.append({"use": use, "fg": fg, "bg": bg, "fg_value": v[fg],
                     "bg_value": v[bg], "ratio": round(r, 4), "body": is_body,
                     "verdict": verdict})
    return bad, rows


def check_matrix_complete():
    """矩阵完整性自检：派生结果必须与独立枚举 EXPECTED_PAIRS 逐对相等。

    防的是「从矩阵里删掉一组让它变绿」—— 删了就当场 exit 1 并点名缺哪对。
    """
    actual = frozenset((fg, bg) for fg, bg, _use, _body in CHECKS)
    missing = sorted(EXPECTED_PAIRS - actual)
    extra = sorted(actual - EXPECTED_PAIRS)
    if not missing and not extra:
        return None
    msgs = []
    if missing:
        msgs.append("矩阵缺少组合对："
                    + "、".join(f"{fg} on {bg}" for fg, bg in missing))
    if extra:
        msgs.append("矩阵存在未登记的组合对："
                    + "、".join(f"{fg} on {bg}" for fg, bg in extra))
    return "；".join(msgs)


def parse_args(argv):
    ap = argparse.ArgumentParser(
        description="WCAG 对比度校验：assets/style.css 浅色 / 深色双主题实算")
    ap.add_argument("css", nargs="?", default=str(DEFAULT_CSS),
                    help="CSS 文件路径（默认 <repo>/assets/style.css）")
    ap.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    # 1) 矩阵完整性自检（先于任何取值 —— 覆盖性无法证明时不得开始校验）
    incomplete = check_matrix_complete()
    if incomplete:
        print(f"❌ 对比度检查矩阵不完整：{incomplete}")
        print("   矩阵缺项即无法证明覆盖完整，必须补齐后再校验（不得靠删行放行）。")
        return 1

    css_path = Path(args.css).resolve()
    if not css_path.is_file():
        print(f"❌ CSS 文件不存在：{css_path}")
        return 1

    try:
        raw = css_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"❌ 读取 CSS 失败：{css_path}（{exc}）")
        return 1
    txt = strip_comments(raw)

    themes = []
    for label, selector in (("浅色", LIGHT_SELECTOR), ("深色", DARK_SELECTOR)):
        v, nblocks = theme_vars(txt, selector)
        if nblocks == 0:
            print(f"❌ {label}主题变量块解析失败：在 {css_path} 中找不到选择器 {selector}")
            return 1
        if len(v) < MIN_VARS:
            print(f"❌ {label}主题变量块解析失败，只解析到 {len(v)} 个变量"
                  f"（要求 ≥ {MIN_VARS}）")
            return 1
        themes.append((label, selector, v))

    out_lines = []
    out_lines.append(f"WCAG 2.1 对比度实算｜{css_path}")
    out_lines.append(f"检查矩阵 {len(CHECKS)} 组（正文级 {sum(1 for c in CHECKS if c[3])} + "
                     f"装饰级 {sum(1 for c in CHECKS if not c[3])}）× 2 主题 = "
                     f"{len(CHECKS) * 2} 行")
    all_bad = []
    all_rows = {}
    for label, selector, v in themes:
        bad, rows = run_theme(label, selector, v, out_lines)
        all_bad.extend(bad)
        all_rows[label] = rows

    # 每套主题的最小余量（最紧的一对）
    for label, _sel, _v in themes:
        body_rows = [r for r in all_rows[label] if r["body"] and r["ratio"] is not None]
        if body_rows:
            tight = min(body_rows, key=lambda r: r["ratio"])
            out_lines.append(f"  └ {label}最紧正文级：{tight['use']}"
                             f"（{tight['fg']} on {tight['bg']}）= {tight['ratio']:.2f}:1"
                             f"（余量 {tight['ratio'] - BODY_MIN:+.2f}）")

    if args.json:
        # JSON 模式下 stdout 只出 JSON，人类可读摘要不污染机器可读输出
        print(json.dumps({
            "css": str(css_path),
            "matrix_size": len(CHECKS),
            "themes": all_rows,
            "failures": all_bad,
            "ok": not all_bad,
        }, ensure_ascii=False, indent=2))
        return 1 if all_bad else 0

    for ln in out_lines:
        print(ln)

    print("")
    print("=" * 78)
    if all_bad:
        print(f"未通过项（共 {len(all_bad)} 项）：")
        for item in all_bad:
            if item["ratio"] is None:
                print(f"  ✗ {item['use']}: {item['fg']} on {item['bg']} —— {item['reason']}")
            else:
                print(f"  ✗ {item['use']}: {item['fg']} on {item['bg']} = "
                      f"{item['ratio']}:1（{item['reason']}）")
        print("对比度校验未通过 —— WCAG AA 不达标")
        return 1

    print("全部正文级组合 ≥ 4.5:1 —— WCAG AA 通过（浅色 + 深色双主题）")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # pragma: no cover - 老版本 Python 无 reconfigure
        pass
    sys.exit(main())
