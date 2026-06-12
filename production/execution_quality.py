"""Execution Quality Analyzer

Evaluates execution quality in real time — spread, slippage, latency,
fill quality, partial fills, execution delay, broker deviation.
Generates Execution Score (0-100) and blocks trades below threshold.
"""

import os
import json
import time
import logging
import statistics
import urllib.request
from typing import List, Dict, Optional, Any
from collections import deque
from datetime import datetime, timezone

log = logging.getLogger(__name__)

EXECUTION_HISTORY_MAX = 500
WARN_THRESHOLD = 70
BLOCK_THRESHOLD = 50
SCORING_WINDOW = 50

EXECUTION_WEIGHTS = {
    'spread': 0.20,
    'slippage': 0.25,
    'latency': 0.15,
    'fill_quality': 0.20,
    'partial_fills': 0.10,
    'delay': 0.05,
    'broker_deviation': 0.05,
}


class ExecutionQualityAnalyzer:
    """Real-time execution quality monitoring and scoring."""

    def __init__(self):
        self._history: Dict[str, deque] = {}
        self._last_score: Dict[str, Dict[str, Any]] = {}
        self._warned_symbols: set = set()
        self._asset_stats: Dict[str, Dict[str, Any]] = {}
        self._symbol_map = {
            'XAUUSD': 'XAU/USD', 'EURUSD': 'EUR/USD', 'GBPUSD': 'GBP/USD',
            'SP500': 'SPX', 'BTCUSD': 'BTC/USD', 'ETHUSD': 'ETH/USD',
            'BNBUSD': 'BNB/USD', 'SOLUSD': 'SOL/USD', 'XRPUSD': 'XRP/USD',
        }

    def record_execution(self, symbol: str, spread: float = 0,
                         slippage: float = 0, latency_ms: float = 0,
                         fill_pct: float = 100.0, delay_ms: float = 0,
                         broker_deviation: float = 0,
                         expected_price: float = 0,
                         actual_fill_price: float = 0) -> None:
        if symbol not in self._history:
            self._history[symbol] = deque(maxlen=EXECUTION_HISTORY_MAX)
        self._history[symbol].append({
            'spread': spread,
            'slippage': slippage,
            'latency_ms': latency_ms,
            'fill_pct': fill_pct,
            'delay_ms': delay_ms,
            'broker_deviation': broker_deviation,
            'expected_price': expected_price,
            'actual_fill_price': actual_fill_price,
            'timestamp': time.time(),
        })
        self._update_asset_stats(symbol, slippage, latency_ms)

    def analyze(self, symbol: str, current_spread: Optional[float] = None,
                current_latency: Optional[float] = None) -> Dict[str, Any]:
        result = {
            'score': 50,
            'components': {},
            'warn': False,
            'block': False,
            'reason': '',
        }
        try:
            records = list(self._history.get(symbol, []))
            if not records:
                result['score'] = 85
                result['components'] = {k: 85 for k in EXECUTION_WEIGHTS}
                result['reason'] = 'No execution history, defaulting to acceptable'
                return result

            window = records[-SCORING_WINDOW:] if len(records) >= SCORING_WINDOW else records
            if not window:
                return result

            # Sub-scores (0-100, higher = better)
            spread_score = self._score_spread(window, current_spread)
            slippage_score = self._score_slippage(window)
            latency_score = self._score_latency(window, current_latency)
            fill_score = self._score_fill(window)
            partial_score = self._score_partial_fills(window)
            delay_score = self._score_delay(window)
            broker_score = self._score_broker_deviation(window)

            components = {
                'spread': spread_score,
                'slippage': slippage_score,
                'latency': latency_score,
                'fill_quality': fill_score,
                'partial_fills': partial_score,
                'delay': delay_score,
                'broker_deviation': broker_score,
            }

            # Weighted composite score
            total_weight = 0
            weighted_score = 0
            for key, weight in EXECUTION_WEIGHTS.items():
                s = components.get(key, 50)
                weighted_score += s * weight
                total_weight += weight
            composite = int(weighted_score / total_weight) if total_weight > 0 else 50
            composite = max(0, min(100, composite))

            # Trend: compare recent vs older
            trend = self._compute_trend(records)

            result['score'] = composite
            result['components'] = components
            result['trend'] = trend
            result['samples'] = len(window)

            # Threshold checks
            if composite < BLOCK_THRESHOLD:
                result['block'] = True
                result['reason'] = (f'Execution quality critical ({composite}): block threshold '
                                    f'{BLOCK_THRESHOLD}')
                if symbol not in self._warned_symbols:
                    self._warned_symbols.add(symbol)
            elif composite < WARN_THRESHOLD:
                result['warn'] = True
                result['reason'] = (f'Execution quality degraded ({composite}): warn threshold '
                                    f'{WARN_THRESHOLD}')
                self._warned_symbols.add(symbol)
            else:
                result['reason'] = f'Execution quality acceptable ({composite})'
                self._warned_symbols.discard(symbol)

            self._last_score[symbol] = result

        except Exception as e:
            log.warning(f"ExecutionQualityAnalyzer.analyze({symbol}) error: {e}")
            result['error'] = str(e)

        return result

    def get_last_score(self, symbol: str = 'XAUUSD') -> Dict[str, Any]:
        return dict(self._last_score.get(symbol, {}))

    def get_asset_stats(self, symbol: str) -> Dict[str, Any]:
        stats = self._asset_stats.get(symbol, {})
        return {
            'avg_slippage_pips': stats.get('avg_slippage_pips', 0),
            'best_execution_time': stats.get('best_execution_time', 0),
            'worst_execution_time': stats.get('worst_execution_time', 0),
            'execution_quality_score': stats.get('execution_quality_score', 85),
            'total_executions': stats.get('total_executions', 0),
        }

    def _fetch_market_data(self, symbol: str) -> Dict[str, Any]:
        api_key = os.environ.get('LIVE_DATA_API_KEY', '')
        if not api_key:
            return {'spread': 0, 'bid': 0, 'ask': 0, 'price': 0, 'volatility': 0}
        td_symbol = self._symbol_map.get(symbol, symbol)
        try:
            url = f"https://api.twelvedata.com/quote?symbol={td_symbol}&apikey={api_key}"
            resp = urllib.request.urlopen(url, timeout=10)
            data = json.loads(resp.read().decode())
            bid = float(data.get('bid', 0))
            ask = float(data.get('ask', 0))
            price = float(data.get('close', 0)) or float(data.get('previous_close', 0))
            spread = abs(ask - bid)
            high = float(data.get('high', 0))
            low = float(data.get('low', 0))
            volatility = ((high - low) / price * 100) if price and high and low else 0
            return {'spread': spread, 'bid': bid, 'ask': ask, 'price': price, 'volatility': volatility}
        except Exception as e:
            log.debug(f"Twelve Data quote fetch failed for {symbol}: {e}")
            return {'spread': 0, 'bid': 0, 'ask': 0, 'price': 0, 'volatility': 0}

    def is_blocked(self, symbol: str = 'XAUUSD') -> bool:
        s = self._last_score.get(symbol, {})
        return s.get('block', False)

    def reset_warnings(self, symbol: Optional[str] = None) -> None:
        if symbol:
            self._warned_symbols.discard(symbol)
        else:
            self._warned_symbols.clear()

    def _update_asset_stats(self, symbol: str, slippage: float, latency_ms: float):
        if symbol not in self._asset_stats:
            self._asset_stats[symbol] = {
                'slippages': [], 'latencies': [], 'total_executions': 0,
                'avg_slippage_pips': 0, 'best_execution_time': 0,
                'worst_execution_time': 0, 'execution_quality_score': 85,
            }
        stats = self._asset_stats[symbol]
        stats['total_executions'] += 1
        stats['slippages'].append(abs(slippage))
        stats['latencies'].append(latency_ms)
        if stats['slippages']:
            stats['avg_slippage_pips'] = statistics.mean(stats['slippages'])
        valid_lats = [t for t in stats['latencies'] if t > 0]
        if valid_lats:
            stats['best_execution_time'] = min(valid_lats)
            stats['worst_execution_time'] = max(valid_lats)
        last = self._last_score.get(symbol, {})
        stats['execution_quality_score'] = last.get('score', 85)

    # ---- Internal scoring methods ----

    def _score_spread(self, records: List[Dict],
                      current_spread: Optional[float] = None) -> int:
        spreads = [r.get('spread', 0) for r in records if r.get('spread', 0) > 0]
        if not spreads:
            return 85
        avg = statistics.mean(spreads)
        if avg <= 1.0:
            return 95
        if avg <= 2.0:
            return 85
        if avg <= 3.0:
            return 70
        if avg <= 5.0:
            return 50
        return max(0, 50 - int((avg - 5) * 5))

    def _score_slippage(self, records: List[Dict]) -> int:
        slips = [abs(r.get('slippage', 0)) for r in records if r.get('slippage') is not None]
        if not slips:
            return 85
        avg = statistics.mean(slips)
        if avg <= 0.2:
            return 95
        if avg <= 0.5:
            return 85
        if avg <= 1.0:
            return 70
        if avg <= 2.0:
            return 50
        return max(0, 50 - int((avg - 2) * 10))

    def _score_latency(self, records: List[Dict],
                       current_latency: Optional[float] = None) -> int:
        lats = [r.get('latency_ms', 0) for r in records if r.get('latency_ms', 0) > 0]
        if current_latency is not None:
            lats.append(current_latency)
        if not lats:
            return 85
        avg = statistics.mean(lats)
        if avg <= 30:
            return 95
        if avg <= 60:
            return 85
        if avg <= 100:
            return 70
        if avg <= 200:
            return 50
        return max(0, 50 - int((avg - 200) / 20))

    def _score_fill(self, records: List[Dict]) -> int:
        fills = [r.get('fill_pct', 100) for r in records if r.get('fill_pct') is not None]
        if not fills:
            return 85
        avg = statistics.mean(fills)
        if avg >= 99:
            return 95
        if avg >= 95:
            return 85
        if avg >= 85:
            return 65
        if avg >= 70:
            return 40
        return max(0, int(avg))

    def _score_partial_fills(self, records: List[Dict]) -> int:
        partials = [r for r in records if r.get('fill_pct', 100) < 100]
        if not records:
            return 85
        pct = len(partials) / len(records)
        if pct <= 0.05:
            return 95
        if pct <= 0.10:
            return 85
        if pct <= 0.20:
            return 65
        if pct <= 0.40:
            return 40
        return max(0, 100 - int(pct * 100))

    def _score_delay(self, records: List[Dict]) -> int:
        delays = [r.get('delay_ms', 0) for r in records if r.get('delay_ms') is not None]
        if not delays:
            return 85
        avg = statistics.mean(delays)
        if avg <= 50:
            return 95
        if avg <= 100:
            return 85
        if avg <= 200:
            return 65
        if avg <= 500:
            return 40
        return max(0, 50 - int((avg - 500) / 50))

    def _score_broker_deviation(self, records: List[Dict]) -> int:
        devs = [abs(r.get('broker_deviation', 0)) for r in records
                if r.get('broker_deviation') is not None]
        if not devs:
            return 85
        avg = statistics.mean(devs)
        if avg <= 0.1:
            return 95
        if avg <= 0.3:
            return 85
        if avg <= 0.5:
            return 70
        if avg <= 1.0:
            return 50
        return max(0, 50 - int((avg - 1) * 20))

    def _compute_trend(self, records: List[Dict]) -> str:
        if len(records) < 10:
            return 'stable'
        half = len(records) // 2
        recent = records[-half:]
        older = records[:half]
        recent_avg = sum(
            r.get('spread', 0) + r.get('slippage', 0) * 2 + r.get('latency_ms', 0) / 20
            for r in recent
        ) / len(recent) if recent else 0
        older_avg = sum(
            r.get('spread', 0) + r.get('slippage', 0) * 2 + r.get('latency_ms', 0) / 20
            for r in older
        ) / len(older) if older else 0
        if recent_avg < older_avg * 0.9:
            return 'improving'
        if recent_avg > older_avg * 1.1:
            return 'degrading'
        return 'stable'


_analyzer: Optional[ExecutionQualityAnalyzer] = None


def get_execution_analyzer() -> ExecutionQualityAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = ExecutionQualityAnalyzer()
    return _analyzer


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    ea = get_execution_analyzer()
    import random
    for _ in range(60):
        ea.record_execution('XAUUSD',
                            spread=random.uniform(0.5, 3.0),
                            slippage=random.uniform(0, 1.0),
                            latency_ms=random.uniform(20, 150),
                            fill_pct=random.uniform(85, 100),
                            delay_ms=random.uniform(10, 300),
                            broker_deviation=random.uniform(0, 0.5))
    result = ea.analyze('XAUUSD')
    print(f"Execution Score: {result['score']}")
    print(f"Warn: {result['warn']}, Block: {result['block']}")
    print(f"Reason: {result['reason']}")
