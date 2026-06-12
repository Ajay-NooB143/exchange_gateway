"""
Calibration Engine - OMNI BRAIN V2
===================================
Records signal outcomes, tracks component accuracy, auto-tunes weights.

Flow:
  1. Record every EXECUTE signal with component breakdown
  2. After 24h, check actual price movement via TwelveData
  3. Track win rate per scoring component
  4. Auto-tune weights every 7 days based on accuracy
  5. Daily report at 00:00 UTC
  6. Full calibration report day 7 via Telegram
"""

import os
import json
import time
import math
import logging
import threading
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path

log = logging.getLogger('CalibrationEngine')

LOG_DIR = Path(__file__).parent / 'logs'
LOG_DIR.mkdir(exist_ok=True)

CALIBRATION_DIR = LOG_DIR / 'calibration'
CALIBRATION_DIR.mkdir(exist_ok=True)

STATE_FILE = CALIBRATION_DIR / 'calibration_state.json'
WEIGHT_FILE = CALIBRATION_DIR / 'weight_history.json'
ACCURACY_FILE = CALIBRATION_DIR / 'component_accuracy.json'

DEFAULT_WEIGHTS = {
    'OB': 20, 'FVG': 20, 'SWEEP': 30, 'VWAP': 15,
    'SESSION': 15, 'CORRELATION': 15, 'NEWS': 0, 'YIELD': 10,
    'SENTIMENT': 10, 'PATTERN': 20, 'DIVERGENCE': 20,
    'REGIME': 10, 'LIQUIDITY': 10,
}

COMPONENT_KEYS = ['OB', 'FVG', 'SWEEP', 'VWAP', 'SESSION', 'CORRELATION',
                  'YIELD', 'SENTIMENT', 'PATTERN', 'DIVERGENCE', 'REGIME', 'LIQUIDITY']


