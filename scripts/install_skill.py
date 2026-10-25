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
import fingerprint  # noqa: E402  v2.8.0：与 release.py 共用归一化指纹口径

SKILL_NAME = "daily-portfolio-analysis"
# v2.8.0 补：skill-studio（run 档案：快照/设计/QA 报告，222 文件 2.4MB）与
# dist（发布中间产物）都不是技能资产，绝不能被装进技能目录。
EXCLUDE_DIRS = {"config", "data", ".git", ".archive", ".github", ".workbuddy",
                "__pycache__", ".pytest_cache", ".ruff_cache", ".venv", "venv",
                "skill-studio", "dist", "node_modules"}
# docs/ui-preview 下只保留 *.py（contrast 校验脚本）；
# 预览 HTML 与成品截图内嵌**真实持仓金额**，PNG 是二进制无法靠文本扫描发现，
# 只能按扩展名整体排除。安装目录是长期驻留的，比仓库更需要注意。
_PREVIEW_DIR = "ui-preview"
_PRIVATE_SUFFIXES = {".html", ".png", ".jpg", ".jpeg"}
PROMPT_DIR = "assets/workbuddy-prompts"


def _is_private_artifact(p: Path) -> bool:
    """是否是「包含真实持仓、不该复制到安装目录」的预览产物。"""
    return p.parent.name == _PREVIEW_DIR and p.suffix.lower() in _PRIVATE_SUFFIXES


def _ignore_for(src_root: Path):
    """shutil.copytree 的 ignore 回调：排除目录 + pyc + ui-preview 私有产物。"""

    def _ignore(dirpath, names):
        base = Path(dirpath)
        ignored = []
        for n in names:
            p = base / n
            if p.is_dir() and n in EXCLUDE_DIRS:
                ignored.append(n)
            elif n.endswith(".pyc"):
                ignored.append(n)
            elif p.is_file() and _is_private_artifact(p):
                ignored.append(n)
        return ignored

    return _ignore


def target_dir() -> Path:
    return Path.home() / ".workbuddy" / "skills" / SKILL_NAME


def _frontmatter_name(skill_md: Path) -> str:
    text = skill_md.read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
    if not m:
        return ""
    mm = re.search(r"(?m)^name:\s*(\S+)", m.group(1))
    return mm.group(1) if mm else ""


def _copy_config_examples(src: Path, dst: Path) -> int:
    """把 config/*.example.* 模板复制过去，但不碰真实配置。

    整个 config/ 目录被 EXCLUDE_DIRS 排除（里面是用户的 holdings.md / notify.json
    等隐私数据），但 *.example.* 是文档里明确让用户手动复制的模板
    （如 config/notify.example.json → config/notify.json），必须随技能安装。
    早先只排除不补回，导致 install --check 永远报「缺失 config/*.example.json」。
    """
    n = 0
    for p in sorted((src / "config").glob("*.example.*")):
        if not p.is_file():
            continue
        d = dst / "config" / p.name
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, d)
        n += 1
    return n


def _mirror(src: Path, dst: Path) -> None:
    """Windows 用 robocopy（快、增量），其它平台用 shutil。"""
    if sys.platform == "win32":
        # robocopy 的 /XF 只能按文件名模式（不支持按目录），所以 ui-preview 的
        # 私有产物只能在镜像完成后单独清掉 —— 见 _purge_private_artifacts。
        cmd = ["robocopy", str(src), str(dst), "/MIR", "/NFL", "/NDL", "/NJH", "/NJS", "/NP",
               "/XD", *EXCLUDE_DIRS, "/XF", "*.pyc"]
        # 只要退出码，不要回读输出：robocopy 输出是系统 ANSI 编码（中文 Windows 为 GBK），
        # text=True 会按 UTF-8 解码，遇到中文字节直接抛 UnicodeDecodeError
        rc = subprocess.run(cmd, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL).returncode
        # robocopy: 0=无变化 1=有复制 2=多余文件 3=1+2 … <8 都是成功
        if rc >= 8:
            raise RuntimeError(f"robocopy 失败（退出码 {rc}）")
        _purge_private_artifacts(dst)
        _copy_config_examples(src, dst)
        return
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst, dirs_exist_ok=True, ignore=_ignore_for(src))
    _copy_config_examples(src, dst)


def _purge_private_artifacts(dst: Path) -> int:
    """删掉安装目录里 docs/ui-preview 下的预览 HTML / 截图（含真实持仓）。

    robocopy /MIR 会先复制再让这里删除，每轮重复一次但结果幂等。
    """
    d = dst / "docs" / _PREVIEW_DIR
    if not d.is_dir():
        return 0
    n = 0
    for p in d.iterdir():
        if p.is_file() and p.suffix.lower() in _PRIVATE_SUFFIXES:
            p.unlink()
            n += 1
    return n


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
        # v2.8.0：与 release.py 共用 fingerprint 的归一化口径。
        # 两处各写一份会让「verify 判一致、副本自检判漂移」得出矛盾结论，
        # 排查极耗时（CRLF 工作区 / LF 副本）。
        if fingerprint.sha256_of(p) != meta["sha256"]:
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
