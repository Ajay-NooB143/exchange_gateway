# OMNI BRAIN V2 - PROJECT STATE
## Checkpoint File for Next Session
**Last Updated:** 2026-06-11
**Test Status:** 337/337 passing

## QUICK RESUME
To resume in new session:
1. Open OpenCode
2. Copy START_SESSION.md content
3. Paste and send
4. System loaded in 30 seconds

---

## PRODUCTION MODULES (25 files)

| Module | File | Purpose |
|--------|------|---------|
| Smart Money Matrix | `production/smart_money_matrix.py` | OB + FVG + Liquidity Sweep detection |
| Numba Smart Money | `evolution_engine/smart_money_matrix_numba.py` | JIT-optimized matrix (sub-ms) |
| MT5 Sync Guard | `production/mt5_sync_guard.py` | Split-brain lock for MT5 data sync |
| Async MT5 Guard | `production/async_mt5_sync_guard.py` | Async version with Semaphore(4) |
| Live Feed Scanner | `production/live_feed_scanner.py` | Twelve Data WebSocket + REST polling |
| Memory Monitor | `production/memory_monitor.py` | psutil memory alerts (80MB threshold) |
| Confidence Scorer | `production/confidence_scorer.py` | Signal score 0-100 (OB+FVG+SWEEP+VWAP+SESSION) |
| Adaptive Threshold | `production/adaptive_threshold.py` | Per-asset threshold adaptation |
| MTF Confirmation | `production/mtf_confirmation.py` | Multi-timeframe chain (M15→H1→H4→D1) |
| Circuit Breaker | `production/circuit_breaker.py` | 5 rules, 4 states (ACTIVE/PAUSED/THROTTLED/HALTED) |
| Health Heartbeat | `production/health_heartbeat.py` | 5min Telegram heartbeat |
| Daily Report | `production/daily_report.py` | Daily performance report generator |
| Auto-Backtester | `production/auto_backtester.py` | Enhanced backtester with score buckets, sessions, streaks |
| Self-Healing Cron | `production/self_healing_cron.py` | PM2 alive, stale locks, disk, .env checks |
| Evo Status Panel | `production/evo_status_panel.py` | ASCII panel + /api/evo-status endpoint |
| GitHub Signal Logger | `production/github_signal_logger.py` | Push EXECUTE signals to GitHub |
| Split-Brain Guard | `production/split_brain_guard.py` | Atomic O_EXCL file lock |
| Async Split-Brain | `production/async_split_brain_guard.py` | Unix socket lock (< 0.1ms) |
| **Telegram Signals** | `production/telegram_signals.py` | **NEW: EXECUTE/WAIT/BLOCK alerts + bot commands + outcome tracking** |
| **Instagram Reels** | `content/instagram_reels_generator.py` | **NEW: Auto-generate Reel scripts from signals** |

---

## EVOLUTION ENGINE (4 modules)

| Module | File | Purpose |
|--------|------|---------|
| Analysis Engine | `evolution_engine/analysis_engine.py` | Log ingestion, metrics, regime detection |
| Parameter Evolution | `evolution_engine/parameter_evolution.py` | Mutation, crossover, regime-adaptive tuning |
| Champion vs Challenger | `evolution_engine/champion_challenger.py` | Backtest engine + battle judge |
| Evolution Log | `evolution_engine/evolution_log.py` | EVOLUTION_LOG.md generator |
| Orchestrator | `evolution_engine/orchestrator.py` | 24-hour loop controller |

---

## CORE FILES

| File | Purpose |
|------|---------|
| `lte_v35.py` | OmniSignalApexV35 main terminal with --asset CLI |
| `pipeline_orchestrator.py` | Full pipeline (scan→CB→MTF→score→threshold→decision) |
| `ecosystem.config.js` | PM2 cluster config (5 apps) |
| `.env.example` | Environment variables template |
| `.env` | Live secrets (NEVER commit) |

---

## FRONTEND

| File | Purpose |
|------|---------|
| `frontend/omni_core_v2/index.html` | **CDN build** - zero-step, loads React/Recharts from unpkg |
| `frontend/omni_core_v2/App.jsx` | **10-panel dashboard** - Header, LiveFeed, Confidence, MTF, CB, Backtest, Evo, MT5, Vitals, Chart |
| `frontend/omni_core_v2/styles.css` | Terminal-noir cyberpunk with pulse/glow animations |
| `frontend/omni_core_v2/package.json` | CDN deps (React 18, Recharts, Lucide) |