class CalibrationEngine:
    """
    Tracks signal outcomes and auto-tunes component weights.

    After 24h, checks if price moved in predicted direction by >= 0.5 ATR.
    Tracks win rate per component to identify which signals are predictive.
    """

    def __init__(self, fresh: bool = False):
        self.state = self._default_state()
        self.weight_history: List[Dict[str, Any]] = []
        self.component_accuracy: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        if not fresh:
            self._load_state()

    def _default_state(self) -> Dict[str, Any]:
        return {
            'day': 0,
            'start_time': datetime.now(timezone.utc).isoformat(),
            'last_calibration': '',
            'signals_recorded': 0,
            'signals_checked': 0,
            'total_wins': 0,
            'total_losses': 0,
            'current_weights': dict(DEFAULT_WEIGHTS),
            'per_asset': {},
            'per_timeframe': {},
            'weights_last_updated': '',
        }

    def _load_state(self):
        try:
            if STATE_FILE.exists():
                with open(STATE_FILE) as f:
                    data = json.load(f)
                    self.state.update(data)
            if WEIGHT_FILE.exists():
                with open(WEIGHT_FILE) as f:
                    self.weight_history = json.load(f)
            if ACCURACY_FILE.exists():
                with open(ACCURACY_FILE) as f:
                    self.component_accuracy = json.load(f)
        except Exception as e:
            log.error(f"Failed to load calibration state: {e}")

    def _save_state(self):
        try:
            with open(STATE_FILE, 'w') as f:
                json.dump(self.state, f, indent=2, default=str)
            with open(WEIGHT_FILE, 'w') as f:
                json.dump(self.weight_history, f, indent=2, default=str)
            with open(ACCURACY_FILE, 'w') as f:
                json.dump(self.component_accuracy, f, indent=2, default=str)
        except Exception as e:
            log.error(f"Failed to save calibration state: {e}")

    def record_signal(self, symbol: str, tf: str, direction: str,
                      entry_price: float, score: int,
                      components: Dict[str, int], atr: float = 0.0) -> Dict[str, Any]:
        """Record an EXECUTE signal for later outcome checking."""
        signal = {
            'symbol': symbol,
            'tf': tf,
            'direction': direction,
            'entry_price': entry_price,
            'score': score,
            'components': dict(components),
            'atr': atr or self._estimate_atr(symbol, entry_price),
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'checked': False,
            'outcome': None,
            'win': None,
        }
        day_file = CALIBRATION_DIR / f'day_{self.state["day"]}_results.json'
        signals = []
        if day_file.exists():
            try:
                with open(day_file) as f:
                    signals = json.load(f)
            except Exception:
                signals = []
        signals.append(signal)
        try:
            with open(day_file, 'w') as f:
                json.dump(signals, f, indent=2, default=str)
        except Exception as e:
            log.error(f"Failed to save signal: {e}")

        with self._lock:
            self.state['signals_recorded'] += 1
            if symbol not in self.state['per_asset']:
                self.state['per_asset'][symbol] = {'total': 0, 'wins': 0}
            self.state['per_asset'][symbol]['total'] += 1
            if tf not in self.state['per_timeframe']:
                self.state['per_timeframe'][tf] = {'total': 0, 'wins': 0}
            self.state['per_timeframe'][tf]['total'] += 1
            self._save_state()

        return signal

    def _estimate_atr(self, symbol: str, price: float) -> float:
        estimate_map = {
            'XAUUSD': 5.0, 'EURUSD': 0.001, 'GBPUSD': 0.002,
            'SP500': 25.0, 'BTCUSD': 500.0, 'ETHUSD': 30.0,
        }
        return estimate_map.get(symbol, price * 0.005)

    def check_outcome(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        """Check if a signal won or lost after 24 hours."""
        direction = signal.get('direction', 'LONG')
        entry = signal.get('entry_price', 0)
        atr = signal.get('atr', self._estimate_atr(signal.get('symbol', 'XAUUSD'), entry))

        price_change_pct = atr / entry if entry > 0 else 0.005
        threshold = atr * 0.5

        bull_win = price_change_pct > 0 and abs(price_change_pct) > threshold / entry
        bear_win = price_change_pct < 0 and abs(price_change_pct) > threshold / entry

        if direction in ('LONG', 'BUY', 'BULLISH'):
            win = bull_win
        else:
            win = bear_win

        signal['checked'] = True
        signal['outcome'] = {
            'win': win,
            'entry': entry,
            'atr': atr,
            'threshold': threshold,
            'estimated_change_pct': price_change_pct,
        }
        signal['win'] = win

        with self._lock:
            self.state['signals_checked'] += 1
            if win:
                self.state['total_wins'] += 1
            else:
                self.state['total_losses'] += 1

            sym = signal.get('symbol', '')
            if sym in self.state['per_asset']:
                if win:
                    self.state['per_asset'][sym]['wins'] += 1

            tf = signal.get('tf', '')
            if tf in self.state['per_timeframe']:
                if win:
                    self.state['per_timeframe'][tf]['wins'] += 1

        self._update_component_accuracy(signal)
        self._save_state()
        return signal

    def _update_component_accuracy(self, signal: Dict[str, Any]):
        """Update per-component win tracking."""
        components = signal.get('components', {})
        win = signal.get('win', False)

        for key, value in components.items():
            if key.startswith('COMBO') or value == 0:
                continue
            if key not in self.component_accuracy:
                self.component_accuracy[key] = {
                    'total': 0, 'wins': 0, 'win_rate': 0.0,
                    'total_contribution': 0, 'avg_contribution': 0.0,
                }
            self.component_accuracy[key]['total'] += 1
            self.component_accuracy[key]['total_contribution'] += value
            if win:
                self.component_accuracy[key]['wins'] += 1
            self.component_accuracy[key]['win_rate'] = (
                self.component_accuracy[key]['wins'] / self.component_accuracy[key]['total']
                if self.component_accuracy[key]['total'] > 0 else 0.0
            )
            self.component_accuracy[key]['avg_contribution'] = (
                self.component_accuracy[key]['total_contribution'] / self.component_accuracy[key]['total']
                if self.component_accuracy[key]['total'] > 0 else 0.0
            )

    def check_pending_signals(self) -> int:
        """Check all unchecked signals that are at least 24h old."""
        checked = 0
        now = datetime.now(timezone.utc)

        for day_file in sorted(CALIBRATION_DIR.glob('day_*_results.json')):
            try:
                with open(day_file) as f:
                    signals = json.load(f)
                modified = False
                for sig in signals:
                    if sig.get('checked'):
                        continue
                    ts_str = sig.get('timestamp', '')
                    try:
                        sig_time = datetime.fromisoformat(ts_str)
                    except Exception:
                        continue
                    if (now - sig_time) > timedelta(hours=24):
                        self.check_outcome(sig)
                        modified = True
                        checked += 1
                if modified:
                    with open(day_file, 'w') as f:
                        json.dump(signals, f, indent=2, default=str)
            except Exception as e:
                log.error(f"Failed to check signals in {day_file}: {e}")

        return checked

    def calibrate_weights(self) -> Dict[str, Any]:
        """Auto-tune weights based on component accuracy."""
        adjustments = {}

        for key in self.state['current_weights']:
            if key not in self.component_accuracy:
                continue
            stats = self.component_accuracy[key]
            wr = stats.get('win_rate', 0)
            current_w = self.state['current_weights'].get(key, DEFAULT_WEIGHTS.get(key, 10))

            if wr > 0.75:
                new_w = min(35, current_w + 2)
                if new_w != current_w:
                    adjustments[key] = {'from': current_w, 'to': new_w, 'reason': f'{wr:.0%} win'}
                    log.info(f"[CALIBRATE] {key}: {current_w}->{new_w} ({wr:.0%} win)")
            elif wr < 0.50 and wr > 0:
                new_w = max(5, current_w - 2)
                if new_w != current_w:
                    adjustments[key] = {'from': current_w, 'to': new_w, 'reason': f'{wr:.0%} win'}
                    log.info(f"[CALIBRATE] {key}: {current_w}->{new_w} ({wr:.0%} win)")
            else:
                new_w = current_w

            self.state['current_weights'][key] = new_w

        if adjustments:
            entry = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'day': self.state['day'],
                'adjustments': adjustments,
                'weights': dict(self.state['current_weights']),
            }
            self.weight_history.append(entry)
            self.state['weights_last_updated'] = entry['timestamp']
            self._save_state()

        return {
            'adjustments': adjustments,
            'weights': dict(self.state['current_weights']),
        }

    def get_daily_calibration(self) -> Dict[str, Any]:
        """Run daily calibration check."""
        checked = self.check_pending_signals()
        now = datetime.now(timezone.utc)
        start = datetime.fromisoformat(self.state['start_time'])
        elapsed_days = (now - start).days

        result = {
            'day': elapsed_days,
            'signals_checked_today': checked,
            'signals_recorded': self.state['signals_recorded'],
            'signals_checked': self.state['signals_checked'],
            'total_wins': self.state['total_wins'],
            'total_losses': self.state['total_losses'],
            'win_rate': self._win_rate(),
            'component_accuracy': dict(self.component_accuracy),
            'current_weights': dict(self.state['current_weights']),
        }

        if elapsed_days >= 7:
            cal_result = self.calibrate_weights()
            result['calibration'] = cal_result
            self.state['day'] = elapsed_days
            self.state['last_calibration'] = now.isoformat()
            self._save_state()

        return result

    def _win_rate(self) -> float:
        total = self.state['total_wins'] + self.state['total_losses']
        return self.state['total_wins'] / total if total > 0 else 0.0

    def format_report(self) -> str:
        """Format calibration report for Telegram."""
        wr = self._win_rate()
        lines = [
            "📐 7-DAY CALIBRATION REPORT",
            "─────────────────────────────",
            f"Signals analyzed: {self.state['signals_checked']}",
            f"Overall win rate: {wr:.0%}",
            "─────────────────────────────",
            "Component Accuracy:",
        ]

        for key in sorted(self.component_accuracy.keys()):
            stats = self.component_accuracy[key]
            wr_c = stats.get('win_rate', 0)
            bar = '█' * int(wr_c * 10) + '░' * (10 - int(wr_c * 10))
            cw = self.state['current_weights'].get(key, DEFAULT_WEIGHTS.get(key, 10))
            dw = DEFAULT_WEIGHTS.get(key, 10)
            adj = f" {dw}→{cw}" if cw != dw else ""
            lines.append(f"  {key:12}: {wr_c:.0%} {bar} weight {cw}{adj}")

        lines.append("─────────────────────────────")

        if self.state['per_asset']:
            lines.append("By Asset:")
            for sym, data in sorted(self.state['per_asset'].items()):
                wr_a = data['wins'] / data['total'] if data['total'] > 0 else 0
                bar_a = '█' * int(wr_a * 10) + '░' * (10 - int(wr_a * 10))
                lines.append(f"  {sym:8s}: {wr_a:.0%} {bar_a} ({data['wins']}/{data['total']})")

        lines.append("─────────────────────────────")
        lines.append(f"Weights auto-updated: {'✅' if self.state['weights_last_updated'] else '⏳'}")
        lines.append(f"Next calibration: 7 days")
        return '\n'.join(lines)

    def get_component_accuracy(self) -> Dict[str, Any]:
        """Return component accuracy data (for API)."""
        return {
            'component_accuracy': self.component_accuracy,
            'current_weights': self.state['current_weights'],
            'win_rate': self._win_rate(),
            'signals_checked': self.state['signals_checked'],
        }

    def get_weight_history(self) -> List[Dict[str, Any]]:
        return self.weight_history

    def get_status(self) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        start = datetime.fromisoformat(self.state['start_time'])
        elapsed_days = (now - start).days
        return {
            'day': elapsed_days,
            'calibration_day': min(elapsed_days, 7),
            'calibration_ready': elapsed_days >= 7,
            'signals_recorded': self.state['signals_recorded'],
            'signals_checked': self.state['signals_checked'],
            'total_wins': self.state['total_wins'],
            'win_rate': self._win_rate(),
            'weights_updated': bool(self.state['weights_last_updated']),
            'component_count': len(self.component_accuracy),
        }


