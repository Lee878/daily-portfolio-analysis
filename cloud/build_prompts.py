#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 assets/workbuddy-prompts/ 生成云端版 prompt（替换路径与解释器）。

云端沙箱差异：
  - {{REPO_DIR}} -> /workspace/dpa
  - python "..." -> python3 "..."
  - 「本机」措辞 -> 「云端 /workspace/dpa」
仅做机械替换 + 头部加一段云端须知，不动流程逻辑。
"""
from __future__ import annotations

import io
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # 仓库根
SRC = ROOT / "assets" / "workbuddy-prompts"
OUT = ROOT / "cloud" / "prompts"
CLOUD_REPO = "/workspace/dpa"

NOTE = (
    "> **云端运行模式（WorkBuddy CloudAgent 沙箱）**\n"
    "> - `REPO_DIR` = `/workspace/dpa`，所有 `python` 命令已改为 `python3`。\n"
    "> - 持仓 / 通知(Bark) / COS 配置由 `cloud/bootstrap.sh` 从 secrets 注入，"
    "任务开始时已是最新（方法 B：直接存文本）。\n"
    "> - 数据源优先走 **NeoData MCP**，需云端 Agent 已连接该连接器；"
    "它走平台侧通道，不受本机代理影响。\n"
    "> - 其余流程、门禁、输出规范与本机完全一致。\n\n"
)

REPL = [
    ("{{REPO_DIR}}", CLOUD_REPO),
    ('python "', 'python3 "'),
    ("## 路径常量（本机）", "## 路径常量（云端：/workspace/dpa）"),
]


def transform(text: str) -> str:
    for a, b in REPL:
        text = text.replace(a, b)
    # 把裸 python 命令（非 python3）也归一，防止遗漏
    text = re.sub(r"(?<![\w/])python (?=scripts/)", "python3 ", text)
    return NOTE + text


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name in ("pre.md", "noon.md", "post.md"):
        src = SRC / name
        if not src.exists():
            print("跳过（源不存在）:", src)
            continue
        out = OUT / f"cloud-{name}"
        out.write_text(transform(src.read_text(encoding="utf-8")), encoding="utf-8")
        print("已生成:", out.relative_to(ROOT))


if __name__ == "__main__":
    main()
