#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WCAG 2.1 对比度校验：A/B 两套主题的文字色 × 背景色全组合实算。

规则：
  正文 (<18.66px 粗体 / <24px 常规)  ≥ 4.5:1  (AA)
  大字 (≥24px 或 ≥18.66px 粗体)     ≥ 3.0:1  (AA Large)
  装饰性（纯图标、计数）              不作要求，但 ≥3.0 更稳
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


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


def vars_of(css_path):
    txt = css_path.read_text(encoding="utf-8")
    head = txt.split(":root{", 1)[1].split("}", 1)[0] if ":root{" in txt else ""
    out = {}
    for name, val in re.findall(r"--([\w-]+)\s*:\s*(#[0-9a-fA-F]{3,6})", head):
        out[name] = val
    return out


# (前景变量, 背景变量, 用途, 是否正文级)
CHECKS_A = [
    ("fg", "bg", "正文", True),
    ("fg2", "bg", "次级正文", True),
    ("fg3", "bg", "辅助标签", True),
    ("fg", "s1", "卡片正文", True),
    ("fg2", "s1", "卡片次级正文", True),
    ("fg3", "s1", "卡片辅助", True),
    ("fg", "s2", "数字数值", True),
    ("fg2", "s2", "数字标签", True),
    ("fg3", "s2", "标签", True),
    ("rise", "s2", "涨（数值）", True),
    ("fall", "s2", "跌（数值）", True),
    ("rise", "s1", "涨（正文）", True),
    ("fall", "s1", "跌（正文）", True),
    ("accent", "s1", "链接/操作", True),
    ("warn", "s1", "提醒", True),
    ("fg4", "s1", "装饰（计数）", False),
    ("fg4", "s2", "装饰", False),
]

CHECKS_B = [
    ("ink", "bg", "正文", True),
    ("ink2", "bg", "次级正文", True),
    ("ink3", "bg", "辅助标签", True),
    ("ink", "paper", "报头正文", True),
    ("ink2", "paper", "次级正文", True),
    ("ink3", "paper", "辅助", True),
    ("rise", "bg", "涨（数值）", True),
    ("fall", "bg", "跌（数值）", True),
    ("rise", "paper", "涨（正文）", True),
    ("fall", "paper", "跌（正文）", True),
    ("gold", "bg", "提示/提醒", True),
    ("accent", "bg", "链接", True),
    ("ink4", "bg", "装饰（计数）", False),
]


def run(theme, css_file, checks):
    v = vars_of(HERE / css_file)
    print(f"\n=== {theme} ===")
    print(f"{'用途':<16}{'前景':<12}{'背景':<12}{'比值':>7}  判定")
    bad = []
    for fg, bg, use, is_body in checks:
        if fg not in v or bg not in v:
            print(f"  缺变量 {fg}/{bg}")
            continue
        r = ratio(v[fg], v[bg])
        if not is_body:
            ok = "装饰 OK" if r >= 3.0 else ("装饰偏浅" if r >= 2.0 else "装饰过浅")
            mark = "✓" if r >= 3.0 else "△"
        else:
            ok = "AA 正文" if r >= 4.5 else "AA 大字" if r >= 3.0 else "不达标"
            mark = "✓" if r >= 4.5 else ("△" if r >= 3.0 else "✗")
        if is_body and r < 4.5:
            bad.append((use, fg, bg, round(r, 2)))
        print(f"{use:<16}{v[fg]:<12}{v[bg]:<12}{r:>6.2f}  {mark} {ok}")
    return bad


bad_a = run("A · Terminal（深色）", "a-terminal.css", CHECKS_A)
bad_b = run("B · Brief（浅色）", "b-brief.css", CHECKS_B)

allbad = bad_a + bad_b
print("\n" + "=" * 60)
if allbad:
    print("正文级未达 4.5:1 的组合：")
    for use, fg, bg, r in allbad:
        print(f"  ✗ {use}: {fg} on {bg} = {r}:1")
    sys.exit(1)
print("全部正文级组合 ≥ 4.5:1 —— WCAG AA 通过")
