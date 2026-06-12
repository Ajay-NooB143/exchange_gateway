"""
Module 2 — Liquidity Sweep Intelligence
=========================================
Detects and classifies liquidity sweeps across multiple levels.
Generates Sweep Score 0-100 with strength classification.

Levels detected:
  Equal High/Low, PDH/PDL, Weekly H/L, Asian H/L, Session grab
"""

import logging
import math
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field

log = logging.getLogger('LiquiditySweepIntelligence')

SWEEP_WEAK = 'WEAK'
SWEEP_AVERAGE = 'AVERAGE'
SWEEP_STRONG = 'STRONG'
SWEEP_INSTITUTIONAL = 'INSTITUTIONAL_GRADE'


@dataclass
class SweepEvent:
    level_type: str
    price: float
    depth_pct: float
    velocity: float
    volume_spike: float
    displacement_strength: float
    fvg_created: bool
    rejection_speed: float
    time_importance: float
    institutional_footprint: float
    score: float = 0.0

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


class LiquiditySweepIntelligence:
    """
    Detect and classify liquidity sweeps across all known levels.
    """

    LEVEL_TYPES = [
        'EQUAL_HIGH', 'EQUAL_LOW',
        'PDH', 'PDL',
        'WEEKLY_HIGH', 'WEEKLY_LOW',
        'ASIAN_HIGH', 'ASIAN_LOW',
        'SESSION_GRAB',
    ]

    def __init__(self):
        self._sweeps: List[SweepEvent] = []
        self._current_score: int = 0
        self._classification: str = SWEEP_WEAK

    def analyze(
        self,
        candles: List[Dict],
        current_price: float,
        pdh: Optional[float] = None,
        pdl: Optional[float] = None,
        weekly_high: Optional[float] = None,
        weekly_low: Optional[float] = None,
        asian_high: Optional[float] = None,
        asian_low: Optional[float] = None,
        session: str = '',
    ) -> Dict[str, Any]:
        """Run full sweep analysis on candle data."""
        if not candles or len(candles) < 5:
            return {'score': 0, 'classification': SWEEP_WEAK, 'events': []}

        events = []
        atr = self._estimate_atr(candles)
        avg_volume = self._avg_volume(candles)

        # Detect sweeps at each level type
        for level_type in self.LEVEL_TYPES:
            level_price = self._get_level_price(
                level_type, candles, current_price,
                pdh, pdl, weekly_high, weekly_low,
                asian_high, asian_low, session,
            )
            if level_price is None:
                continue

            event = self._detect_sweep_at_level(
                candles, current_price, level_price,
                level_type, atr, avg_volume,
            )
            if event and event.score > 0:
                events.append(event)

        # Compute aggregate score
        if events:
            raw_score = sum(e.score for e in events) / max(len(events), 1)
            boost = min(len(events) * 5, 20)
            self._current_score = min(100, int(raw_score + boost))
        else:
            self._current_score = 0

        self._classification = self._classify(self._current_score)
        self._sweeps = events

        return {
            'score': self._current_score,
            'classification': self._classification,
            'events': [e.to_dict() for e in events],
            'event_count': len(events),
        }

    def _get_level_price(
        self,
        level_type: str,
        candles: List[Dict],
        current_price: float,
        pdh: Optional[float],
        pdl: Optional[float],
        weekly_high: Optional[float],
        weekly_low: Optional[float],
        asian_high: Optional[float],
        asian_low: Optional[float],
        session: str,
    ) -> Optional[float]:
        try:
            if level_type == 'EQUAL_HIGH':
                return self._find_equal_high(candles)
            elif level_type == 'EQUAL_LOW':
                return self._find_equal_low(candles)
            elif level_type == 'PDH':
                return pdh
            elif level_type == 'PDL':
                return pdl
            elif level_type == 'WEEKLY_HIGH':
                return weekly_high
            elif level_type == 'WEEKLY_LOW':
                return weekly_low
            elif level_type == 'ASIAN_HIGH':
                return asian_high
            elif level_type == 'ASIAN_LOW':
                return asian_low
            elif level_type == 'SESSION_GRAB':
                return self._detect_session_grab(candles, session)
        except Exception:
            pass
        return None

    def _find_equal_high(self, candles: List[Dict]) -> Optional[float]:
        highs = [c.get('high', 0) for c in candles[-30:] if 'high' in c]
        if len(highs) < 5:
            return None
        freq = {}
        for h in highs:
            rounded = round(h, 1)
            freq[rounded] = freq.get(rounded, 0) + 1
        for h, count in sorted(freq.items(), key=lambda x: -x[1]):
            if count >= 3:
                return h
        return None

    def _find_equal_low(self, candles: List[Dict]) -> Optional[float]:
        lows = [c.get('low', 0) for c in candles[-30:] if 'low' in c]
        if len(lows) < 5:
            return None
        freq = {}
        for l in lows:
            rounded = round(l, 1)
            freq[rounded] = freq.get(rounded, 0) + 1
        for l, count in sorted(freq.items(), key=lambda x: -x[1]):
            if count >= 3:
                return l
        return None

    def _detect_session_grab(self, candles: List[Dict], session: str) -> Optional[float]:
        if not session or len(candles) < 5:
            return None
        recent = candles[-5:]
        if session.upper() in ('LONDON', 'NY'):
            grab_high = max(c['high'] for c in recent if 'high' in c)
            grab_low = min(c['low'] for c in recent if 'low' in c)
            return grab_high if grab_high > 0 else grab_low
        return None

    def _detect_sweep_at_level(
        self,
        candles: List[Dict],
        current_price: float,
        level_price: float,
        level_type: str,
        atr: float,
        avg_volume: float,
    ) -> Optional[SweepEvent]:
        if atr <= 0:
            return None

        recent = candles[-5:] if len(candles) >= 5 else candles
        pre = candles[-10:-5] if len(candles) >= 10 else candles[:5]

        try:
            pre_highs = [c.get('high', 0) for c in pre if 'high' in c]
            pre_lows = [c.get('low', 0) for c in pre if 'low' in c]
            recent_highs = [c.get('high', 0) for c in recent if 'high' in c]
            recent_lows = [c.get('low', 0) for c in recent if 'low' in c]
            recent_volumes = [c.get('volume', 0) for c in recent if 'volume' in c]
            pre_volumes = [c.get('volume', 0) for c in pre if 'volume' in c]

            if not recent_highs or not recent_lows:
                return None

            # Check if price swept through the level
            max_recent = max(recent_highs)
            min_recent = min(recent_lows)
            swept_above = max_recent > level_price and level_price > max(pre_highs or [0])
            swept_below = min_recent < level_price and level_price < min(pre_lows or [float('inf')])

            if not swept_above and not swept_below:
                return None

            # Sweep depth (% of ATR)
            sweep_distance = abs(current_price - level_price)
            depth_pct = min(sweep_distance / max(atr, 0.01), 1.0)

            # Velocity (candles to sweep)
            pre_max = max(pre_highs) if pre_highs else 0
            pre_min = min(pre_lows) if pre_lows else float('inf')
            if swept_above:
                velocity = (max_recent - pre_max) / max(len(recent), 1)
            else:
                velocity = (pre_min - min_recent) / max(len(recent), 1)
            velocity = max(velocity / max(atr, 0.01), 0)

            # Volume spike
            avg_recent_vol = sum(recent_volumes) / max(len(recent_volumes), 1)
            avg_pre_vol = sum(pre_volumes) / max(len(pre_volumes), 1)
            volume_spike = avg_recent_vol / max(avg_pre_vol, 1) if avg_pre_vol > 0 else 1.0
            volume_spike = min(volume_spike, 3.0)

            # Displacement strength
            body_sizes = [abs(c.get('close', 0) - c.get('open', 0)) for c in recent if 'close' in c]
            avg_body = sum(body_sizes) / max(len(body_sizes), 1)
            displacement_strength = min(avg_body / max(atr * 0.3, 0.01), 1.0)

            # FVG creation
            fvg_created = self._check_fvg_creation(recent)

            # Rejection speed (wick length after sweep)
            rejection_speed = 0.0
            if swept_above and recent_lows:
                last_close = recent[-1].get('close', 0) if recent else 0
                rejection_speed = max(0, (max_recent - last_close) / max(atr, 0.01))
            elif swept_below and recent_highs:
                last_close = recent[-1].get('close', 0) if recent else 0
                rejection_speed = max(0, (last_close - min_recent) / max(atr, 0.01))
            rejection_speed = min(rejection_speed, 1.0)

            # Time-of-day importance
            hour = datetime.now(timezone.utc).hour
            if 7 <= hour <= 10 or 13 <= hour <= 16:
                time_importance = 1.0
            elif 6 <= hour < 7 or 12 <= hour < 13:
                time_importance = 0.7
            else:
                time_importance = 0.3

            # Institutional footprint (volume + velocity + depth combo)
            inst_score = (volume_spike / 3.0) * 0.4 + velocity * 0.3 + depth_pct * 0.3
            institutional_footprint = min(inst_score, 1.0)

            # Composite score
            score = (
                depth_pct * 20 +
                velocity * 20 +
                (volume_spike / 3.0) * 15 +
                displacement_strength * 15 +
                (1.0 if fvg_created else 0) * 10 +
                rejection_speed * 10 +
                time_importance * 5 +
                institutional_footprint * 5
            )
            score = min(score, 100)

            return SweepEvent(
                level_type=level_type,
                price=level_price,
                depth_pct=round(depth_pct, 3),
                velocity=round(velocity, 3),
                volume_spike=round(volume_spike, 2),
                displacement_strength=round(displacement_strength, 3),
                fvg_created=fvg_created,
                rejection_speed=round(rejection_speed, 3),
                time_importance=round(time_importance, 2),
                institutional_footprint=round(institutional_footprint, 3),
                score=round(score, 1),
            )

        except Exception:
            return None

    def _check_fvg_creation(self, candles: List[Dict]) -> bool:
        if len(candles) < 3:
            return False
        try:
            c1 = candles[-3]
            c2 = candles[-2]
            c3 = candles[-1]
            gap = max(c1['low'], c3['low']) - min(c1['high'], c3['high'])
            return gap > 0
        except Exception:
            return False

    def _estimate_atr(self, candles: List[Dict], period: int = 14) -> float:
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

    def _avg_volume(self, candles: List[Dict], period: int = 20) -> float:
        volumes = [c.get('volume', 0) for c in candles[-period:] if 'volume' in c]
        return sum(volumes) / max(len(volumes), 1) if volumes else 1.0

    @staticmethod
    def _classify(score: int) -> str:
        if score >= 80:
            return SWEEP_INSTITUTIONAL
        elif score >= 60:
            return SWEEP_STRONG
        elif score >= 35:
            return SWEEP_AVERAGE
        return SWEEP_WEAK


_sweep: Optional[LiquiditySweepIntelligence] = None


def get_sweep_intelligence() -> LiquiditySweepIntelligence:
    global _sweep
    if _sweep is None:
        _sweep = LiquiditySweepIntelligence()
    return _sweep


if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    if '--test' in sys.argv:
        si = get_sweep_intelligence()
        test_candles = [{'high': 100 + i, 'low': 99 + i * 0.5, 'close': 99.5 + i * 0.6, 'open': 99 + i * 0.5, 'volume': 100 + i * 10} for i in range(20)]
        result = si.analyze(test_candles, 110, pdh=105, pdl=95)
        print(f"Sweep score: {result['score']} ({result['classification']})")
        print(f"Events: {result['event_count']}")
        print("LiquiditySweepIntelligence OK")
