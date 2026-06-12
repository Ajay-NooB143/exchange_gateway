"""
Alpha Agent — Layer 2 Trade Management Module
==============================================
Pure state machine for position management: trailing stops via Order Blocks
and profit-target exits.

Dependencies (Layer 0 contracts only):
    - No upward imports to Layer 3 or Layer 4

Asset Convention:
    - XAUUSD: 1 pip = 0.10 price points (e.g., 2200.00 → 2200.10 = 1 pip)
    - Target: 200-pip profit exit
    - Trail: 50-pip minimum profit before trailing to nearest Order Block
"""

import logging
from typing import Dict, Any, Optional, List

log = logging.getLogger('AlphaAgent')

# XAUUSD pip convention
PIP_TO_POINTS = 0.10


class AlphaAgent:
    """
    Layer 2: Trade Management State Machine
    
    Manages open positions by:
      1. Exiting at 200-pip profit target
      2. Trailing stop loss to nearest Order Block after 50-pip profit
      3. Holding otherwise
    """

    def __init__(self, profit_target_pips: float = 200.0, trail_activation_pips: float = 50.0):
        self.profit_target_points = profit_target_pips * PIP_TO_POINTS
        self.trail_activation_points = trail_activation_pips * PIP_TO_POINTS

    def manage_position(
        self,
        position: Dict[str, Any],
        smc: Dict[str, Any],
        current_price: float
    ) -> Dict[str, Any]:
        """
        Evaluate an open position and return a management directive.

        :param position: {
            'side': 'BUY' | 'SELL',
            'entry_price': float,
            'stop_loss': float,
            'take_profit': float,
            'symbol': str (optional)
        }
        :param smc: {
            'order_blocks': [{'type': str, 'ob_high': float, 'ob_low': float, ...}],
            'nearest_ob': {'type': str, 'ob_high': float, 'ob_low': float, ...} | None,
            'mtf_smc_bias': str
        }
        :param current_price: float
        :return: {
            'action': 'HOLD' | 'CLOSE' | 'UPDATE_SL',
            'new_sl': float | None,
            'reason': str,
            'pnl_pips': float
        }
        """
        directive = {
            'action': 'HOLD',
            'new_sl': None,
            'reason': 'Position within management parameters',
            'pnl_pips': 0.0,
        }

        side = position.get('side', 'BUY')
        entry_price = position.get('entry_price', 0)
        current_sl = position.get('stop_loss', 0)

        if not entry_price or not current_price:
            directive['reason'] = 'Missing entry_price or current_price'
            return directive

        # Calculate P&L in pips
        if side == 'BUY':
            pnl_points = current_price - entry_price
        else:
            pnl_points = entry_price - current_price

        pnl_pips = pnl_points / PIP_TO_POINTS
        directive['pnl_pips'] = round(pnl_pips, 2)

        # ── Rule 1: Profit Target (200 pips) ──────────────────────────
        if pnl_points >= self.profit_target_points:
            directive['action'] = 'CLOSE'
            directive['reason'] = (
                f"Profit target reached: {pnl_pips:.1f} pips "
                f"(≥ {self.profit_target_points / PIP_TO_POINTS:.0f})"
            )
            log.info(f"[ALPHA] CLOSE {side} @ {current_price:.2f} — {directive['reason']}")
            return directive

        # ── Rule 2: Trailing Stop (50 pips + OB shift) ────────────────
        if pnl_points >= self.trail_activation_points:
            nearest_ob = smc.get('nearest_ob')
            if nearest_ob:
                ob_high = nearest_ob.get('ob_high', 0)
                ob_low = nearest_ob.get('ob_low', 0)
                ob_type = nearest_ob.get('type', '')

                if side == 'BUY':
                    # Trail SL to just below bullish OB (demand zone support)
                    if 'BULLISH' in ob_type.upper():
                        new_sl = round(ob_low - (0.5 * PIP_TO_POINTS), 2)
                        if new_sl > current_sl:
                            directive['action'] = 'UPDATE_SL'
                            directive['new_sl'] = new_sl
                            directive['reason'] = (
                                f"Trailing SL to bullish OB: {new_sl:.2f} "
                                f"(pnl={pnl_pips:.1f} pips, OB=[{ob_low:.2f}, {ob_high:.2f}])"
                            )
                            log.info(f"[ALPHA] UPDATE_SL {side} → {new_sl:.2f} — {directive['reason']}")
                            return directive

                elif side == 'SELL':
                    # Trail SL to just above bearish OB (supply zone resistance)
                    if 'BEARISH' in ob_type.upper():
                        new_sl = round(ob_high + (0.5 * PIP_TO_POINTS), 2)
                        if new_sl < current_sl:
                            directive['action'] = 'UPDATE_SL'
                            directive['new_sl'] = new_sl
                            directive['reason'] = (
                                f"Trailing SL to bearish OB: {new_sl:.2f} "
                                f"(pnl={pnl_pips:.1f} pips, OB=[{ob_low:.2f}, {ob_high:.2f}])"
                            )
                            log.info(f"[ALPHA] UPDATE_SL {side} → {new_sl:.2f} — {directive['reason']}")
                            return directive

        # ── Rule 3: Hold ──────────────────────────────────────────────
        directive['reason'] = (
            f"Hold: pnl={pnl_pips:.1f} pips, "
            f"target={self.profit_target_points / PIP_TO_POINTS:.0f}, "
            f"trail_active={pnl_points >= self.trail_activation_points}"
        )
        return directive
