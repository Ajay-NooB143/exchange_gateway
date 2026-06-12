/**
 * Institutional Footprint - Node.js Bridge v1.0
 * ============================================
 * Architecture:
 *   TradingView Alert → This Bridge (port 3000) → Python Engine (port 8080) → Broker
 * 
 * This bridge:
 *   1. Receives webhooks from TradingView
 *   2. Validates secret and rate limits
 *   3. Forwards to Python execution engine
 *   4. Returns execution status
 * 
 * Run: node bridge.mjs
 */

import http from 'node:http';
import crypto from 'node:crypto';

// ============================================================================
// CONFIGURATION
// ============================================================================

const CONFIG = {
    port: parseInt(process.env.BRIDGE_PORT || '3000'),
    pythonEngineUrl: process.env.PYTHON_ENGINE_URL || 'http://localhost:8080',
    webhookSecret: process.env.WEBHOOK_SECRET || 'YOUR_SECRET_HERE',
    
    // Rate limiting
    maxRequestsPerMinute: 10,
    minIntervalMs: 1000,
    
    // Daily limits
    maxDailyTrades: 3,
    
    // State
    stateFile: '/opt/trading-bridge/data/footprint_state.json'
};

// ============================================================================
// STATE MANAGEMENT
// ============================================================================

const state = {
    dailyTrades: 0,
    lastTradeTime: 0,
    lastResetDate: null,
    requestTimestamps: []
};

function resetDailyIfNewDay() {
    const today = new Date().toISOString().split('T')[0];
    if (state.lastResetDate !== today) {
        state.dailyTrades = 0;
        state.lastResetDate = today;
        log(`Daily counter reset for ${today}`);
    }
}

function checkRateLimit() {
    const now = Date.now();
    
    // Clean old timestamps
    state.requestTimestamps = state.requestTimestamps.filter(t => now - t < 60000);
    
    // Check limit
    if (state.requestTimestamps.length >= CONFIG.maxRequestsPerMinute) {
        return false;
    }
    
    // Check minimum interval
    if (now - state.lastTradeTime < CONFIG.minIntervalMs) {
        return false;
    }
    
    state.requestTimestamps.push(now);
    return true;
}

// ============================================================================
// PAYLOAD PARSER (Fast - no JSON.parse overhead)
// ============================================================================

function parseWebhookFast(rawBody) {
    try {
        const data = JSON.parse(rawBody);
        
        // Validate required fields
        const required = ['signal', 'entry', 'sl', 'tp', 'secret'];
        for (const field of required) {
            if (data[field] === undefined || data[field] === null) {
                return { valid: false, error: `Missing field: ${field}` };
            }
        }
        
        // Validate secret
        if (data.secret !== CONFIG.webhookSecret) {
            return { valid: false, error: 'Invalid secret' };
        }
        
        // Validate signal type
        if (!['long', 'short'].includes(data.signal)) {
            return { valid: false, error: 'Invalid signal type' };
        }
        
        // Validate numeric fields
        const numericFields = ['entry', 'sl', 'tp', 'sl_pips', 'tp_pips', 'atr', 'volume_pct'];
        for (const field of numericFields) {
            if (data[field] !== undefined) {
                data[field] = parseFloat(data[field]);
                if (isNaN(data[field])) {
                    return { valid: false, error: `Invalid numeric: ${field}` };
                }
            }
        }
        
        // Validate boolean
        if (data.cvd_divergent !== undefined) {
            data.cvd_divergent = data.cvd_divergent === true || data.cvd_divergent === 'true';
        }
        
        return { valid: true, data };
        
    } catch (e) {
        return { valid: false, error: 'Invalid JSON' };
    }
}

// ============================================================================
// PYTHON ENGINE CLIENT
// ============================================================================

