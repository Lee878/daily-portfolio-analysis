#!/usr/bin/env bash
# ============================================================================
# cloud/bootstrap.sh —— 云端沙箱每次任务开头执行
# 作用：确保仓库就位 + 从私有仓/密文注入隐私配置 + 跑门禁自检
# 设计原则：幂等、可重复运行；沙箱无论是否持久化都能工作
#
# 持仓注入策略（已选方法 A：私有仓库存持仓）：
#   1) 若设置了 HOLDINGS_REPO + HOLDINGS_TOKEN → 从你的私有仓拉最新 holdings.md（主路径）
#   2) 否则若设置了 HOLDINGS_MD → 用密文里的持仓文本兜底（方法 B）
#   3) 都没有 → 沿用 setup_local 生成的模板（不含真实数据，仅供流程跑通）
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

# ---- 持仓注入：方法 A（私有仓，推荐）优先，方法 B（secret 文本）兜底 ----
pulled=0
if [ -n "${HOLDINGS_REPO:-}" ] && [ -n "${HOLDINGS_TOKEN:-}" ]; then
  echo "[bootstrap] 从私有仓拉取持仓：$HOLDINGS_REPO"
  tmp=$(mktemp -d)
  if git clone "https://${HOLDINGS_TOKEN}@${HOLDINGS_REPO#https://}" "$tmp/holdings" 2>/dev/null; then
    if [ -f "$tmp/holdings/holdings.md" ]; then
      cp "$tmp/holdings/holdings.md" config/holdings.md
      echo "[bootstrap] ✅ 已从私有仓写入 config/holdings.md"
      pulled=1
    else
      echo "[bootstrap] ⚠️ 私有仓内无 holdings.md，回退 secret/模板"
    fi
  else
    echo "[bootstrap] ⚠️ 私有仓 clone 失败（检查 token/仓库可见性），回退 secret/模板"
  fi
  rm -rf "$tmp"
fi

# 方法 B 兜底：仅当 A 未成功拉取时，尝试用密文文本
if [ "$pulled" -eq 0 ]; then
  val="${HOLDINGS_MD:-}"
  if [ -n "$val" ]; then
    printf '%s' "$val" > config/holdings.md
    echo "[bootstrap] ✅ 已从 secret HOLDINGS_MD 写入 config/holdings.md"
  else
    echo "[bootstrap] ⚠️  未设置持仓来源（HOLDINGS_REPO/HOLDINGS_MD），沿用模板"
  fi
fi

# ---- 推送通道（Bark/COS）始终用密文注入 ----
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
inject NOTIFY_JSON   config/notify.json
inject DELIVERY_JSON config/delivery.json

echo "[bootstrap] 门禁自检…"
python3 scripts/release.py doctor || echo "[bootstrap] ⚠️  doctor 未全绿，详见上方；任务仍继续"

echo "[bootstrap] 完成。REPO_DIR=$REPO_DIR 持仓来源=$([ "$pulled" -eq 1 ] && echo 私有仓 || echo secret/模板)"
