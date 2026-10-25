#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""列出指定文件里所有会被断链检查命中的行内反引号 span（含完整 span 文本与行号）。"""
import re
import sys
from pathlib import Path

ENG = Path(r"D:\Workplace\stock").resolve()
TOKEN_RE = re.compile(r"^[\w][\w.\-/]*$")
EXT_RE = re.compile(r"\.[A-Za-z0-9]{1,6}$")
SKIP_PREFIX = ("http://", "https://", "file://", "mailto:", "#", "/", "~", "-")


def strip_fences_lines(text):
    out, in_fence = [], False
    for line in text.split("\n"):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            out.append(None)
            continue
        out.append(None if in_fence else line)
    return out


def main():
    for rel in sys.argv[1:]:
        p = ENG / rel
        base = ENG / "references" if rel.startswith("references/") else ENG
        print(f"\n########## {rel}  (base={base.name}/) ##########")
        lines = strip_fences_lines(p.read_text(encoding="utf-8"))
        for i, line in enumerate(lines, 1):
            if line is None:
                continue
            for span in re.findall(r"`([^`\n]+)`", line):
                tok = span.strip().split()[0].rstrip(".,;:)")
                if not tok or tok.endswith("/"):
                    continue
                if tok.startswith(SKIP_PREFIX) or not TOKEN_RE.match(tok):
                    continue
                if "/" not in tok and not EXT_RE.search(tok):
                    continue
                exists = (base / tok).exists()
                if not exists:
                    print(f"  L{i:<4} span=`{span}`  tok=`{tok}`")
                    print(f"        | {line.strip()[:150]}")


if __name__ == "__main__":
    main()