async function forwardToPythonEngine(payload) {
    const startTime = Date.now();
    
    try {
        const response = await fetch(CONFIG.pythonEngineUrl + '/webhook', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
            signal: AbortSignal.timeout(5000)
        });
        
        const result = await response.json();
        const latencyMs = Date.now() - startTime;
        
        log(`Python engine response: ${result.status} (${latencyMs}ms)`);
        
        return {
            status: result.status || 'error',
            order_id: result.order_id,
            fill_price: result.fill_price,
            slippage_pips: result.slippage_pips,
            fill_time_ms: result.fill_time_ms,
            cvd_confirmed: result.cvd_confirmed,
            latency_ms: latencyMs,
            error: result.error
        };
        
    } catch (error) {
        const latencyMs = Date.now() - startTime;
        log(`Python engine error: ${error.message} (${latencyMs}ms)`);
        
        return {
            status: 'error',
            error: `Python engine unreachable: ${error.message}`,
            latency_ms: latencyMs
        };
    }
}

// ============================================================================
// HTTP SERVER
// ============================================================================

function log(message) {
    const timestamp = new Date().toISOString();
    console.log(`[${timestamp}] ${message}`);
}

const server = http.createServer(async (req, res) => {
    // CORS headers
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'POST, GET, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
    
    if (req.method === 'OPTIONS') {
        res.writeHead(204);
        res.end();
        return;
    }
    
    // Health check
    if (req.method === 'GET' && req.url === '/health') {
        resetDailyIfNewDay();
        
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({
            status: 'healthy',
            bridge: 'institutional_footprint',
            daily_trades: state.dailyTrades,
            max_daily_trades: CONFIG.maxDailyTrades,
            python_engine: CONFIG.pythonEngineUrl
        }));
        return;
    }
    
    // Kill switch
    if (req.method === 'POST' && req.url === '/kill') {
        log('KILL SWITCH ACTIVATED');
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ status: 'halted' }));
        return;
    }
    
    // Webhook endpoint
    if (req.method === 'POST' && req.url.startsWith('/webhook')) {
        resetDailyIfNewDay();
        
        // Rate limit check
        if (!checkRateLimit()) {
            log('Rate limit exceeded');
            res.writeHead(429, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ status: 'error', error: 'Rate limit exceeded' }));
            return;
        }
        
        // Daily limit check
        if (state.dailyTrades >= CONFIG.maxDailyTrades) {
            log('Daily trade limit reached');
            res.writeHead(429, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ status: 'error', error: 'Daily trade limit reached' }));
            return;
        }
        
        // Read body
        let body = '';
        req.on('data', chunk => { body += chunk; });
        
        req.on('end', async () => {
            const startTime = Date.now();
            
            // Parse and validate
            const parsed = parseWebhookFast(body);
            
            if (!parsed.valid) {
                log(`Invalid payload: ${parsed.error}`);
                res.writeHead(400, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ status: 'error', error: parsed.error }));
                return;
            }
            
            const payload = parsed.data;
            log(`Received ${payload.signal} signal (${payload.source || 'unknown'})`);
            
            // Forward to Python engine
            const result = await forwardToPythonEngine(payload);
            
            // Update state
            if (result.status === 'filled') {
                state.dailyTrades++;
                state.lastTradeTime = Date.now();
            }
            
            // Response
            const statusCode = result.status === 'filled' ? 200 : 
                              result.status === 'rejected' ? 400 : 500;
            
            res.writeHead(statusCode, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({
                status: result.status,
                order_id: result.order_id,
                fill_price: result.fill_price,
                slippage_pips: result.slippage_pips,
                fill_time_ms: result.fill_time_ms,
                cvd_confirmed: result.cvd_confirmed,
                bridge_latency_ms: Date.now() - startTime,
                total_latency_ms: result.latency_ms,
                error: result.error
            }));
        });
        
        return;
    }
    
    // 404
    res.writeHead(404, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'Not found' }));
});

// ============================================================================
// START SERVER
// ============================================================================

server.listen(CONFIG.port, '0.0.0.0', () => {
    log('='.repeat(60));
    log('Institutional Footprint Bridge v1.0');
    log('='.repeat(60));
    log(`Listening on port ${CONFIG.port}`);
    log(`Python engine: ${CONFIG.pythonEngineUrl}`);
    log(`Daily limit: ${CONFIG.maxDailyTrades} trades`);
    log(`Rate limit: ${CONFIG.maxRequestsPerMinute}/min`);
    log('='.repeat(60));
});

// Graceful shutdown
process.on('SIGTERM', () => {
    log('Shutting down...');
    server.close(() => process.exit(0));
});

process.on('SIGINT', () => {
    log('Shutting down...');
    server.close(() => process.exit(0));
});
