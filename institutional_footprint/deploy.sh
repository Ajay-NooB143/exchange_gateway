#!/bin/bash
# Institutional Footprint - Deployment Script
# ============================================
# Run on VPS: bash deploy_institutional.sh

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}════════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  INSTITUTIONAL FOOTPRINT - DEPLOYMENT SCRIPT                  ${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════════════════${NC}"

# Configuration
INSTALL_DIR="/opt/trading-bridge/institutional_footprint"
LOG_DIR="/opt/trading-bridge/logs"
DATA_DIR="/opt/trading-bridge/data"

# Step 1: Create directories
echo -e "\n${YELLOW}1. Creating directories...${NC}"
mkdir -p "$INSTALL_DIR"
mkdir -p "$LOG_DIR"
mkdir -p "$DATA_DIR"
echo -e "${GREEN}   ✓ Directories created${NC}"

# Step 2: Copy files
echo -e "\n${YELLOW}2. Installing files...${NC}"
cp institutional_footprint.pine "$INSTALL_DIR/"
cp execution_engine.py "$INSTALL_DIR/"
cp bridge.mjs "$INSTALL_DIR/"
cp ecosystem.config.cjs "$INSTALL_DIR/"
cp .env.example "$INSTALL_DIR/.env.example"
echo -e "${GREEN}   ✓ Files installed${NC}"

# Step 3: Install Python dependencies
echo -e "\n${YELLOW}3. Installing Python dependencies...${NC}"
pip3 install aiohttp numpy pandas --quiet 2>/dev/null || {
    echo -e "${YELLOW}   Installing with --user...${NC}"
    pip3 install aiohttp numpy pandas --user --quiet
}
echo -e "${GREEN}   ✓ Python dependencies installed${NC}"

# Step 4: Generate secret
echo -e "\n${YELLOW}4. Generating webhook secret...${NC}"
if [ ! -f "$INSTALL_DIR/.env" ]; then
    SECRET=$(openssl rand -hex 32)
    cat > "$INSTALL_DIR/.env" << EOF
# Institutional Footprint Configuration
# Generated: $(date)

# Bridge
BRIDGE_PORT=3000
PYTHON_ENGINE_URL=http://localhost:8080
WEBHOOK_SECRET=$SECRET

# Risk Management
RISK_PER_TRADE=0.01
MAX_DAILY_LOSS=0.03
MAX_DAILY_TRADES=3
MAX_SLIPPAGE_PIPS=2.0

# CVD Validation
CVD_LOOKBACK=10
CVD_THRESHOLD=0.3
MIN_ABSORPTION_VOLUME=50

# Execution
USE_LIMIT_ORDERS=true
LIMIT_OFFSET_PIPS=0.5
MARKET_TIMEOUT_MS=500

# Logging
LOG_FILE=$DATA_DIR/execution_log.csv
STATE_FILE=$DATA_DIR/engine_state.json
EOF
    echo -e "${GREEN}   ✓ Secret generated and .env created${NC}"
    echo -e "${CYAN}   Secret: $SECRET${NC}"
    echo -e "${CYAN}   Save this! You'll need it for TradingView alerts${NC}"
else
    echo -e "${YELLOW}   .env already exists, skipping${NC}"
    source "$INSTALL_DIR/.env"
    echo -e "${CYAN}   Current secret: ${WEBHOOK_SECRET:0:16}...${NC}"
fi

# Step 5: Stop existing processes
echo -e "\n${YELLOW}5. Stopping existing processes...${NC}"
pm2 delete footprint-bridge 2>/dev/null || true
pm2 delete footprint-engine 2>/dev/null || true
echo -e "${GREEN}   ✓ Existing processes stopped${NC}"

# Step 6: Start services
echo -e "\n${YELLOW}6. Starting services...${NC}"
cd "$INSTALL_DIR"
pm2 start ecosystem.config.cjs
pm2 save
echo -e "${GREEN}   ✓ Services started${NC}"

# Step 7: Health check
echo -e "\n${YELLOW}7. Running health check...${NC}"
sleep 3

BRIDGE_HEALTH=$(curl -s http://localhost:3000/health 2>/dev/null || echo '{"status":"error"}')
ENGINE_HEALTH=$(curl -s http://localhost:8080/health 2>/dev/null || echo '{"status":"error"}')

echo -e "   Bridge: $BRIDGE_HEALTH"
echo -e "   Engine: $ENGINE_HEALTH"

# Step 8: Open firewall
echo -e "\n${YELLOW}8. Configuring firewall...${NC}"
if command -v ufw &> /dev/null; then
    ufw allow 3000/tcp 2>/dev/null || true
    echo -e "${GREEN}   ✓ Port 3000 opened in UFW${NC}"
else
    echo -e "${YELLOW}   UFW not installed, skipping firewall config${NC}"
fi

# Summary
echo -e "\n${CYAN}════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  DEPLOYMENT COMPLETE!${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════════════════${NC}"
echo -e ""
echo -e "  ${YELLOW}Services:${NC}"
echo -e "    footprint-bridge   :3000 (Node.js)"
echo -e "    footprint-engine   :8080 (Python)"
echo -e ""
echo -e "  ${YELLOW}TradingView Webhook URL:${NC}"
echo -e "    http://YOUR_VPS_IP:3000/webhook?secret=$WEBHOOK_SECRET"
echo -e ""
echo -e "  ${YELLOW}Commands:${NC}"
echo -e "    pm2 status                 # Check status"
echo -e "    pm2 logs footprint-bridge  # Bridge logs"
echo -e "    pm2 logs footprint-engine  # Engine logs"
echo -e "    pm2 restart all            # Restart all"
echo -e ""
echo -e "  ${YELLOW}Monitor:${NC}"
echo -e "    curl http://localhost:3000/health"
echo -e "    curl http://localhost:8080/stats"
echo -e ""
echo -e "${CYAN}════════════════════════════════════════════════════════════════${NC}"
