#!/bin/bash
# Trading Bridge Deployment Verification
# Run on VPS: bash verify_deployment.sh

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}════════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}         TRADING BRIDGE DEPLOYMENT VERIFIER                   ${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════════════════${NC}"

ERRORS=0

check() {
    local name="$1"
    local cmd="$2"
    local expected="$3"
    
    echo -n "  $name: "
    result=$(eval "$cmd" 2>/dev/null)
    if [ "$result" == "$expected" ] || [ -n "$result" ] && echo "$result" | grep -q "$expected"; then
        echo -e "${GREEN}✓ PASS${NC}"
        return 0
    else
        echo -e "${RED}✗ FAIL (got: $result)${NC}"
        ((ERRORS++))
        return 1
    fi
}

echo -e "\n${YELLOW}1. Directory Structure${NC}"
[ -d "/opt/trading-bridge" ] && echo -e "  /opt/trading-bridge: ${GREEN}✓${NC}" || { echo -e "  /opt/trading-bridge: ${RED}✗ Missing${NC}"; ((ERRORS++)); }
[ -f "/opt/trading-bridge/production_bridge.mjs" ] && echo -e "  production_bridge.mjs: ${GREEN}✓${NC}" || { echo -e "  production_bridge.mjs: ${RED}✗ Missing${NC}"; ((ERRORS++)); }
[ -f "/opt/trading-bridge/ecosystem.config.cjs" ] && echo -e "  ecosystem.config.cjs: ${GREEN}✓${NC}" || { echo -e "  ecosystem.config.cjs: ${RED}✗ Missing${NC}"; ((ERRORS++)); }
[ -f "/opt/trading-bridge/.env.production" ] && echo -e "  .env.production: ${GREEN}✓${NC}" || { echo -e "  .env.production: ${RED}✗ Missing${NC}"; ((ERRORS++)); }

echo -e "\n${YELLOW}2. PM2 Process${NC}"
PM2_STATUS=$(pm2 jlist 2>/dev/null | python3 -c "import sys,json; data=json.load(sys.stdin); [print(p['name']) for p in data]" 2>/dev/null || echo "none")
if echo "$PM2_STATUS" | grep -q "trading-bridge"; then
    echo -e "  PM2 process: ${GREEN}✓ Running${NC}"
    pm2 status trading-bridge
else
    echo -e "  PM2 process: ${RED}✗ Not running${NC}"
    ((ERRORS++))
fi

echo -e "\n${YELLOW}3. Webhook Endpoint${NC}"
HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/health 2>/dev/null || echo "000")
if [ "$HEALTH" == "200" ]; then
    echo -e "  HTTP response: ${GREEN}✓ 200 OK${NC}"
else
    echo -e "  HTTP response: ${RED}✗ $HEALTH${NC}"
    ((ERRORS++))
fi

echo -e "\n${YELLOW}4. Environment Variables${NC}"
if [ -f "/opt/trading-bridge/.env.production" ]; then
    source /opt/trading-bridge/.env.production
    [ -n "$WEBHOOK_SECRET" ] && echo -e "  WEBHOOK_SECRET: ${GREEN}✓ Set${NC}" || { echo -e "  WEBHOOK_SECRET: ${RED}✗ Empty${NC}"; ((ERRORS++)); }
    [ -n "$BROKER_API_KEY" ] && echo -e "  BROKER_API_KEY: ${GREEN}✓ Set${NC}" || { echo -e "  BROKER_API_KEY: ${RED}✗ Empty${NC}"; ((ERRORS++)); }
    [ -n "$TRADINGVIEW_ALERT_URL" ] && echo -e "  TRADINGVIEW_ALERT_URL: ${GREEN}✓ Set${NC}" || { echo -e "  TRADINGVIEW_ALERT_URL: ${RED}✗ Empty${NC}"; ((ERRORS++)); }
    [ -n "$DEAD_MAN_WEBHOOK" ] && echo -e "  DEAD_MAN_WEBHOOK: ${GREEN}✓ Set${NC}" || echo -e "  DEAD_MAN_WEBHOOK: ${YELLOW}⚠ Optional${NC}"
fi

echo -e "\n${YELLOW}5. Port Accessibility${NC}"
PORT_STATUS=$(netstat -tlnp 2>/dev/null | grep ":3000" | head -1)
if [ -n "$PORT_STATUS" ]; then
    echo -e "  Port 3000 (local): ${GREEN}✓ Listening${NC}"
else
    echo -e "  Port 3000 (local): ${RED}✗ Not listening${NC}"
    ((ERRORS++))
fi

echo -e "\n${YELLOW}6. Trade State${NC}"
if [ -f "/opt/trading-bridge/data/production_state.json" ]; then
    echo -e "  State file: ${GREEN}✓ Exists${NC}"
    python3 -c "
import json
with open('/opt/trading-bridge/data/production_state.json') as f:
    state = json.load(f)
print(f'  Current state: {state}')
"
else
    echo -e "  State file: ${YELLOW}⚠ Will be created on first trade${NC}"
fi

echo -e "\n${YELLOW}7. Webhook Test${NC}"
echo "  Testing POST /webhook..."
TEST_RESPONSE=$(curl -s -X POST "http://localhost:3000/webhook?secret=test_invalid" \
  -H "Content-Type: application/json" \
  -d '{"action":"long","price":2650,"sl":2640,"tp":2660}' 2>/dev/null || echo "failed")

if echo "$TEST_RESPONSE" | grep -q "Invalid secret"; then
    echo -e "  Auth validation: ${GREEN}✓ Working${NC}"
elif echo "$TEST_RESPONSE" | grep -q "executed"; then
    echo -e "  Auth validation: ${YELLOW}⚠ Test passed with invalid secret (check secret)${NC}"
else
    echo -e "  Auth validation: ${RED}✗ $TEST_RESPONSE${NC}"
    ((ERRORS++))
fi

echo -e "\n${YELLOW}8. Kill Switch${NC}"
echo "  Testing kill switch..."
KILL_RESPONSE=$(curl -s -X POST "http://localhost:3000/kill" 2>/dev/null || echo "failed")
if echo "$KILL_RESPONSE" | grep -q "halted"; then
    echo -e "  Kill switch: ${GREEN}✓ Working${NC}"
    # Re-enable trading
    curl -s -X POST "http://localhost:3000/resume" 2>/dev/null >/dev/null
else
    echo -e "  Kill switch: ${RED}✗ Not responding${NC}"
    ((ERRORS++))
fi

echo -e "\n════════════════════════════════════════════════════════════════"
if [ $ERRORS -eq 0 ]; then
    echo -e "${GREEN}  ALL CHECKS PASSED ✓${NC}"
    echo -e "${GREEN}  Trading bridge is ready for external configuration${NC}"
else
    echo -e "${RED}  $ERRORS CHECK(S) FAILED${NC}"
    echo -e "${RED}  Fix the issues above before proceeding${NC}"
fi
echo -e "════════════════════════════════════════════════════════════════"
