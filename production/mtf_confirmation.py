"""
Multi-Timeframe Confirmation - OMNI BRAIN V2
=============================================
Confirmation chain for signal validation.

Confirmation Rules:
  M15 signal → confirmed by H1 bias
  H1 signal  → confirmed by H4 structure
  H4 signal  → confirmed by D1 trend

Bias Detection:
  BULLISH if price > VWAP + last OB above price
  BEARISH if price < VWAP + last OB below price
  NEUTRAL if no clear structure
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger('MTFConfirmation')

LOG_DIR = Path(__file__).parent / 'logs'
LOG_DIR.mkdir(exist_ok=True)

TIMEFRAMES = ['M15', 'H1', 'H4', 'D1']

# Confirmation chain: entry_tf → required confirming TF
CONFIRMATION_CHAIN = {
    'M15': ['H1', 'H4', 'D1'],
    'H1': ['H4', 'D1'],
    'H4': ['D1'],
    'D1': []
}


@dataclass
class BiasResult:
    """Bias detection result for a timeframe."""
    tf: str
    bias: str  # BULLISH, BEARISH, NEUTRAL
    price: float
    vwap: float
    ob_level: Optional[float] = None


@dataclass
class MTFResult:
    """Multi-timeframe confirmation result."""
    symbol: str
    entry_tf: str
    biases: Dict[str, str] = field(default_factory=dict)
    confirmed: bool = False
    block_reason: Optional[str] = None
    timestamp: str = ''
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class MTFConfirmation:
    """
    Multi-timeframe confirmation engine.
    
    Validates signals against higher timeframe bias.
    """
    
    def __init__(self):
        self.cache: Dict[str, MTFResult] = {}
    
    def detect_bias(
        self,
        price: float,
        vwap: float,
        ob_high: Optional[float] = None,
        ob_low: Optional[float] = None
    ) -> str:
        """
        Detect bias for a single timeframe.
        
        Rules:
          BULLISH: price > VWAP and (no OB or OB above price)
          BEARISH: price < VWAP and (no OB or OB below price)
          NEUTRAL: conflicting or no clear structure
        """
        # No VWAP data
        if vwap == 0:
            return 'NEUTRAL'
        
        price_above_vwap = price > vwap
        price_below_vwap = price < vwap
        
        # Check OB confirmation
        ob_bullish = ob_high is not None and price < ob_high
        ob_bearish = ob_low is not None and price > ob_low
        
        if price_above_vwap:
            if ob_high is None or ob_bullish:
                return 'BULLISH'
        elif price_below_vwap:
            if ob_low is None or ob_bearish:
                return 'BEARISH'
        
        return 'NEUTRAL'
    
    def check_confirmation(
        self,
        symbol: str,
        entry_tf: str,
        entry_bias: str,
        tf_data: Dict[str, Dict[str, Any]]
    ) -> MTFResult:
        """
        Check multi-timeframe confirmation.
        
        Args:
            symbol: Trading symbol
            entry_tf: Entry timeframe (M15, H1, H4)
            entry_bias: Bias on entry timeframe (BULLISH, BEARISH)
            tf_data: Dict of {tf: {price, vwap, ob_high, ob_low}}
            
        Returns:
            MTFResult with confirmation status
        """
        result = MTFResult(
            symbol=symbol,
            entry_tf=entry_tf,
            biases={entry_tf: entry_bias}
        )
        
        # Get required confirming timeframes
        confirming_tfs = CONFIRMATION_CHAIN.get(entry_tf, [])
        
        if not confirming_tfs:
            # D1 has no higher TF to confirm
            result.confirmed = True
            return result
        
        # Check each confirming TF
        for tf in confirming_tfs:
            if tf not in tf_data:
                result.biases[tf] = 'NEUTRAL'
                continue
            
            data = tf_data[tf]
            bias = self.detect_bias(
                price=data.get('price', 0),
                vwap=data.get('vwap', 0),
                ob_high=data.get('ob_high'),
                ob_low=data.get('ob_low')
            )
            result.biases[tf] = bias
        
        # Check for conflicts
        entry_direction = 'BULL' if entry_bias == 'BULLISH' else ('BEAR' if entry_bias == 'BEARISH' else None)
        
        if entry_direction is None:
            result.confirmed = False
            result.block_reason = "No clear entry bias"
            return result
        
        for tf in confirming_tfs:
            higher_bias = result.biases.get(tf, 'NEUTRAL')
            
            if higher_bias == 'NEUTRAL':
                continue  # Neutral allows trade
            
            higher_direction = 'BULL' if higher_bias == 'BULLISH' else 'BEAR'
            
            if higher_direction != entry_direction:
                result.confirmed = False
                result.block_reason = f"{tf} conflict ({higher_bias} vs {entry_bias})"
                return result
        
        result.confirmed = True
        return result
    
    def check_signal(
        self,
        symbol: str,
        entry_tf: str,
        entry_bias: str,
        tf_data: Dict[str, Dict[str, Any]]
    ) -> MTFResult:
        """Check and cache MTF confirmation."""
        result = self.check_confirmation(symbol, entry_tf, entry_bias, tf_data)
        
        cache_key = f"{symbol}_{entry_tf}"
        self.cache[cache_key] = result
        
        return result
    
    @staticmethod
    def format_result(result: MTFResult) -> str:
        """Format result for terminal display."""
        # Build bias string
        parts = []
        for tf in TIMEFRAMES:
            if tf in result.biases:
                bias = result.biases[tf]
                if bias == 'BULLISH':
                    parts.append(f"{tf}↑")
                elif bias == 'BEARISH':
                    parts.append(f"{tf}↓")
                else:
                    parts.append(f"{tf}→")
            else:
                parts.append(f"{tf}--")
        
        bias_str = ' '.join(parts)
        
        if result.confirmed:
            return f"[MTF] {result.symbol} {bias_str} ✓ CONFIRMED"
        else:
            return f"[MTF] {result.symbol} {bias_str} ✗ BLOCKED ({result.block_reason})"


# Global instance
_mtf_engine: Optional[MTFConfirmation] = None


def get_mtf_engine() -> MTFConfirmation:
    """Get or create global MTF engine."""
    global _mtf_engine
    if _mtf_engine is None:
        _mtf_engine = MTFConfirmation()
    return _mtf_engine


def check_mtf(
    symbol: str,
    entry_tf: str,
    entry_bias: str,
    tf_data: Dict[str, Dict[str, Any]]
) -> MTFResult:
    """Quick MTF check (convenience function)."""
    return get_mtf_engine().check_signal(symbol, entry_tf, entry_bias, tf_data)


# ══════════════════════════════════════════════════════════════════════════════
# CLI TEST
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import sys
    
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    if '--test' in sys.argv:
        print("=" * 60)
        print("  MULTI-TIMEFRAME CONFIRMATION - TEST")
        print("=" * 60)
        
        engine = MTFConfirmation()
        
        # Test 1: All bullish - confirmed
        print("\nTest 1: All bullish")
        result1 = engine.check_signal(
            symbol='XAUUSD',
            entry_tf='M15',
            entry_bias='BULLISH',
            tf_data={
                'M15': {'price': 2355.0, 'vwap': 2350.0, 'ob_high': 2360.0},
                'H1': {'price': 2355.0, 'vwap': 2348.0, 'ob_high': 2365.0},
                'H4': {'price': 2350.0, 'vwap': 2340.0, 'ob_high': 2370.0},
                'D1': {'price': 2345.0, 'vwap': 2330.0, 'ob_high': 2380.0}
            }
        )
        print(engine.format_result(result1))
        
        # Test 2: H1 conflict - blocked
        print("\nTest 2: H1 conflict")
        result2 = engine.check_signal(
            symbol='EURUSD',
            entry_tf='M15',
            entry_bias='BULLISH',
            tf_data={
                'M15': {'price': 1.0850, 'vwap': 1.0840, 'ob_high': 1.0860},
                'H1': {'price': 1.0820, 'vwap': 1.0850, 'ob_low': 1.0830},
                'H4': {'price': 1.0810, 'vwap': 1.0840},
                'D1': {'price': 1.0800, 'vwap': 1.0830}
            }
        )
        print(engine.format_result(result2))
        
        # Test 3: H4 neutral - confirmed
        print("\nTest 3: H4 neutral")
        result3 = engine.check_signal(
            symbol='GBPUSD',
            entry_tf='H1',
            entry_bias='BULLISH',
            tf_data={
                'H1': {'price': 1.2720, 'vwap': 1.2700},
                'H4': {'price': 1.2710, 'vwap': 1.2710},  # Near VWAP = neutral
                'D1': {'price': 1.2700, 'vwap': 1.2680}
            }
        )
        print(engine.format_result(result3))
        
        print("\n" + "=" * 60)
    else:
        print("Usage: python mtf_confirmation.py --test")
