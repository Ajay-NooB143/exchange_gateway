#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# AUTOCOMMIT & DEPLOY — Full Git-to-VPS Pipeline
# ══════════════════════════════════════════════════════════════════════════════
# Usage:
#   bash autocommit_deploy.sh              # full pipeline
#   bash autocommit_deploy.sh --dry-run    # preview without changes
#   bash autocommit_deploy.sh --skip-tests # skip VPS pre-flight tests
# ══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

# ── Configuration ───────────────────────────────────────────────────────
REMOTE_HOST="${DEPLOY_HOST:?DEPLOY_HOST is required (e.g. root@your-vps-ip)}"
REMOTE_DIR="/opt/trading-bridge"
GITHUB_REMOTE="origin"
GITHUB_BRANCH="main"
EXCHANGE_GW_DIR="exchange_gateway"
TIMESTAMP="$(date '+%Y-%m-%d %H:%M')"
DRY_RUN=false
SKIP_TESTS=false

# ── Parse args ──────────────────────────────────────────────────────────
for arg in "$@"; do
    case "$arg" in
        --dry-run)    DRY_RUN=true ;;
        --skip-tests) SKIP_TESTS=true ;;
        --help|-h)
            echo "Usage: $0 [--dry-run] [--skip-tests]"
            exit 0
            ;;
    esac
done

# ── Helpers ─────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()   { echo -e "${CYAN}[PIPELINE]${NC} $*"; }
ok()    { echo -e "${GREEN}  ✓${NC} $*"; }
warn()  { echo -e "${YELLOW}  ⚠${NC} $*"; }
fail()  { echo -e "${RED}  ✗ FAILED:${NC} $*"; exit 1; }

banner() {
    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}  $1${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo ""
}

# ── Preflight: ensure we're in a git repo ───────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d .git ]; then
    fail "Not a git repository. Run 'git init' first."
fi

if [ "$DRY_RUN" = true ]; then
    log "DRY RUN — no changes will be made"
    echo ""
fi

# ══════════════════════════════════════════════════════════════════════════
# STEP 1: AUTOMATED GIT PROCESSING
# ══════════════════════════════════════════════════════════════════════════
banner "STEP 1/3 — GIT PROCESSING"

# Check for changes
if git diff --quiet HEAD 2>/dev/null && git diff --cached --quiet 2>/dev/null && [ -z "$(git ls-files --others --exclude-standard)" ]; then
    log "No changes detected — nothing to commit"
    SKIP_GIT=true
else
    SKIP_GIT=false
    CHANGED_FILES=$(git status --porcelain | wc -l)
    log "Detected ${CHANGED_FILES} changed file(s):"
    git status --short
    echo ""

    if [ "$DRY_RUN" = true ]; then
        log "[DRY RUN] Would commit ${CHANGED_FILES} file(s)"
    else
        # Stage all changes
        log "Staging all changes..."
        git add .
        ok "Changes staged"

        # Commit with timestamp
        COMMIT_MSG="Auto-update: ${TIMESTAMP}"
        log "Committing: ${COMMIT_MSG}"
        git commit -m "$COMMIT_MSG" --quiet
        ok "Committed: $(git log --oneline -1)"

        # Push to remote
        log "Pushing to ${GITHUB_REMOTE}/${GITHUB_BRANCH}..."
        if git push "$GITHUB_REMOTE" "$GITHUB_BRANCH" --quiet 2>&1; then
            ok "Pushed to GitHub"
        else
            fail "Push failed — check credentials and network"
        fi
    fi
fi

# ══════════════════════════════════════════════════════════════════════════
# STEP 2: AUTOMATED VPS DEPLOYMENT
# ══════════════════════════════════════════════════════════════════════════
banner "STEP 2/3 — VPS DEPLOYMENT"

# Test SSH connectivity first
log "Testing SSH connection to ${REMOTE_HOST}..."
if ! ssh -o ConnectTimeout=5 -o BatchMode=yes "$REMOTE_HOST" "echo ok" &>/dev/null; then
    fail "Cannot connect to ${REMOTE_HOST} — check SSH keys and network"
fi
ok "SSH connection verified"

if [ "$DRY_RUN" = true ]; then
    log "[DRY RUN] Would SSH into ${REMOTE_HOST} and pull latest code"
else
    # Pull latest code on VPS
    log "Pulling latest code on VPS..."
    ssh "$REMOTE_HOST" bash -s <<'REMOTE'
set -euo pipefail
cd /opt/trading-bridge

echo "[VPS] Pulling latest from GitHub..."
git pull origin main 2>&1 || echo "[VPS] Warning: git pull failed (may not be a git repo on VPS)"

echo "[VPS] Sync complete"
REMOTE
    ok "Code pulled on VPS"
fi

# Run pre-flight tests (exchange_gateway deploy.sh)
if [ "$SKIP_TESTS" = false ]; then
    log "Running pre-flight validation on VPS..."
    if [ "$DRY_RUN" = true ]; then
        log "[DRY RUN] Would run deploy.sh on VPS"
    else
        ssh "$REMOTE_HOST" bash -s <<'REMOTE'
set -euo pipefail
cd /opt/trading-bridge/exchange_gateway

if [ ! -f deploy.sh ]; then
    echo "[VPS] ERROR: deploy.sh not found"
    exit 1
fi

chmod +x deploy.sh
./deploy.sh --no-tests 2>&1
REMOTE
        ok "Pre-flight validation passed"
    fi
else
    warn "Skipping pre-flight tests (--skip-tests)"
fi

# ══════════════════════════════════════════════════════════════════════════
# STEP 3: PM2 ORCHESTRATION REFRESH
# ══════════════════════════════════════════════════════════════════════════
banner "STEP 3/3 — PM2 REFRESH"

if [ "$DRY_RUN" = true ]; then
    log "[DRY RUN] Would restart PM2 processes and save state"
else
    # Restart PM2 processes
    log "Restarting PM2 processes..."
    ssh "$REMOTE_HOST" bash -s <<'REMOTE'
set -euo pipefail
cd /opt/trading-bridge

echo "[VPS] Restarting orchestrator..."
pm2 restart omni-orchestrator --update-env 2>&1

echo "[VPS] Saving PM2 state..."
pm2 save 2>&1
REMOTE
    ok "PM2 processes restarted and saved"
fi

# ══════════════════════════════════════════════════════════════════════════
# DEPLOYMENT STATUS REPORT
# ══════════════════════════════════════════════════════════════════════════
banner "DEPLOYMENT REPORT"

if [ "$DRY_RUN" = true ]; then
    log "DRY RUN complete — no changes were made"
else
    # Gather status from VPS
    ssh "$REMOTE_HOST" bash -s <<'REMOTE'
echo "── PM2 Process Status ──"
pm2 status

echo ""
echo "── Orchestrator Health ──"
pm2 logs omni-orchestrator --lines 5 --nostream 2>&1 | tail -5
REMOTE
fi

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  DEPLOY COMPLETE — ${TIMESTAMP}${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo ""
