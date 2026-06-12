#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# OMNI BRAIN V2 - MCP Stack Deployment Script
# ══════════════════════════════════════════════════════════════════════════════
# Deploys the full MCP stack on a Linux VPS:
#   1. System dependencies (Python, Node.js, PM2)
#   2. TiDB Cloud Zero MCP server
#   3. FastAPI MCP Bridge server
#   4. OpenStock frontend (Next.js)
#   5. All PM2 services
#
# Usage:
#   bash scripts/deploy_mcp.sh --vps 172.105.252.194
#   bash scripts/deploy_mcp.sh --local
# ══════════════════════════════════════════════════════════════════════════════

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

PROJECT_DIR="/opt/omni-brain"
MCP_DIR="${PROJECT_DIR}/mcp_stack"
FRONTEND_DIR="${PROJECT_DIR}/openstock-dashboard"

log_info()  { echo -e "${CYAN}[INFO]${NC} $1"; }
log_ok()    { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 1: System Dependencies
# ══════════════════════════════════════════════════════════════════════════════

install_system_deps() {
    log_info "Phase 1: Installing system dependencies..."
    
    apt-get update -qq
    apt-get install -y -qq python3 python3-pip python3-venv curl git build-essential
    
    if ! command -v node &>/dev/null; then
        log_info "Installing Node.js 20 LTS..."
        curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
        apt-get install -y -qq nodejs
    fi
    log_ok "Node.js $(node -v)"
    
    if ! command -v pm2 &>/dev/null; then
        log_info "Installing PM2..."
        npm install -g pm2
    fi
    log_ok "PM2 $(pm2 -v)"
    
    if ! command -v uv &>/dev/null; then
        log_info "Installing uv..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="$HOME/.local/bin:$PATH"
    fi
    log_ok "uv installed"
}

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 2: TiDB Cloud Zero MCP
# ══════════════════════════════════════════════════════════════════════════════

setup_tidb_mcp() {
    log_info "Phase 2: Setting up TiDB Cloud Zero MCP..."
    
    mkdir -p "${MCP_DIR}"
    
    if [ ! -d "${MCP_DIR}/.git" ]; then
        git clone https://github.com/siddontang/tidb-cloud-zero-mcp.git "${MCP_DIR}"
    fi
    
    cd "${MCP_DIR}"
    uv sync
    log_ok "TiDB MCP server ready at ${MCP_DIR}"
}

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 3: Python Dependencies
# ══════════════════════════════════════════════════════════════════════════════

install_python_deps() {
    log_info "Phase 3: Installing Python dependencies..."
    
    cd "${PROJECT_DIR}"
    
    pip3 install --quiet --upgrade pip
    pip3 install --quiet \
        fastapi \
        uvicorn[standard] \
        websockets \
        httpx \
        psutil \
        requests
    
    log_ok "Python dependencies installed"
}

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 4: OpenStock Frontend
# ══════════════════════════════════════════════════════════════════════════════

setup_openstock() {
    log_info "Phase 4: Setting up OpenStock dashboard..."
    
    mkdir -p "${FRONTEND_DIR}"
    
    if [ ! -d "${FRONTEND_DIR}/.git" ]; then
        git clone https://github.com/openstack/openstack-dashboard.git "${FRONTEND_DIR}" 2>/dev/null || {
            log_warn "OpenStock repo not found, creating placeholder"
            cat > "${FRONTEND_DIR}/package.json" << 'PKGJSON'
{
  "name": "omni-brain-dashboard",
  "version": "1.0.0",
  "scripts": {
    "dev": "next dev -p 3001",
    "build": "next build",
    "start": "next start -p 3001"
  },
  "dependencies": {
    "next": "^14.0.0",
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "tailwindcss": "^3.4.0"
  }
}
PKGJSON
            cd "${FRONTEND_DIR}"
            npm install --silent 2>/dev/null || true
        })
    fi
    
    if [ -f "${FRONTEND_DIR}/package.json" ]; then
        cd "${FRONTEND_DIR}"
        npm install --silent 2>/dev/null || true
    fi
    
    log_ok "OpenStock dashboard ready"
}

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 5: Environment Configuration
# ══════════════════════════════════════════════════════════════════════════════

