/**
 * ══════════════════════════════════════════════════════════════════════════════
 * WEBHOOK BRIDGE — With Validation Logger Integrated
 * ══════════════════════════════════════════════════════════════════════════════
 */

import http from 'http';
import crypto from 'crypto';
import { TradeLogger, HealthMonitor } from './trade_logger.mjs';

// ══════════════════════════════════════════════════════════════════════════════
// CONFIGURATION
// ══════════════════════════════════════════════════════════════════════════════

const CONFIG = {
  PORT:           process.env.PORT || 3000,
  WEBHOOK_SECRET: process.env.WEBHOOK_SECRET || 'change-me',
  BROKER_API_KEY: process.env.BROKER_API_KEY || '',
  BROKER_BASE_URL: process.env.BROKER_BASE_URL || 'https://api.broker.com/v1',
  MAX_POSITION_SIZE: parseInt(process.env.MAX_POSITION_SIZE) || 10,
  MAX_DAILY_TRADES:  parseInt(process.env.MAX_DAILY_TRADES) || 20,
  ALLOWED_SYMBOLS:   (process.env.ALLOWED_SYMBOLS || 'XAUUSD').split(','),
};

// ══════════════════════════════════════════════════════════════════════════════
// INIT
// ══════════════════════════════════════════════════════════════════════════════

const tradeLogger = new TradeLogger();
const healthMon   = new HealthMonitor();
let tradeCounter  = 0;

// ══════════════════════════════════════════════════════════════════════════════
// VALIDATOR
// ══════════════════════════════════════════════════════════════════════════════

function validatePayload(payload, secret) {
  const errors = [];

  // Signature
  if (secret !== CONFIG.WEBHOOK_SECRET) {
    errors.push('INVALID_SECRET');
  }

  // Required fields
  for (const field of ['symbol', 'side', 'entry_price', 'stop_loss', 'position_size']) {
    if (!payload[field] && payload[field] !== 0) {
      errors.push(`MISSING_${field.toUpperCase()}`);
    }
  }

  // Symbol
  if (payload.symbol && !CONFIG.ALLOWED_SYMBOLS.includes(payload.symbol)) {
    errors.push('SYMBOL_NOT_ALLOWED');
  }

  // Side
  if (payload.side && !['Long', 'Short'].includes(payload.side)) {
    errors.push('INVALID_SIDE');
  }

  // SL validation
  if (payload.side === 'Long' && payload.stop_loss >= payload.entry_price) {
    errors.push('LONG_SL_ABOVE_ENTRY');
  }
  if (payload.side === 'Short' && payload.stop_loss <= payload.entry_price) {
    errors.push('SHORT_SL_BELOW_ENTRY');
  }

  // Position size
  if (payload.position_size > CONFIG.MAX_POSITION_SIZE) {
    errors.push('POSITION_SIZE_EXCEEDS_MAX');
  }

  return { valid: errors.length === 0, errors };
}

// ══════════════════════════════════════════════════════════════════════════════
// BROKER EXECUTOR (Simulated — replace with real API)
// ══════════════════════════════════════════════════════════════════════════════

async function executeOrder(payload) {
  const startTime = Date.now();

  // --- REPLACE WITH YOUR BROKER API ---
  // const response = await fetch(`${CONFIG.BROKER_BASE_URL}/orders`, {
  //   method: 'POST',
  //   headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${CONFIG.BROKER_API_KEY}` },
  //   body: JSON.stringify({ symbol: payload.symbol, side: payload.side, quantity: payload.position_size, price: payload.entry_price, stopLoss: payload.stop_loss })
  // });
  // const result = await response.json();

  // Simulated execution
  await new Promise(r => setTimeout(r, 50 + Math.random() * 100)); // simulate network

  const latencyMs = Date.now() - startTime;

  // Simulate slippage (0.1 to 0.5 points)
  const slippage = 0.1 + Math.random() * 0.4;

  return {
    success: true,
    orderId: `SIM-${Date.now()}`,
    fillPrice: payload.entry_price + (payload.side === 'Long' ? slippage : -slippage),
    latencyMs,
    slippage
  };
}

// ══════════════════════════════════════════════════════════════════════════════
// HTTP SERVER
// ══════════════════════════════════════════════════════════════════════════════

function parseBody(req) {
  return new Promise((resolve, reject) => {
    let body = '';
    req.on('data', chunk => body += chunk);
    req.on('end', () => {
      try { resolve(JSON.parse(body)); }
      catch (e) { reject(new Error('Invalid JSON')); }
    });
    req.on('error', reject);
  });
}

