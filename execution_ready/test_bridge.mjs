/**
 * ══════════════════════════════════════════════════════════════════════════════
 * WEBHOOK BRIDGE — Test Suite
 * Run: node test_bridge.mjs
 * ══════════════════════════════════════════════════════════════════════════════
 */

import crypto from 'crypto';

const SECRET = 'test-secret-key';
const PORT = 3000;
const BASE = `http://localhost:${PORT}`;

// ══════════════════════════════════════════════════════════════════════════════
// TEST HELPERS
// ══════════════════════════════════════════════════════════════════════════════

let passed = 0;
let failed = 0;

function sign(payload) {
  return crypto.createHmac('sha256', SECRET).update(JSON.stringify(payload)).digest('hex');
}

async function test(name, fn) {
  try {
    await fn();
    console.log(`  ✔ ${name}`);
    passed++;
  } catch (err) {
    console.log(`  ✖ ${name}: ${err.message}`);
    failed++;
  }
}

function assert(condition, msg) {
  if (!condition) throw new Error(msg || 'Assertion failed');
}

async function post(path, body, headers = {}) {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...headers },
    body: JSON.stringify(body)
  });
  return { status: res.status, data: await res.json() };
}

// ══════════════════════════════════════════════════════════════════════════════
// TESTS
// ══════════════════════════════════════════════════════════════════════════════

async function runTests() {
  console.log('\n═══ Webhook Bridge Tests ═══\n');

  // --- Health Check ---
  await test('Health check returns 200', async () => {
    const res = await fetch(`${BASE}/health`);
    const data = await res.json();
    assert(res.status === 200, `Expected 200, got ${res.status}`);
    assert(data.status === 'ok', 'Status not ok');
  });

  // --- Valid Long Order ---
  await test('Valid long order accepted', async () => {
    const payload = {
      symbol: 'XAUUSD',
      side: 'Long',
      entry_price: 2350.50,
      stop_loss: 2345.00,
      position_size: 2,
      timestamp: Date.now().toString()
    };
    const { status, data } = await post('/webhook?secret=' + SECRET, payload);
    assert(status === 200, `Expected 200, got ${status}: ${JSON.stringify(data)}`);
    assert(data.status === 'executed', `Expected executed, got ${data.status}`);
  });

  // --- Valid Short Order ---
  await test('Valid short order accepted', async () => {
    const payload = {
      symbol: 'XAUUSD',
      side: 'Short',
      entry_price: 2350.50,
      stop_loss: 2356.00,
      position_size: 1,
      timestamp: Date.now().toString()
    };
    const { status, data } = await post('/webhook?secret=' + SECRET, payload);
    assert(status === 200, `Expected 200, got ${status}`);
  });

  // --- Invalid Signature ---
  await test('Invalid signature rejected', async () => {
    const payload = { symbol: 'XAUUSD', side: 'Long', entry_price: 2350, stop_loss: 2345, position_size: 1 };
    const { status, data } = await post('/webhook?secret=wrong-secret', payload);
    assert(status === 400, `Expected 400, got ${status}`);
    assert(data.errors.includes('INVALID_SIGNATURE'), 'Missing INVALID_SIGNATURE error');
  });

  // --- Missing Fields ---
  await test('Missing required fields rejected', async () => {
    const payload = { symbol: 'XAUUSD' };
    const { status, data } = await post('/webhook?secret=' + SECRET, payload);
    assert(status === 400, `Expected 400, got ${status}`);
    assert(data.errors.length >= 3, `Expected ≥3 errors, got ${data.errors.length}`);
  });

  // --- Wrong Symbol ---
  await test('Disallowed symbol rejected', async () => {
    const payload = {
      symbol: 'BTCUSD',
      side: 'Long',
      entry_price: 65000,
      stop_loss: 64500,
      position_size: 1
    };
    const { status, data } = await post('/webhook?secret=' + SECRET, payload);
    assert(status === 400, `Expected 400, got ${status}`);
    assert(data.errors.includes('SYMBOL_NOT_ALLOWED'), 'Missing SYMBOL_NOT_ALLOWED error');
  });

  // --- Long SL Above Entry ---
  await test('Long with SL above entry rejected', async () => {
    const payload = {
      symbol: 'XAUUSD',
      side: 'Long',
      entry_price: 2350,
      stop_loss: 2360,
      position_size: 1
    };
    const { status, data } = await post('/webhook?secret=' + SECRET, payload);
    assert(status === 400, `Expected 400, got ${status}`);
    assert(data.errors.includes('LONG_SL_ABOVE_ENTRY'), 'Missing LONG_SL_ABOVE_ENTRY error');
  });

  // --- Short SL Below Entry ---
  await test('Short with SL below entry rejected', async () => {
    const payload = {
      symbol: 'XAUUSD',
      side: 'Short',
      entry_price: 2350,
      stop_loss: 2340,
      position_size: 1
    };
    const { status, data } = await post('/webhook?secret=' + SECRET, payload);
    assert(status === 400, `Expected 400, got ${status}`);
    assert(data.errors.includes('SHORT_SL_BELOW_ENTRY'), 'Missing SHORT_SL_BELOW_ENTRY error');
  });

  // --- Position Size Exceeds Max ---
  await test('Oversized position rejected', async () => {
    const payload = {
      symbol: 'XAUUSD',
      side: 'Long',
      entry_price: 2350,
      stop_loss: 2345,
      position_size: 100
    };
    const { status, data } = await post('/webhook?secret=' + SECRET, payload);
    assert(status === 400, `Expected 400, got ${status}`);
    assert(data.errors.includes('POSITION_SIZE_EXCEEDS_MAX'), 'Missing POSITION_SIZE_EXCEEDS_MAX error');
  });

  // --- Kill Switch ---
  await test('Kill switch cancels all', async () => {
    const { status, data } = await post('/kill', {});
    assert(status === 200, `Expected 200, got ${status}`);
    assert(data.status === 'halted', `Expected halted, got ${data.status}`);
  });

  // --- 404 ---
  await test('Unknown route returns 404', async () => {
    const res = await fetch(`${BASE}/unknown`);
    assert(res.status === 404, `Expected 404, got ${res.status}`);
  });

  // --- Summary ---
  console.log(`\n═══ Results: ${passed} passed, ${failed} failed ═══\n`);
  process.exit(failed > 0 ? 1 : 0);
}

runTests();
