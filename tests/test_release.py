#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""release / 版本指纹 / 漂移检测的回归测试（不依赖网络）。

运行：cd scripts && python -m unittest tests.test_release -v
"""
import json
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
    "assets/workbuddy-prompts/pre.md", "assets/workbuddy-prompts/noon.md",
    "assets/workbuddy-prompts/post.md",
]


class ReleaseTests(unittest.TestCase):
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
