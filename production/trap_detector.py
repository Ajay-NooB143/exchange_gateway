"""
Module 3 — Market Maker Trap Detector
=======================================
Detects fake breakouts, bull/bear traps, stop hunts, liquidity raids,
false BOS/MSS, reclaim failures, and manipulation candles.

Generates Trap Probability 0-100. If threshold exceeded, blocks trade.
"""

import logging
import math
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple

log = logging.getLogger('TrapDetector')

TRAP_THRESHOLD_DEFAULT = 70


class TrapDetector:
    """
    Detect market maker traps across multiple patterns.

    Trap types:
      - Fake breakout: price breaks a level but immediately reverses
      - Bull trap: breaks above resistance, closes below
      - Bear trap: breaks below support, closes above
      - Stop hunt: sweeps obvious stop levels then reverses
      - Liquidity raid: aggressive sweep with instant rejection
      - False BOS: breaks structure but fails to sustain
      - False MSS: market structure shift that reverses
      - Reclaim failure: fails to reclaim a key level
      - Manipulation candle: large wick with small body
    """

    def __init__(self, threshold: int = TRAP_THRESHOLD_DEFAULT):
        self.threshold = threshold
        self._current_probability: int = 0
        self._active_trap_types: List[str] = []
        self._blocked: bool = False

    def analyze(
        self,
        candles: List[Dict],
        current_price: float,
        pdh: Optional[float] = None,
        pdl: Optional[float] = None,
        support: Optional[float] = None,
        resistance: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Analyze candles for trap patterns.

        Returns:
            Dict with trap_probability (0-100), blocked (bool),
            trap_types list, and suggested_direction.
        """
        if not candles or len(candles) < 5:
            return {'trap_probability': 0, 'blocked': False, 'trap_types': [], 'suggested_direction': 'NONE'}

        atr = self._estimate_atr(candles)
        trap_probs = []
        active_types = []

        try:
            # Fake breakout
            fake_bos_prob = self._detect_fake_breakout(candles, pdh, pdl, atr)
            if fake_bos_prob > 0:
                trap_probs.append(fake_bos_prob)
                active_types.append('FAKE_BREAKOUT')

            # Bull/bear trap
            bull_trap_prob = self._detect_bull_trap(candles, resistance, atr)
            if bull_trap_prob > 0:
                trap_probs.append(bull_trap_prob)
                active_types.append('BULL_TRAP')

            bear_trap_prob = self._detect_bear_trap(candles, support, atr)
            if bear_trap_prob > 0:
                trap_probs.append(bear_trap_prob)
                active_types.append('BEAR_TRAP')

            # Stop hunt
            stop_hunt_prob = self._detect_stop_hunt(candles, atr)
            if stop_hunt_prob > 0:
                trap_probs.append(stop_hunt_prob)
                active_types.append('STOP_HUNT')

            # Liquidity raid
            raid_prob = self._detect_liquidity_raid(candles, atr)
            if raid_prob > 0:
                trap_probs.append(raid_prob)
                active_types.append('LIQUIDITY_RAID')

            # False BOS/MSS
            false_bos_prob = self._detect_false_bos(candles)
            if false_bos_prob > 0:
                trap_probs.append(false_bos_prob)
                active_types.append('FALSE_BOS')

            false_mss_prob = self._detect_false_mss(candles)
            if false_mss_prob > 0:
                trap_probs.append(false_mss_prob)
                active_types.append('FALSE_MSS')

            # Reclaim failure
            reclaim_prob = self._detect_reclaim_failure(candles, current_price, atr)
            if reclaim_prob > 0:
                trap_probs.append(reclaim_prob)
                active_types.append('RECLAIM_FAILURE')

            # Manipulation candle
            manip_prob = self._detect_manipulation_candle(candles, atr)
            if manip_prob > 0:
                trap_probs.append(manip_prob)
                active_types.append('MANIPULATION_CANDLE')

        except Exception as e:
            log.debug(f"Trap analysis error: {e}")

        # Aggregate
        if trap_probs:
            self._current_probability = min(100, int(sum(trap_probs) / max(len(trap_probs), 1) + min(len(trap_probs) * 5, 20)))
        else:
            self._current_probability = 0

        self._active_trap_types = active_types
        self._blocked = self._current_probability >= self.threshold

        # Suggested opposite direction
        suggested = 'NONE'
        if self._blocked:
            suggested = self._suggest_opposite(candles, current_price)

        return {
            'trap_probability': self._current_probability,
            'blocked': self._blocked,
            'threshold': self.threshold,
            'trap_types': active_types,
            'suggested_direction': suggested,
        }

    def _detect_fake_breakout(self, candles: List[Dict], pdh: Optional[float], pdl: Optional[float], atr: float) -> float:
        if not pdh and not pdl or len(candles) < 3:
            return 0.0
        prob = 0.0
        recent = candles[-3:]
        try:
            for c in recent:
                if pdh and c.get('high', 0) > pdh:
                    close = c.get('close', 0)
                    if close < pdh - atr * 0.3:
                        prob = max(prob, 0.75)
                    elif close < pdh:
                        prob = max(prob, 0.5)
                if pdl and c.get('low', 0) < pdl:
                    close = c.get('close', 0)
                    if close > pdl + atr * 0.3:
                        prob = max(prob, 0.75)
                    elif close > pdl:
                        prob = max(prob, 0.5)
        except Exception:
            pass
        return prob * 100

    def _detect_bull_trap(self, candles: List[Dict], resistance: Optional[float], atr: float) -> float:
        if not resistance or len(candles) < 3:
            return 0.0
        try:
            recent = candles[-3:]
            for c in recent:
                if c.get('high', 0) > resistance:
                    if c.get('close', 0) < resistance - atr * 0.2:
                        return 80.0
                    elif c.get('close', 0) < resistance:
                        return 55.0
        except Exception:
            pass
        return 0.0

    def _detect_bear_trap(self, candles: List[Dict], support: Optional[float], atr: float) -> float:
        if not support or len(candles) < 3:
            return 0.0
        try:
            recent = candles[-3:]
            for c in recent:
                if c.get('low', 0) < support:
                    if c.get('close', 0) > support + atr * 0.2:
                        return 80.0
                    elif c.get('close', 0) > support:
                        return 55.0
        except Exception:
            pass
        return 0.0

    def _detect_stop_hunt(self, candles: List[Dict], atr: float) -> float:
        if len(candles) < 5:
            return 0.0
        try:
            recent = candles[-5:]
            max_high = max(c.get('high', 0) for c in recent)
            min_low = min(c.get('low', 0) for c in recent)
            first_close = recent[0].get('close', 0)
            last_close = recent[-1].get('close', 0)

            if max_high > first_close + atr and last_close < first_close + atr * 0.5:
                return 65.0
            if min_low < first_close - atr and last_close > first_close - atr * 0.5:
                return 65.0
        except Exception:
            pass
        return 0.0

    def _detect_liquidity_raid(self, candles: List[Dict], atr: float) -> float:
        if len(candles) < 4:
            return 0.0
        try:
            c1, c2, c3 = candles[-3], candles[-2], candles[-1]
            # Aggressive move beyond ATR * 1.5 with rejection
            move = abs(c2.get('close', 0) - c1.get('close', 0))
            rejection = abs(c3.get('close', 0) - c2.get('high' if c2.get('close', 0) > c2.get('open', 0) else 'low', 0))
            if move > atr * 1.5 and rejection > move * 0.6:
                return min(100, int((rejection / move) * 80 + 20))
        except Exception:
            pass
        return 0.0

    def _detect_false_bos(self, candles: List[Dict]) -> float:
        if len(candles) < 6:
            return 0.0
        try:
            highs = [c.get('high', 0) for c in candles[-6:]]
            lows = [c.get('low', 0) for c in candles[-6:]]
            if highs[2] > max(highs[:2]) and highs[3] > highs[2]:
                # Broke structure, now check reversal
                if highs[4] < highs[3] and highs[5] < highs[4]:
                    return 60.0
            if lows[2] < min(lows[:2]) and lows[3] < lows[2]:
                if lows[4] > lows[3] and lows[5] > lows[4]:
                    return 60.0
        except Exception:
            pass
        return 0.0

    def _detect_false_mss(self, candles: List[Dict]) -> float:
        if len(candles) < 8:
            return 0.0
        try:
            highs = [c.get('high', 0) for c in candles[-8:]]
            lows = [c.get('low', 0) for c in candles[-8:]]
            # Detect HH then HL break (MSS) then reversal
            if highs[-5] > highs[-6] and lows[-4] > lows[-5]:
                if highs[-2] < highs[-3] and highs[-1] < highs[-2]:
                    return 55.0
            if lows[-5] < lows[-6] and highs[-4] < highs[-5]:
                if lows[-2] > lows[-3] and lows[-1] > lows[-2]:
                    return 55.0
        except Exception:
            pass
        return 0.0

    def _detect_reclaim_failure(self, candles: List[Dict], current_price: float, atr: float) -> float:
        if len(candles) < 5:
            return 0.0
        try:
            recent = candles[-5:]
            avg = sum(c.get('close', 0) for c in recent) / len(recent)
            # Price crossed a key level then failed to hold
            for c in recent:
                if abs(c.get('close', 0) - avg) > atr * 0.5:
                    if abs(current_price - avg) < atr * 0.2:
                        return 45.0
        except Exception:
            pass
        return 0.0

    def _detect_manipulation_candle(self, candles: List[Dict], atr: float) -> float:
        if not candles:
            return 0.0
        try:
            c = candles[-1]
            wick_top = c.get('high', 0) - max(c.get('close', 0), c.get('open', 0))
            wick_bottom = min(c.get('close', 0), c.get('open', 0)) - c.get('low', 0)
            body = abs(c.get('close', 0) - c.get('open', 0))
            total_range = c.get('high', 0) - c.get('low', 0)

            if total_range <= 0 or body <= 0:
                return 0.0

            wick_ratio = max(wick_top, wick_bottom) / max(body, 0.01)
            range_vs_atr = total_range / max(atr, 0.01)

            if wick_ratio > 3.0 and range_vs_atr > 1.5:
                return 75.0
            elif wick_ratio > 2.0 and range_vs_atr > 1.0:
                return 50.0
        except Exception:
            pass
        return 0.0

    def _suggest_opposite(self, candles: List[Dict], current_price: float) -> str:
        if not candles:
            return 'NONE'
        try:
            last = candles[-1]
            if last.get('close', 0) > last.get('open', 0):
                bearish = sum(1 for t in self._active_trap_types if t in ('BULL_TRAP', 'FAKE_BREAKOUT'))
                if bearish >= 2:
                    return 'SELL'
            else:
                bullish = sum(1 for t in self._active_trap_types if t in ('BEAR_TRAP', 'FAKE_BREAKOUT'))
                if bullish >= 2:
                    return 'BUY'
        except Exception:
            pass
        return 'NONE'

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


_trap: Optional[TrapDetector] = None


def get_trap_detector() -> TrapDetector:
    global _trap
    if _trap is None:
        _trap = TrapDetector()
    return _trap


if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    if '--test' in sys.argv:
        td = get_trap_detector()
        candles = [{'high': 100 + i, 'low': 98 + i * 0.5, 'close': 99 + i * 0.8, 'open': 99 + i * 0.7, 'volume': 100} for i in range(10)]
        result = td.analyze(candles, 105, pdh=103, pdl=97)
        print(f"Trap prob: {result['trap_probability']}%, Blocked: {result['blocked']}")
        print(f"Types: {result['trap_types']}")
        print("TrapDetector OK")
