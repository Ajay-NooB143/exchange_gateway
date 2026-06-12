#!/bin/bash
# ══════════════════════════════════════════════════════════════════════════════
# VPS AUTO-DEPLOY SCRIPT
# Trading Bridge Deployment with Health Checks
# ══════════════════════════════════════════════════════════════════════════════

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Symbols
CHECKMARK="✓"
CROSSMARK="✗"
ARROW="→"

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_DIR/.env"
ENV_EXAMPLE="$PROJECT_DIR/.env.example"
ECOSYSTEM_CONFIG="$PROJECT_DIR/ecosystem.config.js"
LOG_DIR="$PROJECT_DIR/logs"

# Functions
print_header() {
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}       TRADING BRIDGE DEPLOYMENT SCRIPT${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
}

print_step() {
    echo -e "\n${YELLOW}[$1/6]${NC} $2"
}

print_success() {
    echo -e "  ${GREEN}${CHECKMARK} SUCCESS${NC}: $1"
}

print_error() {
    echo -e "  ${RED}${CROSSMARK} FAILED${NC}: $1"
}

print_warning() {
    echo -e "  ${YELLOW}! WARNING${NC}: $1"
}

check_command() {
    if command -v "$1" &> /dev/null; then
        return 0
    else
        return 1
    fi
}

# ══════════════════════════════════════════════════════════════════════════════
# STEP 1: CHECK PREREQUISITES
# ══════════════════════════════════════════════════════════════════════════════

step1_check_prerequisites() {
    print_step 1 "Checking prerequisites..."
    
    local all_ok=true
    
    # Check Node.js
    if check_command node; then
        print_success "Node.js $(node -v)"
    else
        print_error "Node.js not found"
        all_ok=false
    fi
    
    # Check npm/pnpm
    if check_command pnpm; then
        print_success "pnpm $(pnpm -v)"
    elif check_command npm; then
        print_success "npm $(npm -v)"
    else
        print_error "npm/pnpm not found"
        all_ok=false
    fi
    
    # Check PM2
    if check_command pm2; then
        print_success "PM2 $(pm2 -v)"
    else
        print_warning "PM2 not found, installing..."
        npm install -g pm2
        print_success "PM2 installed"
    fi
    
    # Check ufw
    if check_command ufw; then
        print_success "ufw available"
    else
        print_warning "ufw not found, skipping firewall setup"
    fi
    
    # Check curl
    if check_command curl; then
        print_success "curl available"
    else
        print_error "curl not found"
        all_ok=false
    fi
    
    if [ "$all_ok" = false ]; then
        echo -e "\n${RED}Prerequisites check failed. Please install missing components.${NC}"
        exit 1
    fi
}

# ══════════════════════════════════════════════════════════════════════════════
# STEP 2: CONFIGURE ENVIRONMENT
# ══════════════════════════════════════════════════════════════════════════════

step2_configure_environment() {
    print_step 2 "Configuring environment..."
    
    # Create .env from example if not exists
    if [ ! -f "$ENV_FILE" ]; then
        if [ -f "$ENV_EXAMPLE" ]; then
            cp "$ENV_EXAMPLE" "$ENV_FILE"
            print_warning ".env created from .env.example"
        else
            # Create minimal .env
            cat > "$ENV_FILE" << 'EOF'
# Trading Bridge Environment Configuration
NODE_ENV=production
PORT=3000

# Webhook Secret (HMAC-SHA256)
WEBHOOK_SECRET=your_webhook_secret_here

# Telegram Alerts (optional)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Broker API (optional)
BROKER_API_KEY=
BROKER_API_SECRET=
EOF
            print_warning ".env created with defaults"
        fi
    fi
    
    # Prompt for secrets if default values
    if grep -q "your_webhook_secret_here" "$ENV_FILE" 2>/dev/null; then
        echo -e "\n${YELLOW}Enter secrets for production deployment:${NC}"
        
        read -p "Webhook Secret (leave blank to generate): " webhook_secret
        if [ -z "$webhook_secret" ]; then
            webhook_secret=$(openssl rand -hex 32)
            print_success "Generated webhook secret"
        fi
        
        read -p "Telegram Bot Token (optional): " telegram_token
        read -p "Telegram Chat ID (optional): " telegram_chat_id
        
        # Update .env file
        sed -i "s/your_webhook_secret_here/$webhook_secret/" "$ENV_FILE"
        
        if [ -n "$telegram_token" ]; then
            sed -i "s/^TELEGRAM_BOT_TOKEN=.*/TELEGRAM_BOT_TOKEN=$telegram_token/" "$ENV_FILE"
        fi
        
        if [ -n "$telegram_chat_id" ]; then
            sed -i "s/^TELEGRAM_CHAT_ID=.*/TELEGRAM_CHAT_ID=$telegram_chat_id/" "$ENV_FILE"
        fi
        
        print_success "Environment configured"
    else
        print_success "Environment already configured"
    fi
}

# ══════════════════════════════════════════════════════════════════════════════
# STEP 3: CONFIGURE FIREWALL
# ══════════════════════════════════════════════════════════════════════════════

