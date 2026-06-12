"""Multi-Timeframe AI Consensus Engine

Hierarchical consensus across H4, H1, M15, M5, M1 timeframes.
Each TF outputs trend, liquidity, order flow, momentum, bias, confidence.
Weighted consensus with higher-timeframe disagreement protection.
"""

import logging
import math
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime, timezone

log = logging.getLogger(__name__)

TIMEFRAMES = ['H4', 'H1', 'M15', 'M5', 'M1']

TF_WEIGHTS = {
    'H4': 0.35,
    'H1': 0.25,
    'M15': 0.20,
    'M5': 0.10,
    'M1': 0.10,
}

DISAGREEMENT_THRESHOLD = 0.30


class MTFConsensus:
    """Hierarchical multi-timeframe consensus with alignment checking."""

    def __init__(self):
        self._last_result: Dict[str, Any] = {}

    def analyze(self, candles: Dict[str, List[Dict]], current_price: float,
                sweep_analysis: Optional[Dict] = None,
                trap_analysis: Optional[Dict] = None,
                orderflow_analysis: Optional[Dict] = None,
                macro_analysis: Optional[Dict] = None,
                regime: str = 'COMPRESSION',
                session: str = '',
                ) -> Dict[str, Any]:
        result = {
            'consensus': 50,
            'alignment': 100,
            'bias': 'NEUTRAL',
            'tfs': {},
            'disagreement': False,
            'rejected': False,
            'reason': '',
        }
        try:
            tf_results = {}
            for tf_name in TIMEFRAMES:
                tf_candles = candles.get(tf_name, [])
                analysis = self._analyze_tf(
                    tf_name, tf_candles, current_price,
                    sweep_analysis, trap_analysis, orderflow_analysis,
                    macro_analysis, regime, session,
                )
                tf_results[tf_name] = analysis
                result['tfs'][tf_name] = analysis

            # -- Weighted consensus --
            total_weight = 0
            weighted_bull = 0
            weighted_bear = 0
            weighted_conf = 0

            for tf_name in TIMEFRAMES:
                a = tf_results.get(tf_name, {})
                weight = TF_WEIGHTS.get(tf_name, 0)
                bull = a.get('bull_prob', 50)
                bear = a.get('bear_prob', 50)
                conf = a.get('confidence', 50)
                weighted_bull += bull * weight
                weighted_bear += bear * weight
                weighted_conf += conf * weight
                total_weight += weight

            if total_weight > 0:
                avg_bull = weighted_bull / total_weight
                avg_bear = weighted_bear / total_weight
                avg_conf = weighted_conf / total_weight
            else:
                avg_bull = avg_bear = 50
                avg_conf = 50

            # -- Determine bias --
            if avg_bull > avg_bear + 10:
                bias = 'BULLISH'
                consensus = int(avg_bull * (avg_conf / 100))
            elif avg_bear > avg_bull + 10:
                bias = 'BEARISH'
                consensus = int(avg_bear * (avg_conf / 100))
            else:
                bias = 'NEUTRAL'
                consensus = int(avg_conf)

            # -- Higher timeframe disagreement check --
            disagreement = self._check_disagreement(tf_results)
            rejected = disagreement and disagreement.get('severity', 0) > DISAGREEMENT_THRESHOLD

            alignment = self._compute_alignment(tf_results)

            result['consensus'] = max(0, min(100, consensus))
            result['alignment'] = alignment
            result['bias'] = bias
            result['bullish_consensus'] = round(avg_bull, 1)
            result['bearish_consensus'] = round(avg_bear, 1)
            result['average_confidence'] = round(avg_conf, 1)
            result['disagreement'] = disagreement is not None
            result['rejected'] = rejected
            if disagreement:
                result['disagreement_detail'] = disagreement
            if rejected:
                result['reason'] = f"Higher timeframe disagreement: {disagreement.get('detail', '')}"
            elif alignment >= 80:
                result['reason'] = f"Strong alignment ({alignment}%) across timeframes"
            elif alignment >= 60:
                result['reason'] = f"Moderate alignment ({alignment}%)"
            else:
                result['reason'] = f"Weak alignment ({alignment}%), caution advised"

            self._last_result = result

        except Exception as e:
            log.warning(f"MTFConsensus.analyze error: {e}")
            result['error'] = str(e)

        return result

    def get_last_result(self) -> Dict[str, Any]:
        return dict(self._last_result) if self._last_result else {}

    # ---- Internal methods ----

    def _analyze_tf(self, tf: str, candles: List[Dict], price: float,
                    sweep: Optional[Dict], trap: Optional[Dict],
                    orderflow: Optional[Dict], macro: Optional[Dict],
                    regime: str, session: str) -> Dict[str, Any]:
        if not candles or len(candles) < 5:
            return {'trend': 0, 'momentum': 0, 'bull_prob': 50, 'bear_prob': 50,
                    'confidence': 30, 'bias': 'NEUTRAL', 'liquidity': 0}

        try:
            closes = [c.get('close', price) for c in candles]
            highs = [c.get('high', price) for c in candles]
            lows = [c.get('low', price) for c in candles]
            volumes = [c.get('volume', 0) for c in candles]

            current = closes[-1] if closes else price

            # Trend: EMA comparison
            ema_short = self._ema(closes, min(5, len(closes)))
            ema_long = self._ema(closes, min(20, len(closes)))
            trend = 0
            if ema_short and ema_long:
                diff_pct = (ema_short - ema_long) / (ema_long or 1) * 100
                trend = max(-100, min(100, diff_pct * 10))

            # Momentum: rate of change
            momentum = 0
            if len(closes) >= 5:
                roc = (current - closes[-5]) / (closes[-5] or 1) * 100
                momentum = max(-100, min(100, roc * 5))

            # Liquidity proxy: recent range expansion
            recent_range = max(highs[-5:]) - min(lows[-5:]) if len(highs) >= 5 else 0
            older_range = max(highs[:5]) - min(lows[:5]) if len(highs) >= 10 else recent_range
            liquidity = 0
            if older_range > 0:
                range_ratio = recent_range / older_range
                if range_ratio > 1.5:
                    liquidity = 30
                elif range_ratio < 0.5:
                    liquidity = 70
                else:
                    liquidity = 50

            # Volume confirmation
            vol_confirm = 0
            if len(volumes) >= 5:
                avg_vol = sum(volumes[-5:]) / 5
                overall_avg = sum(volumes) / len(volumes) if volumes else 1
                if overall_avg > 0:
                    vol_ratio = avg_vol / overall_avg
                    vol_confirm = max(-50, min(50, (vol_ratio - 1) * 50))

            # Combine into bull/bear probability
            combined = trend * 0.4 + momentum * 0.3 + vol_confirm * 0.3
            bull_prob = 50 + combined
            bear_prob = 50 - combined
            bull_prob = max(0, min(100, bull_prob))
            bear_prob = max(0, min(100, bear_prob))

            # Confidence based on data sufficiency and alignment
            data_points = len(candles)
            confidence = min(100, 30 + data_points * 2)
            if abs(trend) > 30 and abs(momentum) > 20:
                confidence = min(100, confidence + 15)
            if vol_confirm > 10:
                confidence = min(100, confidence + 10)

            # Bias
            if bull_prob > bear_prob + 10:
                bias = 'BULLISH'
            elif bear_prob > bull_prob + 10:
                bias = 'BEARISH'
            else:
                bias = 'NEUTRAL'

            return {
                'trend': round(trend, 1),
                'momentum': round(momentum, 1),
                'bull_prob': round(bull_prob, 1),
                'bear_prob': round(bear_prob, 1),
                'confidence': round(confidence, 1),
                'bias': bias,
                'liquidity': round(liquidity, 1),
                'volume_confirm': round(vol_confirm, 1),
                'ema_short': round(ema_short, 2) if ema_short else None,
                'ema_long': round(ema_long, 2) if ema_long else None,
            }

        except Exception as e:
            log.debug(f"MTFConsensus._analyze_tf({tf}) error: {e}")
            return {'trend': 0, 'momentum': 0, 'bull_prob': 50, 'bear_prob': 50,
                    'confidence': 30, 'bias': 'NEUTRAL', 'liquidity': 0}

    def _check_disagreement(self, tf_results: Dict[str, Dict]) -> Optional[Dict]:
        higher_tfs = ['H4', 'H1', 'M15']
        biases = []
        for tf_name in higher_tfs:
            a = tf_results.get(tf_name, {})
            bias = a.get('bias', 'NEUTRAL')
            if bias != 'NEUTRAL':
                biases.append((tf_name, bias))

        if len(biases) < 2:
            return None

        unique_biases = set(b for _, b in biases)
        if len(unique_biases) <= 1:
            return None

        bull_count = sum(1 for _, b in biases if b == 'BULLISH')
        bear_count = sum(1 for _, b in biases if b == 'BEARISH')
        total = len(biases)
        severity = abs(bull_count - bear_count) / total if total > 0 else 0

        return {
            'severity': round(severity, 2),
            'detail': f"H4={'BULLISH' if any(t== 'H4' and b=='BULLISH' for t,b in biases) else 'BEARISH' if any(t=='H4' and b=='BEARISH' for t,b in biases) else 'NEUTRAL'}, "
                      f"H1={'BULLISH' if any(t=='H1' and b=='BULLISH' for t,b in biases) else 'BEARISH' if any(t=='H1' and b=='BEARISH' for t,b in biases) else 'NEUTRAL'}, "
                      f"M15={'BULLISH' if any(t=='M15' and b=='BULLISH' for t,b in biases) else 'BEARISH' if any(t=='M15' and b=='BEARISH' for t,b in biases) else 'NEUTRAL'}",
        }

    def _compute_alignment(self, tf_results: Dict[str, Dict]) -> int:
        biases = {}
        for tf_name in TIMEFRAMES:
            a = tf_results.get(tf_name, {})
            biases[tf_name] = a.get('bias', 'NEUTRAL')

        non_neutral = {k: v for k, v in biases.items() if v != 'NEUTRAL'}
        if not non_neutral:
            return 50

        bull = sum(1 for v in non_neutral.values() if v == 'BULLISH')
        bear = sum(1 for v in non_neutral.values() if v == 'BEARISH')
        total = len(non_neutral)
        majority = max(bull, bear)
        return int((majority / total) * 100)

    @staticmethod
    def _ema(values: List[float], period: int) -> Optional[float]:
        if not values or len(values) < period:
            return None
        try:
            k = 2.0 / (period + 1)
            ema = sum(values[:period]) / period
            for v in values[period:]:
                ema = v * k + ema * (1 - k)
            return ema
        except Exception:
            return None


_consensus: Optional[MTFConsensus] = None


def get_mtf_consensus() -> MTFConsensus:
    global _consensus
    if _consensus is None:
        _consensus = MTFConsensus()
    return _consensus


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    mc = get_mtf_consensus()
    test_candles = {}
    for tf in TIMEFRAMES:
        test_candles[tf] = [
            {'high': 2010 + i, 'low': 1990 + i, 'close': 2000 + i * 0.5,
             'open': 1999 + i * 0.5, 'volume': 100 + i * 10}
            for i in range(50)
        ]
    result = mc.analyze(test_candles, 2025.0, regime='EXPANSION', session='LONDON')
    print(f"Consensus: {result['consensus']}, Bias: {result['bias']}")
    print(f"Alignment: {result['alignment']}%, Rejected: {result['rejected']}")
    print(f"Reason: {result['reason']}")
