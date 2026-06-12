"""
Pattern Recognition Engine - OMNI BRAIN V2
Detects SMC patterns: Breaker Block, Mitigation Block, Propulsion Block, etc.
"""
import logging, math
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

log = logging.getLogger('PatternEngine')

class PatternType(Enum):
    BREAKER_BLOCK = 'BreakerBlock'
    MITIGATION_BLOCK = 'MitigationBlock'
    PROPULSION_BLOCK = 'PropulsionBlock'
    REJECTION_BLOCK = 'RejectionBlock'
    EQUILIBRIUM = 'Equilibrium'
    INDUCEMENT = 'Inducement'

@dataclass
class PatternResult:
    symbol: str
    patterns: List[Dict] = field(default_factory=list)
    total_score: int = 0
    timestamp: str = ''

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

class PatternEngine:
    PATTERN_SCORES = {
        PatternType.BREAKER_BLOCK: 8,
        PatternType.MITIGATION_BLOCK: 6,
        PatternType.PROPULSION_BLOCK: 7,
        PatternType.REJECTION_BLOCK: 5,
        PatternType.EQUILIBRIUM: 5,
        PatternType.INDUCEMENT: 10,
    }
    
    def scan(self, symbol: str, candles: List[Dict], current_price: float) -> PatternResult:
        """
        Scan candles for SMC patterns.
        candles: list of dicts with open, high, low, close, volume
        """
        if not candles or len(candles) < 10:
            return PatternResult(symbol=symbol)
        
        patterns = []
        total = 0
        n = len(candles)
        last = candles[-1]
        prev = candles[-2] if n >= 2 else None
        prev2 = candles[-3] if n >= 3 else None
        
        # 1. Breaker Block: previous OB broken, now acting as support/resistance flip
        bb = self._detect_breaker_block(candles)
        if bb:
            patterns.append({'type': PatternType.BREAKER_BLOCK.value, 'score': self.PATTERN_SCORES[PatternType.BREAKER_BLOCK], 'detail': bb})
            total += self.PATTERN_SCORES[PatternType.BREAKER_BLOCK]
        
        # 2. Mitigation Block: OB partially mitigated, bounce at 50%
        mb = self._detect_mitigation_block(candles, current_price)
        if mb:
            patterns.append({'type': PatternType.MITIGATION_BLOCK.value, 'score': self.PATTERN_SCORES[PatternType.MITIGATION_BLOCK], 'detail': mb})
            total += self.PATTERN_SCORES[PatternType.MITIGATION_BLOCK]
        
        # 3. Propulsion Block: strong imbalance, no wicks
        pb = self._detect_propulsion_block(candles)
        if pb:
            patterns.append({'type': PatternType.PROPULSION_BLOCK.value, 'score': self.PATTERN_SCORES[PatternType.PROPULSION_BLOCK], 'detail': pb})
            total += self.PATTERN_SCORES[PatternType.PROPULSION_BLOCK]
        
        # 4. Rejection Block: long wick at key level
        rb = self._detect_rejection_block(candles)
        if rb:
            patterns.append({'type': PatternType.REJECTION_BLOCK.value, 'score': self.PATTERN_SCORES[PatternType.REJECTION_BLOCK], 'detail': rb})
            total += self.PATTERN_SCORES[PatternType.REJECTION_BLOCK]
        
        # 5. Equilibrium: price at 50% of recent range
        eq = self._detect_equilibrium(candles, current_price)
        if eq:
            patterns.append({'type': PatternType.EQUILIBRIUM.value, 'score': self.PATTERN_SCORES[PatternType.EQUILIBRIUM], 'detail': eq})
            total += self.PATTERN_SCORES[PatternType.EQUILIBRIUM]
        
        # 6. Inducement: small liquidity pool before major move
        idm = self._detect_inducement(candles)
        if idm:
            patterns.append({'type': PatternType.INDUCEMENT.value, 'score': self.PATTERN_SCORES[PatternType.INDUCEMENT], 'detail': idm})
            total += self.PATTERN_SCORES[PatternType.INDUCEMENT]
        
        # 7. Premium/Discount classification
        pd_status = self._classify_premium_discount(candles, current_price)
        
        return PatternResult(symbol=symbol, patterns=patterns, total_score=total)
    
    def _detect_breaker_block(self, candles: List[Dict]) -> Optional[str]:
        if len(candles) < 6:
            return None
        # Look for: OB formed, then price broke through, now returning
        recent = candles[-6:]
        mid_idx = len(recent) // 2
        left = recent[:mid_idx]
        right = recent[mid_idx:]
        left_range = sum(c['high'] - c['low'] for c in left) / len(left)
        right_range = sum(c['high'] - c['low'] for c in right) / len(right)
        if right_range > left_range * 1.5:
            return f"Breaker: volatility shift +{right_range/left_range:.1f}x"
        return None
    
    def _detect_mitigation_block(self, candles: List[Dict], price: float) -> Optional[str]:
        if len(candles) < 5:
            return None
        recent = candles[-5:]
        avg_body = sum(abs(c['close'] - c['open']) for c in recent) / len(recent)
        for c in recent:
            body = abs(c['close'] - c['open'])
            if body > avg_body * 1.5:
                mid = (c['high'] + c['low']) / 2
                if abs(price - mid) / (c['high'] - c['low'] + 0.001) < 0.15:
                    return f"Mitigation at {mid:.2f} (50% of {c['high']:.2f}-{c['low']:.2f})"
        return None
    
    def _detect_propulsion_block(self, candles: List[Dict]) -> Optional[str]:
        if len(candles) < 3:
            return None
        last = candles[-1]
        body = abs(last['close'] - last['open'])
        total_range = last['high'] - last['low']
        if total_range == 0:
            return None
        body_ratio = body / total_range
        upper_wick = last['high'] - max(last['close'], last['open'])
        lower_wick = min(last['close'], last['open']) - last['low']
        if body_ratio > 0.85 and upper_wick < total_range * 0.08 and lower_wick < total_range * 0.08:
            direction = 'BULLISH' if last['close'] > last['open'] else 'BEARISH'
            return f"Propulsion {direction} body {body_ratio:.0%}"
        return None
    
    def _detect_rejection_block(self, candles: List[Dict]) -> Optional[str]:
        if len(candles) < 3:
            return None
        recent = candles[-3:]
        for c in recent:
            total = c['high'] - c['low']
            if total == 0:
                continue
            body = abs(c['close'] - c['open'])
            upper = c['high'] - max(c['close'], c['open'])
            lower = min(c['close'], c['open']) - c['low']
            max_wick = max(upper, lower)
            if max_wick > body * 2 and max_wick > total * 0.6:
                side = 'TOP' if upper > lower else 'BOTTOM'
                return f"Rejection {side} wick {max_wick:.1f} ({(max_wick/total)*100:.0f}% of range)"
        return None
    
    def _detect_equilibrium(self, candles: List[Dict], price: float) -> Optional[str]:
        if len(candles) < 10:
            return None
        recent = candles[-10:]
        high = max(c['high'] for c in recent)
        low = min(c['low'] for c in recent)
        eq = (high + low) / 2
        range_pct = abs(price - eq) / (high - low + 0.001)
        if range_pct < 0.03:
            return f"EQ touch at {eq:.2f} (50% of {high:.2f}-{low:.2f})"
        return None
    
    def _detect_inducement(self, candles: List[Dict]) -> Optional[str]:
        if len(candles) < 5:
            return None
        recent = candles[-5:]
        highs = [c['high'] for c in recent]
        lows = [c['low'] for c in recent]
        if len(highs) >= 3:
            if highs[-1] > max(highs[:-1]) and abs(highs[-1] - max(highs[:-1])) < (sum(c['high']-c['low'] for c in recent)/len(recent))*0.5:
                return f"IDM sweep at {highs[-1]:.2f} (liquidity grab)"
        return None
    
    def _classify_premium_discount(self, candles: List[Dict], price: float) -> Dict:
        if len(candles) < 10:
            return {'zone': 'unknown', 'position': 0.5}
        high = max(c['high'] for c in candles[-10:])
        low = min(c['low'] for c in candles[-10:])
        range_total = high - low
        if range_total == 0:
            return {'zone': 'unknown', 'position': 0.5}
        position = (price - low) / range_total
        zone = 'premium' if position > 0.5 else 'discount'
        return {'zone': zone, 'position': round(position, 3)}
    
    def format_terminal(self, result: PatternResult) -> str:
        if not result.patterns:
            return f"[PATTERN] {result.symbol}: No pattern 0pts"
        parts = [f"[PATTERN] {result.symbol}: "]
        for p in result.patterns:
            parts.append(f"{p['type']}+{p['score']}")
        parts.append(f"={result.total_score}pts")
        return " ".join(parts)

# Global instance
_engine_pat: Optional[PatternEngine] = None
def get_pattern_engine() -> PatternEngine:
    global _engine_pat
    if _engine_pat is None:
        _engine_pat = PatternEngine()
    return _engine_pat
