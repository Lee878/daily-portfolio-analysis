#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""daily-portfolio-analysis 发布 / 版本指纹 / 漂移检测工具。

把"跑的到底是不是已发布的那一版"变成机器可校验：
  bump <major|minor|patch>  递增版本、写 VERSION、重算 MANIFEST
  manifest                 按当前 VERSION 重算 MANIFEST（不递增）
  verify [--target ENG|RT]  实际文件指纹 vs MANIFEST（退出码 0 一致 / 1 漂移）
  test                     跑 scripts/tests 全量 unittest
  sync                     ENG → RT 确定性同步，随后校验 RT 指纹
  doctor                   综合体检：ENG 指纹 + RT 指纹 + 测试

受管文件不含 build_report_*/supplement_* 等一次性当日脚本（它们不是标准）。
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ENG = SCRIPT_DIR.parent
# RT（运行时副本）是豆包云电脑的"云重启会重置"目录，只有双副本部署才需要。
# v2.2.3：改为可选——未配置 DAILY_RT 时 doctor 跳过 RT 校验，不再判死；
# 旧版硬编码 /runtime/... 导致 WorkBuddy/Windows 上 doctor 永远不绿。
RT_ENV = os.environ.get("DAILY_RT", "").strip()
RT = Path(RT_ENV) if RT_ENV else None
VERSION_F = ENG / "VERSION.json"
MANIFEST_F = ENG / "MANIFEST.json"
MIN_TESTS = 62


def managed_files():
    """受管文件（相对 ENG 的 posix 路径），排序去重。"""
    items = [
        "SKILL.md", "BOOTSTRAP.md",
        "scripts/run_daily.py", "scripts/gate_check.py", "scripts/fetch_data.py",
        "scripts/render_report.py", "scripts/reuse_evidence.py",
        "scripts/preflight.py",
        "scripts/release.py", "scripts/redeploy.py",
        "scripts/tests/__init__.py",
        "scripts/tests/test_gate.py", "scripts/tests/test_run_daily.py",
        "scripts/tests/test_release.py",
        "assets/holdings-template.md",
        "assets/style.css", "assets/disclaimer.html", "assets/data-schema.md",
    ]
    items += [f"references/{p.name}" for p in sorted((ENG / "references").glob("*.md"))]
    items += [f"assets/cron-templates/{p.name}"
              for p in sorted((ENG / "assets/cron-templates").glob("*.md"))]
    # 测试文件用 glob 纳入，新增回归用例自动进指纹（不再需要手工登记）
    items += [f"scripts/tests/{p.name}"
              for p in sorted((ENG / "scripts/tests").glob("*.py"))]
    return sorted(set(i for i in items if (ENG / i).exists()))


def sha256_of(path: Path):
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def build_manifest(version):
    files = {}
    for rel in managed_files():
        p = ENG / rel
        files[rel] = {"sha256": sha256_of(p), "bytes": p.stat().st_size}
    return {
        "version": version,
        "released_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "minimum_tests": MIN_TESTS,
        "file_count": len(files),
        "files": files,
    }


def read_version():
    if VERSION_F.exists():
        return json.loads(VERSION_F.read_text(encoding="utf-8")).get("version")
    return None


def bump(level):
    cur = read_version() or "0.0.0"
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)", cur)
    if not m:
        print(f"[release][error] 版本号无法解析：{cur!r}（需形如 2.2.2）")
        return 2
    a, b, c = (int(x) for x in m.groups())
    if level == "major":
        a, b, c = a + 1, 0, 0
    elif level == "minor":
        b, c = b + 1, 0
    else:
        c += 1
    version = f"{a}.{b}.{c}"
    write_version(version)
    write_manifest(version)
    print(f"[release] bump {cur} → {version}；VERSION/MANIFEST 已更新。")
    print("[release] 如有行为变更，请同步 CHANGELOG.md，然后跑 test / sync。")
    return 0


