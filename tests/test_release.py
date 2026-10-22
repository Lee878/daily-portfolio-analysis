#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""release / 版本指纹 / 漂移检测的回归测试（不依赖网络）。

运行：cd scripts && python -m unittest tests.test_release -v
"""
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import release as r  # noqa: E402
import run_daily as rd  # noqa: E402

KEY_FILES = [
    "SKILL.md", "README.md",
    "scripts/run_daily.py", "scripts/gate_check.py", "scripts/fetch_data.py",
    "scripts/release.py", "scripts/paths.py",
    "scripts/derive_indicators.py",
    "references/mcp-data-source.md",
    "assets/workbuddy-prompts/pre.md", "assets/workbuddy-prompts/noon.md",
    "assets/workbuddy-prompts/post.md",
]


class ReleaseTests(unittest.TestCase):
    def test_skill_version_matches_engine(self):
        """SKILL.md 的 version 必须与 VERSION.json 一致。

        bump 靠正则改 frontmatter，正则写错（例如 \\s 被误写成 //s）会静默
        失效——版本号看着升了，skill 元数据还停在旧值。这条用例兜住它。
        """
        text = (r.ENG / "SKILL.md").read_text(encoding="utf-8")
        m = re.search(r"(?m)^version:\s*(\S+)\s*$", text)
        self.assertIsNotNone(m, "SKILL.md frontmatter 缺 version 字段")
        self.assertEqual(m.group(1), r.read_version())

    def test_version_and_manifest(self):
        # 不写死版本号：断言三处版本一致（否则每次 bump 都要改测试）
        v = r.read_version()
        self.assertTrue(v)
        self.assertTrue(r.MANIFEST_F.exists())
        man = json.loads(r.MANIFEST_F.read_text(encoding="utf-8"))
        self.assertEqual(man["version"], v)
        self.assertEqual(man["file_count"], len(man["files"]))
        for f in KEY_FILES:
            self.assertIn(f, man["files"], f"MANIFEST 缺 {f}")

    def test_verify_eng_clean(self):
        self.assertEqual(r.verify_target(r.ENG, "ENG"), 0)

    def test_engine_version_info(self):
        version, build = rd.engine_version_info()
        self.assertEqual(version, r.read_version())
        self.assertEqual(len(build), 8)

    def test_readme_counts_are_accurate(self):
        """README 里「N 个核心脚本 / N 项回归测试」必须等于实际值。

        这类数字靠手写必然漂——本次 review 实测中发现 README 声称
        13 个脚本 / 126 项测试，实际是 12 / 121，两处都偏了。
        而且偏的方向是「说多了」，比说少了更误导：读者会以为有东西没找到。
        这里改成现算，让数字自己跟着代码走。
        """
        text = (r.ENG / "README.md").read_text(encoding="utf-8")

        actual_scripts = len(list((r.ENG / "scripts").glob("*.py")))
        m_script = re.search(r"(\d+)\s*个核心脚本", text)
        self.assertIsNotNone(m_script, "README 未声明「N 个核心脚本」")
        self.assertEqual(
            int(m_script.group(1)), actual_scripts,
            f"README 声称 {m_script.group(1)} 个脚本，实际 {actual_scripts} 个",
        )

        # countTestCases() 只数叶子、不执行，不会触发递归
        loader = unittest.TestLoader()
        suite = loader.discover(str(r.ENG / "tests"), top_level_dir=str(r.ENG / "tests"))
        actual_tests = suite.countTestCases()
        m_test = re.search(r"(\d+)\s*项回归测试", text)
        self.assertIsNotNone(m_test, "README 未声明「N 项回归测试」")
        self.assertEqual(
            int(m_test.group(1)), actual_tests,
            f"README 声称 {m_test.group(1)} 项测试，实际 {actual_tests} 项",
        )

    def test_verify_detects_drift_then_matches(self):
        man = json.loads(r.MANIFEST_F.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            # 按 MANIFEST 铺一份正确副本（等价确定性同步）
            for rel in man["files"]:
                dst = root / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(r.ENG / rel, dst)
            self.assertEqual(r.verify_target(root, "COPY"), 0)
            # 篡改一个受管文件 → 必须检出漂移
            rel0 = "SKILL.md"
            (root / rel0).write_text("tampered content", encoding="utf-8")
            self.assertEqual(r.verify_target(root, "COPY"), 1)
            # 恢复 → 再次一致
            shutil.copyfile(r.ENG / rel0, root / rel0)
            self.assertEqual(r.verify_target(root, "COPY"), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
