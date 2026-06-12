#!/bin/bash
# ══════════════════════════════════════════════════════════════════════════════
# DEPLOY SCRIPT — Go-Live Setup for Trading Bridge
# Run as root or with sudo: sudo bash deploy.sh
# ══════════════════════════════════════════════════════════════════════════════

set -e

echo "═══════════════════════════════════════════════════"
echo "  TRADING BRIDGE — PRODUCTION DEPLOYMENT"
echo "═══════════════════════════════════════════════════"

# --- 1. System Updates ---
echo ""
echo "[1/10] Updating system packages..."
apt-get update -qq && apt-get upgrade -y -qq

# --- 2. Install Node.js (if not present) ---
echo ""
echo "[2/10] Checking Node.js..."
if ! command -v node &> /dev/null; then
    echo "  Installing Node.js 22 LTS..."
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
    apt-get install -y nodejs
fi
echo "  Node.js: $(node -v)"
echo "  npm: $(npm -v)"

# --- 3. Install PM2 ---
echo ""
echo "[3/10] Installing PM2..."
if ! command -v pm2 &> /dev/null; then
    npm install -g pm2
    pm2 startup systemd -u $USER --hp $HOME
fi
echo "  PM2: $(pm2 -v)"

# --- 4. Create directory structure ---
echo ""
echo "[4/10] Creating directories..."
mkdir -p /opt/trading-bridge
mkdir -p /opt/trading-bridge/logs
mkdir -p /opt/trading-bridge/data
mkdir -p /opt/trading-bridge/.env

# --- 5. Copy files ---
echo ""
echo "[5/10] Copying application files..."
cp production_bridge.mjs /opt/trading-bridge/
cp ecosystem.config.cjs /opt/trading-bridge/

# --- 6. Create .env file ---
echo ""
echo "[6/10] Creating environment configuration..."
if [ ! -f /opt/trading-bridge/.env.production ]; then
    cat > /opt/trading-bridge/.env.production << 'EOF'
# Production Environment — EDIT THESE VALUES
NODE_ENV=production
PORT=3000
WEBHOOK_SECRET=CHANGE-ME-TO-A-RANDOM-64-CHAR-STRING
BROKER_API_KEY=your-broker-api-key
BROKER_API_URL=https://api.broker.com/v1
ALLOWED_SYMBOLS=XAUUSD
MAX_POSITION_SIZE=10
MAX_DAILY_TRADES=20
DEAD_MAN_TIMEOUT=3600000
DEAD_MAN_CHECK=60000
ALERT_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK
MAX_DRAWDOWN=3.0
DAILY_LOSS_LIMIT=300
EOF
    echo "  ⚠ Created .env.production — EDIT IT WITH YOUR ACTUAL VALUES"
else
    echo "  .env.production already exists — skipping"
fi

# --- 7. Install dependencies ---
echo ""
echo "[7/10] Installing dependencies..."
cd /opt/trading-bridge
npm init -y
npm install dotenv

# --- 8. Configure firewall (iptables) ---
echo ""
echo "[8/10] Configuring firewall..."

# Get TradingView IP ranges
echo "  Fetching TradingView IP ranges..."
TV_IPS=$(curl -s https://www.tradingview.com/publishing-guidelines/ | grep -oE '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+' | sort -u || echo "")

# Default: allow common TradingView ranges
# These should be updated periodically
TRADINGVIEW_IPS=(
    "104.244.244.0/24"
    "104.244.245.0/24"
    "104.244.246.0/24"
    "104.244.247.0/24"
    "172.67.128.0/24"
)

# Flush existing rules
iptables -F INPUT

# Allow established connections
iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT

# Allow loopback
iptables -A INPUT -i lo -j ACCEPT

# Allow SSH (port 22)
iptables -A INPUT -p tcp --dport 22 -j ACCEPT

# Allow HTTP/HTTPS (for monitoring)
iptables -A INPUT -p tcp --dport 80 -j ACCEPT
iptables -A INPUT -p tcp --dport 443 -j ACCEPT

# Allow TradingView webhook (port 3000) — restrict to TradingView IPs
for ip in "${TRADINGVIEW_IPS[@]}"; do
    iptables -A INPUT -p tcp -s "$ip" --dport 3000 -j ACCEPT
    echo "  Allowed: $ip → :3000"
done

# Block all other traffic to port 3000
iptables -A INPUT -p tcp --dport 3000 -j DROP
echo "  Blocked: all other IPs → :3000"

# Save rules
if command -v iptables-save &> /dev/null; then
    iptables-save > /etc/iptables/rules.v4 2>/dev/null || true
fi

echo "  Firewall configured."

# --- 9. Start application ---
echo ""
echo "[9/10] Starting trading bridge with PM2..."
cd /opt/trading-bridge
pm2 start ecosystem.config.cjs
pm2 save

# --- 10. Verify ---
echo ""
echo "[10/10] Verifying deployment..."
sleep 3

# Health check
HEALTH=$(curl -s http://localhost:3000/health 2>/dev/null || echo '{"status":"error"}')
echo ""
echo "  Health Check:"
echo "  $HEALTH"

# PM2 status
pm2 status

echo ""
echo "═══════════════════════════════════════════════════"
echo "  DEPLOYMENT COMPLETE"
echo "═══════════════════════════════════════════════════"
echo ""
echo "  Next steps:"
echo "  1. Edit /opt/trading-bridge/.env.production with your values"
echo "  2. Restart: pm2 restart trading-bridge"
echo "  3. Logs: pm2 logs trading-bridge"
echo "  4. Status: pm2 status"
echo "  5. Monitor: pm2 monit"
echo ""
echo "  ⚠ IMPORTANT — Telegram Setup:"
echo "  1. Open Telegram and search for @omnibrainsignals_free"
echo "  2. Send /start to the bot"
echo "  3. Run: python3 scripts/get_chat_id.py"
echo "  4. Update TELEGRAM_CHAT_ID in .env"
echo "  5. Restart: pm2 restart all --update-env"
echo ""
echo "  Webhook URL: http://YOUR_VPS_IP:3000/webhook?secret=YOUR_SECRET"
echo ""
