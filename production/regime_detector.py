"""
Regime Detection Engine - Market Environment Classifier
========================================================
Classifies current market into EXPANSION, COMPRESSION, TRAP, or VOLATILITY
using rolling ATR and standard deviation channels.

Integration:
  regime = RegimeDetector().classify(candles)
  scorer.score(..., regime=regime, ...)
"""

import logging
import math
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

log = logging.getLogger('RegimeDetector')

EXPANSION = 'EXPANSION'
COMPRESSION = 'COMPRESSION'
TRAP = 'TRAP'
VOLATILITY = 'VOLATILITY'

REGIME_HALF_LIFE_MINS = {
    EXPANSION: 30,
    COMPRESSION: 60,
    TRAP: 15,
    VOLATILITY: 10,
}

REGIME_RISK_MULTIPLIERS = {
    EXPANSION: 0.8,
    COMPRESSION: 0.4,
    TRAP: 0.6,
    VOLATILITY: 0.0,
}


class RegimeDetector:
    """Classify market regime using ATR velocity + std deviation channels."""

    def __init__(self):
        self._last_regime: Optional[str] = None
        self._last_metrics: Dict[str, float] = {}

    def classify(self, candles: List[Dict], atr: float = None) -> str:
        """
        Classify the current market regime.

        Uses rolling std deviation of returns and ATR velocity.
        Returns one of: EXPANSION, COMPRESSION, TRAP, VOLATILITY.
        """
        if not candles or len(candles) < 20:
            return COMPRESSION  # Default safe

        try:
            closes = [c.get('close', 0) for c in candles if 'close' in c]
            highs = [c.get('high', 0) for c in candles if 'high' in c]
            lows = [c.get('low', 0) for c in candles if 'low' in c]

            if len(closes) < 20:
                return COMPRESSION

            # Rolling returns (log)
            returns = []
            for i in range(1, len(closes)):
                if closes[i - 1] > 0:
                    returns.append(math.log(closes[i] / closes[i - 1]))

            # Std dev of returns (volatility channel)
            n = len(returns)
            mean_ret = sum(returns) / n
            variance = sum((r - mean_ret) ** 2 for r in returns) / n
            std_dev = math.sqrt(variance) if variance > 0 else 1e-10

            # Recent subset (last 5 candles)
            recent_n = min(5, len(returns))
            recent_returns = returns[-recent_n:]
            recent_mean = sum(recent_returns) / recent_n
            recent_var = sum((r - recent_mean) ** 2 for r in recent_returns) / recent_n
            recent_std = math.sqrt(recent_var) if recent_var > 0 else 1e-10

            # Range / ATR analysis
            ranges = [h - l for h, l in zip(highs[-20:], lows[-20:])]
            avg_range = sum(ranges) / max(len(ranges), 1)
            recent_ranges = ranges[-5:] if len(ranges) >= 5 else ranges
            avg_recent_range = sum(recent_ranges) / max(len(recent_ranges), 1)

            range_ratio = avg_recent_range / max(avg_range, 1e-10)
            std_ratio = recent_std / max(std_dev, 1e-10)

            # Detect trap: sweep + immediate rejection (wick pattern)
            trap_score = self._detect_trap(candles[-10:] if len(candles) >= 10 else candles)

            self._last_metrics = {
                'std_dev': std_dev,
                'recent_std': recent_std,
                'std_ratio': std_ratio,
                'avg_range': avg_range,
                'avg_recent_range': avg_recent_range,
                'range_ratio': range_ratio,
                'trap_score': trap_score,
            }

            # Decision tree
            if trap_score >= 0.6:
                regime = TRAP
            elif range_ratio >= 1.5 and std_ratio >= 1.5:
                regime = EXPANSION
            elif range_ratio <= 0.6 and std_ratio <= 0.7:
                regime = COMPRESSION
            elif range_ratio >= 1.3 and std_ratio <= 0.8:
                regime = VOLATILITY
            elif range_ratio >= 1.8:
                regime = EXPANSION
            elif std_ratio >= 1.8:
                regime = VOLATILITY
            else:
                regime = COMPRESSION

            self._last_regime = regime
            return regime

        except Exception as e:
            log.debug(f"Regime classification failed: {e}")
            return COMPRESSION

    def _detect_trap(self, candles: List[Dict]) -> float:
        """
        Detect liquidity trap: sweep of a level followed by immediate rejection.
        Returns score 0.0-1.0.
        """
        if len(candles) < 5:
            return 0.0

        try:
            trap_count = 0
            checks = max(1, len(candles) - 2)

            for i in range(2, len(candles)):
                prev = candles[i - 1]
                curr = candles[i]
                prev2 = candles[i - 2] if i >= 2 else prev

                if not all(k in c for c in (prev, curr, prev2) for k in ('high', 'low', 'close')):
                    continue

                prev_range = prev['high'] - prev['low']
                if prev_range == 0:
                    continue

                # Bull trap: high above prev high, close near low
                if curr['high'] > prev['high'] and curr['close'] <= curr['low'] + prev_range * 0.3:
                    trap_count += 1
                # Bear trap: low below prev low, close near high
                elif curr['low'] < prev['low'] and curr['close'] >= curr['high'] - prev_range * 0.3:
                    trap_count += 1

            return min(trap_count / max(checks, 1), 1.0)

        except Exception:
            return 0.0

    def get_half_life_mins(self, regime: Optional[str] = None) -> int:
        """Get signal half-life in minutes for the given regime."""
        r = regime or self._last_regime or COMPRESSION
        return REGIME_HALF_LIFE_MINS.get(r, 30)

    def get_risk_multiplier(self, regime: Optional[str] = None) -> float:
        """Get position sizing risk multiplier for the given regime."""
        r = regime or self._last_regime or COMPRESSION
        return REGIME_RISK_MULTIPLIERS.get(r, 0.5)

    def get_metrics(self) -> Dict[str, Any]:
        """Return latest classification metrics."""
        return {
            'regime': self._last_regime or COMPRESSION,
            'half_life_mins': self.get_half_life_mins(),
            'risk_multiplier': self.get_risk_multiplier(),
            'std_ratio': self._last_metrics.get('std_ratio', 0),
            'range_ratio': self._last_metrics.get('range_ratio', 0),
            'trap_score': self._last_metrics.get('trap_score', 0),
        }


