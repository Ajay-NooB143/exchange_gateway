"""
Metrics Collector — Layer 2 Read-Only Observer
===============================================
Passively aggregates performance metrics from AlphaAgent and Phase64Chaser.

Read-only constraints:
    - Does NOT modify any other module's state
    - Does NOT hold locks or block threads
    - Only writes to its own metrics_db.json file
    - All operations are non-blocking

Metrics tracked:
    - Win_Rate: % of closed trades that were profitable
    - Avg_RR: Average risk-reward ratio of closed trades
    - Max_Drawdown: Maximum peak-to-trough equity decline
    - Sniper_Entry_Hit_Rate: % of sniper signals that resulted in execution
"""

import os
import json
import time
import logging
import threading
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime, timezone

log = logging.getLogger('MetricsCollector')

METRICS_DIR = Path(__file__).parent.parent / 'logs'
METRICS_DB = METRICS_DIR / 'metrics_db.json'

# XAUUSD pip convention
PIP_TO_POINTS = 0.10


class MetricsCollector:
    """
    Layer 2: Read-Only Performance Observer

    Aggregates trade metrics without modifying system state.
    Thread-safe via atomic file writes.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """Singleton pattern — one collector across the system."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self._db_lock = threading.Lock()
        self._db = self._load_db()

        # In-memory accumulators
        self._trades: List[Dict[str, Any]] = self._db.get('trades', [])
        self._sniper_signals: int = self._db.get('sniper_signals_total', 0)
        self._sniper_executions: int = self._db.get('sniper_executions_total', 0)
        self._equity_peak: float = self._db.get('equity_peak', 10000.0)
        self._equity_current: float = self._db.get('equity_current', 10000.0)
        self._max_drawdown: float = self._db.get('max_drawdown_pct', 0.0)

        log.info(f"[METRICS] Loaded {len(self._trades)} historical trades")

    def _load_db(self) -> Dict[str, Any]:
        """Load metrics database from disk."""
        try:
            if METRICS_DB.exists():
                with open(METRICS_DB, 'r') as f:
                    return json.load(f)
        except Exception as e:
            log.warning(f"[METRICS] Failed to load DB: {e}")
        return {
            'trades': [],
            'sniper_signals_total': 0,
            'sniper_executions_total': 0,
            'equity_peak': 10000.0,
            'equity_current': 10000.0,
            'max_drawdown_pct': 0.0,
            'last_updated': None,
        }

    def _save_db(self):
        """Atomic write to metrics_db.json."""
        self._db['trades'] = self._trades[-500:]  # Keep last 500 trades
        self._db['sniper_signals_total'] = self._sniper_signals
        self._db['sniper_executions_total'] = self._sniper_executions
        self._db['equity_peak'] = self._equity_peak
        self._db['equity_current'] = self._equity_current
        self._db['max_drawdown_pct'] = self._max_drawdown
        self._db['last_updated'] = datetime.now(timezone.utc).isoformat()

        try:
            tmp = str(METRICS_DB) + '.tmp'
            with open(tmp, 'w') as f:
                json.dump(self._db, f, indent=2, default=str)
            os.replace(tmp, str(METRICS_DB))
        except Exception as e:
            log.warning(f"[METRICS] Failed to save DB: {e}")

    # ── Event Recording (called by orchestrator) ──────────────────────

    def record_sniper_signal(self, symbol: str, side: str, confidence: float):
        """Record that the Sniper generated a signal."""
        self._sniper_signals += 1
        log.debug(f"[METRICS] Sniper signal: {symbol} {side} conf={confidence:.2f}")
        self._save_db()

    def record_sniper_execution(self, symbol: str, side: str, confidence: float):
        """Record that a Sniper signal was executed (routed to Phase 64)."""
        self._sniper_executions += 1
        log.debug(f"[METRICS] Sniper execution: {symbol} {side} conf={confidence:.2f}")
        self._save_db()

    def record_trade_open(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        score: float = 0,
    ):
        """Record a new trade entry."""
        trade = {
            'id': f"{symbol}_{side}_{int(time.time())}",
            'symbol': symbol,
            'side': side,
            'entry_price': entry_price,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'exit_price': None,
            'pnl_pips': None,
            'pnl_dollars': None,
            'r_r_ratio': None,
            'result': 'OPEN',
            'opened_at': datetime.now(timezone.utc).isoformat(),
            'closed_at': None,
            'score': score,
        }
        self._trades.append(trade)
        log.info(f"[METRICS] Trade OPEN: {trade['id']} @ {entry_price:.2f}")
        self._save_db()
        return trade['id']

    def record_trade_close(
        self,
        trade_id: str,
        exit_price: float,
        pnl_pips: float,
    ):
        """Record a trade exit and update aggregates."""
        for trade in self._trades:
            if trade['id'] == trade_id and trade['result'] == 'OPEN':
                trade['exit_price'] = exit_price
                trade['pnl_pips'] = round(pnl_pips, 2)
                trade['result'] = 'WIN' if pnl_pips > 0 else 'LOSS'
                trade['closed_at'] = datetime.now(timezone.utc).isoformat()

                # Calculate R:R
                entry = trade['entry_price']
                sl = trade['stop_loss']
                risk_points = abs(entry - sl)
                if risk_points > 0:
                    trade['r_r_ratio'] = round(abs(pnl_pips * PIP_TO_POINTS) / risk_points, 2)
                else:
                    trade['r_r_ratio'] = 0.0

                # Update equity curve
                self._equity_current += pnl_pips * PIP_TO_POINTS * 10  # $10 per pip (standard lot)
                if self._equity_current > self._equity_peak:
                    self._equity_peak = self._equity_current

                # Calculate drawdown
                if self._equity_peak > 0:
                    dd = (self._equity_peak - self._equity_current) / self._equity_peak * 100
                    if dd > self._max_drawdown:
                        self._max_drawdown = round(dd, 2)

                log.info(f"[METRICS] Trade CLOSE: {trade_id} pnl={pnl_pips:.1f} pips result={trade['result']}")
                self._save_db()
                return

        log.warning(f"[METRICS] Trade not found or already closed: {trade_id}")

    def record_position_update(self, trade_id: str, new_sl: float):
        """Record a trailing stop update."""
        for trade in self._trades:
            if trade['id'] == trade_id and trade['result'] == 'OPEN':
                old_sl = trade['stop_loss']
                trade['stop_loss'] = new_sl
                log.debug(f"[METRICS] SL UPDATE: {trade_id} {old_sl:.2f} → {new_sl:.2f}")
                self._save_db()
                return

    # ── Aggregate Queries (read-only) ─────────────────────────────────

    def get_metrics(self) -> Dict[str, Any]:
        """Get aggregated performance metrics."""
        closed = [t for t in self._trades if t['result'] in ('WIN', 'LOSS')]
        wins = [t for t in closed if t['result'] == 'WIN']
        losses = [t for t in closed if t['result'] == 'LOSS']

        # Win rate
        win_rate = (len(wins) / len(closed) * 100) if closed else 0.0

        # Average R:R
        r_r_values = [t.get('r_r_ratio', 0) for t in closed if t.get('r_r_ratio') is not None]
        avg_rr = (sum(r_r_values) / len(r_r_values)) if r_r_values else 0.0

        # Average win / average loss
        avg_win_pips = (sum(t['pnl_pips'] for t in wins) / len(wins)) if wins else 0.0
        avg_loss_pips = (sum(t['pnl_pips'] for t in losses) / len(losses)) if losses else 0.0

        # Sniper hit rate
        sniper_hit_rate = (
            (self._sniper_executions / self._sniper_signals * 100)
            if self._sniper_signals > 0 else 0.0
        )

        # Total P&L
        total_pnl = sum(t.get('pnl_pips', 0) or 0 for t in closed)

        # Profit factor
        gross_profit = sum(t['pnl_pips'] for t in wins) if wins else 0
        gross_loss = abs(sum(t['pnl_pips'] for t in losses)) if losses else 0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float('inf') if gross_profit > 0 else 0.0

        return {
            'total_trades': len(closed),
            'open_trades': len([t for t in self._trades if t['result'] == 'OPEN']),
            'wins': len(wins),
            'losses': len(losses),
            'win_rate_pct': round(win_rate, 2),
            'avg_rr': round(avg_rr, 2),
            'avg_win_pips': round(avg_win_pips, 2),
            'avg_loss_pips': round(avg_loss_pips, 2),
            'total_pnl_pips': round(total_pnl, 2),
            'profit_factor': round(profit_factor, 2),
            'max_drawdown_pct': self._max_drawdown,
            'equity_peak': round(self._equity_peak, 2),
            'equity_current': round(self._equity_current, 2),
            'sniper_signals': self._sniper_signals,
            'sniper_executions': self._sniper_executions,
            'sniper_hit_rate_pct': round(sniper_hit_rate, 2),
            'last_updated': datetime.now(timezone.utc).isoformat(),
        }

    def get_recent_trades(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get most recent trades."""
        return self._trades[-limit:]

    def get_equity_curve(self) -> List[Dict[str, Any]]:
        """Get equity curve data for charting."""
        curve = [{'trade': 0, 'equity': self._equity_peak}]
        running = self._equity_peak
        for i, t in enumerate(self._trades):
            if t['result'] in ('WIN', 'LOSS') and t.get('pnl_pips') is not None:
                running += t['pnl_pips'] * PIP_TO_POINTS * 10
                curve.append({'trade': i + 1, 'equity': round(running, 2)})
        return curve

    def reset(self):
        """Reset all metrics (use with caution)."""
        with self._db_lock:
            self._trades = []
            self._sniper_signals = 0
            self._sniper_executions = 0
            self._equity_peak = 10000.0
            self._equity_current = 10000.0
            self._max_drawdown = 0.0
            self._save_db()
            log.warning("[METRICS] All metrics reset")


# Module-level singleton
_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """Get the global MetricsCollector singleton."""
    global _collector
    if _collector is None:
        _collector = MetricsCollector()
    return _collector
