#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""列出所有断链 token 的上下文 + 在仓库/暂存树中的存在性判定。

用法: python tools/docs_links.py [--ctx 1]
"""
import re
import sys
import tempfile
import shutil
from pathlib import Path

ENG = Path(r"D:\Workplace\stock").resolve()
sys.path.insert(0, str(ENG / "tools"))
from docs_check import build_dst, managed_files  # noqa: E402

TOKEN_RE = re.compile(r"^[\w][\w.\-/]*$")
EXT_RE = re.compile(r"\.[A-Za-z0-9]{1,6}$")
SKIP_PREFIX = ("http://", "https://", "file://", "mailto:", "#", "/", "~", "-")


def strip_fences(text):
    parts, in_fence, out = [], False, []
    for line in text.split("\n"):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append((len(parts) + 1, line))
            parts.append(line)
    return out


def tokens_of(text):
    """返回 [(lineno, token)] —— 与校验器 inline_code_paths 同逻辑，但带行号。"""
    found = []
    lineno = 0
    for line in text.split("\n"):
        lineno += 1
        if line.lstrip().startswith("```"):
            continue
        for span in re.findall(r"`([^`\n]+)`", line):
            token = span.strip()
            if not token:
                continue
            token = token.split()[0].rstrip(".,;:)")
            if not token or token.endswith("/"):
                continue
            if token.startswith(SKIP_PREFIX) or not TOKEN_RE.match(token):
                continue
            if "/" not in token and not EXT_RE.search(token):
                continue
            found.append((lineno, token))
    return found


def main():
    ctx = 1
    if "--ctx" in sys.argv:
        ctx = int(sys.argv[sys.argv.index("--ctx") + 1])

    dst = Path(tempfile.mkdtemp(prefix="docslink_"))
    build_dst(dst)
    packaged = set(managed_files())

    rows = []
    for rel in sorted(packaged):
        if not rel.endswith(".md"):
            continue
        p = dst / rel
        if not p.exists():
            continue
        base = dst / "references" if rel.startswith("references/") else dst
        text = p.read_text(encoding="utf-8")
        lines = text.split("\n")
        for lineno, token in tokens_of(text):
            resolved = (base / token)
            if resolved.exists():
                continue
            # 存在性判定
            rel_from_root = token
            if rel.startswith("references/"):
                rel_from_root = "../" + token
            repo_hit = (ENG / rel_from_root).resolve()
            in_pkg = rel_from_root.replace("\\", "/") in packaged
            rows.append({
                "file": rel, "line": lineno, "token": token,
                "text": lines[lineno - 1] if lineno - 1 < len(lines) else "",
                "repo_exists": repo_hit.exists(),
                "repo_path": str(repo_hit).replace(str(ENG) + "\\", ""),
                "packaged": in_pkg,
            })

    print(f"[broken tokens] {len(rows)}")
    for r in rows:
        flag = "REPO-OK/NOT-PKG" if r["repo_exists"] and not r["packaged"] else (
               "REPO-OK/PKG" if r["repo_exists"] else "NOT-IN-REPO")
        print(f"\n{r['file']}:{r['line']}  token=`{r['token']}`  [{flag} -> {r['repo_path']}]")
        if ctx:
            print(f"    {r['text'][:200]}")

    # 汇总
    from collections import Counter
    c = Counter(r["token"] for r in rows)
    print("\n\n[token summary]")
    for tok, n in c.most_common():
        print(f"  {n:3d}  {tok}")
    shutil.rmtree(dst, ignore_errors=True)


if __name__ == "__main__":
    main()
