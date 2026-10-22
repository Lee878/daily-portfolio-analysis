#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地初始化：建目录、复制模板、检查依赖（幂等，可重复运行）。

    python scripts/setup_local.py            # 只补缺失项，不动已有配置
    python scripts/setup_local.py --force    # 覆盖 config/ 下的示例文件（会丢真实数据，慎用）
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402


def _copy_if_missing(src: Path, dst: Path, label: str, force: bool) -> None:
    if dst.exists() and not force:
        print(f"  跳过 {label}（已存在，保留你的数据）")
        return
    if not src.exists():
        print(f"  [!] 缺模板 {src}，跳过 {label}")
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    print(f"  创建 {label} ← examples/{src.name}")


def _write_if_missing(path: Path, payload: dict, label: str) -> None:
    if path.exists():
        print(f"  跳过 {label}（已存在）")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  创建 {label}")


def main():
    paths.ensure_utf8_stdout()
    ap = argparse.ArgumentParser(description="本地初始化")
    ap.add_argument("--force", action="store_true",
                    help="覆盖 config/ 下已有文件（会丢掉真实持仓，慎用）")
    args = ap.parse_args()

    print("=" * 60)
    print(f"仓库根：{paths.ROOT}")
    print("=" * 60)

    print("1) 目录")
    for d in (paths.config_dir(), paths.report_root() / "evidence"):
        d.mkdir(parents=True, exist_ok=True)
        print(f"  {d}")

    print("2) 配置模板")
    _copy_if_missing(paths.EXAMPLES / "holdings.example.md",
                     paths.config_dir() / "holdings.md", "holdings.md", args.force)
    _copy_if_missing(paths.EXAMPLES / "watchlist.example.md",
                     paths.config_dir() / "watchlist.md", "watchlist.md", args.force)
    _write_if_missing(paths.brief_path(), {
        "_comment": "关注库降级名单：数组里的 ticker 只做简列，其余默认全部深度分析。留空 = 全深做。",
        "pre": [], "noon": [], "post": [],
    }, "watchlist_brief.json（空 = 全部深度分析）")
    _write_if_missing(paths.delivery_path(), {
        "_comment": "报告送达配置。enabled=true 时由定时任务把 HTML 作为附件发到 to。",
        "enabled": False,
        "to": "",
        "subject_prefix": "[持仓报告]",
    }, "delivery.json（邮件推送，默认关闭）")

    print("3) 可选依赖（不装也能跑，只是取数靠 agent 补证）")
    for mod, hint in (("akshare", "A股/港股行情"), ("yfinance", "美股行情")):
        try:
            __import__(mod)
            print(f"  [OK] {mod}")
        except ImportError:
            print(f"  [!] 未安装 {mod}（{hint}）：python -m pip install {mod}")

    print("4) 下一步")
    print("  1. 编辑 config/holdings.md、config/watchlist.md")
    print("  2. python scripts/release.py doctor")
    print("  3. python scripts/run_daily.py fetch --session pre --no-network")
    print("  4. 填 config/delivery.json（要手机收报告的话）")
    print("  5. python scripts/install_skill.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
