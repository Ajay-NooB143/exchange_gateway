"""Adaptive Confidence Calibration Engine

Continuously recalibrates AI confidence using recent trading performance.
Rolling windows: 20, 50, 100 trades. Bayesian adjustment, drawdown penalty,
session-specific and volatility-adjusted confidence.
"""

import time
import logging
import math
from typing import List, Dict, Optional, Any
from collections import deque
from datetime import datetime, timezone

log = logging.getLogger(__name__)

TRADE_RECORD_KEYS = {
    'symbol', 'direction', 'entry', 'exit', 'sl', 'tp',
    'session', 'atr', 'win', 'rr', 'timestamp', 'regime',
}


class AdaptiveConfidence:
    """Calibrates raw AI confidence using historical trade performance."""

    def __init__(self, max_history: int = 200):
        self._trades: deque = deque(maxlen=max_history)
        self._last_calibrated: Dict[str, Any] = {}

    def record_trade(self, trade: Dict[str, Any]) -> None:
        cleaned = {k: trade.get(k) for k in TRADE_RECORD_KEYS}
        cleaned['timestamp'] = trade.get('timestamp', time.time())
        self._trades.append(cleaned)

    def calibrate(self, raw_confidence: float, symbol: str = 'XAUUSD',
                  session: str = '', atr: float = 5.0) -> Dict[str, Any]:
        result = {
            'raw': raw_confidence,
            'calibrated': raw_confidence,
            'adjustment': 0,
            'reason': 'No adjustment needed',
            'components': {},
        }
        if not self._trades:
            return result

        trades_list = list(self._trades)
        total = len(trades_list)
        if total == 0:
            return result

        try:
            adjustments = []

            # -- Rolling windows --
            windows = self._window_analysis(trades_list, total)
            result['components']['windows'] = windows

            # -- Bayesian adjustment --
            bayes_adj = self._bayesian_adjustment(trades_list, total)
            adjustments.append(('Bayesian', bayes_adj))
            result['components']['bayesian'] = round(bayes_adj, 1)

            # -- Win-rate weighting --
            wr_adj = self._winrate_adjustment(trades_list, windows)
            adjustments.append(('WinRate', wr_adj))
            result['components']['winrate'] = round(wr_adj, 1)

            # -- RR weighting --
            rr_adj = self._rr_adjustment(trades_list)
            adjustments.append(('RR', rr_adj))
            result['components']['rr'] = round(rr_adj, 1)

            # -- Drawdown penalty --
            dd_adj = self._drawdown_penalty(trades_list)
            adjustments.append(('Drawdown', dd_adj))
            result['components']['drawdown'] = round(dd_adj, 1)

            # -- Session-specific --
            sess_adj = self._session_adjustment(trades_list, session)
            adjustments.append(('Session', sess_adj))
            result['components']['session'] = round(sess_adj, 1)

            # -- Volatility-adjusted --
            vol_adj = self._volatility_adjustment(trades_list, atr)
            adjustments.append(('Volatility', vol_adj))
            result['components']['volatility'] = round(vol_adj, 1)

            # -- Losing streak decay --
            streak_adj = self._losing_streak_decay(trades_list)
            adjustments.append(('Streak', streak_adj))
            result['components']['streak'] = round(streak_adj, 1)

            # -- Consistency boost --
            boost_adj = self._consistency_boost(trades_list, windows)
            adjustments.append(('Consistency', boost_adj))
            result['components']['consistency'] = round(boost_adj, 1)

            total_adj = sum(a for _, a in adjustments)
            calibrated = max(0.0, min(100.0, raw_confidence + total_adj))
            result['calibrated'] = round(calibrated, 1)
            result['adjustment'] = round(total_adj, 1)

            # Build reason
            significant = [(name, val) for name, val in adjustments if abs(val) >= 1.0]
            if significant:
                parts = [f"{name}: {'+' if v >= 0 else ''}{v:.1f}" for name, v in significant]
                result['reason'] = f"Recent {total} trades: {' '.join(parts)}"
            elif abs(total_adj) >= 0.5:
                result['reason'] = f"Minor adjustment: {total_adj:+.1f} over {total} trades"
            else:
                result['reason'] = f"Stable confidence based on {total} trades"

            self._last_calibrated = result

        except Exception as e:
            log.warning(f"AdaptiveConfidence.calibrate error: {e}")
            result['error'] = str(e)

        return result

    def get_last_calibration(self) -> Dict[str, Any]:
        return dict(self._last_calibrated) if self._last_calibrated else {}

    def get_trade_count(self) -> int:
        return len(self._trades)

    # ---- Internal helpers ----

    def _window_analysis(self, trades: List[Dict], total: int) -> Dict[str, Any]:
        windows = {'total': total}
        for size in (20, 50, 100):
            chunk = trades[-size:] if total >= size else trades
            wins = sum(1 for t in chunk if t.get('win'))
            win_rate = wins / len(chunk) if chunk else 0
            rr_values = [t.get('rr', 0) or 0 for t in chunk]
            avg_rr = sum(rr_values) / len(rr_values) if rr_values else 0
            windows[f'w{size}'] = {
                'count': len(chunk),
                'win_rate': round(win_rate, 3),
                'avg_rr': round(avg_rr, 2),
            }
        return windows

    def _bayesian_adjustment(self, trades: List[Dict], total: int) -> float:
        wins = sum(1 for t in trades if t.get('win'))
        losses = total - wins
        alpha = wins + 1
        beta = losses + 1
        posterior_mean = alpha / (alpha + beta)
        expected = 0.50
        diff = (posterior_mean - expected) * 100
        return diff * 0.15

    def _winrate_adjustment(self, trades: List[Dict],
                            windows: Dict[str, Any]) -> float:
        for size in (20, 50, 100):
            w = windows.get(f'w{size}', {})
            count = w.get('count', 0)
            if count >= size:
                wr = w.get('win_rate', 0.5)
                diff = (wr - 0.5) * 100
                return diff * 0.10
        w = windows.get('w20', {})
        wr = w.get('win_rate', 0.5)
        diff = (wr - 0.5) * 100
        return diff * 0.05

    def _rr_adjustment(self, trades: List[Dict]) -> float:
        recent = trades[-20:] if len(trades) >= 20 else trades
        rr_values = [t.get('rr', 1.0) or 0 for t in recent if t.get('rr')]
        if not rr_values:
            return 0
        avg_rr = sum(rr_values) / len(rr_values)
        diff = (avg_rr - 1.5) * 5
        return max(-10.0, min(10.0, diff))

    def _drawdown_penalty(self, trades: List[Dict]) -> float:
        recent = trades[-20:] if len(trades) >= 20 else trades
        running = 10000
        peak = running
        max_dd = 0
        for t in recent:
            if t.get('win'):
                running *= (1 + (t.get('rr', 0) * 0.01))
            else:
                running *= (1 - 0.01)
            if running > peak:
                peak = running
            dd = (peak - running) / peak * 100
            if dd > max_dd:
                max_dd = dd
        if max_dd > 5:
            return -max_dd * 0.5
        return 0

    def _session_adjustment(self, trades: List[Dict], session: str) -> float:
        if not session:
            return 0
        session_trades = [t for t in trades if t.get('session') == session]
        if len(session_trades) < 5:
            return 0
        wins = sum(1 for t in session_trades if t.get('win'))
        wr = wins / len(session_trades)
        return (wr - 0.5) * 15

    def _volatility_adjustment(self, trades: List[Dict], atr: float) -> float:
        recent = trades[-20:] if len(trades) >= 20 else trades
        atrs = [t.get('atr', atr) or atr for t in recent]
        avg_atr = sum(atrs) / len(atrs) if atrs else atr
        baseline = 5.0
        if avg_atr > baseline * 2:
            return -8.0
        if avg_atr < baseline * 0.5:
            return 3.0
        return 0

    def _losing_streak_decay(self, trades: List[Dict]) -> float:
        streak = 0
        for t in reversed(trades):
            if not t.get('win'):
                streak += 1
            else:
                break
        if streak >= 5:
            return -15.0
        if streak >= 3:
            return -8.0
        if streak >= 2:
            return -3.0
        return 0

    def _consistency_boost(self, trades: List[Dict],
                           windows: Dict[str, Any]) -> float:
        w50 = windows.get('w50', {})
        if w50.get('count', 0) >= 50:
            wr = w50.get('win_rate', 0)
            if wr >= 0.65:
                return 8.0
        w20 = windows.get('w20', {})
        if w20.get('count', 0) >= 20:
            wr = w20.get('win_rate', 0)
            if wr >= 0.70 and w20.get('avg_rr', 0) >= 1.8:
                return 10.0
        return 0


_calibrator: Optional[AdaptiveConfidence] = None


def get_calibrator() -> AdaptiveConfidence:
    global _calibrator
    if _calibrator is None:
        _calibrator = AdaptiveConfidence()
    return _calibrator


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    c = get_calibrator()
    import random
    for i in range(100):
        c.record_trade({
            'symbol': 'XAUUSD', 'direction': 'BUY',
            'entry': 2000, 'exit': 2010, 'sl': 1995, 'tp': 2020,
            'session': random.choice(['ASIAN', 'LONDON', 'NY', '']),
            'atr': random.uniform(3, 12),
            'win': random.random() > 0.45,
            'rr': random.uniform(0.5, 3.0),
            'regime': random.choice(['EXPANSION', 'COMPRESSION']),
        })
    result = c.calibrate(84.0, session='LONDON', atr=7.2)
    print(f"Raw: {result['raw']}% -> Calibrated: {result['calibrated']}%")
    print(f"Adjustment: {result['adjustment']:+.1f}")
    print(f"Reason: {result['reason']}")
