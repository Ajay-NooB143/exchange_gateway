/**
 * ══════════════════════════════════════════════════════════════════════════════
 * VALIDATION LOGGER — 100-Trade Live-Sim Tracker
 * Captures: P&L, execution latency, slippage, regime, system health
 * ══════════════════════════════════════════════════════════════════════════════
 */

import fs from 'fs';
import path from 'path';

// ══════════════════════════════════════════════════════════════════════════════
// CONFIGURATION
// ══════════════════════════════════════════════════════════════════════════════

const CONFIG = {
  LOG_DIR:          './logs',
  TRADE_LOG:        './logs/trades.csv',
  HEALTH_LOG:       './logs/health.jsonl',
  REGIME_LOG:       './logs/regime_analysis.json',
  MAX_TRADES:       100,
  HEALTH_INTERVAL:  30000,  // 30 seconds
};

// ══════════════════════════════════════════════════════════════════════════════
// TRADE LOGGER
// ══════════════════════════════════════════════════════════════════════════════

class TradeLogger {
  constructor() {
    this.trades = [];
    this.ensureLogDir();
    this.initCSV();
  }

  ensureLogDir() {
    if (!fs.existsSync(CONFIG.LOG_DIR)) {
      fs.mkdirSync(CONFIG.LOG_DIR, { recursive: true });
    }
  }

  initCSV() {
    const headers = [
      'trade_id',
      'timestamp',
      'symbol',
      'side',
      'regime',
      'atr_percentile',
      'entry_price',
      'exit_price',
      'stop_loss',
      'position_size',
      'pnl_dollars',
      'pnl_pct',
      'slippage_points',
      'execution_latency_ms',
      'spread_at_entry',
      'atr_at_entry',
      'volume_ratio',
      'session_hour_gmt',
      'outcome',        // WIN / LOSS / BREAKEVEN
      'rr_achieved',    // actual risk-reward achieved
      'bars_held',
      'exit_reason'     // SL / TP / BE / MANUAL
    ];

    if (!fs.existsSync(CONFIG.TRADE_LOG)) {
      fs.writeFileSync(CONFIG.TRADE_LOG, headers.join(',') + '\n');
    }
  }

  /**
   * Log a completed trade
   * @param {Object} trade - Trade data object
   */
  logTrade(trade) {
    const record = {
      trade_id:            trade.tradeId,
      timestamp:           new Date(trade.exitTime).toISOString(),
      symbol:              trade.symbol,
      side:                trade.side,
      regime:              trade.regime,
      atr_percentile:      trade.atrPercentile?.toFixed(4) || '',
      entry_price:         trade.entryPrice,
      exit_price:          trade.exitPrice,
      stop_loss:           trade.stopLoss,
      position_size:       trade.positionSize,
      pnl_dollars:         trade.pnl?.toFixed(2) || '',
      pnl_pct:             trade.pnlPct?.toFixed(4) || '',
      slippage_points:     trade.slippage?.toFixed(2) || '',
      execution_latency_ms: trade.latencyMs || '',
      spread_at_entry:     trade.spreadAtEntry?.toFixed(2) || '',
      atr_at_entry:        trade.atrAtEntry?.toFixed(2) || '',
      volume_ratio:        trade.volumeRatio?.toFixed(2) || '',
      session_hour_gmt:    trade.sessionHour || '',
      outcome:             trade.pnl > 0 ? 'WIN' : trade.pnl < 0 ? 'LOSS' : 'BREAKEVEN',
      rr_achieved:         trade.rrAchieved?.toFixed(2) || '',
      bars_held:           trade.barsHeld || '',
      exit_reason:         trade.exitReason || ''
    };

    const csvLine = Object.values(record).map(v => `"${v}"`).join(',');
    fs.appendFileSync(CONFIG.TRADE_LOG, csvLine + '\n');
    this.trades.push(record);

    console.log(`[TRADE #${record.trade_id}] ${record.side} ${record.regime} | PnL: $${record.pnl_dollars} | Slippage: ${record.slippage_points}pts | Latency: ${record.execution_latency_ms}ms`);

    return record;
  }

