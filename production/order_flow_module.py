"""
Module 10 — Institutional Order Flow Module
=============================================
Estimates institutional participation using delta imbalance, aggressive
buying/selling, volume imbalance, CVD divergence, absorption, exhaustion,
iceberg behavior, and liquidity absorption.

Generates Institutional Pressure Score (Bullish/Bearish/Neutral) 0-100.
"""

import logging
import math
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone

log = logging.getLogger('OrderFlowModule')

PRESSURE_BULLISH = 'BULLISH'
PRESSURE_BEARISH = 'BEARISH'
PRESSURE_NEUTRAL = 'NEUTRAL'


class OrderFlowModule:
    """
    Estimate institutional order flow from OHLCV data.

    Uses volume analysis and price action to infer institutional
    participation direction and intensity.
    """

    def __init__(self):
        self._pressure: str = PRESSURE_NEUTRAL
        self._pressure_score: int = 50
        self._components: Dict[str, Any] = {}

    def analyze(
        self,
        candles: List[Dict],
        current_price: float,
    ) -> Dict[str, Any]:
        """
        Analyze institutional order flow.

        Returns:
            Dict with pressure (Bullish/Bearish/Neutral),
            score (0-100), and component breakdown.
        """
        if not candles or len(candles) < 10:
            return {'pressure': PRESSURE_NEUTRAL, 'score': 50, 'components': {}}

        components = {}
        signals = []
        total_weight = 0

        try:
            # Delta imbalance
            delta_score, delta_weight = self._delta_imbalance(candles)
            components['DELTA'] = delta_score
            signals.append(delta_score * delta_weight)
            total_weight += delta_weight * 100

            # Aggressive buying/selling
            agg_score, agg_weight = self._aggressive_activity(candles)
            components['AGGRESSIVE'] = agg_score
            signals.append(agg_score * agg_weight)
            total_weight += agg_weight * 100

            # Volume imbalance
            vol_score, vol_weight = self._volume_imbalance(candles)
            components['VOLUME'] = vol_score
            signals.append(vol_score * vol_weight)
            total_weight += vol_weight * 100

            # CVD divergence proxy
            cvd_score, cvd_weight = self._cvd_divergence(candles)
            components['CVD'] = cvd_score
            signals.append(cvd_score * cvd_weight)
            total_weight += cvd_weight * 100

            # Absorption
            abs_score, abs_weight = self._absorption(candles)
            components['ABSORPTION'] = abs_score
            signals.append(abs_score * abs_weight)
            total_weight += abs_weight * 100

            # Exhaustion
            exh_score, exh_weight = self._exhaustion(candles)
            components['EXHAUSTION'] = exh_score
            signals.append(exh_score * exh_weight)
            total_weight += exh_weight * 100

            # Iceberg behavior
            iceberg_score, iceberg_weight = self._iceberg_behavior(candles)
            components['ICEBERG'] = iceberg_score
            signals.append(iceberg_score * iceberg_weight)
            total_weight += iceberg_weight * 100

        except Exception as e:
            log.debug(f"Order flow analysis error: {e}")

        # Aggregate score
        if total_weight > 0 and signals:
            self._pressure_score = int(sum(signals) / total_weight * 100)
        else:
            self._pressure_score = 50

        self._pressure_score = max(0, min(100, self._pressure_score))

        # Classification
        if self._pressure_score >= 60:
            self._pressure = PRESSURE_BULLISH
        elif self._pressure_score <= 40:
            self._pressure = PRESSURE_BEARISH
        else:
            self._pressure = PRESSURE_NEUTRAL

        self._components = components

        return {
            'pressure': self._pressure,
            'score': self._pressure_score,
            'components': components,
        }

    def _delta_imbalance(self, candles: List[Dict]) -> Tuple[float, float]:
        """Estimate delta from bullish/bearish candle volume."""
        if len(candles) < 5:
            return 0.5, 0.15
        try:
            recent = candles[-10:]
            bullish_vol = sum(
                c.get('volume', 0) for c in recent
                if c.get('close', 0) > c.get('open', 0)
            )
            bearish_vol = sum(
                c.get('volume', 0) for c in recent
                if c.get('close', 0) < c.get('open', 0)
            )
            total_vol = bullish_vol + bearish_vol
            if total_vol == 0:
                return 0.5, 0.15
            ratio = bullish_vol / total_vol
            return ratio, 0.15
        except Exception:
            return 0.5, 0.15

    def _aggressive_activity(self, candles: List[Dict]) -> Tuple[float, float]:
        if len(candles) < 5:
            return 0.5, 0.15
        try:
            recent = candles[-10:]
            aggressive_count = 0
            for c in recent:
                body = abs(c.get('close', 0) - c.get('open', 0))
                wick_top = c.get('high', 0) - max(c.get('close', 0), c.get('open', 0))
                wick_bottom = min(c.get('close', 0), c.get('open', 0)) - c.get('low', 0)
                total = body + wick_top + wick_bottom
                if total <= 0:
                    continue
                body_ratio = body / total
                if body_ratio > 0.7:
                    aggressive_count += 1 if c.get('close', 0) > c.get('open', 0) else -1
            # Normalize to 0-1
            score = 0.5 + (aggressive_count / max(len(recent), 1)) * 0.3
            return max(0, min(1, score)), 0.15
        except Exception:
            return 0.5, 0.15

    def _volume_imbalance(self, candles: List[Dict]) -> Tuple[float, float]:
        if len(candles) < 5:
            return 0.5, 0.12
        try:
            recent = candles[-10:]
            volumes = [c.get('volume', 0) for c in recent if 'volume' in c]
            if not volumes:
                return 0.5, 0.12
            avg_vol = sum(volumes) / len(volumes)
            last_vol = volumes[-1]
            if avg_vol == 0:
                return 0.5, 0.12

            vol_ratio = last_vol / avg_vol
            if vol_ratio > 2.0:
                last_bullish = candles[-1].get('close', 0) > candles[-1].get('open', 0)
                return (0.75 if last_bullish else 0.25), 0.12
            return 0.5, 0.12
        except Exception:
            return 0.5, 0.12

    def _cvd_divergence(self, candles: List[Dict]) -> Tuple[float, float]:
        """CVD proxy: cumulative volume delta divergence."""
        if len(candles) < 10:
            return 0.5, 0.12
        try:
            delta_sum = 0
            for c in candles[-10:]:
                vol = c.get('volume', 0)
                if c.get('close', 0) > c.get('open', 0):
                    delta_sum += vol
                elif c.get('close', 0) < c.get('open', 0):
                    delta_sum -= vol

            price_change = candles[-1].get('close', 0) - candles[-10].get('close', 0)
            if delta_sum > 0 and price_change < 0:
                return 0.25, 0.12
            elif delta_sum < 0 and price_change > 0:
                return 0.75, 0.12
            return 0.5, 0.12
        except Exception:
            return 0.5, 0.12

    def _absorption(self, candles: List[Dict]) -> Tuple[float, float]:
        """Detect absorption: wide-range candle with small close change."""
        if len(candles) < 3:
            return 0.5, 0.12
        try:
            c = candles[-1]
            prev = candles[-2]
            range_c = c.get('high', 0) - c.get('low', 0)
            move = abs(c.get('close', 0) - prev.get('close', 0))
            if range_c > 0 and move < range_c * 0.2:
                vol = c.get('volume', 0)
                avg_vol = sum(x.get('volume', 0) for x in candles[-10:] if 'volume' in x) / max(len(candles[-10:]), 1)
                if vol > avg_vol * 1.5:
                    return 0.70, 0.12
            return 0.5, 0.12
        except Exception:
            return 0.5, 0.12

    def _exhaustion(self, candles: List[Dict]) -> Tuple[float, float]:
        """Detect exhaustion: large move with shrinking volume."""
        if len(candles) < 5:
            return 0.5, 0.10
        try:
            recent = candles[-5:]
            moves = [abs(c.get('close', 0) - c.get('open', 0)) for c in recent if 'close' in c]
            volumes = [c.get('volume', 0) for c in recent if 'volume' in c]
            if len(moves) < 3 or len(volumes) < 3:
                return 0.5, 0.10

            move_trend = moves[-1] - moves[0]
            vol_trend = volumes[-1] - sum(volumes[:3]) / 3

            if move_trend > 0 and vol_trend < 0:
                return 0.30, 0.10
            elif move_trend < 0 and vol_trend > 0:
                return 0.65, 0.10
            return 0.5, 0.10
        except Exception:
            return 0.5, 0.10

    def _iceberg_behavior(self, candles: List[Dict]) -> Tuple[float, float]:
        """Detect potential iceberg orders: repeated same-level rejection."""
        if len(candles) < 10:
            return 0.5, 0.12
        try:
            highs = [c.get('high', 0) for c in candles[-10:] if 'high' in c]
            lows = [c.get('low', 0) for c in candles[-10:] if 'low' in c]
            if not highs or not lows:
                return 0.5, 0.12

            high_touches = sum(1 for i in range(1, len(highs)) if abs(highs[i] - highs[i - 1]) / max(highs[i], 1) < 0.002)
            low_touches = sum(1 for i in range(1, len(lows)) if abs(lows[i] - lows[i - 1]) / max(lows[i], 1) < 0.002)

            if high_touches >= 3:
                return 0.70, 0.12
            elif low_touches >= 3:
                return 0.30, 0.12
            return 0.5, 0.12
        except Exception:
            return 0.5, 0.12


_orderflow: Optional[OrderFlowModule] = None


def get_order_flow_module() -> OrderFlowModule:
    global _orderflow
    if _orderflow is None:
        _orderflow = OrderFlowModule()
    return _orderflow


if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    if '--test' in sys.argv:
        of = get_order_flow_module()
        candles = [{'high': 100 + i * 0.5, 'low': 99 + i * 0.3, 'close': 99.5 + i * 0.4, 'open': 99 + i * 0.3, 'volume': 100 + i * 20} for i in range(15)]
        result = of.analyze(candles, 105)
        print(f"Pressure: {result['pressure']} ({result['score']}/100)")
        print(f"Components: {result['components']}")
        print("OrderFlowModule OK")
