/**
 * ══════════════════════════════════════════════════════════════════════════════
 * PRODUCTION DEPLOYMENT — Go-Live Checklist Implementation
 * PM2 + Firewall + Dead-Man's Switch + Hard-Stop
 * ══════════════════════════════════════════════════════════════════════════════
 */

import http from 'http';
import fs from 'fs';
import { execSync } from 'child_process';
import crypto from 'crypto';

// ══════════════════════════════════════════════════════════════════════════════
// CONFIGURATION
// ══════════════════════════════════════════════════════════════════════════════

const CONFIG = {
  PORT:                    parseInt(process.env.PORT) || 3000,
  WEBHOOK_SECRET:          process.env.WEBHOOK_SECRET || 'CHANGE-ME',
  BROKER_API_KEY:          process.env.BROKER_API_KEY || '',
  BROKER_BASE_URL:         process.env.BROKER_BASE_URL || '',
  ALLOWED_SYMBOLS:         (process.env.ALLOWED_SYMBOLS || 'XAUUSD').split(','),
  MAX_POSITION_SIZE:       parseInt(process.env.MAX_POSITION_SIZE) || 10,
  MAX_DAILY_TRADES:        parseInt(process.env.MAX_DAILY_TRADES) || 20,

  // --- Dead-Man's Switch ---
  DEAD_MAN_TIMEOUT_MS:     parseInt(process.env.DEAD_MAN_TIMEOUT) || 3600000, // 1 hour
  DEAD_MAN_CHECK_MS:       parseInt(process.env.DEAD_MAN_CHECK) || 60000,    // check every 1 min
  ALERT_WEBHOOK_URL:       process.env.ALERT_WEBHOOK_URL || '',  // Slack/Discord/etc

  // --- Hard-Stop ---
  MAX_DAILY_DRAWDOWN_PCT:  parseFloat(process.env.MAX_DRAWDOWN) || 3.0,     // 3%
  DAILY_LOSS_LIMIT_USD:    parseFloat(process.env.DAILY_LOSS_LIMIT) || 300,  // $300

  // --- Paths ---
  STATE_FILE:              './data/production_state.json',
  LOG_DIR:                 './logs',
  LOCK_FILE:               './data/.trading.lock',
};

// ══════════════════════════════════════════════════════════════════════════════
// CHECKLIST 1: STATE PERSISTENCE (survives restarts)
// ══════════════════════════════════════════════════════════════════════════════

class StateManager {
  constructor(filePath) {
    this.filePath = filePath;
    this.ensureDir();
    this.state = this.load();
  }

  ensureDir() {
    const dir = this.filePath.substring(0, this.filePath.lastIndexOf('/'));
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  }

  load() {
    try {
      if (fs.existsSync(this.filePath)) {
        return JSON.parse(fs.readFileSync(this.filePath, 'utf8'));
      }
    } catch (e) {
      console.error('[STATE] Failed to load, using defaults');
    }
    return this.defaults();
  }

  defaults() {
    const today = new Date().toISOString().split('T')[0];
    return {
      dailyPnl:          0,
      dailyTrades:       0,
      lastSignalTime:    Date.now(),
      tradingHalted:     false,
      haltReason:        null,
      haltTime:          null,
      lastResetDate:     today,
      startDate:         today,
      totalTrades:       0,
      totalPnl:          0,
      peakEquity:        10000,
      currentEquity:     10000,
    };
  }

  save() {
    fs.writeFileSync(this.filePath, JSON.stringify(this.state, null, 2));
  }

  resetDaily() {
    const today = new Date().toISOString().split('T')[0];
    if (this.state.lastResetDate !== today) {
      console.log(`[STATE] New day detected — resetting daily counters`);
      this.state.dailyPnl = 0;
      this.state.dailyTrades = 0;
      this.state.tradingHalted = false;
      this.state.haltReason = null;
      this.state.haltTime = null;
      this.state.lastResetDate = today;
      this.save();
    }
  }

  recordTrade(pnl) {
    this.state.dailyPnl += pnl;
    this.state.dailyTrades++;
    this.state.totalTrades++;
    this.state.totalPnl += pnl;
    this.state.currentEquity += pnl;

    if (this.state.currentEquity > this.state.peakEquity) {
      this.state.peakEquity = this.state.currentEquity;
    }

    this.state.lastSignalTime = Date.now();
    this.save();
  }

  isHalted() {
    this.resetDaily();
    return this.state.tradingHalted;
  }

  halt(reason) {
    this.state.tradingHalted = true;
    this.state.haltReason = reason;
    this.state.haltTime = Date.now();
    this.save();
    console.error(`[HALT] Trading halted: ${reason}`);
  }

