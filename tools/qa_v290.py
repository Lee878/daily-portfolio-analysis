"""v2.8.0 QA 验收：逐项核验并输出结果表。"""
import json
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, "scripts")
import release as r  # noqa: E402
import fingerprint as fp  # noqa: E402

res = []


def rec(name, ok, detail=""):
    res.append((name, ok, detail))


# ---- 1. 版本四处一致 ----
v = r.read_version()
pm_text = Path("pyproject.toml").read_text(encoding="utf-8")
mm = re.search(r'(?m)^version\s*=\s*"?([\w.]+)"?', pm_text)
pm = mm.group(1) if mm else "<未匹配>"
sk = re.search(r"(?m)^version:\s*(\S+)", Path("SKILL.md").read_text(encoding="utf-8")).group(1)
ch = re.search(r"(?m)^## (v[\d.]+)", Path("CHANGELOG.md").read_text(encoding="utf-8")).group(1)
man = json.loads(Path("MANIFEST.json").read_text(encoding="utf-8"))
vers = {v, pm, sk, ch.lstrip("v"), man["version"]}
rec("版本五处一致", len(vers) == 1,
    f"VERSION={v} pyproject={pm} SKILL={sk} CHANGELOG={ch} MANIFEST={man['version']}")

# ---- 2. 指纹 ----
rec("MANIFEST 标注 eol=lf", man.get("eol") == "lf", f"eol={man.get('eol')}")
rc = r.verify_target(r.ENG, "ENG")
rec("指纹 verify 一致", rc == 0, f"exit={rc} / {man['file_count']} 文件")
rec("MANIFEST 不含自引用", "MANIFEST.json" not in man["files"], "")

# ---- 3. 受管清单 ----
m = r.managed_files()
rec("受管清单 ≥ 61", len(m) >= 61, f"实际 {len(m)}")
rec("adapters 全部纳入", sum(1 for x in m if x.startswith("scripts/adapters/")) == 7,
    f"{sum(1 for x in m if x.startswith('scripts/adapters/'))} 个")
rec("examples 全部纳入", sum(1 for x in m if x.startswith("examples/")) == 3,
    f"{sum(1 for x in m if x.startswith('examples/'))} 个")
rec("config 只收 example", all("example" in x for x in m if x.startswith("config/")),
    str([x for x in m if x.startswith("config/")]))
rec("清单无 .bak / 无 ui-preview 产物",
    not any(".bak" in x or x.endswith(".png") or "ui-preview" in x for x in m), "")

# ---- 4. 测试 ----
p = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests",
                    "-p", "test_*.py"], capture_output=True, text=True)
tail = " | ".join(l for l in p.stderr.splitlines() if l.startswith(("Ran ", "OK", "FAILED")))
rec("全量测试通过", p.returncode == 0, tail)
rec("测试数 ≥ 164", "Ran 164" in p.stderr, "")

# ---- 5. 上架校验（暂存树） ----
DST = Path(tempfile.mkdtemp(prefix="daily-portfolio-analysis-"))
r._build_staging(DST)
V = (r"C:\Users\Lenovo\.workbuddy\plugins\cache\experts\skill-lifecycle-studio"
     r"\2.0.0\skills\skill-lifecycle-toolkit\scripts\validate_skill.py")
vp = subprocess.run([sys.executable, V, str(DST), "--json"], capture_output=True, text=True)
d = json.loads(vp.stdout)
e, w = d.get("errors", []), d.get("warnings", [])
rec("上架校验 error = 0（暂存树）", len(e) == 0, f"error={len(e)} warn={len(w)} exit={vp.returncode}")
for x in e[:5]:
    rec("  └ 残留错误", False, x["message"][:120])

# ---- 6. frontmatter ----
fm = Path("SKILL.md").read_text(encoding="utf-8").split("---")[1]
for f in ("name", "description", "description_zh", "description_en", "version", "author"):
    rec(f"frontmatter 有 {f}", bool(re.search(rf"(?m)^{f}:", fm)), "")
rec("license 已移入 metadata", "license:" in fm.split("metadata:", 1)[1], "")
rec("顶层无 license 字段", not re.search(r"(?m)^license:", fm), "")

