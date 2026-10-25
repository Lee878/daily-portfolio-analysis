#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""受管文件指纹的唯一口径（v2.8.0）。

为什么需要这个模块
------------------
本仓库的 ``.gitattributes`` 强制 ``* text=auto eol=lf``（各扩展名另有显式声明），
于是同一份代码在磁盘上有三种形态：

  * git 仓库里的 blob —— **LF** 字节
  * Windows 工作区检出结果 —— **CRLF** 字节
  * Linux / fresh clone / zip 包内 —— **LF** 字节

MANIFEST 若按**工作区原始字节**算 sha256，同一份代码在三种形态下指纹不同：
在 Linux 或 fresh clone 上 ``release.py verify`` 与 ``install_skill.py`` 的副本自检
会集体失败（实测受管 46 文件中 20 个是 CRLF/LF 差异）。

口径
----
  * 文本类（扩展名白名单）→ 先把 CRLF 归一化成 LF，再算 sha256；``bytes`` 同口径
  * 其它扩展名（一律按**原始字节**）→ 直接算 sha256；``bytes`` = 原始长度

硬性约束
--------
归一化**只影响指纹计算**，绝不改写工作区文件的字节。改文件是 git 的职责
（``git add --renormalize`` / ``git checkout``），不是指纹器的职责。

二进制文件不做任何字节级改写：图片 / 压缩包 / 字体的字节序列有实际语义，
无脑替换 \\r\\n 会损坏内容。
"""
from __future__ import annotations

import hashlib
from pathlib import Path

# MANIFEST 里标注的换行口径（写进 MANIFEST 顶层，供人读）
EOL = "lf"

# ---------------------------------------------------------------- 文本类白名单
# 命中 → 做 CRLF→LF 归一化。小写、带点。
TEXT_EXTENSIONS = frozenset({
    ".py", ".md", ".css", ".html", ".htm", ".json", ".yml", ".yaml",
    ".txt", ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".sh", ".bash",
    ".zsh", ".cfg", ".ini", ".toml", ".xml", ".svg", ".csv", ".tsv",
    ".rst", ".bat", ".ps1", ".lock", ".properties", ".editorconfig",
    ".diff", ".patch", ".sql", ".log",
})

# ---------------------------------------------------------------- 二进制黑名单
# 命中 → 一律按原始字节算。列出来是为了"显式比隐式安全"：
# 万一以后加了新扩展名，黑名单里的至少不会被误当成文本。
BINARY_EXTENSIONS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".tiff",
    ".gz", ".bz2", ".xz", ".zip", ".7z", ".tar", ".tgz", ".rar",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".mp3", ".mp4", ".avi", ".mov", ".mkv", ".wav",
    ".so", ".dll", ".dylib", ".exe", ".bin", ".pkl",
    ".pyc", ".pyo", ".pyd", ".db", ".sqlite", ".sqlite3",
})


def _looks_like_text(raw: bytes) -> bool:
    """无扩展名文件的内容启发式（与 git ``text=auto`` 的判定思路一致）。

    没有 NUL 字节、且能按 UTF-8 解码 → 当文本处理。
    这样 ``LICENSE`` / ``Makefile`` / ``.gitignore`` 这类没有扩展名的
    源文件也能正确归一化，而不是因为"猜不出类型"就被当成二进制。
    """
    if b"\x00" in raw:
        return False
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _decide_text(path: Path, raw: bytes) -> bool:
    """按扩展名判定；扩展名缺失时才回退到内容启发式。"""
    suffix = Path(path).suffix.lower()
    if suffix in BINARY_EXTENSIONS:
        return False
    if suffix in TEXT_EXTENSIONS:
        return True
    if suffix:
        # 未知扩展名 → 保守按二进制处理（宁可漏归一化，也不要损坏字节）
        return False
    return _looks_like_text(raw)


def is_text_file(path: Path) -> bool:
    """该路径是否按"文本类"处理（→ 指纹前做 CRLF→LF 归一化）。"""
    p = Path(path)
    return _decide_text(p, p.read_bytes())


def normalize_bytes(raw: bytes, path: Path) -> bytes:
    """文本类内容把 CRLF 归一化成 LF；其余原样返回。

    只做 ``\\r\\n`` → ``\\n``，不碰单独的 ``\\r``（老 Mac 换行）与 ``\\n``——
    git 的 ``eol=lf`` 做的也是同一件事。
    """
    if not _decide_text(Path(path), raw):
        return raw
    return raw.replace(b"\r\n", b"\n")


def sha256_of(path: Path) -> str:
    """归一化后的 sha256（文本类归一化 / 二进制按原始字节）。"""
    p = Path(path)
    raw = p.read_bytes()
    return hashlib.sha256(normalize_bytes(raw, p)).hexdigest()


def bytes_of(path: Path) -> int:
    """归一化后的字节长度（与 :func:`sha256_of` 同一口径）。"""
    p = Path(path)
    return len(normalize_bytes(p.read_bytes(), p))


def raw_sha256_of(path: Path) -> str:
    """**旧口径**：按工作区原始字节算 sha256。

    仅供对比验证使用（证明"原始字节口径会漂移、归一化口径不漂移"），
    业务代码不要调用。
    """
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


if __name__ == "__main__":  # pragma: no cover - 手工自检入口
    import sys

    if len(sys.argv) < 2:
        print("用法：python scripts/fingerprint.py <file> [...]")
        raise SystemExit(2)
    for arg in sys.argv[1:]:
        p = Path(arg)
        print(f"{p}\ttext={is_text_file(p)}\tsha256={sha256_of(p)}\tbytes={bytes_of(p)}")
