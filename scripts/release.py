#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""daily-portfolio-analysis 发布 / 版本指纹 / 漂移检测工具（v2.4.0）。

    bump <major|minor|patch>  递增版本；同步 VERSION.json / pyproject.toml / MANIFEST.json
    manifest                  按当前版本重算 MANIFEST（不递增）
    verify                    实际文件指纹 vs MANIFEST（0 一致 / 1 漂移）
    test                      跑 tests/ 全量 unittest
    doctor                    综合体检：语法 + 指纹 + 测试 + 本地数据就绪情况

v2.4.0 变化：
  - 路径统一走 paths.py，仓库根 = skill 根（scripts/ references/ assets/ tests/）
  - 删除 RT（豆包云"运行时副本"）与 sync：本地单副本部署不需要，且会让 doctor 永远不绿
  - MANIFEST 定位降级为"安装副本自检"；版本权威是 VERSION.json 与 git tag
"""
import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import paths  # noqa: E402

ENG = paths.ROOT
VERSION_F = ENG / "VERSION.json"
MANIFEST_F = ENG / "MANIFEST.json"
PYPROJECT_F = ENG / "pyproject.toml"
MIN_TESTS = 62


def managed_files():
    """受管文件（相对仓库根的 posix 路径）。新增文件自动纳入，无需手工登记。"""
    items = ["SKILL.md", "README.md", "LICENSE", "pyproject.toml", "CHANGELOG.md"]
    items += [f"scripts/{p.name}" for p in sorted(paths.SCRIPTS.glob("*.py"))]
    items += [f"references/{p.name}" for p in sorted(paths.REFERENCES.glob("*.md"))]
    items += ["assets/style.css", "assets/disclaimer.html",
              "assets/data-schema.md", "assets/holdings-template.md"]
    items += [f"assets/workbuddy-prompts/{p.name}"
              for p in sorted((paths.ASSETS / "workbuddy-prompts").glob("*.md"))]
    items += [f"tests/{p.name}" for p in sorted(paths.TESTS.glob("*.py"))]
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


def _sync_pyproject_version(version: str) -> None:
    """把 pyproject.toml 的 version 同步为同一版本（存在才改，失败只警告）。"""
    if not PYPROJECT_F.exists():
        return
    try:
        text = PYPROJECT_F.read_text(encoding="utf-8")
        new, n = re.subn(r'(?m)^version\s*=\s*"[^"]*"',
                         f'version = "{version}"', text, count=1)
        if n:
            PYPROJECT_F.write_text(new, encoding="utf-8")
            print(f"[release] pyproject.toml version → {version}")
        else:
            print("[release][warn] pyproject.toml 里没找到 version 字段，已跳过")
    except Exception as e:
        print(f"[release][warn] 同步 pyproject.toml 失败（不影响发布）：{e}")


def bump(level):
    cur = read_version() or "0.0.0"
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)", cur)
    if not m:
        print(f"[release][error] 版本号无法解析：{cur!r}（需形如 2.4.0）")
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
    _sync_pyproject_version(version)
    write_manifest(version)
    print(f"[release] bump {cur} → {version}；VERSION / pyproject / MANIFEST 已更新。")
    print("[release] 记得补 CHANGELOG.md，然后跑 release.py test。")
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


def verify_target(root: Path, label="ENG"):
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
        if sha256_of(p) != meta["sha256"]:
            problems.append(f"变更 {rel}")
    if root == ENG:
        for extra in sorted(set(managed_files()) - set(man["files"])):
            problems.append(f"未登记 {extra}")
    if problems:
        print(f"[verify][{label}] 漂移 {len(problems)} 处（MANIFEST 版本 {man['version']}）：")
        for x in problems:
            print("   [X]", x)
        return 1
    print(f"[verify][{label}] 一致 [OK]（版本 {man['version']}，{man['file_count']} 文件）")
    return 0


def run_tests():
    print("[release] 跑 tests/ 全量 unittest …")
    rc = subprocess.run([sys.executable, "-m", "unittest", "discover",
                         "-s", "tests", "-p", "test_*.py"],
                        cwd=str(ENG)).returncode
    if rc == 0:
        print("[release] 测试全绿 [OK]")
    else:
        print("[release] 测试失败 [X] —— 禁止发布。")
    return rc


def check_syntax():
    """全量语法检查（不写字节码）。

    回归用例只覆盖被 import 的模块，命令行脚本（setup_local / install_skill 等）
    坏了测试发现不了——2026-10-21 踩过一次，doctor 里加一道兜底。
    """
    bad = []
    targets = list(paths.SCRIPTS.glob("*.py")) + list(paths.TESTS.glob("*.py"))
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


def check_local_ready():
    """本地数据就绪检查：只提示，不阻断（首次运行还没配数据也能体检）。"""
    holdings = paths.resolve_holdings()
    wl = paths.watchlist_path(holdings) if holdings else None
    root = paths.report_root()
    print("=" * 60)
    print(f"[doctor] 配置目录：{paths.config_dir()}")
    print(f"[doctor] 报告目录：{root}")
    print(f"  holdings.md ：{'OK ' + str(holdings) if holdings else '未找到（先跑 scripts/setup_local.py）'}")
    print(f"  watchlist.md：{wl if wl else '未找到（可选）'}")
    print(f"  历史报告数  ：{len(list(root.glob('*.html'))) if root.exists() else 0}")
    return 0


def doctor():
    print("=" * 60)
    print(f"[doctor] 仓库根：{ENG}")
    print("=" * 60)
    v = read_version()
    print("版本：", v or "无 VERSION.json")
    rc_syn = check_syntax()
    rc_eng = verify_target(ENG, "ENG")
    rc_test = run_tests()
    check_local_ready()
    print("=" * 60)
    ok = (v is not None and rc_syn == 0 and rc_eng == 0 and rc_test == 0)
    print("[doctor]", "全部健康 [OK]" if ok else "存在问题 [X]（见上）")
    return 0 if ok else 1


def main():
    paths.ensure_utf8_stdout()
    ap = argparse.ArgumentParser(description="发布/指纹/漂移检测")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("bump")
    b.add_argument("level", choices=["major", "minor", "patch"])
    sub.add_parser("manifest")
    sub.add_parser("verify")
    sub.add_parser("test")
    sub.add_parser("doctor")
    args = ap.parse_args()
    if args.cmd == "bump":
        sys.exit(bump(args.level))
    if args.cmd == "manifest":
        sys.exit(manifest())
    if args.cmd == "verify":
        sys.exit(verify_target(ENG, "ENG"))
    if args.cmd == "test":
        sys.exit(run_tests())
    if args.cmd == "doctor":
        sys.exit(doctor())


if __name__ == "__main__":
    main()