# ══════════════════════════════════════════════════════════════════════════════
# SIGNAL DECAY TIMER
# ══════════════════════════════════════════════════════════════════════════════

def compute_signal_decay(
    initial_score: float,
    elapsed_seconds: float,
    half_life_seconds: int = 1800,
) -> float:
    """
    Exponential half-life decay for signal validity.

    Score_decayed = Score_initial * e^(-λ * t)
    where λ = ln(2) / T_half_life

    Args:
        initial_score: Original confidence score (0-100)
        elapsed_seconds: Time since signal generated
        half_life_seconds: Configurable half-life (default 30min)

    Returns:
        Decayed score (clamped 0-100)
    """
    if half_life_seconds <= 0 or elapsed_seconds <= 0:
        return max(0, min(100, initial_score))

    try:
        decay_constant = math.log(2) / half_life_seconds
        decayed = initial_score * math.exp(-decay_constant * elapsed_seconds)
        return max(0, min(100, decayed))
    except (ValueError, OverflowError):
        return max(0, min(100, initial_score))


def get_signal_strength_pct(decayed_score: float, initial_score: float) -> str:
    """Format signal strength as percentage string."""
    if initial_score <= 0:
        return '0%'
    pct = (decayed_score / initial_score) * 100
    return f'{pct:.0f}%'


# ══════════════════════════════════════════════════════════════════════════════
# LIQUIDITY QUALITY SCORING
# ══════════════════════════════════════════════════════════════════════════════

LIQUIDITY_TIERS = {
    'ASIAN': 1,
    'PDH_PDL': 2,
    'PWH_PWL': 3,
    'CLUSTER': 4,
}


