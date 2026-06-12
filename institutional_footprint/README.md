# Institutional Footprint Tracker - Documentation

## Overview

The Institutional Footprint Tracker is a complete automated trading system that detects and trades institutional order flow patterns in XAUUSD (Gold). It consists of three integrated components:

```
┌─────────────────────────────────────────────────────────────────┐
│                    ARCHITECTURE                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │  Pine Script  │    │  Node.js     │    │  Python      │       │
│  │  v6 Strategy  │───▶│  Bridge      │───▶│  CVD Engine  │       │
│  │  (Detection)  │    │  :3000       │    │  :8080       │       │
│  └──────────────┘    └──────────────┘    └──────────────┘       │
│         │                   │                   │                │
│         │                   │                   │                │
│         ▼                   ▼                   ▼                │
│  TradingView          Webhook            Broker API             │
│  Alerts               Routing            Execution              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Components

### 1. Pine Script Strategy (`institutional_footprint.pine`)

**Detection Modules:**

| Module | Description |
|--------|-------------|
| Institutional Order Blocks (IOB) | High-volume candles causing Break of Structure |
| Liquidity Sweeps | Stop hunts / false breakouts at retail levels |
| Fair Value Gaps (FVG) | Institutional imbalance zones |
| Break of Structure (BOS) | Trend shift confirmation |
| CVD Divergence | Price/volume divergence (validated in Python) |

**Signal Generation:**

```pine
// Long Signal Conditions:
1. Price sweeps below old lows (liquidity grab)
2. Closes back above the level (sweep confirmed)
3. Returns to mitigate bullish IOB zone
// OR
1. High-volume candle causes bullish BOS
2. Price returns to open of that candle (IOB mitigation)

// Short Signal (inverse logic)
```

**Risk Management:**
- 1% risk per trade
- 3% daily max drawdown
- 3 trades per day maximum
- Break-even trigger at 1:1 RR
- Time-stop at 180 seconds

### 2. Node.js Bridge (`bridge.mjs`)

**Features:**
- Sub-millisecond webhook parsing
- Rate limiting (10 req/min)
- Daily trade limit enforcement
- Secret validation
- Health monitoring

**Endpoints:**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/webhook` | POST | Receive TradingView alerts |
| `/health` | GET | Health check |
| `/kill` | POST | Emergency stop |

### 3. Python Execution Engine (`execution_engine.py`)

**Validation Pipeline:**

```
Signal Received → CVD Validation → Risk Check → Position Sizing → Execute
        │               │              │              │              │
        │               │              │              │              │
        ▼               ▼              ▼              ▼              ▼
   Parse JSON    Check Divergence  Daily Limits   1% Risk      Market/Limit
   Validate      Detect Absorption  Session       ATR-based    Fill Order
   Secret        Confirm Direction  R:R Check     Calculate    Log Trade
```

**CVD Validation Logic:**

For sweep_return signals:
- If price swept lows and CVD shows higher low = **ABSORPTION** = CONFIRM
- If price swept highs and CVD shows lower high = **ABSORPTION** = CONFIRM

For iob_mitigation signals:
- Verify selling/buying pressure was absorbed
- Check CVD direction supports the trade

## Installation

### Quick Deploy (Recommended)

```bash
# On VPS
cd /home/userland/api_workspace/institutional_footprint
bash deploy.sh
```

### Manual Deploy

```bash
# 1. Install Python dependencies
pip3 install aiohttp numpy pandas

# 2. Copy files
cp *.pine *.py *.mjs *.cjs /opt/trading-bridge/institutional_footprint/

# 3. Configure
cp .env.example .env
nano .env  # Edit with your values

# 4. Start with PM2
pm2 start ecosystem.config.cjs
pm2 save
```

## Configuration

### Environment Variables (`.env`)

```bash
# Required
WEBHOOK_SECRET=your_secret_here  # Generate: openssl rand -hex 32

# Risk Management
RISK_PER_TRADE=0.01      # 1% per trade
MAX_DAILY_LOSS=0.03      # 3% daily max
MAX_DAILY_TRADES=3       # 3 trades max

# CVD Validation
CVD_LOOKBACK=10          # Bars to check
CVD_THRESHOLD=0.3        # Min divergence
MIN_ABSORPTION_VOLUME=50 # Min ticks for absorption

# Execution
USE_LIMIT_ORDERS=true
LIMIT_OFFSET_PIPS=0.5
```

### TradingView Alert Setup

