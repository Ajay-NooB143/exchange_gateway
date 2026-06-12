"""
Module 7 — Killzone Probability Engine
=======================================
Evaluates session quality for London Open, NY Open, London Close,
and Asian Session.

Metrics: ADR completion, volatility, remaining liquidity, news proximity,
historical expectancy, sweep probability.

Generates Killzone Quality Score 0-100 with classification:
  Aggressive (>=75), Normal (50-74), Avoid (<50).
"""

import logging
import math
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

log = logging.getLogger('KillzoneEngine')

KILLZONE_AGGRESSIVE = 'AGGRESSIVE'
KILLZONE_NORMAL = 'NORMAL'
KILLZONE_AVOID = 'AVOID'

SESSION_LONDON_OPEN = 'LONDON_OPEN'
SESSION_NY_OPEN = 'NY_OPEN'
SESSION_LONDON_CLOSE = 'LONDON_CLOSE'
SESSION_ASIAN = 'ASIAN'

SESSION_HOURS = {
    SESSION_ASIAN: (0, 6),
    SESSION_LONDON_OPEN: (7, 10),
    SESSION_LONDON_CLOSE: (10, 12),
    SESSION_NY_OPEN: (13, 16),
}

SESSION_NAMES = {
    SESSION_ASIAN: 'Asian Session',
    SESSION_LONDON_OPEN: 'London Open',
    SESSION_LONDON_CLOSE: 'London Close',
    SESSION_NY_OPEN: 'NY Open',
}