  getDrawdownPct() {
    if (this.state.peakEquity <= 0) return 0;
    return ((this.state.peakEquity - this.state.currentEquity) / this.state.peakEquity) * 100;
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// CHECKLIST 4: HARD-STOP — Daily Drawdown Circuit Breaker
// ══════════════════════════════════════════════════════════════════════════════

class HardStop {
  constructor(state, config) {
    this.state = state;
    this.config = config;
  }

  check() {
    const s = this.state.state;

    // Check 1: Daily PnL loss limit
    if (s.dailyPnl <= -this.config.DAILY_LOSS_LIMIT_USD) {
      this.state.halt(`DAILY_LOSS_LIMIT: $${s.dailyPnl.toFixed(2)} exceeded limit of -$${this.config.DAILY_LOSS_LIMIT_USD}`);
      return { allowed: false, reason: 'DAILY_LOSS_LIMIT' };
    }

    // Check 2: Drawdown from peak
    const dd = this.state.getDrawdownPct();
    if (dd >= this.config.MAX_DAILY_DRAWDOWN_PCT) {
      this.state.halt(`DRAWDOWN: ${dd.toFixed(2)}% exceeded limit of ${this.config.MAX_DAILY_DRAWDOWN_PCT}%`);
      return { allowed: false, reason: 'DRAWDOWN_LIMIT' };
    }

    // Check 3: Daily trade count
    if (s.dailyTrades >= this.config.MAX_DAILY_TRADES) {
      this.state.halt(`TRADE_LIMIT: ${s.dailyTrades} trades exceeded limit of ${this.config.MAX_DAILY_TRADES}`);
      return { allowed: false, reason: 'TRADE_LIMIT' };
    }

    // Check 4: Already halted
    if (s.tradingHalted) {
      return { allowed: false, reason: s.haltReason };
    }

    return { allowed: true, reason: null };
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// CHECKLIST 3: DEAD-MAN'S SWITCH
// ══════════════════════════════════════════════════════════════════════════════

class DeadMansSwitch {
  constructor(config, state) {
    this.config = config;
    this.state = state;
    this.alertSent = false;
  }

  check() {
    const lastSignal = this.state.state.lastSignalTime;
    const elapsed = Date.now() - lastSignal;

    if (elapsed >= this.config.DEAD_MAN_TIMEOUT_MS && !this.alertSent) {
      this.sendAlert(`⚠️ DEAD-MAN: No signal received for ${(elapsed / 60000).toFixed(0)} minutes`);
      this.alertSent = true;
      return false;
    }

    // Reset alert flag when signal is received
    if (elapsed < this.config.DEAD_MAN_TIMEOUT_MS) {
      this.alertSent = false;
    }

    return true;
  }

  async sendAlert(message) {
    console.error(`[DEAD-MAN] ${message}`);

    if (!this.config.ALERT_WEBHOOK_URL) {
      console.error('[DEAD-MAN] No alert webhook configured — skipping notification');
      return;
    }

    try {
      // Slack / Discord / Telegram webhook
      await fetch(this.config.ALERT_WEBHOOK_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: message,
          content: message, // Discord format
          username: 'Trading Bot',
        }),
      });
      console.log('[DEAD-MAN] Alert sent successfully');
    } catch (err) {
      console.error(`[DEAD-MAN] Failed to send alert: ${err.message}`);
    }
  }

  reset() {
    this.state.state.lastSignalTime = Date.now();
    this.state.save();
    this.alertSent = false;
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// CHECKLIST 2: VALIDATOR
// ══════════════════════════════════════════════════════════════════════════════

function validatePayload(payload, secret) {
  const errors = [];

  if (secret !== CONFIG.WEBHOOK_SECRET) {
    errors.push('AUTH_FAILED');
  }

  for (const field of ['symbol', 'side', 'entry_price', 'stop_loss', 'position_size']) {
    if (!payload[field] && payload[field] !== 0) {
      errors.push(`MISSING_${field.toUpperCase()}`);
    }
  }

  if (payload.symbol && !CONFIG.ALLOWED_SYMBOLS.includes(payload.symbol)) {
    errors.push('SYMBOL_NOT_ALLOWED');
  }

  if (payload.side === 'Long' && payload.stop_loss >= payload.entry_price) {
    errors.push('SL_INVALID');
  }
  if (payload.side === 'Short' && payload.stop_loss <= payload.entry_price) {
    errors.push('SL_INVALID');
  }

  if (payload.position_size > CONFIG.MAX_POSITION_SIZE) {
    errors.push('SIZE_EXCEEDS_MAX');
  }

  return { valid: errors.length === 0, errors };
}

// ══════════════════════════════════════════════════════════════════════════════
// MAIN SERVER
// ══════════════════════════════════════════════════════════════════════════════

const state = new StateManager(CONFIG.STATE_FILE);
const hardStop = new HardStop(state, CONFIG);
const deadMan = new DeadMansSwitch(CONFIG, state);

// Start dead-man's check interval
setInterval(() => deadMan.check(), CONFIG.DEAD_MAN_CHECK_MS);

// Start daily reset check
setInterval(() => state.resetDaily(), 60000);

const server = http.createServer(async (req, res) => {
  try {
    // --- Health ---
    if (req.method === 'GET' && req.url === '/health') {
      const s = state.state;
      const dd = state.getDrawdownPct();
      return send(res, 200, {
        status: 'ok',
        uptime: `${((Date.now() - (s.startTime || Date.now())) / 1000).toFixed(0)}s`,
        dailyPnl: `$${s.dailyPnl.toFixed(2)}`,
        dailyTrades: s.dailyTrades,
        drawdown: `${dd.toFixed(2)}%`,
        tradingHalted: s.tradingHalted,
        haltReason: s.haltReason,
        lastSignal: new Date(s.lastSignalTime).toISOString(),
        pid: process.pid,
      });
    }

    // --- Kill Switch ---
    if (req.method === 'POST' && req.url === '/kill') {
      state.halt('MANUAL_KILL_SWITCH');
      return send(res, 200, { status: 'halted', reason: 'Manual kill switch activated' });
    }

    // --- Resume ---
    if (req.method === 'POST' && req.url === '/resume') {
      state.state.tradingHalted = false;
      state.state.haltReason = null;
      state.save();
      return send(res, 200, { status: 'resumed' });
    }

    // --- Webhook ---
    if (req.method === 'POST' && req.url.startsWith('/webhook')) {
      const url = new URL(req.url, `http://${req.headers.host}`);
      const secret = url.searchParams.get('secret');

      // Collect body
      const chunks = [];
      let totalLen = 0;
      req.on('data', c => { chunks.push(c); totalLen += c.length; });

      req.on('end', () => {
        try {
          const body = JSON.parse(Buffer.concat(chunks, totalLen).toString());

          // Validate payload
          const validation = validatePayload(body, secret);
          if (!validation.valid) {
            return send(res, 400, { status: 'rejected', errors: validation.errors });
          }

          // Check hard-stop
          const stopCheck = hardStop.check();
          if (!stopCheck.allowed) {
            return send(res, 403, { status: 'halted', reason: stopCheck.reason });
          }

          // Record signal for dead-man
          deadMan.reset();

          // Execute order (replace with broker API)
          const result = {
            success: true,
            orderId: `PROD-${Date.now()}`,
            fillPrice: body.entry_price,
          };

          // Record trade
          state.recordTrade(0); // PnL updated on exit

          console.log(`[TRADE] ${body.side} ${body.symbol} @ ${body.entry_price} | SL: ${body.stop_loss} | Size: ${body.position_size}`);

          return send(res, 200, {
            status: 'executed',
            orderId: result.orderId,
            fillPrice: result.fillPrice,
            dailyPnl: state.state.dailyPnl,
            drawdown: `${state.getDrawdownPct().toFixed(2)}%`,
          });

        } catch (err) {
          console.error(`[ERROR] ${err.message}`);
          return send(res, 500, { status: 'error', message: err.message });
        }
      });

      return;
    }

    send(res, 404, { status: 'not_found' });

  } catch (err) {
    console.error(`[FATAL] ${err.message}`);
    send(res, 500, { status: 'error', message: err.message });
  }
});

function send(res, status, data) {
  res.writeHead(status, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify(data, null, 2));
}

server.listen(CONFIG.PORT, () => {
  console.log('═══════════════════════════════════════════════════');
  console.log('  PRODUCTION TRADING BRIDGE');
  console.log(`  Port: ${CONFIG.PORT}`);
  console.log(`  Hard-Stop: ${CONFIG.MAX_DAILY_DRAWDOWN_PCT}% drawdown / $${CONFIG.DAILY_LOSS_LIMIT_USD} daily loss`);
  console.log(`  Dead-Man: ${CONFIG.DEAD_MAN_TIMEOUT_MS / 60000}min timeout`);
  console.log(`  PID: ${process.pid}`);
  console.log('═══════════════════════════════════════════════════');
});
