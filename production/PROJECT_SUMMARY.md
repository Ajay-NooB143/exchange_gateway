# XAUUSD Trading System - Complete Summary

## Project Overview

Automated institutional-grade XAUUSD scalping system with:
- Pine Script strategies (multiple variants)
- Node.js webhook bridge (low-latency)
- Python HFT liquidity chase engine
- Production deployment on Ubuntu VPS

## File Structure

```
api_workspace/
├── xauusd_sniper/           # Basic VWRSI strategy
├── xauusd_institutional/    # Full institutional strategy
├── execution_ready/         # Strategy + basic webhook bridge
├── advanced_modules/        # Order flow, regime, news, MTF
├── optimization/            # Low-latency bridge, DOM analyzer
├── validation/              # Trade logger, scalability docs
├── production/              # Production bridge, deploy scripts
├── smc_scalper/             # SMC strategy (OB+FVG+MSS)
├── hft_liquidity_chase/     # Async HFT engine
├── TradingAgents/           # Cloned research repo
└── TradingView-API/         # Cloned TV API repo
```

## Key Components

### 1. Pine Script Strategies

| File | Features | Best For |
|------|----------|----------|
| `xauusd_sniper/strategy.pine` | VWRSI + multi-agent | Learning |
| `xauusd_institutional/strategy.pine` | Sweep+MSS+FVG+VRSI+Risk | Production |
| `execution_ready/strategy.pine` | Slippage modeling | Backtesting |
| `smc_scalper/smc_strategy.pine` | OB+FVG+MSS | SMC traders |
| `advanced_modules/modules.pine` | 4 standalone modules | Custom combos |

### 2. Webhook Bridges

| File | Latency | Features |
|------|---------|----------|
| `execution_ready/webhook_bridge.mjs` | ~10ms | Basic |
| `optimization/low_latency_bridge.mjs` | ~1ms | Zero-copy parser |
| `validation/webhook_bridge_validated.mjs` | ~5ms | Trade logging |
| `production/production_bridge.mjs` | ~2ms | Full risk engine |

### 3. Python Execution

| File | Purpose |
|------|---------|
| `smc_scalper/smc_executor.py` | SMC strategy executor |
| `hft_liquidity_chase/engine.py` | Async HFT engine |

### 4. Deployment

| File | Purpose |
|------|---------|
| `production/deploy.sh` | VPS setup script |
| `production/ecosystem.config.cjs` | PM2 config |
| `production/monitor.sh` | Real-time monitoring |
| `production/verify_deployment.sh` | Deployment verification |

## VPS Deployment Status

**IP**: 172.105.252.194
**Port**: 3000
**Process**: PM2 cluster (2 instances)

### Current State
- ✓ Bridge deployed and running
- ✓ Webhook endpoint responding
- ✓ Health check working
- ✓ Kill switch functional
- ⚠ Port 3000 not externally accessible (needs security group)
- ⚠ Using placeholder secrets

## Risk Management

| Rule | Value |
|------|-------|
| Max risk per trade | 1% equity |
| Max daily drawdown | 3% |
| Max trades per day | 10 |
| Max consecutive losses | 3 (then halt) |
| Time-stop | 180 seconds |
| Break-even trigger | 1:1 RR |

## Trading Sessions

- **Primary**: London/NY overlap (13:00-16:00 GMT)
- **Secondary**: London (07:00-16:00 GMT), NY (13:00-22:00 GMT)
- **Avoid**: Asian session, NFP, FOMC, major news

## Next Actions

1. Edit `/opt/trading-bridge/.env.production` with real secrets
2. Open port 3000 in VPS cloud security group
3. Configure TradingView webhook URL
4. Paper trade 48+ hours
5. Go live with minimum size

## Monitoring

```bash
# Quick check
ssh root@172.105.252.194
pm2 status
curl http://localhost:3000/health

# Full monitor
bash /opt/trading-bridge/monitor.sh

# Logs
pm2 logs trading-bridge
```

## Emergency Stop

```bash
# Via API
curl -X POST http://172.105.252.194:3000/kill

# Via PM2
pm2 stop trading-bridge
```

## Support

- Health endpoint: `GET /health`
- Kill switch: `POST /kill`
- Resume trading: `POST /resume`
- Trade state: `/opt/trading-bridge/data/production_state.json`
- Trade log: `/opt/trading-bridge/data/trade_log.csv`