step3_configure_firewall() {
    print_step 3 "Configuring firewall..."
    
    if ! check_command ufw; then
        print_warning "ufw not available, skipping firewall configuration"
        return 0
    fi
    
    # Check if ufw is active
    if ! sudo ufw status | grep -q "Status: active"; then
        print_warning "ufw is not active"
        read -p "Enable ufw? (y/N): " enable_ufw
        if [[ "$enable_ufw" =~ ^[Yy]$ ]]; then
            sudo ufw allow OpenSSH
            sudo ufw enable
            print_success "ufw enabled"
        else
            print_warning "Skipping ufw configuration"
            return 0
        fi
    fi
    
    # Open port 3000
    if sudo ufw status | grep -q "3000/tcp.*ALLOW"; then
        print_success "Port 3000 already open"
    else
        sudo ufw allow 3000/tcp
        print_success "Port 3000 opened"
    fi
    
    # Reload ufw
    sudo ufw reload
    print_success "Firewall configured"
}

# ══════════════════════════════════════════════════════════════════════════════
# STEP 4: INSTALL DEPENDENCIES
# ══════════════════════════════════════════════════════════════════════════════

step4_install_dependencies() {
    print_step 4 "Installing dependencies..."
    
    cd "$PROJECT_DIR"
    
    # Install with pnpm or npm
    if check_command pnpm; then
        pnpm install --production
        print_success "Dependencies installed with pnpm"
    else
        npm install --production
        print_success "Dependencies installed with npm"
    fi
}

# ══════════════════════════════════════════════════════════════════════════════
# STEP 5: START PM2
# ══════════════════════════════════════════════════════════════════════════════

step5_start_pm2() {
    print_step 5 "Starting PM2 processes..."
    
    cd "$PROJECT_DIR"
    
    # Create logs directories
    mkdir -p "$LOG_DIR"
    mkdir -p "$LOG_DIR/pm2"
    
    # Check if ecosystem config exists
    if [ ! -f "$ECOSYSTEM_CONFIG" ]; then
        print_error "ecosystem.config.js not found"
        exit 1
    fi
    
    # Stop existing processes
    pm2 delete all 2>/dev/null || true
    
    # Start with ecosystem config
    pm2 start "$ECOSYSTEM_CONFIG"
    
    # Save PM2 state
    pm2 save
    
    # Setup startup script
    pm2 startup systemd -u $(whoami) --hp $(echo $HOME) 2>/dev/null || true
    
    print_success "PM2 processes started"
    
    # Show status
    echo ""
    pm2 list
}

# ══════════════════════════════════════════════════════════════════════════════
# STEP 6: REGISTER WEBHOOK URL
# ══════════════════════════════════════════════════════════════════════════════

step6_register_webhook() {
    print_step 6 "Registering TradingView webhook URL..."
    
    # Get server IP
    SERVER_IP=$(curl -s ifconfig.me || curl -s icanhazip.com || echo "localhost")
    
    # Read webhook secret from .env
    WEBHOOK_SECRET=$(grep "^WEBHOOK_SECRET=" "$ENV_FILE" | cut -d'=' -f2)
    
    if [ -z "$WEBHOOK_SECRET" ] || [ "$WEBHOOK_SECRET" = "your_webhook_secret_here" ]; then
        print_warning "Webhook secret not configured, skipping registration"
        return 0
    fi
    
    WEBHOOK_URL="http://${SERVER_IP}:3000/webhook?secret=${WEBHOOK_SECRET}"
    
    echo -e "\n${BLUE}TradingView Webhook Configuration:${NC}"
    echo -e "  URL: ${GREEN}$WEBHOOK_URL${NC}"
    echo ""
    echo -e "  ${YELLOW}Instructions for TradingView:${NC}"
    echo -e "  1. Open TradingView alert settings"
    echo -e "  2. Select 'Webhook URL' notification"
    echo -e "  3. Paste the URL above"
    echo -e "  4. Save the alert"
    echo ""
    
    # Test webhook endpoint
    print_warning "Testing webhook endpoint..."
    if curl -s -o /dev/null -w "%{http_code}" "http://localhost:3000/health" | grep -q "200"; then
        print_success "Webhook endpoint is responding"
    else
        print_warning "Webhook endpoint not responding (may need restart)"
    fi
}

# ══════════════════════════════════════════════════════════════════════════════
# DEPLOYMENT SUMMARY
# ══════════════════════════════════════════════════════════════════════════════

print_summary() {
    echo ""
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}       DEPLOYMENT COMPLETE${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "  ${ARROW} Server IP: ${GREEN}$SERVER_IP${NC}"
    echo -e "  ${ARROW} Webhook URL: ${GREEN}http://$SERVER_IP:3000/webhook${NC}"
    echo -e "  ${ARROW} Health Check: ${GREEN}http://$SERVER_IP:3000/health${NC}"
    echo -e "  ${ARROW} PM2 Status: ${GREEN}pm2 list${NC}"
    echo -e "  ${ARROW} PM2 Logs: ${GREEN}pm2 logs trading-bridge${NC}"
    echo ""
    echo -e "  ${YELLOW}Next Steps:${NC}"
    echo -e "  1. Configure TradingView alert with webhook URL"
    echo -e "  2. Test with paper trading first"
    echo -e "  3. Monitor logs: pm2 logs trading-bridge"
    echo -e "  4. Check health: curl http://$SERVER_IP:3000/health"
    echo ""
}

# ══════════════════════════════════════════════════════════════════════════════
# MAIN EXECUTION
# ══════════════════════════════════════════════════════════════════════════════

main() {
    print_header
    
    step1_check_prerequisites
    step2_configure_environment
    step3_configure_firewall
    step4_install_dependencies
    step5_start_pm2
    step6_register_webhook
    print_summary
}

# Run with error handling
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
