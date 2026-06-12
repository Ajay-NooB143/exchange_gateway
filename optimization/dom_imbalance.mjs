/**
 * ══════════════════════════════════════════════════════════════════════════════
 * DOM IMBALANCE FEEDER — Conceptual Bridge
 * Accepts external DOM data and injects it into TradingView via webhook
 * ══════════════════════════════════════════════════════════════════════════════
 */

/**
 * ARCHITECTURE
 * 
 * ┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
 * │  DOM Feed    │────►│  Imbalance   │────►│  Pine Script │────►│  Strategy    │
 * │  (Broker WS) │     │  Calculator  │     │  Webhook     │     │  Execution   │
 * └──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
 * 
 * Flow:
 * 1. Connect to broker's Level 2 / DOM websocket
 * 2. Calculate bid/ask imbalance in real-time
 * 3. When imbalance exceeds threshold, send to TradingView webhook
 * 4. Pine Script uses this as additional confirmation for FVG entries
 */

// ══════════════════════════════════════════════════════════════════════════════
// DOM IMBALANCE CALCULATOR
// ══════════════════════════════════════════════════════════════════════════════

class DOMImbalanceCalculator {
  constructor(config = {}) {
    this.depth = config.depth || 10;           // price levels to analyze
    this.threshold = config.threshold || 0.65;  // 65% imbalance = signal
    this.decay = config.decay || 0.95;          // exponential decay for old data
    this.history = [];
    this.maxHistory = config.maxHistory || 100;
  }

  /**
   * Process a DOM snapshot
   * @param {Object} snapshot - { bids: [[price, size], ...], asks: [[price, size], ...] }
   * @returns {Object} Imbalance signal
   */
  processSnapshot(snapshot) {
    const { bids, asks } = snapshot;

    // Take top N levels
    const topBids = bids.slice(0, this.depth);
    const topAsks = asks.slice(0, this.depth);

    // Calculate total volume at each side
    const bidVolume = topBids.reduce((sum, [, size]) => sum + size, 0);
    const askVolume = topAsks.reduce((sum, [, size]) => sum + size, 0);
    const totalVolume = bidVolume + askVolume;

    if (totalVolume === 0) return { imbalance: 0, signal: 'NEUTRAL' };

    // Imbalance ratio: >0.5 = more bids, <0.5 = more asks
    const imbalance = bidVolume / totalVolume;

    // Weighted imbalance (closer levels weighted more)
    const weightedBidVol = topBids.reduce((sum, [price, size], i) => 
      sum + size * Math.pow(this.decay, i), 0);
    const weightedAskVol = topAsks.reduce((sum, [price, size], i) => 
      sum + size * Math.pow(this.decay, i), 0);
    const weightedTotal = weightedBidVol + weightedAskVol;
    const weightedImbalance = weightedTotal > 0 ? weightedBidVol / weightedTotal : 0;

    // Detect absorption (large resting orders being consumed)
    const bidAbsorption = this.detectAbsorption(bids, 'bid');
    const askAbsorption = this.detectAbsorption(asks, 'ask');

    // Determine signal
    let signal = 'NEUTRAL';
    if (weightedImbalance > this.threshold) signal = 'BULLISH_DOM';
    else if (weightedImbalance < (1 - this.threshold)) signal = 'BEARISH_DOM';

    // Strong absorption overrides
    if (askAbsorption && signal === 'BULLISH_DOM') signal = 'STRONG_BULLISH';
    if (bidAbsorption && signal === 'BEARISH_DOM') signal = 'STRONG_BEARISH';

    const result = {
      imbalance: weightedImbalance,
      rawImbalance: imbalance,
      bidVolume,
      askVolume,
      signal,
      bidAbsorption,
      askAbsorption,
      timestamp: Date.now(),
    };

    // Store history
    this.history.push(result);
    if (this.history.length > this.maxHistory) {
      this.history.shift();
    }

    return result;
  }