def write_version(version):
    VERSION_F.write_text(json.dumps({
        "version": version,
        "released_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "minimum_tests": MIN_TESTS,
        "changelog": "CHANGELOG.md",
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def write_manifest(version):
    MANIFEST_F.write_text(json.dumps(build_manifest(version), ensure_ascii=False,
                                     indent=2), encoding="utf-8")


def manifest():
    version = read_version()
    if not version:
        print("[release][error] 无 VERSION.json，先 bump。")
        return 2
    write_manifest(version)
    print(f"[release] MANIFEST 已按 {version} 重算（{len(managed_files())} 个受管文件）。")
    return 0


def verify_target(root: Path, label):
    if not MANIFEST_F.exists():
        print(f"[verify][{label}] 无 MANIFEST.json，先 bump/manifest。")
        return 2
    man = json.loads(MANIFEST_F.read_text(encoding="utf-8"))
    problems = []
    for rel, meta in man["files"].items():
        p = root / rel
        if not p.exists():
            problems.append(f"缺失 {rel}")
            continue
        actual = sha256_of(p)
        if actual != meta["sha256"]:
            problems.append(f"变更 {rel}")
    if root == ENG:
        managed = set(managed_files())
        listed = set(man["files"])
        for extra in sorted(managed - listed):
            problems.append(f"未登记 {extra}")
    if problems:
        print(f"[verify][{label}] 漂移 {len(problems)} 处（MANIFEST 版本 {man['version']}）：")
        for x in problems:
            print("   [X]", x)
        return 1
    print(f"[verify][{label}] 一致 [OK]（版本 {man['version']}，{man['file_count']} 文件）")
    return 0


def run_tests():
    print("[release] 跑 scripts/tests 全量 unittest …")
    rc = subprocess.run([sys.executable, "-m", "unittest", "discover",
                         "-s", "tests", "-p", "test_*.py"],
                        cwd=str(SCRIPT_DIR)).returncode
    if rc == 0:
        print("[release] 测试全绿 [OK]")
    else:
        print("[release] 测试失败 [X] —— 禁止发布/sync。")
    return rc


def sync():
    version = read_version()
    if not version:
        print("[release][error] 无 VERSION.json，先 bump。")
        return 2
    if RT is None:
        print("[release][error] 未配置 DAILY_RT，单副本部署无需 sync。"
              "（豆包云电脑需要时可 export DAILY_RT=/runtime/user_skills/daily-portfolio-analysis）")
        return 2
    if run_tests() != 0:
        return 1
    RT.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ENG / "SKILL.md", RT / "SKILL.md")
    for d in ("scripts", "references", "assets"):
        shutil.copytree(ENG / d, RT / d, dirs_exist_ok=True)
    for f in ("VERSION.json", "MANIFEST.json", "CHANGELOG.md", "BOOTSTRAP.md"):
        if (ENG / f).exists():
            shutil.copy2(ENG / f, RT / f)
    print(f"[release] 已同步 ENG → RT（{version}）。")
    return verify_target(RT, "RT")


def check_syntax():
    """全量语法检查（不写字节码）。

    回归用例只覆盖被 import 的模块，preflight/redeploy 这类"只在命令行跑"的脚本
    坏了测试也发现不了——2026-10-21 就踩过一次。doctor 里加一道兜底。
    """
    bad = []
    targets = list(SCRIPT_DIR.glob("*.py")) + list((SCRIPT_DIR / "tests").glob("*.py"))
    for p in sorted(targets):
        try:
            compile(p.read_text(encoding="utf-8"), str(p), "exec")
        except SyntaxError as e:
            bad.append(f"{p.name}:{e.lineno}: {e.msg}")
    if bad:
        print(f"[release] 语法检查失败 [X]（{len(bad)} 处）：")
        for b in bad:
            print("   [X]", b)
        return 1
    print(f"[release] 语法检查通过 [OK]（{len(targets)} 个文件）")
    return 0


def doctor():
    print("=" * 60)
    print(f"[doctor] ENG={ENG}")
    print("=" * 60)
    v = read_version()
    print("版本：", v or "无 VERSION.json")
    rc_syn = check_syntax()
    rc_eng = verify_target(ENG, "ENG")
    if RT is None:
        print("[verify][RT] 未配置 DAILY_RT —— 单副本部署，跳过 RT 指纹")
        rc_rt = 0
    elif not RT.exists():
        print(f"[verify][RT] DAILY_RT 指向的目录不存在：{RT} —— 跳过 RT 指纹")
        rc_rt = 0
    else:
        rc_rt = verify_target(RT, "RT")
    rc_test = run_tests()
    print("=" * 60)
    ok = (v is not None and rc_syn == 0 and rc_eng == 0 and rc_rt == 0 and rc_test == 0)
    print("[doctor]", "全部健康 [OK]" if ok else "存在问题 [X]（见上）")
    return 0 if ok else 1


def ensure_utf8_stdout():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main():
    ensure_utf8_stdout()
    ap = argparse.ArgumentParser(description="发布/指纹/漂移检测")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("bump"); b.add_argument("level", choices=["major", "minor", "patch"])
    sub.add_parser("manifest")
    vf = sub.add_parser("verify"); vf.add_argument("--target", choices=["ENG", "RT"], default="ENG")
    sub.add_parser("test")
    sub.add_parser("sync")
    sub.add_parser("doctor")
    args = ap.parse_args()
    if args.cmd == "bump":
        sys.exit(bump(args.level))
    if args.cmd == "manifest":
        sys.exit(manifest())
    if args.cmd == "verify":
        if args.target == "RT" and RT is None:
            print("[verify][RT] 未配置 DAILY_RT —— 单副本部署，跳过")
            sys.exit(0)
        sys.exit(verify_target(ENG if args.target == "ENG" else RT, args.target))
    if args.cmd == "test":
        sys.exit(run_tests())
    if args.cmd == "sync":
        sys.exit(sync())
    if args.cmd == "doctor":
        sys.exit(doctor())


if __name__ == "__main__":
    main()