class KillzoneEngine:
    """
    Evaluate trading session quality with probability scoring.
    """

    def __init__(self):
        self._current_session: str = ''
        self._quality_score: int = 0
        self._classification: str = KILLZONE_NORMAL

    def get_current_session(self) -> str:
        """Detect current trading session based on UTC hour."""
        hour = datetime.now(timezone.utc).hour
        for session, (start, end) in SESSION_HOURS.items():
            if start <= hour < end:
                return session
        return 'OFF_HOURS'

    def analyze(
        self,
        candles: List[Dict],
        current_price: float,
        session: Optional[str] = None,
        adr: Optional[float] = None,
        has_news: bool = False,
        sweep_probability: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate the current killzone quality.

        Args:
            candles: OHLCV candle data
            current_price: Current price
            session: Session name (auto-detected if None)
            adr: Average Daily Range
            has_news: Whether high-impact news is nearby
            sweep_probability: Probability of a sweep (from sweep module)

        Returns:
            Dict with quality_score, classification, components.
        """
        if not candles or len(candles) < 5:
            return {'quality_score': 30, 'classification': KILLZONE_AVOID, 'session': session or self.get_current_session()}

        self._current_session = session or self.get_current_session()
        atr = self._estimate_atr(candles)
        adr = adr or atr * 2.0

        components = {}

        # 1. ADR completion
        adr_score = self._assess_adr_completion(candles, adr)
        components['ADR'] = adr_score

        # 2. Volatility assessment
        vol_score = self._assess_volatility(candles, atr)
        components['VOLATILITY'] = vol_score

        # 3. Remaining liquidity
        liquidity_score = self._assess_liquidity(candles, current_price)
        components['LIQUIDITY'] = liquidity_score

        # 4. News proximity
        news_score = max(0, 50 - (30 if has_news else 0))
        components['NEWS'] = news_score

        # 5. Historical expectancy by session
        hist_score = self._get_session_expectancy(self._current_session)
        components['HISTORICAL'] = hist_score

        # 6. Sweep probability
        if sweep_probability is not None:
            if sweep_probability > 60:
                sweep_score = 75
            elif sweep_probability > 35:
                sweep_score = 55
            else:
                sweep_score = 30
        else:
            sweep_score = 50
        components['SWEEP_PROB'] = sweep_score

        # Session weighting
        weights = self._get_session_weights(self._current_session)
        weighted_sum = sum(components.get(k, 50) * weights.get(k, 1.0) for k in components)
        total_weight = sum(weights.get(k, 1.0) for k in components)

        self._quality_score = int(weighted_sum / max(total_weight, 1)) if total_weight > 0 else 30

        # Classification
        if self._quality_score >= 75:
            self._classification = KILLZONE_AGGRESSIVE
        elif self._quality_score >= 50:
            self._classification = KILLZONE_NORMAL
        else:
            self._classification = KILLZONE_AVOID

        return {
            'quality_score': self._quality_score,
            'classification': self._classification,
            'session': self._current_session,
            'session_name': SESSION_NAMES.get(self._current_session, 'Off Hours'),
            'components': components,
        }

    def _assess_adr_completion(self, candles: List[Dict], adr: float) -> int:
        if not candles or adr <= 0:
            return 50
        try:
            day_candles = candles[-24:]
            day_range = max(c.get('high', 0) for c in day_candles if 'high' in c) - min(c.get('low', 0) for c in day_candles if 'low' in c)
            completion = day_range / max(adr, 0.01)
            if completion < 0.3:
                return 80
            elif completion < 0.5:
                return 65
            elif completion < 0.7:
                return 50
            elif completion < 0.9:
                return 40
            else:
                return 25
        except Exception:
            return 50

    def _assess_volatility(self, candles: List[Dict], atr: float) -> int:
        if not candles or len(candles) < 10 or atr <= 0:
            return 50
        try:
            recent = candles[-10:]
            recent_range = sum(c.get('high', 0) - c.get('low', 0) for c in recent if 'high' in c) / max(len(recent), 1)
            ratio = recent_range / max(atr, 0.01)
            if ratio > 1.2:
                return 75
            elif ratio > 0.8:
                return 60
            elif ratio > 0.5:
                return 45
            return 30
        except Exception:
            return 50

    def _assess_liquidity(self, candles: List[Dict], current_price: float) -> int:
        if not candles:
            return 50
        try:
            highs = [c.get('high', 0) for c in candles[-10:] if 'high' in c]
            lows = [c.get('low', 0) for c in candles[-10:] if 'low' in c]
            if not highs or not lows:
                return 50
            near_high = abs(current_price - max(highs)) / max(current_price, 1) < 0.01
            near_low = abs(current_price - min(lows)) / max(current_price, 1) < 0.01
            if near_high or near_low:
                return 70
            mid_range = (max(highs) + min(lows)) / 2
            if abs(current_price - mid_range) / max(current_price, 1) < 0.005:
                return 40
            return 55
        except Exception:
            return 50

    def _get_session_expectancy(self, session: str) -> int:
        expectancy = {
            SESSION_LONDON_OPEN: 65,
            SESSION_NY_OPEN: 60,
            SESSION_LONDON_CLOSE: 50,
            SESSION_ASIAN: 35,
        }
        return expectancy.get(session, 40)

    def _get_session_weights(self, session: str) -> Dict[str, float]:
        base = {'ADR': 1.0, 'VOLATILITY': 1.0, 'LIQUIDITY': 1.0, 'NEWS': 1.0, 'HISTORICAL': 1.0, 'SWEEP_PROB': 1.0}
        if session == SESSION_LONDON_OPEN:
            base['VOLATILITY'] = 1.5
            base['LIQUIDITY'] = 1.3
        elif session == SESSION_NY_OPEN:
            base['VOLATILITY'] = 1.4
            base['ADR'] = 1.3
        elif session == SESSION_LONDON_CLOSE:
            base['ADR'] = 1.2
        elif session == SESSION_ASIAN:
            base['HISTORICAL'] = 1.3
        return base

    @staticmethod
    def _estimate_atr(candles: List[Dict], period: int = 14) -> float:
        if not candles or len(candles) < 2:
            return 5.0
        ranges = []
        for i in range(max(1, len(candles) - period), len(candles)):
            c = candles[i]
            prev = candles[i - 1]
            tr = max(
                c.get('high', 0) - c.get('low', 0),
                abs(c.get('high', 0) - prev.get('close', 0)),
                abs(c.get('low', 0) - prev.get('close', 0)),
            )
            ranges.append(tr)
        return sum(ranges) / max(len(ranges), 1) if ranges else 5.0


_killzone: Optional[KillzoneEngine] = None


def get_killzone_engine() -> KillzoneEngine:
    global _killzone
    if _killzone is None:
        _killzone = KillzoneEngine()
    return _killzone


if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    if '--test' in sys.argv:
        ke = get_killzone_engine()
        candles = [{'high': 100 + i * 0.3, 'low': 99 + i * 0.2, 'close': 99.5 + i * 0.25, 'open': 99 + i * 0.2, 'volume': 100} for i in range(30)]
        result = ke.analyze(candles, 105.5, session='LONDON_OPEN', adr=2.0, has_news=False)
        print(f"Quality: {result['quality_score']} ({result['classification']})")
        print(f"Session: {result['session_name']}")
        print(f"Components: {result['components']}")
        print("KillzoneEngine OK")