---

## .ENV VARIABLES

```bash
# MT5 Broker
MT5_LOGIN=your_mt5_login
MT5_PASSWORD=your_mt5_password
MT5_SERVER=your_mt5_server

# Telegram Alerts
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Twelve Data Live Feed
LIVE_DATA_API_KEY=your_twelve_data_key
LIVE_DATA_PROVIDER=twelve_data
SCAN_INTERVAL_SECONDS=60

# GitHub Signal Archive
GITHUB_TOKEN=your_github_pat_token
GITHUB_REPO=yourusername/signals-log

# Trading Parameters
MAX_POSITION_SIZE=0.1
MAX_DAILY_TRADES=20
MAX_DRAWDOWN_PCT=3
RISK_PER_TRADE_PCT=1

# Network
PORT=3000
BIND_HOST=0.0.0.0
```

---

## PM2 PROCESS NAMES

| Process | Script | Purpose |
|---------|--------|---------|
| `omni-scanner` | `production/live_feed_scanner.py` | Twelve Data feed |
| `omni-pipeline` | `pipeline_orchestrator.py` | API server on :3000 |
| `omni-heartbeat` | `production/health_heartbeat.py` | 5min Telegram heartbeat |
| `omni-report` | `production/daily_report.py` | Daily report scheduler |
| `omni-monitor` | `production/memory_monitor.py` | Memory alerts |
| `omni-telegram` | `production/telegram_signals.py` | **NEW:** Signal alerts + bot commands |

---