  detectAbsorption(levels, side) {
    // Absorption: large order at a level that isn't moving price
    if (levels.length < 3) return false;
    
    const avgSize = levels.reduce((s, [, size]) => s + size, 0) / levels.length;
    const maxSize = Math.max(...levels.map(([, size]) => size));
    
    // If max level is 3x average, likely absorption
    return maxSize > avgSize * 3;
  }

  /**
   * Get recent imbalance trend
   * @param {number} lookback - number of snapshots to average
   * @returns {string} Trend direction
   */
  getTrend(lookback = 10) {
    const recent = this.history.slice(-lookback);
    if (recent.length < 3) return 'INSUFFICIENT_DATA';
    
    const avgImbalance = recent.reduce((s, h) => s + h.imbalance, 0) / recent.length;
    const slope = (recent[recent.length - 1].imbalance - recent[0].imbalance) / recent.length;
    
    if (avgImbalance > this.threshold && slope > 0) return 'STRONG_BULLISH';
    if (avgImbalance < (1 - this.threshold) && slope < 0) return 'STRONG_BEARISH';
    if (slope > 0.02) return 'SHIFTING_BULLISH';
    if (slope < -0.02) return 'SHIFTING_BEARISH';
    return 'BALANCED';
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// DOM FEED INTEGRATION
// ══════════════════════════════════════════════════════════════════════════════

/**
 * Connect to broker DOM websocket and feed signals to TradingView
 * 
 * REPLACE THIS with your broker's actual DOM websocket implementation
 */
async function startDOMFeed(config) {
  const calculator = new DOMImbalanceCalculator({
    depth: 10,
    threshold: 0.65,
    decay: 0.95,
  });

  // Example: Connect to broker DOM feed
  // const ws = new WebSocket(config.brokerDomUrl);
  //
  // ws.on('message', (data) => {
  //   const snapshot = JSON.parse(data);
  //   const signal = calculator.processSnapshot(snapshot);
  //
  //   // Send to TradingView when threshold is hit
  //   if (signal.signal !== 'NEUTRAL') {
  //     sendToTradingView({
  //       symbol: 'XAUUSD',
  //       dom_imbalance: signal.imbalance,
  //       dom_signal: signal.signal,
  //       bid_volume: signal.bidVolume,
  //       ask_volume: signal.askVolume,
  //       absorption: signal.bidAbsorption || signal.askAbsorption,
  //     });
  //   }
  // });

  return calculator;
}

/**
 * Send DOM signal to TradingView webhook
 */
async function sendToTradingView(payload) {
  // This would typically go through your webhook bridge
  const url = `http://localhost:3000/webhook/dom`;
  
  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    return await response.json();
  } catch (err) {
    console.error('Failed to send DOM signal:', err.message);
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// PINE SCRIPT INTEGRATION CONCEPT
// ══════════════════════════════════════════════════════════════════════════════

/**
 * In your Pine Script, add a DOM confirmation layer:
 * 
 * // Store DOM imbalance from external feed
 * var float domImbalance = na
 * var string domSignal = "NEUTRAL"
 * 
 * // When webhook fires with DOM data, update these vars
 * // (TradingView doesn't have a native DOM feed, so this comes via webhook)
 * 
 * // DOM Confirmation Rule:
 * bool domBullConfirm = domSignal == "BULLISH_DOM" or domSignal == "STRONG_BULLISH"
 * bool domBearConfirm = domSignal == "BEARISH_DOM" or domSignal == "STRONG_BEARISH"
 * 
 * // Final entry requires DOM alignment:
 * bool entryLong  = structLong  and volLong  and domBullConfirm
 * bool entryShort = structShort and volShort and domBearConfirm
 * 
 * // The DOM signal acts as a "second opinion" on order flow direction
 * // It confirms that institutional players are actually present at the level
 */

export { DOMImbalanceCalculator, startDOMFeed, sendToTradingView };