1. Open your chart in TradingView
2. Add alert on `institutional_footprint` strategy
3. Set **Webhook URL**:
   ```
   http://YOUR_VPS_IP:3000/webhook?secret=YOUR_SECRET
   ```
4. Set **Message** (JSON):
   ```json
   {
     "signal": "{{strategy.order.action}}",
     "entry": {{close}},
     "sl": {{plot("SL")}},
     "tp": {{plot("TP")}},
     "sl_pips": {{plot("SL Pips")}},
     "tp_pips": {{plot("TP Pips")}},
     "type": "{{plot("Signal Type")}}",
     "cvd_divergent": {{plot("CVD Divergent")}},
     "regime": "{{plot("Regime")}}",
     "atr": {{plot("ATR")}},
     "volume_pct": {{plot("Volume Pct")}},
     "session": "{{plot("Session")}}",
     "risk_pct": 1.0,
     "timestamp": "{{timenow}}",
     "secret": "YOUR_SECRET_HERE"
   }
   ```
5. Save and enable

## Webhook Payload Format

```json
{
  "signal": "long|short",
  "entry": 2650.50,
  "sl": 2648.00,
  "tp": 2655.50,
  "sl_pips": 25.0,
  "tp_pips": 50.0,
  "type": "sweep_return|iob_mitigation",
  "cvd_divergent": true,
  "regime": "bullish|bearish",
  "atr": 2.5,
  "volume_pct": 85.3,
  "session": "active|inactive",
  "risk_pct": 1.0,
  "timestamp": "2026-06-10T14:30:00Z",
  "secret": "your_secret_here"
}
```

## Monitoring

### Health Checks

```bash
# Bridge health
curl http://localhost:3000/health

# Engine stats
curl http://localhost:8080/stats

# PM2 status
pm2 status
```

### Logs

```bash
# Real-time logs
pm2 logs footprint-bridge
pm2 logs footprint-engine

# Trade log
cat /opt/trading-bridge/data/execution_log.csv | column -t -s','
```

### Monitor Script

```bash
# Continuous monitoring
watch -n 5 'curl -s http://localhost:3000/health | python3 -m json.tool'
```

## Emergency Procedures

### Kill Switch

```bash
# Via API
curl -X POST http://localhost:3000/kill

# Via PM2
pm2 stop footprint-bridge
pm2 stop footprint-engine

# Nuclear option
pm2 delete all
```

### Reset Daily Counter

```bash
# Restart bridge
pm2 restart footprint-bridge
```

## Trading Logic Deep Dive

### Liquidity Sweep Detection

```
1. Identify old retail highs/lows (equal highs/lows)
2. Wait for price to spike past these levels
3. Check if price closes back inside within 1-3 candles
4. Flag as "Liquidity Sweep"
5. Enter when price returns to the level
```

### IOB Mitigation

```
1. Detect high-volume candle (90th percentile)
2. Confirm it caused Break of Structure
3. Mark open/close as IOB zone
4. Wait for price to return to zone
5. Enter on mitigation
```

### CVD Absorption

```
1. Large market orders hit (aggressive selling)
2. Price makes lower low
3. But CVD shows higher low (passive buying absorbed)
4. Confirm institutional accumulation
5. Enter long
```

## Performance Metrics

| Metric | Target |
|--------|--------|
| Webhook parse time | < 1ms |
| CVD validation | < 5ms |
| End-to-end latency | < 50ms |
| Daily win rate | > 55% |
| Average R:R | > 1.8 |

## Troubleshooting

### Bridge not responding

```bash
# Check PM2 status
pm2 status

# Check logs
pm2 logs footprint-bridge --lines 50

# Restart
pm2 restart footprint-bridge
```

### Engine not validating

```bash
# Check Python process
pm2 status footprint-engine

# Check engine logs
pm2 logs footprint-engine --lines 50

# Test endpoint
curl http://localhost:8080/health
```

### Trades not executing

1. Verify TradingView alert is enabled
2. Check webhook URL is correct
3. Verify secret matches
4. Check daily limits
5. Check session filter

## File Structure

```
institutional_footprint/
├── institutional_footprint.pine   # Pine Script strategy
├── execution_engine.py            # Python CVD engine
├── bridge.mjs                     # Node.js webhook bridge
├── ecosystem.config.cjs           # PM2 configuration
├── .env.example                   # Environment template
├── deploy.sh                      # Deployment script
└── README.md                      # This file
```
