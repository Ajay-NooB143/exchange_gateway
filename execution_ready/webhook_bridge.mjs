/**
 * ══════════════════════════════════════════════════════════════════════════════
 * TRADINGVIEW WEBHOOK BRIDGE — Node.js
 * Listens for Pine Script alerts, validates, and executes via broker API
 * ══════════════════════════════════════════════════════════════════════════════
 */

import crypto from 'crypto';
import https from 'https';

// ══════════════════════════════════════════════════════════════════════════════
// CONFIGURATION
// ══════════════════════════════════════════════════════════════════════════════

const CONFIG = {
  PORT: process.env.PORT || 3000,
  
  // TradingView webhook secret — set this in TradingView alert URL
  // e.g. https://your-server.com/webhook?secret=YOUR_SECRET_HERE
  WEBHOOK_SECRET: process.env.WEBHOOK_SECRET || 'change-me-to-a-strong-secret',
  
  // Broker API (example: generic REST broker)
  BROKER_API_KEY:    process.env.BROKER_API_KEY    || '',
  BROKER_API_SECRET: process.env.BROKER_API_SECRET || '',
  BROKER_BASE_URL:   process.env.BROKER_BASE_URL   || 'https://api.broker.com/v1',
  
  // Safety limits
  MAX_POSITION_SIZE: parseInt(process.env.MAX_POSITION_SIZE) || 10,
  MAX_DAILY_TRADES:  parseInt(process.env.MAX_DAILY_TRADES)  || 20,
  ALLOWED_SYMBOLS:   (process.env.ALLOWED_SYMBOLS || 'XAUUSD').split(','),
  
  // Logging
  LOG_LEVEL: process.env.LOG_LEVEL || 'info'
};

// ══════════════════════════════════════════════════════════════════════════════
// VALIDATOR
// ══════════════════════════════════════════════════════════════════════════════

class PayloadValidator {
  constructor(secret) {
    this.secret = secret;
    this.dailyTradeCount = 0;
    this.lastResetDate = new Date().toDateString();
  }

  resetDailyCount() {
    const today = new Date().toDateString();
    if (today !== this.lastResetDate) {
      this.dailyTradeCount = 0;
      this.lastResetDate = today;
    }
  }

  validate(payload, signature) {
    this.resetDailyCount();

    const errors = [];

    // 1. Signature verification
    if (signature) {
      const expected = crypto
        .createHmac('sha256', this.secret)
        .update(JSON.stringify(payload))
        .digest('hex');
      
      if (signature !== expected) {
        errors.push('INVALID_SIGNATURE');
      }
    }

    // 2. Required fields
    const required = ['symbol', 'side', 'entry_price', 'stop_loss', 'position_size'];
    for (const field of required) {
      if (payload[field] === undefined || payload[field] === null) {
        errors.push(`MISSING_${field.toUpperCase()}`);
      }
    }

    // 3. Symbol whitelist
    if (payload.symbol && !CONFIG.ALLOWED_SYMBOLS.includes(payload.symbol)) {
      errors.push('SYMBOL_NOT_ALLOWED');
    }

    // 4. Side validation
    if (payload.side && !['Long', 'Short'].includes(payload.side)) {
      errors.push('INVALID_SIDE');
    }

    // 5. Price sanity
    if (payload.entry_price && (payload.entry_price <= 0 || payload.entry_price > 100000)) {
      errors.push('ENTRY_PRICE_OUT_OF_RANGE');
    }

    // 6. Stop loss validation
    if (payload.side === 'Long' && payload.stop_loss >= payload.entry_price) {
      errors.push('LONG_SL_ABOVE_ENTRY');
    }
    if (payload.side === 'Short' && payload.stop_loss <= payload.entry_price) {
      errors.push('SHORT_SL_BELOW_ENTRY');
    }

    // 7. Position size limits
    if (payload.position_size > CONFIG.MAX_POSITION_SIZE) {
      errors.push('POSITION_SIZE_EXCEEDS_MAX');
    }

    // 8. Daily trade limit
    if (this.dailyTradeCount >= CONFIG.MAX_DAILY_TRADES) {
      errors.push('DAILY_TRADE_LIMIT_REACHED');
    }

    return {
      valid: errors.length === 0,
      errors,
      approved: errors.length === 0
    };
  }

