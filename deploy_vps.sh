#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# DEPLOY — Push code to VPS and restart PM2 orchestrator
# ══════════════════════════════════════════════════════════════════════════════
# Usage:
#   bash deploy_vps.sh              # full deploy
#   bash deploy_vps.sh --dry-run    # rsync --dry-run only
# ══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

REMOTE_HOST="${DEPLOY_HOST:-root@172.105.252.194}"
REMOTE_DIR="/opt/trading-bridge"
LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"
DRY_RUN=""
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN="--dry-run"

echo "═══════════════════════════════════════════════════════════"
echo "  TRADING BRIDGE — DEPLOY TO ${REMOTE_HOST}"
echo "═══════════════════════════════════════════════════════════"

# ── 1. Rsync code ──────────────────────────────────────────────────────
echo ""
echo "[1/3] Syncing code → ${REMOTE_HOST}:${REMOTE_DIR}"

rsync -avz --delete \
  --exclude='venv/' \
  --exclude='.env' \
  --exclude='__pycache__/' \
  --exclude='.git/' \
  --exclude='logs/' \
  --exclude='.pytest_cache/' \
  --exclude='node_modules/' \
  "${LOCAL_DIR}/" "${REMOTE_HOST}:${REMOTE_DIR}/" ${DRY_RUN}

if [[ -n "${DRY_RUN}" ]]; then
  echo "  (dry run — no changes made)"
  exit 0
fi

# ── 2. Restart PM2 on remote ──────────────────────────────────────────
echo ""
echo "[2/3] Flushing stale PM2 processes and starting orchestrator"

ssh "${REMOTE_HOST}" bash -s <<'REMOTE'
set -euo pipefail
cd /opt/trading-bridge

# Ensure log directory exists
mkdir -p logs/pm2

# Flush all stale PM2 processes
pm2 delete all 2>/dev/null || true

# Start the consolidated orchestrator
pm2 start ecosystem.config.js --update-env

# Persist process list for reboot survival
pm2 save

echo ""
echo "  PM2 process list saved"
REMOTE

# ── 3. Verify ─────────────────────────────────────────────────────────
echo ""
echo "[3/3] Verifying deployment"

ssh "${REMOTE_HOST}" bash -s <<'REMOTE'
echo ""
echo "── PM2 Status ──"
pm2 status

echo ""
echo "── Orchestrator Logs (last 20 lines) ──"
pm2 logs omni-orchestrator --lines 20 --nostream
REMOTE

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  DEPLOY COMPLETE"
echo "═══════════════════════════════════════════════════════════"
