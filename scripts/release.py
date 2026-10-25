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
import posixpath
import re
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import paths  # noqa: E402
import fingerprint  # noqa: E402  v2.8.0：归一化指纹的唯一口径

ENG = paths.ROOT
VERSION_F = ENG / "VERSION.json"
MANIFEST_F = ENG / "MANIFEST.json"
PYPROJECT_F = ENG / "pyproject.toml"
MIN_TESTS = 184


def managed_files():
    """受管文件（相对仓库根的 posix 路径）。新增文件自动纳入，无需手工登记。

    v2.8.0 扩容（46 → 61）：补齐运行时不缺就起不来的文件 —— 数据源适配器、
    examples 模板、config 示例、测试夹具。此前 46 文件树跑测试只执行 62 项且
    有 10 个 ERROR（84 项静默不执行 = 假绿），补齐后 164 项全绿。

    **MANIFEST.json 自身不入清单**：它的内容包含所有文件的 sha256，
    把它自己也纳入会导致「写入即改变自己的指纹」→ 永远漂移。校验清单
    不含清单自身，这是 checksum 文件的通行做法。
    """
    items = ["SKILL.md", "README.md", "LICENSE", "pyproject.toml", "CHANGELOG.md"]
    items += [f"scripts/{p.name}" for p in sorted(paths.SCRIPTS.glob("*.py"))]
    items += [f"scripts/adapters/{p.name}"
              for p in sorted((paths.SCRIPTS / "adapters").glob("*.py"))]
    items += [f"references/{p.name}" for p in sorted(paths.REFERENCES.glob("*.md"))]
    items += ["assets/style.css", "assets/disclaimer.html",
              "assets/data-schema.md", "assets/holdings-template.md"]
    items += [f"assets/workbuddy-prompts/{p.name}"
              for p in sorted((paths.ASSETS / "workbuddy-prompts").glob("*.md"))]
    items += [f"tests/{p.name}" for p in sorted(paths.TESTS.glob("*.py"))]
    items += [f"tests/fixtures/{p.name}"
              for p in sorted((paths.TESTS / "fixtures").glob("*"))]
    items += [f"examples/{p.name}" for p in sorted(paths.EXAMPLES.glob("*"))]
    # 只收 *.example.*，真实配置（holdings.md / notify.json 等）含隐私，绝不入包
    items += [f"config/{p.name}"
              for p in sorted((ENG / "config").glob("*.example.*"))]
    # 版本说明文档随技能分发：用户在装好的技能里能直接读到安装/验证/主题说明
    items += ["docs/INSTALL.md"]
    items += ["VERSION.json"]
    out = []
    for i in sorted(set(items)):
        p = ENG / i
        if not p.is_file():
            continue
        # 隐私 / 非资产兜底排除（glob 规则之外的显式防线）
        if p.suffix == ".bak" or "__pycache__" in p.parts:
            continue
        if i == "MANIFEST.json":          # 自引用，见 docstring
            continue
        out.append(i)
    return out


def sha256_of(path: Path):
    """归一化后的 sha256（文本类 CRLF→LF 后再哈希，二进制按原始字节）。

    走 fingerprint 模块，与 install_skill.py 的副本自检共用同一实现 ——
    两处各写一份会让「verify 判一致、副本自检判漂移」得出矛盾结论。
    """
    return fingerprint.sha256_of(path)


