#!/usr/bin/env bash
set -euo pipefail

# Exchange Gateway — Production Deploy Script
# Usage: ./deploy.sh [--no-tests]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"
SKIP_TESTS=false

for arg in "$@"; do
    case "$arg" in
        --no-tests) SKIP_TESTS=true ;;
    esac
done

log() { echo "[DEPLOY] $*"; }

# ── 1. Virtual environment ─────────────────────────────────────────────

if [ ! -d "$VENV_DIR" ]; then
    log "Creating virtual environment in ${VENV_DIR}"
    python3 -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"
log "Activated: $(python3 --version) @ ${VENV_DIR}"

# ── 2. Install dependencies ────────────────────────────────────────────

log "Installing dependencies from requirements.txt"
pip install --quiet --upgrade pip
pip install --quiet -r "${SCRIPT_DIR}/requirements.txt"
log "Dependencies installed"

# ── 3. Validate configuration ──────────────────────────────────────────

CONFIG_FILE="${SCRIPT_DIR}/config/exchanges.json"
if [ ! -f "$CONFIG_FILE" ]; then
    log "WARNING: ${CONFIG_FILE} not found"
    log "Copying from exchanges.json.example"
    cp "${SCRIPT_DIR}/config/exchanges.json.example" "$CONFIG_FILE"
    log "Edit ${CONFIG_FILE} with your API credentials before running in production"
fi

# Verify JSON is parseable
if ! python3 -c "import json; json.load(open('${CONFIG_FILE}'))" 2>/dev/null; then
    log "ERROR: ${CONFIG_FILE} is not valid JSON"
    exit 1
fi
log "Configuration validated: ${CONFIG_FILE}"

# ── 4. Syntax check ────────────────────────────────────────────────────

log "Running syntax check on all Python files"
SYNTAX_ERRORS=0
while IFS= read -r pyfile; do
    if ! python3 -m py_compile "$pyfile" 2>/dev/null; then
        log "  SYNTAX ERROR: ${pyfile}"
        SYNTAX_ERRORS=$((SYNTAX_ERRORS + 1))
    fi
done < <(find "$SCRIPT_DIR" -name '*.py' -not -path '*/__pycache__/*' -not -path '*/.venv/*' | sort)

if [ "$SYNTAX_ERRORS" -gt 0 ]; then
    log "ERROR: ${SYNTAX_ERRORS} file(s) have syntax errors"
    exit 1
fi
log "Syntax check passed (0 errors)"

# ── 5. Run tests ───────────────────────────────────────────────────────

if [ "$SKIP_TESTS" = false ]; then
    log "Running test suite"
    python3 "${SCRIPT_DIR}/test_gateway.py"
    log "All tests passed"
else
    log "Skipping tests (--no-tests)"
fi

# ── Done ────────────────────────────────────────────────────────────────

log "Deployment complete"
log "  Virtual env: ${VENV_DIR}"
log "  Config:      ${CONFIG_FILE}"
log "  To activate: source ${VENV_DIR}/bin/activate"
