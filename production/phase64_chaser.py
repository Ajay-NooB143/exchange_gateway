"""
Phase 64 Anti-Slippage Chaser — Layer 2 Execution Module
========================================================
Dynamic limit-order walking algorithm for volatile orderbooks (e.g., XAUUSD).

Instead of market orders, Phase 64 places limit orders and "chases" the price
if it moves away, stepping closer by a fixed increment up to a maximum tolerance.

Dependencies (Layer 0 contracts only):
    - No upward imports to Layer 3 or Layer 4

Algorithm:
    1. Place limit order at target price
    2. If market moves away by > chase_threshold_pips → replace limit 1 step closer
    3. If total slippage exceeds max_chase_pips → CANCEL (protect capital)
    4. Clamp new limit to avoid crossing the spread (no accidental market fills)
"""

import logging
from typing import Dict, Any, Optional

log = logging.getLogger('Phase64Chaser')

# Asset-dependent pip conversion: 1 pip = X price points
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
DEFAULT_PIP_CONVERSION = 0.0001


def get_pip_conversion(symbol: str) -> float:
    """Get the pip conversion factor for a given symbol."""
    return PIP_CONVERSION.get(symbol.upper(), DEFAULT_PIP_CONVERSION)


class Phase64Chaser:
    """
    Layer 2: Execution Logic
    Phase 64: The Anti-Slippage Limit-Order Chaser.
    Tracks, steps, and dynamically walks limit orders into volatile orderbooks (e.g., XAUUSD).
    """

    def __init__(self, max_chase_pips: float = 10.0, step_pips: float = 1.0, chase_threshold_pips: float = 2.0):
        self.max_chase_pips = max_chase_pips
        self.step_pips = step_pips
        self.chase_threshold_pips = chase_threshold_pips

    def process_chase_cycle(self, order_state: Dict[str, Any], order_book: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluates active limit orders against the current spread and decides whether to hold,
        chase (replace closer), or kill the order due to runaway slippage.
        
        :param order_state: Dict containing {'active': bool, 'side': 'BUY'|'SELL', 'limit_price': float, 'initial_price': float}
        :param order_book: Dict containing {'bid': float, 'ask': float}
        """
        directive = {
            "action": "HOLD",
            "new_limit_price": 0.0,
            "reason": "Order resting within optimal threshold"
        }

        if not order_state.get("active"):
            directive["action"] = "IDLE"
            directive["reason"] = "No active order tracking required"
            return directive

        side = order_state.get("side")
        limit_price = order_state.get("limit_price", 0.0)
        initial_price = order_state.get("initial_price", 0.0)
        symbol = order_state.get("symbol", "XAUUSD")
        
        bid = order_book.get("bid", 0.0)
        ask = order_book.get("ask", 0.0)

        if not bid or not ask or not limit_price:
            directive["reason"] = "Incomplete market price data arrays"
            return directive

        # Use asset-dependent pip conversion
        pip_to_points = get_pip_conversion(symbol)
        max_chase_points = self.max_chase_pips * pip_to_points
        step_points = self.step_pips * pip_to_points
        chase_threshold_points = self.chase_threshold_pips * pip_to_points

        if side == "BUY":
            # Market is moving away if the lowest seller (Ask) climbs far above our buy limit
            distance_away = ask - limit_price
            total_slippage = ask - initial_price

            # 1. Check if the asset has run completely out of our maximum tolerance zone
            if total_slippage > max_chase_points:
                directive["action"] = "CANCEL"
                directive["reason"] = f"Max slippage breached ({total_slippage / pip_to_points:.1f} pips). Protecting capital."
                return directive

            # 2. Check if the price has pulled away enough to trigger a chase step
            if distance_away > chase_threshold_points:
                # Increment the limit order 1 step closer to the market price
                proposed_price = limit_price + step_points
                # Never place the limit higher than the current ask (to avoid accidental market fills)
                new_price = min(proposed_price, ask - (0.1 * pip_to_points))
                
                directive["action"] = "UPDATE_LIMIT"
                directive["new_limit_price"] = round(new_price, 2)
                directive["reason"] = f"Chasing BUY order. Market moved away by {distance_away / pip_to_points:.1f} pips."
                return directive

        elif side == "SELL":
            # Market is moving away if the highest buyer (Bid) drops far below our sell limit
            distance_away = limit_price - bid
            total_slippage = initial_price - bid

            if total_slippage > max_chase_points:
                directive["action"] = "CANCEL"
                directive["reason"] = f"Max slippage breached ({total_slippage / pip_to_points:.1f} pips). Protecting capital."
                return directive

            if distance_away > chase_threshold_points:
                proposed_price = limit_price - step_points
                new_price = max(proposed_price, bid + (0.1 * pip_to_points))
                
                directive["action"] = "UPDATE_LIMIT"
                directive["new_limit_price"] = round(new_price, 2)
                directive["reason"] = f"Chasing SELL order. Market moved away by {distance_away / pip_to_points:.1f} pips."
                return directive

        return directive
