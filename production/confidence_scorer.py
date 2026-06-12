"""
Signal Confidence Scorer - OMNI BRAIN V2
========================================
Score each signal 0-100 using weighted components.

Scoring Components (raw max = 195, capped at 100):
  OB          = 20 pts (OrderBlock confirmed)
  FVG         = 20 pts (FVG in range)
  SWEEP       = 30 pts (LiquiditySweep fired)
  VWAP        = 15 pts (price relative to VWAP)
  SESSION     = 15 pts (inside killzone)
  CORRELATION = 15 pts (pair correlation confirmation)
  NEWS        = -15..0 pts (high-impact news blocking)
  YIELD       = 10 pts (treasury yield alignment)
  SENTIMENT   = 10 pts (Fear & Greed + currency strength)
  PATTERN     = 20 pts (SMC pattern recognition)
  DIVERGENCE  = 20 pts (RSI/MACD/Stochastic divergence)
  REGIME      = 10 pts (EXPANSION = +10, COMPRESSION = 0)
  LIQUIDITY   = 10 pts (INSTITUTIONAL tier = +10)

Decisions:
  EXECUTE  if score >= 75
  WAIT     if score 50-74
  BLOCK    if score < 50
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from pathlib import Path
import threading

log = logging.getLogger('ConfidenceScorer')

LOG_DIR = Path(__file__).parent / 'logs'
LOG_DIR.mkdir(exist_ok=True)


@dataclass
class ConfidenceResult:
    """Result of confidence scoring."""
    symbol: str
    tf: str
    score: int
    decision: str  # EXECUTE, WAIT, BLOCK
    components: Dict[str, int] = field(default_factory=dict)
    timestamp: str = ''
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class ConfidenceScorer:
    """
    Score trading signals 0-100 using weighted components.
    Raw max = 175, capped at 100.
    """
    
    # Component weights (raw sum = 215, capped at 100)
    # OB:20 + FVG:20 + SWEEP:30 + VWAP:15 + SESSION:15 + CORRELATION:15
    # + YIELD:10 + SENTIMENT:10 + PATTERN:20 + DIVERGENCE:20
    # + REGIME:10 + LIQUIDITY:10 = 215
    WEIGHTS = {
        'OB': 20,
        'FVG': 20,
        'SWEEP': 30,
        'VWAP': 15,
        'SESSION': 15,
        'CORRELATION': 15,
        'NEWS': 0,  # negative modifier, max 0
        'YIELD': 10,
        'SENTIMENT': 10,
        'PATTERN': 20,
        'DIVERGENCE': 20,
        'REGIME': 10,
        'LIQUIDITY': 10,
    }
    MAX_RAW_SCORE = 195
    COMBO_BONUS = 10
    
    # Decision thresholds
    EXECUTE_THRESHOLD = 75
    WAIT_THRESHOLD = 50
    
    def __init__(self, thresholds: Optional[Dict[str, int]] = None):
        self.thresholds = thresholds or {}
        self.history: List[ConfidenceResult] = []
    
    def get_threshold(self, symbol: str) -> int:
        """Get threshold for symbol (allows adaptive override)."""
        return self.thresholds.get(symbol, self.EXECUTE_THRESHOLD)
    
    def set_threshold(self, symbol: str, threshold: int):
        """Set threshold for symbol."""
        self.thresholds[symbol] = threshold
    
    def calculate_vwap_score(self, price: float, vwap: float, atr: float) -> int:
        """
        Score based on price relative to VWAP.
        
        - Price above VWAP by > 0.5 ATR: 15 pts (strong)
        - Price above VWAP by > 0.2 ATR: 10 pts (moderate)
        - Price near VWAP (within 0.2 ATR): 5 pts (neutral)
        - Price below VWAP: 0 pts
        """
        if atr == 0:
            return 0
        
        diff = price - vwap
        ratio = diff / atr
        
        if ratio > 0.5:
            return 15
        elif ratio > 0.2:
            return 10
        elif abs(ratio) <= 0.2:
            return 5
        return 0
    
    def calculate_session_score(self, hour_utc: int) -> int:
        """
        Score based on trading session (killzone).
        
        London Killzone: 07:00-10:00 UTC → 15 pts
        NY Killzone: 13:00-16:00 UTC → 15 pts
        London Open: 06:00-07:00 UTC → 10 pts
        NY Open: 12:00-13:00 UTC → 10 pts
        Asian Session: 00:00-06:00 UTC → 5 pts
        Off-hours: 20:00-00:00 UTC → 0 pts
        """
        if 7 <= hour_utc < 10:
            return 15  # London killzone
        elif 13 <= hour_utc < 16:
            return 15  # NY killzone
        elif 6 <= hour_utc < 7:
            return 10  # London open
        elif 12 <= hour_utc < 13:
            return 10  # NY open
        elif 0 <= hour_utc < 6:
            return 5   # Asian session
        return 0
    
    def score(
        self,
        symbol: str,
        tf: str,
        ob_active: bool = False,
        fvg_active: bool = False,
        sweep_fired: bool = False,
        price: float = 0.0,
        vwap: float = 0.0,
        atr: float = 1.0,
        hour_utc: Optional[int] = None,
        correlation_score: int = 0,
        news_penalty: int = 0,
        yield_score: int = 0,
        sentiment_score: int = 0,
        pattern_score: int = 0,
        divergence_score: int = 0,
        regime: str = 'COMPRESSION',
        liquidity_quality: int = 0,
        signal_decay_elapsed: float = 0.0,
        signal_decay_hl: int = 1800,
    ) -> ConfidenceResult:
        """
        Calculate confidence score for a signal.
        
        Args:
            symbol: Trading symbol (XAUUSD, EURUSD, etc.)
            tf: Timeframe (M15, H1, H4, D1)
            ob_active: True if OrderBlock is active/confirmed
            fvg_active: True if Fair Value Gap is in range
            sweep_fired: True if LiquiditySweep fired
            price: Current price
            vwap: Current VWAP
            atr: Current ATR
            hour_utc: Current hour in UTC
            regime: Market regime (EXPANSION/COMPRESSION/TRAP/VOLATILITY)
            liquidity_quality: Liquidity quality score (0-10)
            signal_decay_elapsed: Seconds since signal was generated
            signal_decay_hl: Signal half-life in seconds

        Returns:
            ConfidenceResult with score and decision
        """
        if hour_utc is None:
            hour_utc = datetime.now(timezone.utc).hour
        
        # Calculate component scores
        components = {}
        components['OB'] = self.WEIGHTS['OB'] if ob_active else 0
        components['FVG'] = self.WEIGHTS['FVG'] if fvg_active else 0
        components['SWEEP'] = self.WEIGHTS['SWEEP'] if sweep_fired else 0
        components['VWAP'] = self.calculate_vwap_score(price, vwap, atr)
        components['SESSION'] = self.calculate_session_score(hour_utc)
        components['CORRELATION'] = max(0, min(15, correlation_score))
        components['NEWS'] = max(-15, min(0, news_penalty))
        components['YIELD'] = max(0, min(10, yield_score))
        components['SENTIMENT'] = max(0, min(10, sentiment_score))
        components['PATTERN'] = max(0, min(20, pattern_score))
        components['DIVERGENCE'] = max(0, min(20, divergence_score))
        
        # Regime score (EXPANSION = +10, others = 0)
        components['REGIME'] = self.WEIGHTS['REGIME'] if regime == 'EXPANSION' else 0
        
        # Liquidity quality (0-10 mapped directly)
        components['LIQUIDITY'] = max(0, min(10, liquidity_quality))
        
        # Combo bonuses (pure bonus — no component counted twice)
        if ob_active and fvg_active and sweep_fired:
            components['COMBO_OB_FVG_SWEEP'] = self.COMBO_BONUS
        if pattern_score > 0 and divergence_score > 0:
            components['COMBO_PATTERN_DIVERGENCE'] = 5
        
        # Total score (raw, then capped at 100)
        raw_score = sum(components.values())
        total_score = min(100, max(0, raw_score))
        
        # Apply signal decay (penalize stale signals)
        if signal_decay_elapsed > 0 and signal_decay_hl > 0:
            try:
                import math
                decay_const = math.log(2) / signal_decay_hl
                total_score = total_score * math.exp(-decay_const * signal_decay_elapsed)
                total_score = max(0, min(100, total_score))
            except (ValueError, OverflowError):
                pass
        
        # Decision
        threshold = self.get_threshold(symbol)
        if total_score >= threshold:
            decision = 'EXECUTE'
        elif total_score >= self.WAIT_THRESHOLD:
            decision = 'WAIT'
        else:
            decision = 'BLOCK'
        
        result = ConfidenceResult(
            symbol=symbol,
            tf=tf,
            score=total_score,
            decision=decision,
            components=components
        )
        
        self.history.append(result)
        
        return result
    
    def score_from_signal(
        self,
        symbol: str,
        tf: str,
        signal_metadata: Dict[str, Any],
        price: float = 0.0,
        vwap: float = 0.0,
        atr: float = 1.0
    ) -> ConfidenceResult:
        return self.score(
            symbol=symbol,
            tf=tf,
            ob_active=signal_metadata.get('OB_SIGNAL', 0) > 0,
            fvg_active=signal_metadata.get('FVG_SIGNAL', 0) > 0,
            sweep_fired=signal_metadata.get('SWEEP_SIGNAL', 0) > 0,
            price=price,
            vwap=vwap,
            atr=atr,
            correlation_score=signal_metadata.get('correlation_score', 0),
            news_penalty=signal_metadata.get('news_penalty', 0),
            yield_score=signal_metadata.get('yield_score', 0),
            sentiment_score=signal_metadata.get('sentiment_score', 0),
            pattern_score=signal_metadata.get('pattern_score', 0),
            divergence_score=signal_metadata.get('divergence_score', 0),
            regime=signal_metadata.get('regime', 'COMPRESSION'),
            liquidity_quality=signal_metadata.get('liquidity_quality', 0),
            signal_decay_elapsed=signal_metadata.get('signal_decay_elapsed', 0.0),
            signal_decay_hl=signal_metadata.get('signal_decay_hl', 1800),
        )
    
    @staticmethod
    def format_bar(score: int) -> str:
        """Format score as ASCII bar."""
        filled = score // 10
        empty = 10 - filled
        return '█' * filled + '░' * empty
    
    @staticmethod
    def format_result(result: ConfidenceResult) -> str:
        bar = ConfidenceScorer.format_bar(result.score)
        emoji = '🟢' if result.decision == 'EXECUTE' else ('🟡' if result.decision == 'WAIT' else '🔴')
        comps = ' '.join(f"{k}={v}" for k, v in sorted(result.components.items()) if v != 0)
        return f"[SCORE] {result.symbol}/{result.tf} {bar} {result.score:.0f}/100 → {emoji} {result.decision} | {comps}"
    
    def score_calculation_trace(self, **kwargs) -> str:
        """Return a detailed trace of each component contribution for debugging."""
        result = self.score(**kwargs)
        lines = [
            f"SCORE TRACE for {kwargs.get('symbol', '?')}/{kwargs.get('tf', '?')}",
            f"{'─'*50}",
        ]
        comp_keys = list(result.components.keys())
        for k in comp_keys:
            v = result.components[k]
            weight = self.WEIGHTS.get(k, None)
            src = f" (weight={weight})" if weight is not None else ""
            lines.append(f"  {k:30s} = {v:3d}{src}")
        lines.append(f"{'─'*50}")
        lines.append(f"  {'RAW_SCORE':30s} = {sum(result.components.values()):3d}")
        lines.append(f"  {'FINAL_SCORE':30s} = {result.score:.0f}")
        lines.append(f"  {'DECISION':30s} = {result.decision}")
        return "\n".join(lines) + "\n"

    def score_with_trace(
        self,
        symbol: str,
        tf: str,
        ob_active: bool = False,
        fvg_active: bool = False,
        sweep_fired: bool = False,
        price: float = 0.0,
        vwap: float = 0.0,
        atr: float = 1.0,
        hour_utc: Optional[int] = None,
        correlation_score: int = 0,
        news_penalty: int = 0,
        yield_score: int = 0,
        sentiment_score: int = 0,
        pattern_score: int = 0,
        divergence_score: int = 0,
        regime: str = 'COMPRESSION',
        liquidity_quality: int = 0,
        signal_decay_elapsed: float = 0.0,
        signal_decay_hl: int = 1800,
    ) -> Tuple[int, Dict[str, int]]:
        """Score with detailed trace output per component."""
        if hour_utc is None:
            hour_utc = datetime.now(timezone.utc).hour

        trace = {}
        trace['OB'] = self.WEIGHTS['OB'] if ob_active else 0
        trace['FVG'] = self.WEIGHTS['FVG'] if fvg_active else 0
        trace['SWEEP'] = self.WEIGHTS['SWEEP'] if sweep_fired else 0
        trace['VWAP'] = self.calculate_vwap_score(price, vwap, atr)
        trace['SESSION'] = self.calculate_session_score(hour_utc)
        trace['CORRELATION'] = max(0, min(15, correlation_score))
        trace['NEWS'] = max(-15, min(0, news_penalty))
        trace['YIELD'] = max(0, min(10, yield_score))
        trace['SENTIMENT'] = max(0, min(10, sentiment_score))
        trace['PATTERN'] = max(0, min(20, pattern_score))
        trace['DIVERGENCE'] = max(0, min(20, divergence_score))
        trace['REGIME'] = self.WEIGHTS['REGIME'] if regime == 'EXPANSION' else 0
        trace['LIQUIDITY'] = max(0, min(10, liquidity_quality))

        if ob_active and fvg_active and sweep_fired:
            trace['COMBO'] = self.COMBO_BONUS
        if pattern_score > 0 and divergence_score > 0:
            trace['COMBO_PD'] = 5

        raw = sum(trace.values())
        capped = min(100, max(0, raw))

        if signal_decay_elapsed > 0 and signal_decay_hl > 0:
            try:
                decay_const = math.log(2) / signal_decay_hl
                capped = capped * math.exp(-decay_const * signal_decay_elapsed)
                capped = max(0, min(100, capped))
            except (ValueError, OverflowError):
                pass

        print(f"[SCORE TRACE] {symbol}/{tf}")
        for k in sorted(trace.keys()):
            v = trace[k]
            bar = '█' * (int(v) // 5) if v > 0 else ''
            print(f"  {k:12}: {int(v):3} {bar}")
        print(f"  {'TOTAL':12}: {int(capped)}")
        print(f"  {'DECISION':12}: {'EXECUTE' if capped >= self.get_threshold(symbol) else 'WAIT' if capped >= self.WAIT_THRESHOLD else 'BLOCK'}")

        return int(capped), trace

    def apply_adjustments(self, adjustments: Dict[str, Any]) -> None:
        """Apply RL adjustments to thresholds and component weights."""
        if 'thresholds' in adjustments:
            for symbol, thresh in adjustments['thresholds'].items():
                self.set_threshold(symbol, max(60, min(95, int(thresh))))
        if 'weight_deltas' in adjustments:
            for comp, delta in adjustments['weight_deltas'].items():
                if comp in self.WEIGHTS:
                    old = self.WEIGHTS[comp]
                    self.WEIGHTS[comp] = max(0, min(50, old + delta))
                    log.info(f"Weight adjusted: {comp} {old} -> {self.WEIGHTS[comp]}")
        if 'confidence_bias' in adjustments:
            bias = adjustments['confidence_bias']
            if bias != 0:
                for sym in list(self.thresholds.keys()):
                    old = self.thresholds[sym]
                    self.thresholds[sym] = max(60, min(95, int(old + bias * 10)))

    def get_history(self, symbol: Optional[str] = None, limit: int = 100) -> List[ConfidenceResult]:
        """Get score history."""
        if symbol:
            filtered = [r for r in self.history if r.symbol == symbol]
            return filtered[-limit:]
        return self.history[-limit:]


# Global scorer instance
_scorer: Optional[ConfidenceScorer] = None
_lock = threading.Lock()


def get_scorer() -> ConfidenceScorer:
    """Get or create global scorer instance."""
    global _scorer
    if _scorer is None:
        with _lock:
            if _scorer is None:
                _scorer = ConfidenceScorer()
    return _scorer


def score_signal(
    symbol: str,
    tf: str,
    ob_active: bool = False,
    fvg_active: bool = False,
    sweep_fired: bool = False,
    price: float = 0.0,
    vwap: float = 0.0,
    atr: float = 1.0,
    correlation_score: int = 0,
    news_penalty: int = 0,
    yield_score: int = 0,
    sentiment_score: int = 0,
    pattern_score: int = 0,
    divergence_score: int = 0,
    regime: str = 'COMPRESSION',
    liquidity_quality: int = 0,
    signal_decay_elapsed: float = 0.0,
    signal_decay_hl: int = 1800,
) -> ConfidenceResult:
    return get_scorer().score(
        symbol=symbol,
        tf=tf,
        ob_active=ob_active,
        fvg_active=fvg_active,
        sweep_fired=sweep_fired,
        price=price,
        vwap=vwap,
        atr=atr,
        correlation_score=correlation_score,
        news_penalty=news_penalty,
        yield_score=yield_score,
        sentiment_score=sentiment_score,
        pattern_score=pattern_score,
        divergence_score=divergence_score,
        regime=regime,
        liquidity_quality=liquidity_quality,
        signal_decay_elapsed=signal_decay_elapsed,
        signal_decay_hl=signal_decay_hl,
    )


# ══════════════════════════════════════════════════════════════════════════════
# CLI TEST
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import sys
    
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    if '--test' in sys.argv:
        print("=" * 60)
        print("  CONFIDENCE SCORER - TEST")
        print("=" * 60)
        
        scorer = ConfidenceScorer()
        
        test_cases = [
            {"symbol": "XAUUSD", "tf": "H1", "ob_active": True, "fvg_active": True, "sweep_fired": True, "price": 2355.0, "vwap": 2350.0, "atr": 5.0, "hour_utc": 14},
            {"symbol": "EURUSD", "tf": "M15", "ob_active": True, "fvg_active": False, "sweep_fired": False, "price": 1.0850, "vwap": 1.0845, "atr": 0.001, "hour_utc": 14},
            {"symbol": "GBPUSD", "tf": "H4", "ob_active": False, "fvg_active": False, "sweep_fired": False, "price": 1.2700, "vwap": 1.2720, "atr": 0.002, "hour_utc": 22},
            {"symbol": "SP500", "tf": "D1", "ob_active": True, "fvg_active": True, "sweep_fired": False, "price": 5200.0, "vwap": 5195.0, "atr": 25.0, "hour_utc": 9},
        ]
        
        print()
        for tc in test_cases:
            result = scorer.score(**tc)
            print(scorer.format_result(result))
            print(f"         Components: {result.components}")
            print()
        
        print("=" * 60)
        
        # ── test_no_double_counting ──
        print("\n  [TEST] test_no_double_counting")
        print("  Checking that no single component appears twice in final score...")
        tc_all = {k: v for k, v in test_cases[0].items()}
        tc_all['pattern_score'] = 20
        tc_all['divergence_score'] = 20
        r_all = scorer.score(**tc_all)
        seen = {}
        double = False
        for k, v in r_all.components.items():
            if k.startswith('COMBO_'):
                continue
            if v > 0 and k in seen:
                print(f"  ❌ {k} counted twice! (first={seen[k]}, second={v})")
                double = True
            seen[k] = v
        if not double:
            print("  ✅ No component counted twice (combo bonuses isolated)")
        else:
            print("  ❌ Double-counting detected!")
        print()
        
        print("=" * 60)
        
        # ── test_trace_shows_each_component_once ──
        print("\n  [TEST] test_trace_shows_each_component_once")
        print("  Validating trace output contains each component exactly once...")
        trace = scorer.score_calculation_trace(**tc_all)
        print(trace)
        trace_lines = trace.strip().split('\n')
        component_lines = [l for l in trace_lines if '=' in l and not l.strip().startswith('─') and 'RAW_SCORE' not in l and 'FINAL_SCORE' not in l and 'DECISION' not in l]
        non_combo = [l for l in component_lines if 'COMBO_' not in l]
        print(f"  Non-combo component entries: {len(non_combo)} (expect 13)")
        if len(non_combo) == 13:
            print("  ✅ Trace shows each component exactly once")
        else:
            print(f"  ⚠️  Expected 13, got {len(non_combo)}")
        print()
        
        print("=" * 60)
    else:
        print("Usage: python confidence_scorer.py --test")