def score_liquidity_quality(
    current_price: float,
    candles: List[Dict],
    asian_high: Optional[float] = None,
    asian_low: Optional[float] = None,
    pdh: Optional[float] = None,
    pdl: Optional[float] = None,
    pwh: Optional[float] = None,
    pwl: Optional[float] = None,
) -> int:
    """
    Score and tier liquidity pools based on proximity.

    Tier scoring:
      Asian Session H/L        → +1  each
      PDH / PDL                → +2  each
      PWH / PWL                → +3  each
      Multi-TF cluster (3+)    → +4

    Returns cumulative score (0-10).
    """
    if not candles or current_price <= 0:
        return 0

    try:
        score = 0
        proximity_threshold = 0.001  # 0.1% price proximity

        # Compute prices if not provided
        if asian_high is None or asian_low is None:
            asian_h, asian_l = _compute_high_low(candles, 8)
            asian_high = asian_high or asian_h
            asian_low = asian_low or asian_l

        if pdh is None or pdl is None:
            pd_h, pd_l = _compute_high_low(candles[-24:], 0)
            pdh = pdh or pd_h
            pdl = pdl or pd_l

        if pwh is None or pwl is None:
            pw_h, pw_l = _compute_high_low(candles[-120:], 0)
            pwh = pwh or pw_h
            pwl = pwl or pw_l

        # Asian session proximity
        if asian_high and abs(current_price - asian_high) / max(current_price, 1) <= proximity_threshold:
            score += LIQUIDITY_TIERS['ASIAN']
        if asian_low and abs(current_price - asian_low) / max(current_price, 1) <= proximity_threshold:
            score += LIQUIDITY_TIERS['ASIAN']

        # PDH/PDL proximity
        if pdh and abs(current_price - pdh) / max(current_price, 1) <= proximity_threshold:
            score += LIQUIDITY_TIERS['PDH_PDL']
        if pdl and abs(current_price - pdl) / max(current_price, 1) <= proximity_threshold:
            score += LIQUIDITY_TIERS['PDH_PDL']

        # PWH/PWL proximity
        if pwh and abs(current_price - pwh) / max(current_price, 1) <= proximity_threshold:
            score += LIQUIDITY_TIERS['PWH_PWL']
        if pwl and abs(current_price - pwl) / max(current_price, 1) <= proximity_threshold:
            score += LIQUIDITY_TIERS['PWH_PWL']

        # Cluster bonus: 3+ liquidity levels within proximity
        levels_near = 0
        for level in [asian_high, asian_low, pdh, pdl, pwh, pwl]:
            if level and abs(current_price - level) / max(current_price, 1) <= proximity_threshold:
                levels_near += 1
        if levels_near >= 3:
            score += LIQUIDITY_TIERS['CLUSTER']

        return min(score, 10)

    except Exception as e:
        log.debug(f"Liquidity scoring failed: {e}")
        return 0


def _compute_high_low(candles: List[Dict], lookback: int = 0) -> tuple:
    """Compute highest high and lowest low over a candle window."""
    if not candles:
        return None, None
    try:
        segment = candles[-lookback:] if lookback > 0 else candles
        highs = [c.get('high', 0) for c in segment if 'high' in c]
        lows = [c.get('low', 0) for c in segment if 'low' in c]
        if highs and lows:
            return max(highs), min(lows)
        return None, None
    except Exception:
        return None, None


def get_liquidity_tier_label(quality_score: int) -> str:
    """Get human-readable tier label."""
    if quality_score >= 8:
        return 'INSTITUTIONAL'
    elif quality_score >= 5:
        return 'HIGH'
    elif quality_score >= 3:
        return 'MODERATE'
    return 'LOW'


# ══════════════════════════════════════════════════════════════════════════════
# GLOBAL INSTANCE
# ══════════════════════════════════════════════════════════════════════════════

_detector: Optional[RegimeDetector] = None


def get_regime_detector() -> RegimeDetector:
    global _detector
    if _detector is None:
        _detector = RegimeDetector()
    return _detector


if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.INFO, format='%(message)s')

    if '--test' in sys.argv:
        rd = get_regime_detector()
        test_candles = [
            {'high': 100 + i * 0.5, 'low': 99 + i * 0.3, 'close': 99.5 + i * 0.4}
            for i in range(50)
        ]
        regime = rd.classify(test_candles)
        print(f"Regime: {regime}")
        print(f"Metrics: {rd.get_metrics()}")

        # Decay test
        decayed = compute_signal_decay(85, 900, 1800)
        print(f"Score 85 after 15min (HL 30min): {decayed:.1f}")

        decayed2 = compute_signal_decay(85, 3600, 1800)
        print(f"Score 85 after 60min (HL 30min): {decayed2:.1f}")

        # Liquidity quality test
        liq_score = score_liquidity_quality(
            100.5, test_candles,
            asian_high=100.5, asian_low=99.0,
            pdh=101.0, pdl=99.5,
        )
        print(f"Liquidity quality: {liq_score} ({get_liquidity_tier_label(liq_score)})")

        print("RegimeDetector OK")
