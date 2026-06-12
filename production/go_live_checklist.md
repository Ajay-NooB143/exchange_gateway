# Go-Live Checklist — 10-Point Production Readiness

## Pre-Deployment

### ☐ 1. PM2 Auto-Restart + Memory Monitoring
```bash
# Install PM2
npm install -g pm2

# Start with cluster mode (1 process per CPU)
pm2 start ecosystem.config.cjs

# Auto-restart on crash
pm2 startup systemd
pm2 save

# Memory monitoring (auto-restart if >256MB)
pm2 set pm2:max_memory_restart 256M

# Live monitoring dashboard
pm2 monit
```

**What PM2 handles:**
- Auto-restart on crash (up to 50 restarts)
- Memory limit enforcement (kills + restarts at 256MB)
- Log rotation
- Cluster mode for load distribution
- Graceful shutdown on `pm2 stop`

---

### ☐ 2. Network Security — iptables Firewall
```bash
# Allow only TradingView IPs to reach port 3000
iptables -A INPUT -p tcp -s 104.244.244.0/24 --dport 3000 -j ACCEPT
iptables -A INPUT -p tcp -s 104.244.245.0/24 --dport 3000 -j ACCEPT
iptables -A INPUT -p tcp -s 104.244.246.0/24 --dport 3000 -j ACCEPT
iptables -A INPUT -p tcp -s 104.244.247.0/24 --dport 3000 -j ACCEPT

# Block everything else to port 3000
iptables -A INPUT -p tcp --dport 3000 -j DROP

# Allow SSH (don't lock yourself out!)
iptables -A INPUT -p tcp --dport 22 -j ACCEPT

# Allow established connections
iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT

# Save rules
iptables-save > /etc/iptables/rules.v4
```

**Why:** Your webhook endpoint should only accept traffic from TradingView's servers. All other traffic is rejected before it reaches your application.

---

### ☐ 3. Dead-Man's Switch — Auto-Alert on Silence
```bash
# Set in .env.production
ALERT_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK
DEAD_MAN_TIMEOUT=3600000  # 1 hour in milliseconds
```

**How it works:**
1. Every time a signal is received, timestamp is recorded
2. Background checker runs every 60 seconds
3. If no signal for 1 hour → sends alert to Slack/Discord/Telegram
4. Alert resets when next signal arrives

**Alert example:**
```
⚠️ DEAD-MAN: No signal received for 65 minutes
Timestamp: 2026-06-09T15:30:00Z
Server: production-bridge-01
```

---

### ☐ 4. Hard-Stop — Daily Drawdown Circuit Breaker
```bash
# Set in .env.production
MAX_DRAWDOWN=3.0        # 3% max drawdown from peak equity
DAILY_LOSS_LIMIT=300    # $300 max daily loss
MAX_DAILY_TRADES=20     # Max 20 trades per day
```

**How it works:**
```javascript
// Before every trade:
if (dailyPnl <= -300) → HALT (daily loss limit)
if (drawdown >= 3%)   → HALT (drawdown limit)
if (dailyTrades >= 20) → HALT (trade count limit)
```

**When halted:**
- All incoming signals are rejected with `403`
- Reason is logged and stored in state file
- Manual resume required via `POST /resume`
- State persists across restarts

---

### ☐ 5. SSL/TLS Encryption
```bash
# Install certbot
apt install certbot

# Get certificate
certbot certonly --standalone -d your-domain.com

# In nginx config:
ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

# Force HTTPS redirect
return 301 https://$host$request_uri;
```

**Why:** TradingView webhooks with secrets in URL params must be encrypted in transit.

---

### ☐ 6. Log Rotation
```bash
# PM2 log rotation
pm2 install pm2-logrotate
pm2 set pm2-logrotate:max_size 10M
pm2 set pm2-logrotate:retain 30
pm2 set pm2-logrotate:compress true
```

