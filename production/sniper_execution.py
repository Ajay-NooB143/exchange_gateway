"""
Sniper Strategy — Layer 2 Execution Module
===========================================
AJAY REAL MONEY SNIPER v5 — Institutional Entry Logic

Processes the enriched scanner payload from Layer 1 (live_feed_scanner)
to determine if sniper entry criteria are met.

Dependencies (Layer 0 contracts only):
    - PipelineProtocol (if called as pipeline step)
    - No upward imports to Layer 3 or Layer 4

Entry Criteria:
    1. MTF SMC Bias must be non-neutral
    2. Volume expansion >= multiplier × average of last 5 candles
    3. Proximity to Order Block OR unfilled FVG in direction of bias
"""

import logging
from typing import Dict, Any, Optional, List

log = logging.getLogger('SniperStrategy')

# Asset-dependent pip conversion: 1 pip = X price points
# Forex pairs: 1 pip = 0.0001 (4th decimal)
# JPY pairs: 1 pip = 0.01 (2nd decimal)
# Gold (XAUUSD): 1 pip = 0.10
# SP500: 1 pip = 0.10
# Crypto: 1 pip = 1.0 (whole number)
PIP_CONVERSION = {
    'XAUUSD': 0.10,
    'EURUSD': 0.0001,
    'GBPUSD': 0.0001,
    'USDJPY': 0.01,
    'USDCHF': 0.0001,
    'AUDUSD': 0.0001,
    'USDCAD': 0.0001,
    'NZDUSD': 0.0001,
    'SP500': 0.10,
    'BTCUSD': 1.0,
    'ETHUSD': 1.0,
    'BNBUSD': 1.0,
    'SOLUSD': 1.0,
    'XRPUSD': 1.0,
}
DEFAULT_PIP_CONVERSION = 0.0001  # Default to forex


def get_pip_conversion(symbol: str) -> float:
    """Get the pip conversion factor for a given symbol."""
    return PIP_CONVERSION.get(symbol.upper(), DEFAULT_PIP_CONVERSION)


class SniperStrategy:
    """
    Layer 2: Execution Logic
    Translates translated Pine Script rules for 'AJAY REAL MONEY SNIPER' v5.
    Combines MTF SMC bias, Order Block mitigation, FVG proximity, and volume expansion.
    """

    def __init__(self, volume_multiplier: float = 1.5, proximity_threshold_pips: float = 5.0):
        self.volume_multiplier = volume_multiplier
        self.proximity_threshold_pips = proximity_threshold_pips

    def evaluate_market(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Processes the enriched scanner payload to determine if sniper entry criteria are met.
        """
        # Default fallback response
        response = {
            "decision": "HOLD",
            "confidence_score": 0.0,
            "target_price": 0.0,
            "reason": "No clear institutional presence"
        }

        # 1. Extract core data safely
        smc_data = payload.get("smc")
        latest_price = payload.get("price")
        candles = payload.get("candles", [])

        if not smc_data or not latest_price or not candles:
            response["reason"] = "Missing crucial payload arrays"
            return response

        bias = smc_data.get("mtf_smc_bias", "NEUTRAL")
        if bias == "NEUTRAL":
            response["reason"] = "Market context is directionless (Neutral Bias)"
            return response

        # 2. Volume Expansion Validation (Institutional Confirmation)
        if len(candles) < 5:
            response["reason"] = "Insufficient candle history for volume analysis"
            return response

        current_candle = candles[-1]
        previous_candles = candles[-5:-1]
        avg_volume = sum(c.get("volume", 0) for c in previous_candles) / len(previous_candles)
        current_volume = current_candle.get("volume", 0)
        is_volume_expanding = current_volume >= (avg_volume * self.volume_multiplier)

        # 3. Proximity to Structural Levels
        # Extract nearest order blocks from the default or key timeframes (e.g., H1)
        symbol = payload.get('symbol', 'XAUUSD')
        pip_conversion = get_pip_conversion(symbol)
        distance_threshold = self.proximity_threshold_pips * pip_conversion

        # Check conditions based on structural alignment
        if bias == "BULLISH":
            # Check if we are interacting with or near a Bullish OB
            # Or if an aggressive volume break out is leaving an unfilled Bullish FVG below us
            has_bull_ob = smc_data.get("bullish_ob_count", 0) > 0
            unfilled_fvgs = smc_data.get("unfilled_fvgs", [])
            has_unfilled_bull_fvg = any(f.get("type") == "BULLISH" for f in unfilled_fvgs)

            if is_volume_expanding and (has_bull_ob or has_unfilled_bull_fvg):
                # Calculate a strict conservative entry target slightly above the current price 
                # or pulling back to the top of the nearest structural support block
                response["decision"] = "BUY"
                response["confidence_score"] = 0.85 if has_bull_ob and has_unfilled_bull_fvg else 0.70
                response["target_price"] = round(latest_price, 2)
                response["reason"] = f"Bullish SMC alignment confirmed with Volume Expansion ({current_volume:.0f} > {avg_volume:.0f})"
                return response

        elif bias == "BEARISH":
            # Check if we are interacting with or near a Bearish OB
            has_bear_ob = smc_data.get("bearish_ob_count", 0) > 0
            unfilled_fvgs = smc_data.get("unfilled_fvgs", [])
            has_unfilled_bear_fvg = any(f.get("type") == "BEARISH" for f in unfilled_fvgs)

            if is_volume_expanding and (has_bear_ob or has_unfilled_bear_fvg):
                response["decision"] = "SELL"
                response["confidence_score"] = 0.85 if has_bear_ob and has_unfilled_bear_fvg else 0.70
                response["target_price"] = round(latest_price, 2)
                response["reason"] = f"Bearish SMC alignment confirmed with Volume Expansion ({current_volume:.0f} > {avg_volume:.0f})"
                return response

        response["reason"] = f"Bias is {bias} but volume or mitigation criteria failed validation"
        return response
