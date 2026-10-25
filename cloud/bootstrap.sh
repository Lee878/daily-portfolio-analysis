#!/usr/bin/env bash
# ============================================================================
# cloud/bootstrap.sh —— 云端沙箱每次任务开头执行
# 作用：确保仓库就位 + 从 secrets 注入隐私配置 + 跑门禁自检
# 设计原则：幂等、可重复运行；沙箱无论是否持久化都能工作
# ============================================================================
set -euo pipefail

REPO_DIR=/workspace/dpa
BRANCH=main
REMOTE=https://github.com/Lee878/daily-portfolio-analysis.git

echo "[bootstrap] 仓库准备…"
if [ -d "$REPO_DIR/.git" ]; then
  git -C "$REPO_DIR" pull --ff-only 2>/dev/null || echo "[bootstrap] pull 失败，沿用现有副本"
else
  git clone --depth 1 --branch "$BRANCH" "$REMOTE" "$REPO_DIR" \
    || echo "[bootstrap] ⚠️ clone 失败（检查 git/网络）；若工作区已挂载仓库请忽略"
fi
cd "$REPO_DIR"

echo "[bootstrap] 初始化本地配置（生成 holdings/watchlist 模板）…"
python3 scripts/setup_local.py 2>/dev/null || true

# ---- 方法 B（默认）：从 secrets 注入隐私文件 ----
# secrets 名称：HOLDINGS_MD / NOTIFY_JSON / DELIVERY_JSON
# 未设置则该文件沿用 setup_local 生成的模板（不含真实数据，仅供流程跑通）
inject() {
  local name="$1" target="$2"
  local val="${!name:-}"
  if [ -n "$val" ]; then
    printf '%s' "$val" > "$target"
    echo "[bootstrap] ✅ 已写入 $target (from secret $name)"
  else
    echo "[bootstrap] ⚠️  未设置 secret $name，沿用模板 $target"
  fi
}
inject HOLDINGS_MD   config/holdings.md
inject NOTIFY_JSON   config/notify.json
inject DELIVERY_JSON config/delivery.json

# ---- 方法 A（可选）：若设置了私有持仓仓库，则优先从其拉取最新 holdings ----
# secrets 名称：HOLDINGS_REPO（如 github.com/you/private-holdings.git）+ HOLDINGS_TOKEN
if [ -n "${HOLDINGS_REPO:-}" ] && [ -n "${HOLDINGS_TOKEN:-}" ]; then
  echo "[bootstrap] 从私有仓拉取持仓：$HOLDINGS_REPO"
  tmp=$(mktemp -d)
  if git clone "https://${HOLDINGS_TOKEN}@${HOLDINGS_REPO#https://}" "$tmp/holdings" 2>/dev/null; then
    if [ -f "$tmp/holdings/holdings.md" ]; then
      cp "$tmp/holdings/holdings.md" config/holdings.md
      echo "[bootstrap] ✅ 已从私有仓覆盖 config/holdings.md"
    fi
  else
    echo "[bootstrap] ⚠️ 私有仓 clone 失败，回退到 secret/模板"
  fi
  rm -rf "$tmp"
fi

echo "[bootstrap] 门禁自检…"
python3 scripts/release.py doctor || echo "[bootstrap] ⚠️  doctor 未全绿，详见上方；任务仍继续"

echo "[bootstrap] 完成。REPO_DIR=$REPO_DIR"