def build_manifest(version):
    files = {}
    for rel in managed_files():
        p = ENG / rel
        files[rel] = {"sha256": sha256_of(p), "bytes": fingerprint.bytes_of(p)}
    return {
        "version": version,
        "released_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "minimum_tests": MIN_TESTS,
        "eol": fingerprint.EOL,
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


def _sync_skill_version(version: str) -> None:
    """把 SKILL.md frontmatter 的 version 同步为同一版本（skill 规范要求）。"""
    f = ENG / "SKILL.md"
    if not f.exists():
        return
    try:
        text = f.read_text(encoding="utf-8")
        new, n = re.subn(r"(?m)^version:\s*\S+\s*$", f"version: {version}",
                         text, count=1)
        if n:
            f.write_text(new, encoding="utf-8")
            print(f"[release] SKILL.md version → {version}")
    except Exception as e:
        print(f"[release][warn] 同步 SKILL.md 版本失败（不影响发布）：{e}")


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
    _sync_skill_version(version)
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


# ---------------------------------------------------------------- fixlinks
# 复刻上架校验器的断链规则（validate_skill.py 的 check_links）：
#   只扫「行内反引号」内的 token；围栏代码块内不扫；
#   基准目录：references/ 下的 md 以 references/ 为基准，其余以技能根为基准。
# 注意 skillcheck:allow 标记对断链检查**无效**（只作用于 content_scan），已实测确认。
_TOKEN_RE = re.compile(r"^[\w][\w.\-/]*$")
_EXT_RE = re.compile(r"\.[A-Za-z0-9]{1,6}$")
_SKIP_PREFIX = ("http://", "https://", "file://", "mailto:", "#", "/", "~", "-")

# 候选前缀：加了之后能解析到真实文件，说明原 token 只是漏了目录前缀
_ROOT_PREFIXES = ("scripts/", "tests/", "assets/", "references/", "config/",
                  "examples/", "scripts/adapters/")
# 注意必须是 tuple 而不是生成器：生成器在第一次迭代后就耗尽，
# 会让第二个 token 起全部走错分支（曾导致 references/ 下的路径被误去反引号）。
_REF_PREFIXES = ("../",) + tuple("../" + p for p in _ROOT_PREFIXES)


def _strip_fences(text):
    """去掉围栏代码块，只留普通文本（与校验器同口径）。"""
    parts, in_fence = [], False
    for line in text.split("\n"):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            parts.append(line)
    return "\n".join(parts)


def _inline_paths(text):
    """提取行内反引号内形似路径的 token（保持出现顺序、可重复）。"""
    found = []
    for span in re.findall(r"`([^`\n]+)`", _strip_fences(text)):
        token = span.strip().split()[0].rstrip(".,;:)") if span.strip() else ""
        if not token or token.endswith("/"):
            continue
        if token.startswith(_SKIP_PREFIX) or not _TOKEN_RE.match(token):
            continue
        if "/" not in token and not _EXT_RE.search(token):
            continue
        found.append(token)
    return found


def _link_scan_files():
    """参与断链检查的 md（受管清单内的 md；references 单独标基准）。"""
    out = []
    for rel in managed_files():
        if not rel.endswith(".md"):
            continue
        base = (ENG / "references") if rel.startswith("references/") else ENG
        out.append((rel, base))
    return out


def fixlinks(write=False):
    """批量修断链。默认只报告；--write 才落盘。

    两类处理：
      1. 加候选前缀后文件存在 → 补全相对路径（类 1）
      2. 否则 → 去反引号裸写（类 2/3：根本不是文件路径的 token）

    **存在性判定只认「受管清单内」的文件**，不认整个工作区。
    理由：上架校验跑在白名单暂存树上，而暂存树不含私有 `config/*.md` /
    `data/` / `docs/ui-preview/` 等。若按工作区判存，`watchlist.md` 会被
    改写成 `config/watchlist.md`（工作区存在、包内不存在）→ 包内依然断链。
    宁可去反引号写成概念描述，也不要指向一个不随包分发的文件。

    幂等：已补全的路径再次运行会因「存在性判定」直接跳过。
    """
    shipped = set(managed_files())
    changed_files, auto_fixed, need_manual = 0, [], []
    for rel, base in _link_scan_files():
        p = ENG / rel
        text = p.read_text(encoding="utf-8")
        prefixes = _REF_PREFIXES if rel.startswith("references/") else _ROOT_PREFIXES
        fixed_here, manual_here = [], []

        def _repl(m, _rel=rel, _prefixes=prefixes):
            """只重写反引号片段内的**首词**，保留 `--session pre` 这类参数尾巴。

            早先的整串 replace 写法对带参数的行内代码无效（`` `x.py --a` `` 里
            没有 `` `x.py` `` 这个子串），却会被计入"已修复"→ 不幂等且实际未改。
            """
            span = m.group(1)
            head = span.split()[0]
            rest = span[len(head):]
            token = head.rstrip(".,;:)")
            tail_punct = head[len(token):]
            if not token or token.endswith("/"):
                return m.group(0)
            if token.startswith(_SKIP_PREFIX) or not _TOKEN_RE.match(token):
                return m.group(0)
            if "/" not in token and not _EXT_RE.search(token):
                return m.group(0)

            here = ("references/" + token) if _rel.startswith("references/") else token
            if _shipped_exists(here, shipped):
                return m.group(0)

            for pre in _prefixes:
                cand = pre + token
                cand_norm = ("references/" + cand) if _rel.startswith("references/") else cand
                if _shipped_exists(cand_norm, shipped):
                    fixed_here.append((_rel, token, cand))
                    return f"`{cand}{tail_punct}{rest}`"

            # 不是包内文件路径 → 去反引号。
            # 带参数也照样去引号：校验器只取片段首词做判定，留着反引号就会一直
            # 判断链；而这些 token 本身不是路径（股票代码、已废弃脚本名），
            # 去掉反引号既消掉误报，也不损失信息。
            manual_here.append((_rel, token))
            return span

        new_text = re.sub(r"`([^`\n]+)`", _repl, text)
        auto_fixed += fixed_here
        need_manual += manual_here
        if new_text != text:
            changed_files += 1
            if write:
                p.write_text(new_text, encoding="utf-8")

    verb = "已修改" if write else "将修改"
    print(f"[fixlinks] {verb} {changed_files} 个文件；"
          f"补全路径 {len(auto_fixed)} 处；去反引号 {len(need_manual)} 处")
    if not write:
        print("[fixlinks] 当前为只报告模式，加 --write 才会落盘")
    for rel, old, new in auto_fixed:
        print(f"   [路径] {rel}: `{old}` → `{new}`")
    for rel, tok in need_manual:
        print(f"   [去引号] {rel}: `{tok}` → {tok}")
    return 0


def _shipped_exists(rel_posix: str, shipped: set) -> bool:
    """该路径是否真的会随包分发（受管清单 + 随包额外文件）。

    只认会分发的文件，不认工作区里存在但不出包的东西（私有 config、
    docs/ui-preview 下的预览 HTML 等）—— 否则改出来的路径在包内依然断链。

    需要做**真实路径归一化**：references/ 下的候选前缀是 ``../scripts/x.py``，
    拼上基准就是 ``references/../scripts/x.py``，必须折叠成 ``scripts/x.py``
    才能与清单比对（朴素的字符串拼接会让所有 references 相对引用失效）。
    """
    norm = posixpath.normpath(rel_posix.replace("\\", "/"))
    while norm.startswith("./"):
        norm = norm[2:]
    return norm in shipped or norm in _STAGING_EXTRA


# ---------------------------------------------------------------- package
_PKG_PRIVATE_PATTERNS = (
    "config/holdings.md", "config/watchlist.md", "config/notify.json",
    "config/delivery.json", "config/watchlist_depth.json", "data/",
    ".bak", "docs/ui-preview/", ".workbuddy/", "skill-studio/", "__pycache__",
    "_probe_", "tools/",
)
_PKG_EXPECT = ("scripts/adapters/", "examples/", "config/data-sources.example.json",
               "config/notify.example.json", "VERSION.json", "MANIFEST.json",
               "tests/fixtures/", "scripts/fingerprint.py",
               "docs/INSTALL.md")


# 随包分发但不参与自哈希的文件。MANIFEST.json 的内容包含所有文件的 sha256，
# 把它自己也算进去会导致「写入即改变自己的指纹」→ 永远漂移；但它必须随包走，
# 否则装好后 install_skill.py --check 找不到清单。
_STAGING_EXTRA = ("MANIFEST.json",)


def _build_staging(dst: Path):
    """按受管清单铺一棵 LF 暂存树（zip 内字节 == 归一化指纹口径）。"""
    rels = managed_files() + [x for x in _STAGING_EXTRA if (ENG / x).exists()]
    for rel in rels:
        d = dst / rel
        d.parent.mkdir(parents=True, exist_ok=True)
        raw = (ENG / rel).read_bytes()
        d.write_bytes(fingerprint.normalize_bytes(raw, ENG / rel))
    return len(rels)


def package(out_path=None, dry_run=False):
    """白名单暂存树打包 + 产物卫生自检 + 包内重跑测试。

    直接打包工作目录会带进 1500+ 个私有文件（真实持仓、日报历史、预览截图、
    .workbuddy/、skill-studio/），必须走白名单。
    """
    import tempfile
    import zipfile

    ver = read_version() or "0.0.0"
    if not out_path:
        out_path = (ENG / "skill-studio" / "20261022-091618-stockdaily" / "05-发布"
                    / f"daily-portfolio-analysis-v{ver}.zip")
    out_path = Path(out_path)

    with tempfile.TemporaryDirectory() as td:
        stage_root = Path(td) / "daily-portfolio-analysis"
        stage_root.mkdir()
        n = _build_staging(stage_root)
        print(f"[package] 暂存树：{n} 个受管文件（版本 {ver}，eol={fingerprint.EOL}）")

        # ---- 卫生自检 1：混入私有文件？ ----
        leaked = [str(f.relative_to(stage_root)).replace("\\", "/")
                  for f in stage_root.rglob("*") if f.is_file()]
        bad = [x for x in leaked for pat in _PKG_PRIVATE_PATTERNS if pat in x]
        print(f"[package] 私有文件混入：{len(bad)} 个"
              f"{' [OK]' if not bad else ' [X] ' + str(bad[:5])}")

        # ---- 卫生自检 2：该有的齐不齐？ ----
        missing = [e for e in _PKG_EXPECT
                   if not any(e in x for x in leaked)]
        print(f"[package] 必需项缺失：{len(missing)} 个"
              f"{' [OK]' if not missing else ' [X] ' + str(missing)}")

        # ---- 卫生自检 3：主题变量名集合对称性 ----
        css = (stage_root / "assets" / "style.css").read_text(encoding="utf-8")
        sym = _css_var_symmetry(css)
        print(f"[package] 主题变量名对称性：{sym}")

        if dry_run:
            print("[package] dry-run：未写 zip")
            for x in leaked:
                print("   ", x)
            return 0 if not bad and not missing else 1

        out_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(stage_root.rglob("*")):
                if f.is_file():
                    z.write(f, f.relative_to(stage_root.parent).as_posix())
        size_kb = out_path.stat().st_size / 1024
        print(f"[package] 已写出 {out_path}（{size_kb:.1f} KB）")

        # ---- 包内解出重跑测试 ----
        ex = Path(td) / "verify"
        with zipfile.ZipFile(out_path) as z:
            z.extractall(ex)
        pkg = ex / "daily-portfolio-analysis"
        rc = subprocess.run([sys.executable, "-m", "unittest", "discover",
                             "-s", "tests", "-p", "test_*.py"],
                            cwd=str(pkg), capture_output=True, text=True)
        tail = [l for l in rc.stderr.strip().splitlines()
                if l.startswith(("Ran ", "OK", "FAILED"))]
        print(f"[package] 包内重跑测试：{' | '.join(tail)} "
              f"{'[OK]' if rc.returncode == 0 else '[X]'}")
        if rc.returncode != 0:
            return 1
    return 0 if not bad and not missing else 1


def _css_var_symmetry(css_text):
    """浅色 :root 与深色 [data-theme=dark] 的变量名集合是否对称。

    必须按**变量名**比对，不能按 hex 值比对 —— a11y_check 的 vars_from_block
    只收 hex，rgba()/color-mix() 形式的变量它完全看不见，会漏掉最该拦的那类。
    主题无关的字体栈 --serif / --mono 只在 :root 定义一次，列入白名单。
    """
    def block(sel):
        i = css_text.find(sel)
        if i < 0:
            return ""
        j = css_text.find("{", i)
        depth = 0
        for k in range(j, len(css_text)):
            if css_text[k] == "{":
                depth += 1
            elif css_text[k] == "}":
                depth -= 1
                if depth == 0:
                    return css_text[j + 1:k]
        return ""

    light = set(re.findall(r"(--[\w-]+)\s*:", block(":root{")))
    dark = set(re.findall(r"(--[\w-]+)\s*:", block('[data-theme="dark"]')))
    ignored = {"--serif", "--mono"}
    only_light = (light - dark) - ignored
    only_dark = (dark - light) - ignored
    if only_light or only_dark:
        return (f"[X] 不对称 仅浅色={sorted(only_light)} "
                f"仅深色={sorted(only_dark)}")
    return f"[OK] 对称（浅 {len(light)} / 深 {len(dark)}，忽略字体栈）"


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
    fl = sub.add_parser("fixlinks", help="批量修断链（默认只报告，--write 才落盘）")
    fl.add_argument("--write", action="store_true", help="真的写盘（默认只报告）")
    pk = sub.add_parser("package", help="白名单暂存树打包 + 产物卫生自检")
    pk.add_argument("--out", help="zip 输出路径")
    pk.add_argument("--dry-run", action="store_true", help="只自检不出包")
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
    if args.cmd == "fixlinks":
        sys.exit(fixlinks(write=args.write))
    if args.cmd == "package":
        sys.exit(package(args.out, args.dry_run))


if __name__ == "__main__":
    main()