## API ENDPOINTS

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/health` | Health check |
| GET | `/api/omni-status` | Dashboard status (scores, MTF, CB, evolution) |
| GET | `/api/last-scan` | Last scan results |
| GET | `/api/feed-status` | Twelve Data feed status |
| GET | `/api/backtest-results` | **NEW:** Latest backtest JSON results |
| POST | `/api/trigger-scan` | Manual scan trigger |
| POST | `/api/pause/{symbol}` | **NEW:** Reset circuit breaker for asset |
| GET | `/api/evo-status` | Evolution engine status (JSON) |

---

## ASSETS & TIMEFRAMES

**Assets:** XAUUSD, EURUSD, GBPUSD, SP500
**Timeframes:** M15, H1, H4, D1
**Symbol Mapping (Twelve Data):**
- XAUUSD → XAU/USD
- EURUSD → EUR/USD
- GBPUSD → GBP/USD
- SP500 → SPX

---

## CONFIDENCE SCORING

| Component | Weight | Source |
|-----------|--------|--------|
| OB_SIGNAL | 20 pts | Smart Money Matrix |
| FVG_SIGNAL | 20 pts | Smart Money Matrix |
| SWEEP_SIGNAL | 30 pts | Smart Money Matrix |
| VWAP_SIGNAL | 15 pts | Price vs VWAP |
| SESSION_SIGNAL | 15 pts | London/NY session |

**Decision Thresholds:**
- EXECUTE: score >= 75
- WAIT: 50-74
- BLOCK: < 50

---

## CIRCUIT BREAKER RULES

1. **LOSS_STREAK**: 3 consecutive losses → pause 1hr
2. **MEMORY_HIGH**: > 80MB → throttle alerts
3. **MT5_UNSTABLE**: 3 connection failures → halt trading
4. **SCORE_LOW**: avg score < 45 → pause signals
5. **DAILY_LOSS**: 3% drawdown → halt all trading

**States:** ACTIVE → PAUSED → THROTTLED → HALTED

---

## TEST FILES

| File | Tests | Purpose |
|------|-------|---------|
| `tests/test_edge_cases.py` | 22 | OB, FVG, sweep, zero-volume, gaps |
| `tests/test_live_feed.py` | 27 | Twelve Data, rate limiting, GitHub |
| `tests/test_mt5_sync_guard.py` | 20 | Locks, validation, reconnect, async |
| `tests/test_new_modules.py` | ~100 | All 11 intelligence modules |
| `tests/test_monetization.py` | ~80 | PaperTrader, Subscription, Content |
| `tests/test_crypto.py` | ~40 | Crypto assets, session scoring |
| `tests/test_evolution.py` | **30+** | **NEW: DNA, fitness, mutation, scheduler, writer, AI engine** |
| **TOTAL** | **314+** | **All passing** |

---

## KEY PATHS

```
Lock files:     /tmp/mt5_sync_{symbol}_{tf}.lock
Error logs:     logs/mt5_errors.log
CSV fallback:   data/csv/{symbol}_{tf}.csv
Pipeline log:   logs/pipeline_log.csv
Signal logs:    logs/signals_{symbol}.csv
Last scan:      logs/last_scan.json
API state:      logs/api_state.json
Heartbeat:      logs/heartbeat.json
Circuit state:  logs/circuit_state.json
Threshold:      logs/threshold_{symbol}.json
Reports:        logs/reports/
```

---

## DEPLOY COMMAND

```bash
# Copy to VPS
scp -r /home/userland/api_workspace/* root@172.105.252.194:/opt/trading-bridge/

# SSH and start
ssh root@172.105.252.194
cd /opt/trading-bridge
cp .env.example .env  # Edit with secrets
pm2 start ecosystem.config.js
pm2 status
pm2 logs omni-scanner
```

---

## VPS INFO

- **IP:** 172.105.252.194
- **Port:** 3000 (TCP must be open in cloud security group)
- **OS:** Ubuntu 26.04
- **PM2:** Cluster mode, auto-restart

---

## TWELVE DATA API

- **Free Plan:** 8 requests/minute, 800/day
- **Rate Limiting:** 0.8s between requests
- **REST Batching:** 8 batches × 2 requests = 16 per cycle (~2 min)
- **WebSocket:** wss://ws.twelvedata.com/v1/quotes/price
- **REST:** GET https://api.twelvedata.com/time_series

---

## CONTENT & SOCIAL

| File | Purpose |
|------|---------|
| `content/instagram_reels_generator.py` | **NEW:** Auto-generate Reel scripts from signals |
| `content/templates/signal_card.txt` | ASCII visual template for signal cards |
| `content/templates/weekly_card.txt` | ASCII visual template for weekly results |
| `content/calendar.json` | Dynamic 30-day content calendar |
| `content/reels/` | Generated Reel scripts (signal, weekly, educational) |

---

## TELEGRAM COMMANDS

| Command | Description |
|---------|-------------|
| `/status` | Current scores all 4 assets |
| `/score XAUUSD` | Detailed score breakdown |
| `/cb` | Circuit breaker states |
| `/pause` | Pause all alerts 1 hour |
| `/resume` | Resume alerts immediately |
| `/report` | Trigger daily report now |
| `/backtest` | Trigger backtest now |
| `/dna` | DNA evolution summary |
| `/dna_history` | Evolution generation history |
| `/rollback {N}` | Rollback DNA to generation N |
| `/evolution` | Trigger evolution cycle |
| `/fitness` | Current fitness score |
| `/apply_evolution` | Apply pending AI evolution suggestion |
| `/reject_evolution` | Reject pending AI evolution suggestion |
| `/help` | List all commands |

---

## SELF-EVOLVING AI PROMPT SYSTEM (NEW)

| Module | File | Purpose |
|--------|------|---------|
| Prompt DNA | `production/prompt_evolution.py` | DNA storage, MutationEngine (7 types), EvolutionScheduler, rollback |
| Fitness Evaluator | `production/fitness_evaluator.py` | Win rate, signal quality, false positive, avg RR scoring |
| Prompt Writer | `production/prompt_writer.py` | Self-writing signal/entry/risk/asset prompts |
| AI Evolution Engine | `production/ai_evolution_engine.py` | Claude API integration for intelligent suggestions |
| Evolution Tests | `tests/test_evolution.py` | 30+ tests covering all evolution components |

**DNA Directory:** `logs/prompt_dna/`
**Backup Directory:** `logs/prompt_dna/backups/`
**Evolved Prompts:** `logs/evolved_prompts/`

**Telegram Commands:** `/dna`, `/dna_history`, `/rollback {N}`, `/evolution`, `/fitness`, `/apply_evolution`, `/reject_evolution`

**API Endpoints:** `GET /api/evolution-status`, `GET /api/evolution-fitness`

**Frontend Panel:** DNA Evolution Tracker in dashboard grid

## NEXT STEPS

1. Open TCP port 3000 in VPS cloud security group
2. Edit `/opt/trading-bridge/.env` with real secrets (add `ANTHROPIC_API_KEY` for AI evolution)
3. Deploy: `bash scripts/deploy.sh`
4. Run evolution init: `python production/prompt_evolution.py --init`
5. Generate prompts: `python production/prompt_writer.py --generate`
6. Paper trade 48+ hours before live capital
7. First evolution cycle after 30+ live trades