**Or via logrotate:**
```
/opt/trading-bridge/logs/*.log {
    daily
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 root root
}
```

---

### ☐ 7. Monitoring + Alerting
```bash
# Install PM2 plus for web dashboard
npm install -g pm2-plus

# Connect to PM2 Plus monitoring
pm2 plus

# Or use Prometheus + Grafana
# Expose /metrics endpoint in your bridge
```

**Metrics to monitor:**
| Metric | Alert Threshold |
|--------|----------------|
| Error rate | >5% |
| Response latency | >500ms |
| Memory usage | >200MB |
| CPU usage | >80% for 5min |
| Daily PnL | <-$200 |
| Dead-man silence | >1 hour |

---

### ☐ 8. Backup + Recovery
```bash
# Backup state file daily
crontab -e
0 0 * * * cp /opt/trading-bridge/data/production_state.json /opt/trading-bridge/backups/state_$(date +\%Y\%m\%d).json

# Keep last 30 days
0 1 * * * find /opt/trading-bridge/backups -name "state_*.json" -mtime +30 -delete

# Backup to remote
0 2 * * * rclone copy /opt/trading-bridge/backups/ remote:trading-backups/
```

**Critical files to backup:**
- `data/production_state.json` — daily PnL, halt status, equity
- `logs/` — trade history
- `.env.production` — configuration

---

### ☐ 9. Process Limits + Security
```bash
# Limit file descriptors
ulimit -n 65535

# Limit connections per IP (prevent abuse)
iptables -A INPUT -p tcp --dport 3000 -m connlimit --connlimit-above 10 -j DROP

# Rate limiting (max 10 requests/second per IP)
iptables -A INPUT -p tcp --dport 3000 -m hashlimit \
    --hashlimit-name webhook \
    --hashlimit-above 10/sec \
    --hashlimit-burst 20 \
    --hashlimit-mode srcip \
    --hashlimit-htable-expire 30000 \
    -j DROP
```

---

### ☐ 10. Pre-Live Testing
```bash
# 1. Test health endpoint
curl http://localhost:3000/health

# 2. Test webhook with valid payload
curl -X POST http://localhost:3000/webhook?secret=YOUR_SECRET \
  -H "Content-Type: application/json" \
  -d '{"symbol":"XAUUSD","side":"Long","entry_price":2350,"stop_loss":2345,"position_size":1}'

# 3. Test hard-stop (should reject)
curl -X POST http://localhost:3000/kill

# 4. Verify state persisted
cat /opt/trading-bridge/data/production_state.json

# 5. Test restart
pm2 restart trading-bridge
curl http://localhost:3000/health

# 6. Paper trade for 48 hours minimum before live
```

---

## Quick Reference

| Command | Purpose |
|---------|---------|
| `pm2 status` | Check process status |
| `pm2 logs trading-bridge` | View live logs |
| `pm2 monit` | Real-time monitoring |
| `pm2 restart trading-bridge` | Restart application |
| `pm2 stop trading-bridge` | Stop application |
| `pm2 delete trading-bridge` | Remove from PM2 |
| `curl localhost:3000/health` | Health check |
| `POST /kill` | Emergency halt |
| `POST /resume` | Resume trading |

---

## Emergency Procedures

**If bot is trading erratically:**
```bash
# 1. Immediate halt
curl -X POST http://localhost:3000/kill

# 2. Stop PM2 process
pm2 stop trading-bridge

# 3. Check state
cat /opt/trading-bridge/data/production_state.json

# 4. Review logs
pm2 logs trading-bridge --lines 100
```

**If server is compromised:**
```bash
# 1. Block all traffic immediately
iptables -F INPUT
iptables -A INPUT -p tcp --dport 22 -j ACCEPT
iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
iptables -A INPUT -j DROP

# 2. Stop all trading
pm2 stop all

# 3. Change all secrets
# 4. Review access logs
# 5. Rebuild from clean image
```
