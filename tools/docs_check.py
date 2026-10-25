#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""构建白名单暂存树并跑 marketplace 校验器，统计 error/warning。

用法:
  python tools/docs_check.py            # 构树 + 校验 + 打印统计
  python tools/docs_check.py --list     # 额外打印全部 error 明细
  python tools/docs_check.py --keep     # 保留暂存树并打印路径
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ENG = Path(r"D:\Workplace\stock").resolve()
VALIDATOR = Path(
    r"C:\Users\Lenovo\.workbuddy\plugins\cache\experts\skill-lifecycle-studio"
    r"\2.0.0\skills\skill-lifecycle-toolkit\scripts\validate_skill.py"
)

# 受管文件清单（白名单暂存树）
ROOT_FILES = ["SKILL.md", "README.md", "CHANGELOG.md", "LICENSE", "pyproject.toml",
             "MANIFEST.json", "VERSION.json"]
SCRIPTS = [
    "derive_indicators.py", "fetch_data.py", "gate_check.py", "install_skill.py",
    "notify.py", "paths.py", "preflight.py", "release.py", "render_report.py",
    "reuse_evidence.py", "run_daily.py", "setup_local.py",
]
ADAPTERS = [
    "__init__.py", "baostock_src.py", "cboe.py", "eastmoney.py",
    "north.py", "sina.py", "tencent.py",
]
REFERENCES = [
    "agent-roles.md", "analysis-workflow.md", "data-sources.md", "debate-protocol.md",
    "evidence-schema.md", "evidence-standards.md", "market-models.md", "mcp-data-source.md",
    "output-templates.md", "report-html-template.md", "risk-compliance.md", "test-cases.md",
]
ASSETS = ["data-schema.md", "disclaimer.html", "holdings-template.md", "style.css"]
PROMPTS = ["noon.md", "post.md", "pre.md"]
TESTS = [
    "__init__.py", "test_adapters.py", "test_derive.py", "test_gate.py",
    "test_notify.py", "test_parity.py", "test_regressions.py", "test_release.py",
    "test_render_ui.py", "test_run_daily.py", "test_theme_contract.py",
]
EXAMPLES = ["holdings.example.md", "watchlist.example.md", "watchlist_brief.example.json"]
CONFIGS = ["data-sources.example.json", "notify.example.json"]
FIXTURES = ["holdings.sample.md"]


def managed_files():
    out = list(ROOT_FILES)
    out += ["scripts/" + f for f in SCRIPTS]
    out += ["scripts/adapters/" + f for f in ADAPTERS]
    out += ["references/" + f for f in REFERENCES]
    out += ["assets/" + f for f in ASSETS]
    out += ["assets/workbuddy-prompts/" + f for f in PROMPTS]
    out += ["tests/" + f for f in TESTS]
    out += ["examples/" + f for f in EXAMPLES]
    out += ["config/" + f for f in CONFIGS]
    out += ["tests/fixtures/" + f for f in FIXTURES]
    return out


def build_dst(dst):
    """把受管文件复制到 dst，字节统一转 LF。"""
    dst.mkdir(parents=True, exist_ok=True)
    copied, missing = [], []
    for rel in managed_files():
        src = ENG / rel
        if not src.exists():
            missing.append(rel)
            continue
        data = src.read_bytes().replace(b"\r\n", b"\n")
        out = dst / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        copied.append(rel)
    return copied, missing


def run_validator(dst):
    proc = subprocess.run(
        [sys.executable, str(VALIDATOR), str(dst),
         "--platform", "workbuddy", "--channel", "marketplace", "--json"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return proc


def parse_json(proc):
    out = (proc.stdout or "").strip()
    start = out.find("{")
    if start < 0:
        return None, out, proc.stderr or ""
    try:
        return json.loads(out[start:]), out, proc.stderr or ""
    except json.JSONDecodeError:
        return None, out, proc.stderr or ""


def summarize(errors):
    by_code = {}
    by_file = {}
    for e in errors:
        by_code[e.get("code", "?")] = by_code.get(e.get("code", "?"), 0) + 1
        msg = e.get("message", "")
        rel = msg.split(":")[0] if ":" in msg else "?"
        by_file[rel] = by_file.get(rel, 0) + 1
    return by_code, by_file


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="打印全部 error 明细")
    ap.add_argument("--keep", action="store_true", help="保留暂存树")
    args = ap.parse_args()

    dst = Path(tempfile.mkdtemp(prefix="docscheck_"))
    copied, missing = build_dst(dst)
    print(f"[staging] {dst}")
    print(f"[staging] copied={len(copied)} missing={len(missing)}")
    if missing:
        print(f"[staging] MISSING: {missing}")

    proc = run_validator(dst)
    data, raw, err = parse_json(proc)
    if data is None:
        print("[validator] 无法解析 JSON 输出")
        print(raw[:4000])
        print(err[:4000])
        return 2

    errors = data.get("errors", [])
    warnings = data.get("warnings", [])
    by_code, by_file = summarize(errors)
    print(f"\n[RESULT] errors={len(errors)} warnings={len(warnings)}")
    print("\n[by code]")
    for k in sorted(by_code, key=lambda x: -by_code[x]):
        print(f"  {k}: {by_code[k]}")
    print("\n[by file]")
    for k in sorted(by_file, key=lambda x: (-by_file[x], x)):
        print(f"  {by_file[k]:4d}  {k}")

    if args.list:
        print("\n[error details]")
        for e in errors:
            print(f"  {e.get('code')}: {e.get('message')}")

    if args.keep:
        print(f"\n[staging kept] {dst}")
    else:
        shutil.rmtree(dst, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