setup_env() {
    log_info "Phase 5: Configuring environment..."
    
    ENV_FILE="${PROJECT_DIR}/.env"
    
    if [ ! -f "${ENV_FILE}" ]; then
        cat > "${ENV_FILE}" << 'ENVEOF'
# OMNI BRAIN V2 - Environment Configuration
# ==========================================

# MT5 Broker
MT5_LOGIN=1100086011
MT5_PASSWORD=Ajay1143@
MT5_SERVER=JustMarkets-Live2

# Telegram Alerts
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Twelve Data Live Feed
LIVE_DATA_API_KEY=
LIVE_DATA_PROVIDER=twelve_data
SCAN_INTERVAL_SECONDS=60

# GitHub Signal Archive
GITHUB_TOKEN=
GITHUB_REPO=

# Trading Parameters
MAX_POSITION_SIZE=0.1
MAX_DAILY_TRADES=20
MAX_DRAWDOWN_PCT=3
RISK_PER_TRADE_PCT=1

# MCP Stack - Perplexity
PERPLEXITY_API_KEY=

# MCP Stack - Firecrawl
FIRECRAWL_API_KEY=

# MCP Stack - TiDB Cloud Zero
TIDB_HOST=
TIDB_USERNAME=
TIDB_PASSWORD=
TIDB_DATABASE=omni_brain
TIDB_INSTANCE_ID=

# MCP Bridge Server
MCP_BRIDGE_PORT=8080

# Network
PORT=3000
BIND_HOST=0.0.0.0
ENVEOF
        log_warn "Created ${ENV_FILE} — fill in API keys!"
    else
        log_ok "Environment file exists"
    fi
}

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 6: PM2 Services
# ══════════════════════════════════════════════════════════════════════════════

start_services() {
    log_info "Phase 6: Starting PM2 services..."
    
    cd "${PROJECT_DIR}"
    
    pm2 delete all 2>/dev/null || true
    
    pm2 start ecosystem.config.js
    
    pm2 save
    
    pm2 startup 2>/dev/null || true
    
    sleep 3
    
    pm2 list
    
    log_ok "All services started"
}

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 7: Health Check
# ══════════════════════════════════════════════════════════════════════════════

health_check() {
    log_info "Phase 7: Running health checks..."
    
    sleep 5
    
    if curl -s http://127.0.0.1:3000/health | grep -q "healthy"; then
        log_ok "Pipeline server (3000): HEALTHY"
    else
        log_warn "Pipeline server (3000): not responding"
    fi
    
    if curl -s http://127.0.0.1:8080/health | grep -q "healthy"; then
        log_ok "MCP Bridge (8080): HEALTHY"
    else
        log_warn "MCP Bridge (8080): not responding"
    fi
    
    echo ""
    log_info "=== DEPLOYMENT COMPLETE ==="
    echo ""
    echo "Services:"
    echo "  Pipeline API:     http://$(hostname -I | awk '{print $1}'):3000"
    echo "  MCP Bridge:       http://$(hostname -I | awk '{print $1}'):8080"
    echo "  Dashboard:        http://$(hostname -I | awk '{print $1}'):3001"
    echo ""
    echo "PM2 Commands:"
    echo "  pm2 list          — View all services"
    echo "  pm2 logs          — View live logs"
    echo "  pm2 restart all   — Restart all services"
    echo "  pm2 monit         — Monitor resources"
    echo ""
    echo "Next steps:"
    echo "  1. Fill in API keys in ${PROJECT_DIR}/.env"
    echo "  2. Open TCP ports 3000, 8080, 3001 in cloud security group"
    echo "  3. Configure MCP in Claude Desktop with claude_desktop_config.json"
}

# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

main() {
    echo ""
    echo "═══════════════════════════════════════════════════════════"
    echo "  OMNI BRAIN V2 — MCP Stack Deployment"
    echo "═══════════════════════════════════════════════════════════"
    echo ""
    
    install_system_deps
    setup_tidb_mcp
    install_python_deps
    setup_openstock
    setup_env
    start_services
    health_check
}

main "$@"
