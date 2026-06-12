# Final Deployment Steps

## Step 1: Configure Secrets (Run on VPS)

```bash
# Edit environment config
nano /opt/trading-bridge/.env.production
```

Set these values:
```bash
WEBHOOK_SECRET=your_random_secret_here  # Generate: openssl rand -hex 32
BROKER_API_KEY=your_real_broker_api_key
BROKER_ACCOUNT_ID=your_account_id
TRADINGVIEW_ALERT_URL=https://your-tradingview-alert-url.com/webhook
DEAD_MAN_WEBHOOK=https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK  # Optional
```

Restart after editing:
```bash
pm2 restart trading-bridge
```

## Step 2: Open Port 3000 (Cloud Provider)

Log into your VPS provider dashboard (AWS/GCP/Azure/DigitalOcean):

1. Go to **Networking** → **Firewall** or **Security Groups**
2. **Add Rule**:
   - **Type**: Custom TCP
   - **Port**: 3000
   - **Source**: 0.0.0.0/0 (or TradingView IPs only for security)
   - **Action**: Allow
3. Save

TradingView IPs (if restricting):
```
104.16.0.0/12
172.64.0.0/13
131.0.0.0/16
```

## Step 3: Run Verification (On VPS)

```bash
bash /opt/trading-bridge/verify_deployment.sh
```

Or copy the file from workspace:
```bash
scp verify_deployment.sh root@172.105.252.194:/opt/trading-bridge/
ssh root@172.105.252.194
bash /opt/trading-bridge/verify_deployment.sh
```

## Step 4: Configure TradingView Alert

In TradingView:
1. Open XAUUSD chart
2. Add alert on your Pine Script
3. Set **Webhook URL**:
   ```
   http://172.105.252.194:3000/webhook?secret=YOUR_SECRET_HERE
   ```
4. Set **Message** (JSON):
   ```json
   {
     "action": "{{strategy.order.action}}",
     "price": {{close}},
     "sl": {{plot("SL")}},
     "tp": {{plot("TP")}},
     "regime": "{{plot("Regime")}}",
     "confluence": {{plot("Confluence")}},
     "time": "{{timenow}}"
   }
   ```
5. Save and enable alert

## Step 5: Paper Trade (48+ Hours)

```bash
# Monitor trades
bash /opt/trading-bridge/monitor.sh

# Watch logs
pm2 logs trading-bridge --lines 100
```

Check for:
- ✓ Trades executing correctly
- ✓ Risk limits respected
- ✓ No errors in logs
- ✓ Proper position sizing

## Step 6: Firewall (Optional but Recommended)

```bash
# Install UFW
apt update && apt install ufw -y

# Allow SSH
ufw allow 22/tcp

# Allow webhook (TradingView only)
ufw allow from 104.16.0.0/12 to any port 3000
ufw allow from 172.64.0.0/13 to any port 3000
ufw allow from 131.0.0.0/16 to any port 3000

# Enable
ufw enable
ufw status
```

## Step 7: Go Live (When Ready)

After 48+ hours of successful paper trading:

1. Update `.env.production` with real broker credentials
2. Set `PAPER_TRADE=false` (if applicable)
3. `pm2 restart trading-bridge`
4. Start with minimum position size
5. Monitor first 10 trades closely

## Monitoring Commands

```bash
# Quick status
pm2 status

# Watch real-time
pm2 logs trading-bridge

# Full monitor
bash /opt/trading-bridge/monitor.sh

# Trade log
cat /opt/trading-bridge/data/trade_log.csv | column -t -s','

# Check state
cat /opt/trading-bridge/data/production_state.json | python3 -m json.tool
```

## Emergency Stop

```bash
# Kill switch via API
curl -X POST http://localhost:3000/kill

# Or via PM2
pm2 stop trading-bridge

# Nuclear option
pm2 delete trading-bridge
```
