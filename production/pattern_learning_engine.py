"""
Module 5 — Self-Learning Pattern Engine
=========================================
Stores every trade with full context: session, regime, trend, liquidity type,
FVG, OB, MSS, BOS, volume, confidence, RR, duration, win/loss, max excursion,
drawdown.

Continuously computes win rate, expectancy, average RR, session/pattern/regime
performance. Automatically adjusts future confidence weights based on history.
"""

import logging
import json
import math
import os
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path

log = logging.getLogger('PatternLearningEngine')

DATA_DIR = Path(__file__).parent / 'data' / 'learning'
DATA_DIR.mkdir(parents=True, exist_ok=True)

TRADE_DB_FILE = DATA_DIR / 'trade_history.json'
WEIGHTS_FILE = DATA_DIR / 'learned_weights.json'
PERFORMANCE_FILE = DATA_DIR / 'performance_cache.json'

_lock = threading.Lock()


class PatternLearningEngine:
    """
    Self-learning engine that stores every trade and continuously
    adjusts confidence weights based on historical outcomes.
    """

    def __init__(self):
        self._trades: List[Dict] = []
        self._weights: Dict[str, float] = {}
        self._performance: Dict[str, Any] = {}
        self._load_state()

    def _load_state(self):
        try:
            if TRADE_DB_FILE.exists():
                self._trades = json.loads(TRADE_DB_FILE.read_text())
            if WEIGHTS_FILE.exists():
                self._weights = json.loads(WEIGHTS_FILE.read_text())
            if PERFORMANCE_FILE.exists():
                self._performance = json.loads(PERFORMANCE_FILE.read_text())
        except Exception as e:
            log.debug(f"Failed to load learning state: {e}")

    def _save_trades(self):
        try:
            with _lock:
                TRADE_DB_FILE.write_text(json.dumps(self._trades[-500:], indent=2, default=str))
        except Exception as e:
            log.debug(f"Failed to save trades: {e}")

    def _save_weights(self):
        try:
            with _lock:
                WEIGHTS_FILE.write_text(json.dumps(self._weights, indent=2))
        except Exception as e:
            log.debug(f"Failed to save weights: {e}")

    def _save_performance(self):
        try:
            with _lock:
                PERFORMANCE_FILE.write_text(json.dumps(self._performance, indent=2, default=str))
        except Exception as e:
            log.debug(f"Failed to save performance: {e}")

    def record_trade(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        exit_price: float,
        pnl: float,
        rr: float,
        confidence: float,
        session: str = '',
        regime: str = '',
        trend: str = '',
        liquidity_type: str = '',
        fvg_present: bool = False,
        ob_present: bool = False,
        mss_detected: bool = False,
        bos_detected: bool = False,
        volume_ratio: float = 1.0,
        duration_minutes: float = 0.0,
        max_excursion: float = 0.0,
        max_drawdown: float = 0.0,
        trap_detected: bool = False,
        notes: str = '',
    ) -> bool:
        """Record a completed trade with full context."""
        try:
            trade = {
                'symbol': symbol,
                'direction': direction,
                'entry_price': entry_price,
                'exit_price': exit_price,
                'pnl': pnl,
                'rr': rr,
                'confidence': confidence,
                'session': session,
                'regime': regime,
                'trend': trend,
                'liquidity_type': liquidity_type,
                'fvg_present': fvg_present,
                'ob_present': ob_present,
                'mss_detected': mss_detected,
                'bos_detected': bos_detected,
                'volume_ratio': volume_ratio,
                'duration_minutes': duration_minutes,
                'max_excursion': max_excursion,
                'max_drawdown': max_drawdown,
                'trap_detected': trap_detected,
                'outcome': 'WIN' if pnl > 0 else 'LOSS',
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'notes': notes,
            }
            with _lock:
                self._trades.append(trade)
            self._save_trades()
            self._recompute_performance()
            self._recompute_weights()
            return True
        except Exception as e:
            log.warning(f"Failed to record trade: {e}")
            return False

    def _recompute_performance(self):
        """Recompute aggregate performance stats."""
        try:
            with _lock:
                trades = self._trades[-200:]  # Last 200 trades

            if not trades:
                return

            wins = [t for t in trades if t['outcome'] == 'WIN']
            losses = [t for t in trades if t['outcome'] == 'LOSS']
            total = len(trades)

            win_rate = len(wins) / max(total, 1)
            total_rr = sum(t.get('rr', 0) for t in trades)
            avg_rr = total_rr / max(total, 1)
            expectancy = (len(wins) / max(total, 1)) * (sum(t.get('rr', 0) for t in wins) / max(len(wins), 1)) - \
                         (len(losses) / max(total, 1)) * (abs(sum(t.get('rr', 0) for t in losses)) / max(len(losses), 1))

            # Session performance
            session_stats = {}
            for t in trades:
                sess = t.get('session', 'UNKNOWN')
                if sess not in session_stats:
                    session_stats[sess] = {'wins': 0, 'losses': 0, 'total_rr': 0}
                if t['outcome'] == 'WIN':
                    session_stats[sess]['wins'] += 1
                else:
                    session_stats[sess]['losses'] += 1
                session_stats[sess]['total_rr'] += t.get('rr', 0)

            # Regime performance
            regime_stats = {}
            for t in trades:
                reg = t.get('regime', 'UNKNOWN')
                if reg not in regime_stats:
                    regime_stats[reg] = {'wins': 0, 'losses': 0, 'total_rr': 0}
                if t['outcome'] == 'WIN':
                    regime_stats[reg]['wins'] += 1
                else:
                    regime_stats[reg]['losses'] += 1
                regime_stats[reg]['total_rr'] += t.get('rr', 0)

            # Pattern performance
            pattern_stats = {}
            for t in trades:
                key = f"FVG={'Y' if t.get('fvg_present') else 'N'}_OB={'Y' if t.get('ob_present') else 'N'}_MSS={'Y' if t.get('mss_detected') else 'N'}"
                if key not in pattern_stats:
                    pattern_stats[key] = {'wins': 0, 'losses': 0, 'count': 0}
                pattern_stats[key]['count'] += 1
                if t['outcome'] == 'WIN':
                    pattern_stats[key]['wins'] += 1
                else:
                    pattern_stats[key]['losses'] += 1

            # Duration buckets
            duration_buckets = {'<1h': 0, '1-4h': 0, '4-12h': 0, '12-24h': 0, '>24h': 0}
            for t in trades:
                d = t.get('duration_minutes', 0)
                if d < 60:
                    duration_buckets['<1h'] += 1
                elif d < 240:
                    duration_buckets['1-4h'] += 1
                elif d < 720:
                    duration_buckets['4-12h'] += 1
                elif d < 1440:
                    duration_buckets['12-24h'] += 1
                else:
                    duration_buckets['>24h'] += 1

            self._performance = {
                'total_trades': total,
                'win_rate': round(win_rate, 4),
                'avg_rr': round(avg_rr, 3),
                'expectancy': round(expectancy, 4),
                'total_pnl': round(sum(t.get('pnl', 0) for t in trades), 2),
                'max_drawdown': round(max(t.get('max_drawdown', 0) for t in trades), 2),
                'avg_duration_minutes': round(sum(t.get('duration_minutes', 0) for t in trades) / max(total, 1), 1),
                'win_streak': self._longest_streak(trades, 'WIN'),
                'loss_streak': self._longest_streak(trades, 'LOSS'),
                'session_performance': session_stats,
                'regime_performance': regime_stats,
                'pattern_performance': pattern_stats,
                'duration_distribution': duration_buckets,
                'updated': datetime.now(timezone.utc).isoformat(),
            }
            self._save_performance()

        except Exception as e:
            log.debug(f"Performance recompute failed: {e}")

    def _recompute_weights(self):
        """Automatically adjust confidence weights based on historical success."""
        try:
            with _lock:
                trades = self._trades[-200:]

            if len(trades) < 20:
                return

            # Base weights
            weights = {
                'OB': 1.0, 'FVG': 1.0, 'SWEEP': 1.0, 'VWAP': 1.0,
                'SESSION': 1.0, 'PATTERN': 1.0, 'DIVERGENCE': 1.0,
                'REGIME': 1.0, 'LIQUIDITY': 1.0,
            }

            # Adjust based on session performance
            sess_perf = self._performance.get('session_performance', {})
            for session, stats in sess_perf.items():
                total = stats['wins'] + stats['losses']
                if total >= 10:
                    wr = stats['wins'] / total
                    if wr > 0.65:
                        weights['SESSION'] = max(weights['SESSION'], 1.15)
                    elif wr < 0.40:
                        weights['SESSION'] = min(weights['SESSION'], 0.85)

            # Adjust based on regime performance
            reg_perf = self._performance.get('regime_performance', {})
            for regime, stats in reg_perf.items():
                total = stats['wins'] + stats['losses']
                if total >= 5:
                    wr = stats['wins'] / total
                    if regime == 'EXPANSION' and wr > 0.6:
                        weights['REGIME'] = max(weights['REGIME'], 1.2)
                    elif regime == 'COMPRESSION' and wr < 0.4:
                        weights['REGIME'] = min(weights['REGIME'], 0.8)

            # Adjust based on pattern performance
            pat_perf = self._performance.get('pattern_performance', {})
            for pattern, stats in pat_perf.items():
                if stats['count'] >= 5:
                    wr = stats['wins'] / max(stats['count'], 1)
                    has_fvg = 'FVG=Y' in pattern
                    has_ob = 'OB=Y' in pattern
                    if has_fvg and wr > 0.6:
                        weights['FVG'] = max(weights['FVG'], 1.15)
                    if has_ob and wr > 0.6:
                        weights['OB'] = max(weights['OB'], 1.15)

            self._weights = weights
            self._save_weights()

        except Exception as e:
            log.debug(f"Weight recompute failed: {e}")

    def get_weight(self, component: str) -> float:
        """Get the learned weight multiplier for a confidence component."""
        return self._weights.get(component, 1.0)

    def get_adjusted_score(self, base_score: float, component: str) -> float:
        """Apply learned weight to a component score."""
        w = self.get_weight(component)
        return base_score * w

    def get_performance(self) -> Dict[str, Any]:
        return dict(self._performance)

    def get_trade_count(self) -> int:
        return len(self._trades)

    def get_recent_trades(self, limit: int = 20) -> List[Dict]:
        return self._trades[-limit:]

    @staticmethod
    def _longest_streak(trades: List[Dict], outcome: str) -> int:
        streak = 0
        max_streak = 0
        for t in reversed(trades):
            if t.get('outcome') == outcome:
                streak += 1
                max_streak = max(max_streak, streak)
            else:
                streak = 0
        return max_streak

    def get_session_win_rate(self, session: str) -> Optional[float]:
        sp = self._performance.get('session_performance', {})
        stats = sp.get(session)
        if stats:
            total = stats['wins'] + stats['losses']
            return stats['wins'] / max(total, 1) if total > 0 else None
        return None

    def get_regime_win_rate(self, regime: str) -> Optional[float]:
        rp = self._performance.get('regime_performance', {})
        stats = rp.get(regime)
        if stats:
            total = stats['wins'] + stats['losses']
            return stats['wins'] / max(total, 1) if total > 0 else None
        return None


_learning: Optional[PatternLearningEngine] = None


def get_learning_engine() -> PatternLearningEngine:
    global _learning
    if _learning is None:
        _learning = PatternLearningEngine()
    return _learning


if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    if '--test' in sys.argv:
        le = get_learning_engine()
        for i in range(25):
            le.record_trade('XAUUSD', 'BUY', 2350 + i, 2360 + i, 10 + i, 2.0, 85,
                            session='LONDON_OPEN', regime='EXPANSION' if i % 2 == 0 else 'COMPRESSION',
                            fvg_present=i % 3 == 0, ob_present=True,
                            duration_minutes=120 + i * 10,
                            max_excursion=15.0, max_drawdown=5.0)

        perf = le.get_performance()
        print(f"Win rate: {perf.get('win_rate', 0):.1%}")
        print(f"Expectancy: {perf.get('expectancy', 0):.3f}")
        print(f"Weight OB: {le.get_weight('OB'):.2f}")
        print(f"Weight FVG: {le.get_weight('FVG'):.2f}")
        print("PatternLearningEngine OK")
