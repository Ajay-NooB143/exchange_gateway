# OMNI BRAIN V2 — SESSION CONTEXT
Last updated: auto-update each session

## PROJECT
Name: OMNI BRAIN V2 (OmniSignalApexV35)
Workspace: /home/userland/api_workspace
VPS: root@172.105.252.194:/opt/trading-bridge
Tests: 258/258 passing
PM2: 13+ processes online

## CORE FILES
lte_v35.py                    — main terminal
pipeline_orchestrator.py      — API server :3000
ecosystem.config.js           — PM2 config
.env / .env.example           — all secrets
PROJECT_STATE.md              — full file tree

## PRODUCTION MODULES (production/)
confidence_scorer.py          — 0-100 scoring
adaptive_threshold.py         — auto-adjust
mtf_confirmation.py           — M15→H1→H4→D1
circuit_breaker.py            — loss protection
health_heartbeat.py           — 5min Telegram ping
live_feed_scanner.py          — TwelveData WS
auto_backtester.py            — weekly backtest
github_signal_logger.py       — signal archive
daily_report.py               — 23:59 UTC report
self_healing_cron.py          — 15min health check
telegram_signals.py           — alerts + bot commands
paper_trader.py               — virtual $10k
subscription_manager.py       — free/VIP channels
correlation_engine.py         — 11-pair matrix
treasury_monitor.py           — US yield curve
sentiment_engine.py           — VADER+FinBERT
forex_factory_news.py         — news gate
mt5_sync_guard.py             — atomic lock
async_mt5_sync_guard.py       — async version
risk_manager.py               — Kelly sizing
pattern_engine.py             — 7 SMC patterns
divergence_scanner.py         — RSI/MACD divergence
prompt_evolution.py           — self-evolving DNA
fitness_evaluator.py          — fitness scoring
prompt_writer.py              — prompt generator
ai_evolution_engine.py        — Claude integration

## CONTENT MODULES (content/)
multilingual_engine.py        — 32 languages
auto_poster.py                — daily Instagram
youtube_generator.py          — 10 video scripts
instagram_reels_generator.py  — Reels content
showcase_generator.py         — signal cards
education_series.py           — 30-day course

## EVOLUTION ENGINE (evolution_engine/)
analysis_engine.py            — log ingestion + metrics
parameter_evolution.py        — Bayesian mutation
champion_challenger.py        — battle judge
evolution_log.py              — markdown logger
orchestrator.py               — 24hr loop

## SELF-EVOLVING PROMPT SYSTEM
Components: confidence_scorer, pattern_engine, mtf_confirmation, signal_filter, entry_rules, risk_rules
Mutation types: WEIGHT_SHIFT, THRESHOLD_DRIFT, RULE_INJECTION, RULE_DELETION, ASSET_SPECIALIZATION, CROSSOVER, FULL_RESET
Scheduler: MICRO (24h), MACRO (7d), EMERGENCY (triggered)
Claude API: Optional — generates evolution suggestions
Telegram commands: /dna, /dna_history, /rollback {N}, /evolution, /fitness, /apply_evolution, /reject_evolution
API endpoints: GET /api/evolution-status, GET /api/evolution-fitness
Dashboard: DNA Evolution Tracker panel

## SCORING SYSTEM
OB:          20pts
FVG:         20pts
Sweep:       30pts
VWAP:        15pts
Session:     15pts
Correlation: 15pts
Yield:       10pts
Sentiment:   10pts
Pattern:     20pts
Divergence:  20pts
MAX:         175pts → capped 100
EXECUTE:     >=75
WAIT:        50-74
BLOCK:       <50

## ASSETS
Forex:  XAUUSD, EURUSD, GBPUSD, SP500
Crypto: BTCUSD, ETHUSD, BNBUSD, SOLUSD, XRPUSD

## PM2 PROCESSES + PORTS
omni-pipeline     :3000  — main API
omni-scanner      —      — forex feed
omni-crypto       —      — crypto feed
omni-telegram     —      — bot polling
omni-monitor      —      — memory watch
omni-correlation  :5005  — correlation
omni-treasury     :5006  — yields
omni-sentiment    :5004  — sentiment
omni-news         :5007  — news feed
omni-mcp-bridge   —      — WS dashboard
omni-heartbeat    —      — Telegram ping
omni-report       —      — daily report
omni-status       :8089  — status page
omni-paper-trader —      — paper trading

## API ENDPOINTS (localhost:3000)
GET  /api/omni-status
GET  /api/last-scan
GET  /api/feed-status
GET  /api/backtest-results
GET  /api/correlation
GET  /api/news
GET  /api/yields
GET  /api/sentiment
GET  /api/evolution-status
GET  /api/evolution-fitness
POST /api/trigger-scan
POST /api/pause/{symbol}
GET  /api/backtest-results

## PIPELINE FLOW
TwelveData WS
→ Candle Validation
→ MT5 Split-Brain Lock
→ News Gate (Forex Factory)
→ Treasury Yield Check
→ Sentiment Check
→ Smart Money Matrix
→ Pattern Engine
→ MTF Confirmation
→ Divergence Scanner
→ Confidence Score
→ Correlation Check
→ Session Detector
→ Risk Manager
→ Adaptive Threshold
→ Circuit Breaker
→ EXECUTE/WAIT/BLOCK
→ Telegram + GitHub + Git + Dashboard

## MONETIZATION
Free Telegram:  @omnibrainsignals_free
VIP Telegram:   @omnibrainsignals_vip
Price:          ₹999/month India
                $12/month USD
Landing page:   :8080
Instagram:      @forextrader_9
YouTube:        10 scripts ready
Languages:      32 supported
Payment:        Razorpay/UPI manual verify

## .ENV REQUIRED KEYS
LIVE_DATA_API_KEY      — TwelveData
TELEGRAM_BOT_TOKEN     — bot token
TELEGRAM_CHAT_ID       — your chat ID
GITHUB_TOKEN           — PAT token
GITHUB_REPO            — signals-log
MT5_LOGIN/PASSWORD/SERVER
ACCOUNT_BALANCE=10000
RISK_PCT=1.0
SPREAD_MAX_PIPS=3.0
PAYMENT_LINK           — Razorpay URL
PERPLEXITY_API_KEY     — optional
ANTHROPIC_API_KEY      — optional (Claude evolution)

## LAST SESSION STATUS
Tests:    258/258 passing
Added:    32-language content system
Added:    Multilingual Telegram signals
Added:    Regional pricing
Added:    30-day educational series
Added:    YouTube scripts (10 videos)
Added:    Self-evolving prompt system (DNA, fitness, mutation, Claude)
Next:     Deploy + go public