function send(res, status, data) {
  res.writeHead(status, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify(data, null, 2));
}

const server = http.createServer(async (req, res) => {
  try {
    // Health endpoint
    if (req.method === 'GET' && req.url === '/health') {
      const snapshot = healthMon.getSnapshot();
      return send(res, 200, snapshot);
    }

    // Health history
    if (req.method === 'GET' && req.url === '/health/history') {
      const lines = fs.readFileSync('./logs/health.jsonl', 'utf-8').trim().split('\n');
      const last20 = lines.slice(-20).map(l => JSON.parse(l));
      return send(res, 200, last20);
    }

    // Trade log
    if (req.method === 'GET' && req.url === '/trades') {
      return send(res, 200, tradeLogger.trades.slice(-50));
    }

    // Report
    if (req.method === 'GET' && req.url === '/report') {
      const report = tradeLogger.generateReport();
      return send(res, 200, report || { message: 'No trades yet' });
    }

    // Kill switch
    if (req.method === 'POST' && req.url === '/kill') {
      console.log('✖ KILL SWITCH ACTIVATED');
      return send(res, 200, { status: 'halted' });
    }

    // Webhook
    if (req.method === 'POST' && req.url.startsWith('/webhook')) {
      const url = new URL(req.url, `http://${req.headers.host}`);
      const secret = url.searchParams.get('secret');
      const payload = await parseBody(req);

      // Record signal
      const validation = validatePayload(payload, secret);
      healthMon.recordSignal(validation.valid);

      if (!validation.valid) {
        console.log(`✖ Rejected: ${validation.errors.join(', ')}`);
        return send(res, 400, { status: 'rejected', errors: validation.errors });
      }

      // Execute
      const result = await executeOrder(payload);
      healthMon.recordOrder(result.success, result.latencyMs);

      // Log trade
      tradeCounter++;
      tradeLogger.logTrade({
        tradeId:         tradeCounter,
        exitTime:        Date.now(),
        symbol:          payload.symbol,
        side:            payload.side,
        regime:          payload.regime || 'UNKNOWN',
        atrPercentile:   payload.atr_percentile || null,
        entryPrice:      result.fillPrice,
        exitPrice:       null,  // updated on exit
        stopLoss:        payload.stop_loss,
        positionSize:    payload.position_size,
        pnl:             null,
        pnlPct:          null,
        slippage:        result.slippage,
        latencyMs:       result.latencyMs,
        spreadAtEntry:   payload.spread || null,
        atrAtEntry:      payload.atr || null,
        volumeRatio:     payload.volume_ratio || null,
        sessionHour:     payload.session_hour || null,
        rrAchieved:      null,
        barsHeld:        null,
        exitReason:      null
      });

      console.log(`✔ #${tradeCounter} ${payload.side} ${payload.symbol} @ ${result.fillPrice} | SL: ${payload.stop_loss} | Latency: ${result.latencyMs}ms | Slippage: ${result.slippage.toFixed(2)}pts`);

      return send(res, 200, { 
        status: 'executed', 
        orderId: result.orderId, 
        fillPrice: result.fillPrice,
        latencyMs: result.latencyMs
      });
    }

    send(res, 404, { status: 'not_found' });

  } catch (err) {
    healthMon.recordError(err);
    console.error(`✖ Error: ${err.message}`);
    send(res, 500, { status: 'error', message: err.message });
  }
});

// ══════════════════════════════════════════════════════════════════════════════
// START
// ══════════════════════════════════════════════════════════════════════════════

server.listen(CONFIG.PORT, () => {
  console.log('═══════════════════════════════════════════════════');
  console.log('  VALIDATION WEBHOOK BRIDGE');
  console.log(`  Port: ${CONFIG.PORT}`);
  console.log(`  Webhook: http://localhost:${CONFIG.PORT}/webhook?secret=${CONFIG.WEBHOOK_SECRET}`);
  console.log(`  Health:  http://localhost:${CONFIG.PORT}/health`);
  console.log(`  Report:  http://localhost:${CONFIG.PORT}/report`);
  console.log(`  Kill:    http://localhost:${CONFIG.PORT}/kill`);
  console.log('═══════════════════════════════════════════════════');

  // Health log every 30s
  setInterval(() => healthMon.logHealth(), CONFIG.HEALTH_INTERVAL || 30000);
});
