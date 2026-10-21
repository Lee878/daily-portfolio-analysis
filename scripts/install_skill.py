#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把本仓库安装/更新为 WorkBuddy 技能副本。

    python scripts/install_skill.py           # 同步（增量镜像，排除数据目录）
    python scripts/install_skill.py --check    # 只检查副本与 MANIFEST 是否一致
    python scripts/install_skill.py --render   # 只渲染三份 prompt（打印路径）

装到：%USERPROFILE%\\.workbuddy\\skills\\daily-portfolio-analysis
只同步代码与资产；config/ data/ .git/ .archive/ 一律不同步。
prompt 里的 {{REPO_DIR}} 会替换成本仓库的绝对路径（数据留在这边）。
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402

SKILL_NAME = "daily-portfolio-analysis"
EXCLUDE_DIRS = {"config", "data", ".git", ".archive", ".github", ".workbuddy",
                "__pycache__", ".pytest_cache", ".ruff_cache", ".venv", "venv"}
PROMPT_DIR = "assets/workbuddy-prompts"


def target_dir() -> Path:
    return Path.home() / ".workbuddy" / "skills" / SKILL_NAME


def _frontmatter_name(skill_md: Path) -> str:
    text = skill_md.read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
    if not m:
        return ""
    mm = re.search(r"(?m)^name:\s*(\S+)", m.group(1))
    return mm.group(1) if mm else ""


def _mirror(src: Path, dst: Path) -> None:
    """Windows 用 robocopy（快、增量），其它平台用 shutil。"""
    if sys.platform == "win32":
        cmd = ["robocopy", str(src), str(dst), "/MIR", "/NFL", "/NDL", "/NJH", "/NJS", "/NP",
               "/XD", *EXCLUDE_DIRS, "/XF", "*.pyc"]
        # 只要退出码，不要回读输出：robocopy 输出是系统 ANSI 编码（中文 Windows 为 GBK），
        # text=True 会按 UTF-8 解码，遇到中文字节直接抛 UnicodeDecodeError
        rc = subprocess.run(cmd, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL).returncode
        # robocopy: 0=无变化 1=有复制 2=多余文件 3=1+2 … <8 都是成功
        if rc >= 8:
            raise RuntimeError(f"robocopy 失败（退出码 {rc}）")
        return
    dst.mkdir(parents=True, exist_ok=True)
    ignore = shutil.ignore_patterns(*EXCLUDE_DIRS, "*.pyc")
    shutil.copytree(src, dst, dirs_exist_ok=True, ignore=ignore)


def render_prompts(out_dir: Path) -> list[Path]:
    """把 prompt 里的 {{REPO_DIR}} 换成本仓库绝对路径。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name in ("pre", "noon", "post"):
        src = paths.ASSETS / "workbuddy-prompts" / f"{name}.md"
        if not src.exists():
            continue
        text = src.read_text(encoding="utf-8").replace(
            "{{REPO_DIR}}", paths.ROOT.as_posix())
        dst = out_dir / f"{name}.md"
        dst.write_text(text, encoding="utf-8")
        written.append(dst)
    return written


def check() -> int:
    dst = target_dir()
    if not dst.exists():
        print(f"[check] 未安装：{dst}")
        return 1
    man_f = paths.ROOT / "MANIFEST.json"
    if not man_f.exists():
        print("[check] 仓库无 MANIFEST.json，先跑 release.py manifest")
        return 2
    man = json.loads(man_f.read_text(encoding="utf-8"))
    bad = []
    for rel, meta in man["files"].items():
        p = dst / rel
        if not p.exists():
            bad.append(f"缺失 {rel}")
            continue
        import hashlib
        if hashlib.sha256(p.read_bytes()).hexdigest() != meta["sha256"]:
            bad.append(f"不一致 {rel}")
    if bad:
        print(f"[check] 副本漂移 {len(bad)} 处：")
        for b in bad[:10]:
            print("   [X]", b)
        print("   修复：python scripts/install_skill.py")
        return 1
    print(f"[check] 副本一致 [OK]（{man['file_count']} 个受管文件，版本 {man['version']}）")
    return 0


def main():
    paths.ensure_utf8_stdout()
    ap = argparse.ArgumentParser(description="安装/更新 WorkBuddy 技能副本")
    ap.add_argument("--check", action="store_true", help="只检查，不写入")
    ap.add_argument("--render", action="store_true", help="只渲染 prompt")
    args = ap.parse_args()

    if args.check:
        return check()

    dst = target_dir()
    if args.render:
        written = render_prompts(dst / "prompts-rendered")
        for w in written:
            print("[render]", w)
        return 0

    name = _frontmatter_name(paths.ROOT / "SKILL.md")
    if name != SKILL_NAME:
        print(f"[error] SKILL.md frontmatter name={name!r}，与目录名 {SKILL_NAME} 不一致"
              "（skill 规范要求两者相同）")
        return 2

    print(f"[install] {paths.ROOT} → {dst}")
    _mirror(paths.ROOT, dst)
    written = render_prompts(dst / "prompts-rendered")
    print(f"[install] 已同步；prompt 已渲染 {len(written)} 份到 {dst / 'prompts-rendered'}")
    print("[install] 校验：", "通过" if check() == 0 else "见上")
    return 0


if __name__ == "__main__":
    sys.exit(main())