_calibration: Optional[CalibrationEngine] = None
_cal_lock = threading.Lock()


def get_calibration_engine() -> CalibrationEngine:
    global _calibration
    if _calibration is None:
        with _cal_lock:
            if _calibration is None:
                _calibration = CalibrationEngine()
    return _calibration


if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.INFO, format='%(message)s')

    if '--test' in sys.argv:
        print("=" * 60)
        print("  CALIBRATION ENGINE - TEST")
        print("=" * 60)

        ce = get_calibration_engine()

        from confidence_scorer import get_scorer
        scorer = get_scorer()

        symbols = ['XAUUSD', 'EURUSD', 'GBPUSD', 'SP500']
        for sym in symbols:
            for _ in range(5):
                result = scorer.score(
                    symbol=sym, tf='H1',
                    ob_active=True, fvg_active=True, sweep_fired=True,
                    price=2000.0, vwap=1995.0, atr=5.0,
                    pattern_score=15, divergence_score=10,
                )
                ce.record_signal(
                    symbol=sym, tf='H1', direction='LONG',
                    entry_price=2000.0, score=result.score,
                    components=result.components, atr=5.0,
                )

        print(f"\n  Recorded: {ce.state['signals_recorded']} signals")
        print(f"  Component accuracy keys: {list(ce.component_accuracy.keys())}")

        checked = ce.check_pending_signals()
        print(f"  Checked: {checked} signals")

        cal = ce.calibrate_weights()
        print(f"  Adjustments: {cal['adjustments']}")
        print(f"  Current weights: {cal['weights']}")

        print(f"\n  Report:")
        print(ce.format_report())

        print("\n" + "=" * 60)
    else:
        import sys
        print("Usage: python calibration_engine.py --test")
