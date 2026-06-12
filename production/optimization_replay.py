"""
Optimization Replay Engine - Offline Parameter Sweep
=====================================================
Reads weekly trade logs from content_logger, simulates parameter
sweeps over threshold and ATR multiplier combinations, finds
peak net-pip performance.

Designed for Sunday background thread (weekly optimization).
"""

import logging
import json
import math
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path

log = logging.getLogger('OptimizationReplay')

TRADE_LOG_BASE = Path(__file__).parent / 'content' / 'trade_logs'

# Default sweep ranges
SWEEP_PARAMS = {
    'score_thresholds': [60, 65, 70, 75, 80, 85],
    'atr_multipliers': [0.5, 1.0, 1.5, 2.0, 2.5],
    'decay_half_lives': [10, 20, 30, 45, 60],  # minutes
}


class OptimizationReplay:
    """
    Offline replay engine that sweeps parameters against historical trades.
    """

    def __init__(self, trade_log_dir: str = str(TRADE_LOG_BASE)):
        self.trade_log_dir = trade_log_dir
        self._cache: Dict[str, Any] = {}

    def load_weekly_trades(self, week_start: str = None) -> List[Dict]:
        """
        Load trade logs for a specific week.

        Args:
            week_start: ISO date string (YYYY-MM-DD) for Monday of target week.
                        If None, loads the most recent week's data.

        Returns:
            List of trade dicts.
        """
        if week_start:
            target_dir = Path(self.trade_log_dir) / week_start
            if not target_dir.is_dir():
                log.info(f"No trades found for week {week_start}")
                return []
            return self._load_trades_from_dir(target_dir)

        # Find most recent week with data
        base = Path(self.trade_log_dir)
        if not base.is_dir():
            return []

        date_dirs = sorted(
            [d for d in base.iterdir() if d.is_dir() and d.name[:4].isdigit()],
            reverse=True,
        )
        if not date_dirs:
            return []

        return self._load_trades_from_dir(date_dirs[0])

    def _load_trades_from_dir(self, directory: Path) -> List[Dict]:
        """Load all trades from a date directory."""
        trades = []
        try:
            for f in sorted(directory.glob('*.json')):
                with open(f) as fh:
                    data = json.load(fh)
                    if isinstance(data, list):
                        trades.extend(data)
                    elif isinstance(data, dict):
                        trades.append(data)
        except Exception as e:
            log.warning(f"Failed to load trades from {directory}: {e}")
        return trades

    def sweep_thresholds(
        self,
        trades: List[Dict],
        thresholds: List[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Sweep score threshold from 60-85, report net pips at each.

        Args:
            trades: List of trade dicts with 'score' and 'pnl' keys
            thresholds: List of threshold values to test (default: 60-85 step 5)

        Returns:
            List of {threshold, total_pnl, win_rate, trade_count, max_dd}
        """
        if not trades:
            return []

        results = []
        for thresh in (thresholds or SWEEP_PARAMS['score_thresholds']):
            filtered = [t for t in trades if t.get('score', 0) >= thresh]
            if not filtered:
                results.append({
                    'threshold': thresh,
                    'total_pnl': 0,
                    'win_rate': 0.0,
                    'trade_count': 0,
                    'max_dd': 0.0,
                    'avg_pnl': 0.0,
                })
                continue

            pnls = [t.get('pnl', 0) for t in filtered]
            wins = sum(1 for p in pnls if p > 0)

            total_pnl = sum(pnls)
            win_rate = wins / max(len(pnls), 1)

            # Max drawdown
            running = 0
            peak = 0
            dd = 0
            for p in pnls:
                running += p
                if running > peak:
                    peak = running
                dd = max(dd, peak - running)

            results.append({
                'threshold': thresh,
                'total_pnl': round(total_pnl, 2),
                'win_rate': round(win_rate, 3),
                'trade_count': len(pnls),
                'max_dd': round(dd, 2),
                'avg_pnl': round(total_pnl / max(len(pnls), 1), 2),
            })

        return results

    def sweep_atr_multipliers(
        self,
        trades: List[Dict],
        multipliers: List[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Sweep ATR multipliers to find optimal stop placement.

        Simulates how different ATR multiplier stops would have
        affected trade outcomes.

        Args:
            trades: List of trade dicts with 'atr', 'pnl', 'entry' keys
            multipliers: List of ATR multipliers (default: 0.5-2.5)

        Returns:
            List of {multiplier, total_pnl, survived_count}
        """
        if not trades:
            return []

        results = []
        for mult in (multipliers or SWEEP_PARAMS['atr_multipliers']):
            simulated_pnls = []
            survived = 0

            for t in trades:
                atr = t.get('atr', 0)
                pnl = t.get('pnl', 0)
                if atr <= 0:
                    simulated_pnls.append(pnl)
                    survived += 1
                    continue

                # Simulate: if stop distance >= mult * ATR, trade survives
                entry = t.get('entry', 0)
                sl = t.get('sl', 0)
                if entry and sl and atr:
                    stop_distance = abs(entry - sl)
                    if stop_distance >= mult * atr:
                        simulated_pnls.append(pnl)
                        survived += 1
                    else:
                        # Would have been stopped out
                        simulated_pnls.append(-stop_distance)
                else:
                    simulated_pnls.append(pnl)
                    survived += 1

            results.append({
                'multiplier': mult,
                'total_pnl': round(sum(simulated_pnls), 2),
                'trade_count': len(simulated_pnls),
                'survived_count': survived,
                'survival_rate': round(survived / max(len(simulated_pnls), 1), 3),
            })

        return results

    def sweep_decay_half_lives(
        self,
        trades: List[Dict],
        half_lives: List[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Sweep decay half-life in minutes.

        Simulates how fast signal decay affects PnL if delayed execution.

        Args:
            trades: List of trade dicts with 'score', 'pnl', and 'delay_seconds'
            half_lives: List of half-life values (default: 10-60 min)

        Returns:
            List of {half_life_mins, total_pnl, avg_score_decay}
        """
        if not trades:
            return []

        results = []
        for hl_mins in (half_lives or SWEEP_PARAMS['decay_half_lives']):
            hl_seconds = hl_mins * 60
            total_pnl = 0
            total_decay_pct = 0.0

            for t in trades:
                delay = t.get('delay_seconds', 0)
                score = t.get('score', 50)
                pnl = t.get('pnl', 0)

                if delay <= 0 or hl_seconds <= 0:
                    total_pnl += pnl
                    continue

                try:
                    decay_const = math.log(2) / hl_seconds
                    decay_factor = math.exp(-decay_const * delay)
                    total_pnl += pnl * decay_factor
                    total_decay_pct += (1 - decay_factor) * 100
                except (ValueError, OverflowError):
                    total_pnl += pnl

            n = max(len(trades), 1)
            results.append({
                'half_life_mins': hl_mins,
                'total_pnl': round(total_pnl, 2),
                'avg_decay_pct': round(total_decay_pct / n, 1),
            })

        return results

    def full_sweep(self, week_start: str = None) -> Dict[str, Any]:
        """
        Run all sweeps and return best params.

        Returns:
            Dict with best_threshold, best_atr_mult, best_decay_hl, and details.
        """
        trades = self.load_weekly_trades(week_start)
        if not trades:
            return {'error': 'No trades found', 'best_threshold': 75}

        threshold_results = self.sweep_thresholds(trades)
        atr_results = self.sweep_atr_multipliers(trades)
        decay_results = self.sweep_decay_half_lives(trades)

        # Best threshold: max total PnL with at least 3 trades
        valid_thresh = [r for r in threshold_results if r['trade_count'] >= 3]
        best_thresh = max(valid_thresh, key=lambda r: r['total_pnl']) if valid_thresh else {}
        best_threshold = best_thresh.get('threshold', 75)

        # Best ATR multiplier: max total PnL
        best_atr = max(atr_results, key=lambda r: r['total_pnl']) if atr_results else {}
        best_atr_mult = best_atr.get('multiplier', 1.0)

        # Best decay half-life: max total PnL
        best_decay = max(decay_results, key=lambda r: r['total_pnl']) if decay_results else {}
        best_decay_hl = best_decay.get('half_life_mins', 30)

        return {
            'best_threshold': best_threshold,
            'best_atr_multiplier': best_atr_mult,
            'best_decay_half_life_mins': best_decay_hl,
            'threshold_details': threshold_results,
            'atr_details': atr_results,
            'decay_details': decay_results,
            'total_trades_analyzed': len(trades),
        }


# ══════════════════════════════════════════════════════════════════════════════
# GLOBAL INSTANCE
# ══════════════════════════════════════════════════════════════════════════════

_replay: Optional[OptimizationReplay] = None


def get_replay() -> OptimizationReplay:
    global _replay
    if _replay is None:
        _replay = OptimizationReplay()
    return _replay


# ══════════════════════════════════════════════════════════════════════════════
# CLI TEST
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import sys
    import tempfile
    logging.basicConfig(level=logging.INFO, format='%(message)s')

    if '--test' in sys.argv:
        replay = get_replay()

        # Create synthetic trade data
        tmp_dir = tempfile.mkdtemp()
        test_trades = [
            {'score': 85, 'pnl': 25.0, 'atr': 5.0, 'entry': 2355, 'sl': 2345, 'delay_seconds': 120},
            {'score': 60, 'pnl': -8.0, 'atr': 5.0, 'entry': 2360, 'sl': 2350, 'delay_seconds': 600},
            {'score': 75, 'pnl': 12.0, 'atr': 4.0, 'entry': 2340, 'sl': 2332, 'delay_seconds': 300},
            {'score': 70, 'pnl': 5.0, 'atr': 6.0, 'entry': 2370, 'sl': 2358, 'delay_seconds': 50},
            {'score': 90, 'pnl': 30.0, 'atr': 5.5, 'entry': 2350, 'sl': 2340, 'delay_seconds': 10},
        ]

        # Override trade log base for test
        replay.trade_log_dir = tmp_dir

        # Write synthetic trades
        os.makedirs(f"{tmp_dir}/2026-06-08", exist_ok=True)
        with open(f"{tmp_dir}/2026-06-08/trades.json", 'w') as f:
            json.dump(test_trades, f)

        # Run sweeps
        result = replay.full_sweep('2026-06-08')
        print(f"Best threshold: {result.get('best_threshold')}")
        print(f"Best ATR mult: {result.get('best_atr_multiplier')}")
        print(f"Best decay HL: {result.get('best_decay_half_life_mins')}")
        print(f"Trades analyzed: {result.get('total_trades_analyzed')}")
        print(f"Threshold sweep: {result.get('threshold_details')}")
        print(f"ATR sweep: {result.get('atr_details')}")
        print(f"Decay sweep: {result.get('decay_details')}")

        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)

        print("OptimizationReplay OK")