  /**
   * Generate 100-trade summary report
   */
  generateReport() {
    if (this.trades.length === 0) return null;

    const wins   = this.trades.filter(t => t.outcome === 'WIN');
    const losses = this.trades.filter(t => t.outcome === 'LOSS');

    const totalPnl    = this.trades.reduce((sum, t) => sum + parseFloat(t.pnl_dollars || 0), 0);
    const avgSlippage = this.trades.reduce((sum, t) => sum + parseFloat(t.slippage_points || 0), 0) / this.trades.length;
    const avgLatency  = this.trades.reduce((sum, t) => sum + parseInt(t.execution_latency_ms || 0), 0) / this.trades.length;

    // Regime breakdown
    const trending = this.trades.filter(t => t.regime === 'TRENDING');
    const ranging  = this.trades.filter(t => t.regime === 'RANGING');
    const transition = this.trades.filter(t => t.regime === 'TRANSITIONING');

    const regimeStats = (trades) => {
      if (trades.length === 0) return null;
      const w = trades.filter(t => t.outcome === 'WIN').length;
      const pnl = trades.reduce((s, t) => s + parseFloat(t.pnl_dollars || 0), 0);
      return {
        count: trades.length,
        winRate: ((w / trades.length) * 100).toFixed(1) + '%',
        totalPnl: pnl.toFixed(2),
        avgPnl: (pnl / trades.length).toFixed(2)
      };
    };

    // Max drawdown
    let peak = 0, maxDD = 0, running = 0;
    for (const t of this.trades) {
      running += parseFloat(t.pnl_dollars || 0);
      if (running > peak) peak = running;
      const dd = peak - running;
      if (dd > maxDD) maxDD = dd;
    }

    // Profit factor
    const grossProfit = wins.reduce((s, t) => s + parseFloat(t.pnl_dollars || 0), 0);
    const grossLoss   = Math.abs(losses.reduce((s, t) => s + parseFloat(t.pnl_dollars || 0), 0));
    const profitFactor = grossLoss > 0 ? (grossProfit / grossLoss).toFixed(2) : '∞';

    const report = {
      summary: {
        totalTrades:     this.trades.length,
        winRate:         ((wins.length / this.trades.length) * 100).toFixed(1) + '%',
        totalPnl:        '$' + totalPnl.toFixed(2),
        profitFactor:    profitFactor,
        maxDrawdown:     '$' + maxDD.toFixed(2),
        avgSlippage:     avgSlippage.toFixed(2) + ' pts',
        avgLatency:      avgLatency.toFixed(0) + ' ms',
        avgRRAchieved:   (this.trades.reduce((s, t) => s + parseFloat(t.rr_achieved || 0), 0) / this.trades.length).toFixed(2)
      },
      regimeBreakdown: {
        trending:      regimeStats(trending),
        ranging:       regimeStats(ranging),
        transitioning: regimeStats(transition)
      },
      riskMetrics: {
        largestWin:   Math.max(...wins.map(t => parseFloat(t.pnl_dollars || 0))).toFixed(2),
        largestLoss:  Math.min(...losses.map(t => parseFloat(t.pnl_dollars || 0))).toFixed(2),
        avgWin:       wins.length > 0 ? (grossProfit / wins.length).toFixed(2) : '0',
        avgLoss:      losses.length > 0 ? (grossLoss / losses.length).toFixed(2) : '0',
        expectancy:   ((grossProfit - grossLoss) / this.trades.length).toFixed(2)
      }
    };

    fs.writeFileSync(CONFIG.REGIME_LOG, JSON.stringify(report, null, 2));
    console.log('\n═══════════════════════════════════════════');
    console.log('  VALIDATION REPORT — 100-TRADE LIVE-SIM');
    console.log('═══════════════════════════════════════════');
    console.log(JSON.stringify(report, null, 2));
    console.log('═══════════════════════════════════════════\n');

    return report;
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// HEALTH MONITOR
// ══════════════════════════════════════════════════════════════════════════════

class HealthMonitor {
  constructor() {
    this.metrics = {
      uptime:          0,
      signalsReceived: 0,
      signalsRejected: 0,
      ordersPlaced:    0,
      ordersFailed:    0,
      avgResponseTime: 0,
      lastSignalTime:  null,
      errorRate:       0,
      memoryUsage:     0,
      cpuUsage:        0
    };
    this.responseTimes = [];
    this.errors = [];
  }

  recordSignal(valid) {
    this.metrics.signalsReceived++;
    if (!valid) this.metrics.signalsRejected++;
    this.metrics.lastSignalTime = new Date().toISOString();
  }

  recordOrder(success, responseTimeMs) {
    if (success) {
      this.metrics.ordersPlaced++;
      this.responseTimes.push(responseTimeMs);
      if (this.responseTimes.length > 100) this.responseTimes.shift();
      this.metrics.avgResponseTime = this.responseTimes.reduce((a, b) => a + b, 0) / this.responseTimes.length;
    } else {
      this.metrics.ordersFailed++;
    }
  }

  recordError(error) {
    this.errors.push({ timestamp: new Date().toISOString(), message: error.message || error });
    if (this.errors.length > 50) this.errors.shift();
  }

  getSnapshot() {
    const mem = process.memoryUsage();
    this.metrics.memoryUsage = (mem.heapUsed / 1024 / 1024).toFixed(1) + ' MB';
    this.metrics.errorRate = this.metrics.signalsReceived > 0 
      ? ((this.metrics.ordersFailed / this.metrics.signalsReceived) * 100).toFixed(1) + '%'
      : '0%';
    this.metrics.uptime = (process.uptime()).toFixed(0) + 's';

    return {
      timestamp: new Date().toISOString(),
      ...this.metrics,
      recentErrors: this.errors.slice(-5)
    };
  }

  logHealth() {
    const snapshot = this.getSnapshot();
    fs.appendFileSync(CONFIG.HEALTH_LOG, JSON.stringify(snapshot) + '\n');

    // Console output
    console.log(`[HEALTH] Uptime: ${snapshot.uptime} | Signals: ${snapshot.signalsReceived} (${snapshot.signalsRejected} rejected) | Orders: ${snapshot.ordersPlaced} (${snapshot.ordersFailed} failed) | Latency: ${snapshot.avgResponseTime.toFixed(0)}ms | Memory: ${snapshot.memoryUsage}`);

    return snapshot;
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// EXPORTS
// ══════════════════════════════════════════════════════════════════════════════

export { TradeLogger, HealthMonitor, CONFIG };
