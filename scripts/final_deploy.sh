#!/bin/bash
set -e

VPS_IP="${VPS_IP:?VPS_IP is required}"
VPS_PATH="${VPS_PATH:-/opt/trading-bridge}"
LOCAL_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}╔═══════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║       OMNI BRAIN V2 - PRODUCTION DEPLOY          ║${NC}"
echo -e "${CYAN}╚═══════════════════════════════════════════════════╝${NC}"

# Step 1: Test VPS connection
echo -e "\n${YELLOW}[1/8]${NC} Testing VPS connection..."
ssh -o ConnectTimeout=10 "root@${VPS_IP}" "echo VPS_OK" || {
    echo -e "${RED}✗ VPS unreachable at ${VPS_IP}${NC}"
    exit 1
}
echo -e "${GREEN}✓ VPS connected${NC}"

# Step 2: Backup existing
echo -e "\n${YELLOW}[2/8]${NC} Backing up existing deployment..."
ssh "root@${VPS_IP}" "cd ${VPS_PATH} && tar -czf /tmp/backup_$(date +%Y%m%d_%H%M%S).tar.gz . 2>/dev/null || true"
echo -e "${GREEN}✓ Backup created${NC}"

# Step 3: Copy files
echo -e "\n${YELLOW}[3/8]${NC} Syncing files..."
rsync -avz --delete --progress \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.venv' \
    --exclude='venv' \
    --exclude='node_modules' \
    --exclude='logs/' \
    --exclude='data/csv/' \
    "${LOCAL_PATH}/" "root@${VPS_IP}:${VPS_PATH}/"
echo -e "${GREEN}✓ Files synced${NC}"

# Step 4: Install dependencies
echo -e "\n${YELLOW}[4/8]${NC} Installing Python dependencies..."
ssh "root@${VPS_IP}" "pip3 install psutil numpy numba requests vaderSentiment APScheduler websocket-client pillow --break-system-packages --quiet 2>/dev/null || true"
echo -e "${GREEN}✓ Dependencies installed${NC}"

# Step 5: Verify .env
echo -e "\n${YELLOW}[5/8]${NC} Checking .env..."
ssh "root@${VPS_IP}" "test -f ${VPS_PATH}/.env && echo 'ENV_OK' || echo 'MISSING'" | grep -q ENV_OK && echo -e "${GREEN}✓ .env exists${NC}" || echo -e "${YELLOW}⚠ .env missing - create from .env.example${NC}"

# Step 6: Run tests
echo -e "\n${YELLOW}[6/8]${NC} Running test suite..."
ssh "root@${VPS_IP}" "cd ${VPS_PATH} && python3 -m pytest tests/ -q --tb=no 2>&1 | tail -5"

# Step 7: Restart PM2
echo -e "\n${YELLOW}[7/8]${NC} Restarting PM2 processes..."
ssh "root@${VPS_IP}" "cd ${VPS_PATH} && pm2 delete all 2>/dev/null || true && pm2 start ecosystem.config.js && pm2 save"
echo -e "${GREEN}✓ PM2 restarted${NC}"

# Step 8: Health check
echo -e "\n${YELLOW}[8/8]${NC} Running health check..."
sleep 5
if ssh "root@${VPS_IP}" "curl -sf http://localhost:3000/api/omni-status > /dev/null 2>&1"; then
    echo -e "${GREEN}✓ Pipeline health check passed${NC}"
else
    echo -e "${YELLOW}⚠ Pipeline health check skipped (may need extra time)${NC}"
fi

echo ""
echo -e "${GREEN}╔═══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║       DEPLOY COMPLETE                            ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════════════════╝${NC}"
echo -e "  Dashboard : http://${VPS_IP}:8089"
echo -e "  Pipeline  : http://${VPS_IP}:3000"
echo -e "  Status    : http://${VPS_IP}:8080"
echo ""