# ---- 7. 双主题 CSS ----
css = Path("assets/style.css").read_text(encoding="utf-8")


def blk(sel):
    i = css.find(sel)
    j = css.find("{", i)
    depth = 0
    for k in range(j, len(css)):
        if css[k] == "{":
            depth += 1
        elif css[k] == "}":
            depth -= 1
            if depth == 0:
                return css[j + 1:k]
    return ""


L = set(re.findall(r"(--[\w-]+)\s*:", blk(":root{")))
D = set(re.findall(r"(--[\w-]+)\s*:", blk('[data-theme="dark"]')))
rec("变量名集合对称（仅 serif/mono 豁免）",
    (L - D) <= {"--serif", "--mono"} and not (D - L),
    f"浅 {len(L)} / 深 {len(D)}")
rec("深色块位于浅色块之后", css.find('[data-theme="dark"]') > css.find(":root{"), "")
rec("4 个 warn 语义色双套齐全",
    all(f"--warn-{s}" in L and f"--warn-{s}" in D for s in ("bg", "fg", "strong", "rule")), "")
rec("无 --gold-line 残留（已裁决撤回）", "--gold-line" not in css, "")
rec("无 color-mix 依赖（旧 WebView 兼容）", "color-mix" not in css, "")

# ---- 8. a11y ----
ap = subprocess.run([sys.executable, "docs/ui-preview/a11y_check.py"],
                    capture_output=True, text=True)
rec("a11y 双主题对比度 exit 0", ap.returncode == 0, f"exit={ap.returncode}")
rec("a11y 覆盖 ink3 on paper", "ink3" in ap.stdout and "paper" in ap.stdout, "")

# ---- 9. 隐私 ----
gi = Path(".gitignore").read_text(encoding="utf-8")
rec(".gitignore 含 *.bak", "*.bak" in gi, "")
rec(".gitignore 排除 ui-preview html/png",
    "docs/ui-preview/*.html" in gi and "docs/ui-preview/*.png" in gi, "")
tracked = subprocess.run(["git", "ls-files"], capture_output=True, text=True).stdout
rec("git 未跟踪 .bak", ".bak" not in tracked, "")
rec("git 未跟踪 ui-preview html/png",
    not any(x in tracked for x in ("ui-preview/a-terminal-preview.html",
                                   "ui-preview/b-brief-preview.html")), "")

# ---- 10. 打包 ----
zp = Path("skill-studio/20261022-091618-stockdaily/05-发布/daily-portfolio-analysis-v2.8.0.zip")
rec("zip 产物存在", zp.exists(), f"{zp.stat().st_size/1024:.1f} KB" if zp.exists() else "缺失")
if zp.exists():
    with zipfile.ZipFile(zp) as z:
        names = z.namelist()
    rec("zip 顶层目录正确", all(n.startswith("daily-portfolio-analysis/") for n in names),
        f"{len(names)} 项")
    blob = " ".join(names)
    rec("zip 无私有文件混入",
        not any(x in blob for x in ("holdings.md", "watchlist.md", "notify.json",
                                    "delivery.json", "data/daily-reports", ".bak", ".png")), "")

# ---- 11. 文档 ----
inst = Path("docs/INSTALL.md")
rec("INSTALL 文档存在", inst.exists(), f"{len(inst.read_text(encoding='utf-8').splitlines())} 行" if inst.exists() else "")
if inst.exists():
    it = inst.read_text(encoding="utf-8")
    rec("INSTALL 明示无 tag/Release（不谎报）",
        "不是 GitHub tag" in it and "不创建标准 Release" not in it or "版本标记是**分支" in it, "")

# ---- 输出 ----
print(f"{'结果':6s} {'检查项':42s} 证据")
print("-" * 112)
ok_n = 0
for name, ok, detail in res:
    if ok:
        ok_n += 1
    print(f"{'PASS' if ok else 'FAIL':6s} {name:42s} {detail}")
print("-" * 112)
print(f"合计 {ok_n}/{len(res)} 通过")
sys.exit(0 if ok_n == len(res) else 1)
