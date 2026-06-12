#!/bin/bash
# Trading Bridge Monitoring Script
# Run on VPS: bash monitor.sh

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

clear
echo -e "${CYAN}════════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}         TRADING BRIDGE MONITOR                              ${NC}"
echo -e "${CYAN}         Press Ctrl+C to exit                                 ${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════════════════${NC}"

while true; do
    echo ""
    echo -e "${CYAN}──────────────────────────────────────────────────────────────${NC}"
    echo -e "${CYAN}  $(date '+%Y-%m-%d %H:%M:%S')${NC}"
    echo -e "${CYAN}──────────────────────────────────────────────────────────────${NC}"
    
    # PM2 Status
    echo -e "\n${YELLOW}[PM2 STATUS]${NC}"
    pm2 status trading-bridge 2>/dev/null || echo -e "${RED}PM2 process not found${NC}"
    
    # Health Check
    echo -e "\n${YELLOW}[HEALTH CHECK]${NC}"
    HEALTH=$(curl -s http://localhost:3000/health 2>/dev/null)
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Bridge responding${NC}"
        echo "  $HEALTH" | python3 -m json.tool 2>/dev/null || echo "  $HEALTH"
    else
        echo -e "${RED}✗ Bridge not responding${NC}"
    fi
    
    # Uptime
    echo -e "\n${YELLOW}[UPTIME]${NC}"
    ps -o etimes= -p $(pm2 pid trading-bridge) 2>/dev/null | awk '{printf "%d days, %d hours, %d minutes\n", $1/86400, ($1%86400)/3600, ($1%3600)/60}' || echo "N/A"
    
    # Memory Usage
    echo -e "\n${YELLOW}[MEMORY]${NC}"
    pm2 show trading-bridge 2>/dev/null | grep -E "memory|heap" || echo "N/A"
    
    # Trade State
    echo -e "\n${YELLOW}[TODAY'S STATE]${NC}"
    if [ -f "/opt/trading-bridge/data/production_state.json" ]; then
        python3 -c "
import json
with open('/opt/trading-bridge/data/production_state.json') as f:
    state = json.load(f)
print(f'  Trades today: {state.get(\"trades_today\", 0)}/10')
print(f'  Daily P&L: \${state.get(\"daily_pnl\", 0):.2f}')
print(f'  Kill switch: {\"ACTIVE\" if state.get(\"kill_switch_active\", False) else \"inactive\"}')
print(f'  Consecutive losses: {state.get(\"consecutive_losses\", 0)}/3')
"
    else
        echo "  No state file found"
    fi
    
    # Last 3 Trades
    echo -e "\n${YELLOW}[LAST 3 TRADES]${NC}"
    if [ -f "/opt/trading-bridge/data/trade_log.csv" ]; then
        tail -3 /opt/trading-bridge/data/trade_log.csv | awk -F',' '{printf "  %s | %s | %s | %s | %s | %s\n", $1, $2, $3, $4, $5, $6}'
    else
        echo "  No trades logged"
    fi
    
    # System Resources
    echo -e "\n${YELLOW}[SYSTEM]${NC}"
    echo "  CPU: $(top -bn1 | grep "Cpu(s)" | awk '{print $2}')%"
    echo "  RAM: $(free -h | awk '/^Mem:/ {print $3"/"$2}')"
    echo "  Disk: $(df -h / | awk 'NR==2 {print $5}') used"
    
    # Refresh
    sleep 10
done
