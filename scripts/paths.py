#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全项目路径唯一真相（v2.4.0）。

背景：旧版脚本各自用 ``Path(__file__).parent.parent`` 推导 assets / references /
holdings / daily-reports，目录一调整就全部错位——2026-10-21 重排目录后，
根目录跑测试 4 个 ImportError、release.py doctor 的 MANIFEST 32 项全部"缺失"、
渲染器找不到 style.css。此后**只允许从本模块取路径**，不要在脚本里再算 parent。

解析优先级：显式参数 > 环境变量 > 项目默认值。
所有函数返回 Path（找不到时返回 None，由调用方决定提示与退出码）。
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

# scripts/paths.py -> scripts/ -> 仓库根
ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
ASSETS = ROOT / "assets"
REFERENCES = ROOT / "references"
EXAMPLES = ROOT / "examples"
TESTS = ROOT / "tests"
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
DEFAULT_REPORT_ROOT = DATA_DIR / "daily-reports"

ENV_CONFIG_DIR = "DAILY_CONFIG_DIR"
ENV_REPORT_ROOT = "DAILY_REPORT_ROOT"
ENV_HOLDINGS = "DAILY_HOLDINGS"
ENV_BRIEF = "DAILY_BRIEF"


def _env_path(name: str) -> Path | None:
    raw = (os.environ.get(name) or "").strip()
    return Path(raw).expanduser() if raw else None


def config_dir() -> Path:
    """配置目录：holdings.md / watchlist.md / watchlist_brief.json 所在处。"""
    p = _env_path(ENV_CONFIG_DIR)
    return p if p else CONFIG_DIR


def report_root() -> Path:
    """报告与证据根目录（daily-reports/）。"""
    p = _env_path(ENV_REPORT_ROOT)
    return p if p else DEFAULT_REPORT_ROOT


def resolve_holdings(explicit: str | Path | None = None) -> Path | None:
    """按 显式 > 环境变量 > config/holdings.md > 当前目录/holdings.md 顺序找持仓档案。"""
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    env = _env_path(ENV_HOLDINGS)
    if env:
        candidates.append(env)
    candidates.append(config_dir() / "holdings.md")
    candidates.append(Path.cwd() / "holdings.md")
    for c in candidates:
        if c.exists():
            return c
    return None


def watchlist_path(holdings: Path | None = None) -> Path | None:
    """关注库位置。

    给了 holdings 就**只认同级** watchlist.md（避免临时目录/测试串到真实 config）；
    没给才回落到 config/watchlist.md。
    """
    if holdings:
        cand = holdings.parent / "watchlist.md"
        return cand if cand.exists() else None
    cand = config_dir() / "watchlist.md"
    return cand if cand.exists() else None


def brief_path() -> Path:
    """关注库"降级名单"文件（v2.4.0 起语义反转，缺省 = 全部深度分析）。"""
    p = _env_path(ENV_BRIEF)
    return p if p else config_dir() / "watchlist_brief.json"


def resolve_report_root(explicit: str | Path | None = None,
                        holdings: Path | None = None) -> Path:
    """报告根目录。

    显式 > 环境变量 > 便携模式（holdings 同级已有 daily-reports/）> data/daily-reports。
    """
    if explicit:
        return Path(explicit)
    env = _env_path(ENV_REPORT_ROOT)
    if env:
        return env
    if holdings and (holdings.parent / "daily-reports").is_dir():
        return holdings.parent / "daily-reports"
    return DEFAULT_REPORT_ROOT


def delivery_path() -> Path:
    """送达通道配置（收件人 / 开关），不入库。"""
    return config_dir() / "delivery.json"


def version_info() -> tuple[str, str]:
    """返回 (版本号, MANIFEST 短指纹)；文件缺失时对应为空串。"""
    version = ""
    vf = ROOT / "VERSION.json"
    if vf.exists():
        try:
            version = json.loads(vf.read_text(encoding="utf-8")).get("version", "")
        except Exception:
            version = ""
    build = ""
    mf = ROOT / "MANIFEST.json"
    if mf.exists():
        build = hashlib.sha256(mf.read_bytes()).hexdigest()[:8]
    return version, build


def safe_name(ticker: str) -> str:
    """跨平台安全文件名（与 gate_check/fetch_data 保持同一实现）。"""
    out = str(ticker)
    for ch in (".", "/", ":", chr(92), "*", "?", '"', "<", ">", "|"):
        out = out.replace(ch, "_")
    return out


def ensure_utf8_stdout() -> None:
    """Windows 控制台/计划任务默认 GBK，打印符号会 UnicodeEncodeError。"""
    import sys
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