  incrementTradeCount() {
    this.dailyTradeCount++;
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// BROKER EXECUTOR
// ══════════════════════════════════════════════════════════════════════════════

class BrokerExecutor {
  constructor(config) {
    this.baseUrl = config.BROKER_BASE_URL;
    this.apiKey = config.BROKER_API_KEY;
    this.apiSecret = config.BROKER_API_SECRET;
  }

  async placeOrder(payload) {
    const order = {
      symbol:     payload.symbol,
      side:       payload.side.toUpperCase(),
      type:       'LIMIT',
      quantity:   payload.position_size,
      price:      payload.entry_price,
      stopLoss:   payload.stop_loss,
      timeInForce: 'GTC',
      timestamp:  Date.now()
    };

    log('info', `Placing order: ${JSON.stringify(order)}`);

    // --- REPLACE THIS BLOCK WITH YOUR BROKER'S API ---
    // Example for a generic REST broker:
    //
    // const response = await fetch(`${this.baseUrl}/orders`, {
    //   method: 'POST',
    //   headers: {
    //     'Content-Type': 'application/json',
    //     'Authorization': `Bearer ${this.apiKey}`,
    //     'X-Signature': this.sign(order)
    //   },
    //   body: JSON.stringify(order)
    // });
    // return await response.json();
    //
    // --- END BROKER API BLOCK ---

    // Simulated response for testing
    return {
      success: true,
      orderId: `SIM-${Date.now()}`,
      filled: true,
      fillPrice: payload.entry_price,
      message: 'Order placed (simulated)'
    };
  }

  async cancelAllOrders() {
    log('warn', 'CANCELLING ALL OPEN ORDERS');
    // Replace with broker API call
    // await fetch(`${this.baseUrl}/orders/cancel-all`, { method: 'DELETE' });
    return { success: true, message: 'All orders cancelled' };
  }

  async closeAllPositions() {
    log('warn', 'CLOSING ALL POSITIONS');
    // Replace with broker API call
    // await fetch(`${this.baseUrl}/positions/close-all`, { method: 'DELETE' });
    return { success: true, message: 'All positions closed' };
  }

  sign(data) {
    return crypto
      .createHmac('sha256', this.apiSecret)
      .update(JSON.stringify(data))
      .digest('hex');
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// HTTP SERVER
// ══════════════════════════════════════════════════════════════════════════════

import http from 'http';

function log(level, message) {
  const timestamp = new Date().toISOString();
  const prefix = { info: 'ℹ', warn: '⚠', error: '✖', success: '✔' }[level] || '•';
  console.log(`[${timestamp}] ${prefix} ${message}`);
}

function parseBody(req) {
  return new Promise((resolve, reject) => {
    let body = '';
    req.on('data', chunk => body += chunk);
    req.on('end', () => {
      try {
        resolve(JSON.parse(body));
      } catch (e) {
        reject(new Error('Invalid JSON'));
      }
    });
    req.on('error', reject);
  });
}

function sendResponse(res, status, data) {
  res.writeHead(status, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify(data, null, 2));
}

// ══════════════════════════════════════════════════════════════════════════════
// MAIN
// ══════════════════════════════════════════════════════════════════════════════

const validator = new PayloadValidator(CONFIG.WEBHOOK_SECRET);
const broker    = new BrokerExecutor(CONFIG);

const server = http.createServer(async (req, res) => {
  // Health check
  if (req.method === 'GET' && req.url === '/health') {
    return sendResponse(res, 200, { status: 'ok', uptime: process.uptime() });
  }

  // Kill switch endpoint
  if (req.method === 'POST' && req.url === '/kill') {
    log('warn', 'KILL SWITCH TRIGGERED VIA API');
    await broker.cancelAllOrders();
    await broker.closeAllPositions();
    return sendResponse(res, 200, { status: 'halted', message: 'All orders cancelled, positions closed' });
  }

  // Webhook endpoint
  if (req.method === 'POST' && req.url.startsWith('/webhook')) {
    try {
      // Parse URL params for secret
      const url = new URL(req.url, `http://${req.headers.host}`);
      const secretParam = url.searchParams.get('secret');

      // Parse body
      const payload = await parseBody(req);

      // Validate
      const validation = validator.validate(payload, secretParam);
      if (!validation.valid) {
        log('error', `Validation failed: ${validation.errors.join(', ')}`);
        return sendResponse(res, 400, { 
          status: 'rejected', 
          errors: validation.errors 
        });
      }

      // Execute
      const result = await broker.placeOrder(payload);
      validator.incrementTradeCount();
      
      log('success', `Order executed: ${payload.side} ${payload.symbol} @ ${payload.entry_price}, SL: ${payload.stop_loss}, Qty: ${payload.position_size}`);
      
      return sendResponse(res, 200, {
        status: 'executed',
        orderId: result.orderId,
        fillPrice: result.fillPrice
      });

    } catch (error) {
      log('error', `Webhook error: ${error.message}`);
      return sendResponse(res, 500, { status: 'error', message: error.message });
    }
  }

  // 404
  sendResponse(res, 404, { status: 'not_found' });
});

server.listen(CONFIG.PORT, () => {
  log('info', `═══════════════════════════════════════════════`);
  log('info', `  TradingView Webhook Bridge`);
  log('info', `  Port: ${CONFIG.PORT}`);
  log('info', `  Webhook URL: http://localhost:${CONFIG.PORT}/webhook?secret=${CONFIG.WEBHOOK_SECRET}`);
  log('info', `  Kill Switch: http://localhost:${CONFIG.PORT}/kill`);
  log('info', `  Health:      http://localhost:${CONFIG.PORT}/health`);
  log('info', `  Allowed: ${CONFIG.ALLOWED_SYMBOLS.join(', ')}`);
  log('info', `  Max Position: ${CONFIG.MAX_POSITION_SIZE} | Max Daily: ${CONFIG.MAX_DAILY_TRADES}`);
  log('info', `═══════════════════════════════════════════════`);
});
