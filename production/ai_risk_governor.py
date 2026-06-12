"""
Module 8 — AI Risk Governor
=============================
Adaptive position sizing based on confidence score, recent drawdown,
and statistical edge. Protects account before maximizing returns.

Tiers:
  Confidence >= 95: High risk
  90-94: Normal risk
  80-89: Reduced risk
  70-79: Small risk
  60-69: Very small risk
  Below 60: No trade
"""

import logging
import math
from typing import Dict, Optional, Any
from datetime import datetime, timezone

log = logging.getLogger('AIRiskGovernor')

RISK_TIER_HIGH = 'HIGH'
RISK_TIER_NORMAL = 'NORMAL'
RISK_TIER_REDUCED = 'REDUCED'
RISK_TIER_SMALL = 'SMALL'
RISK_TIER_VERY_SMALL = 'VERY_SMALL'
RISK_TIER_NO_TRADE = 'NO_TRADE'

CONFIDENCE_TIERS = [
    (95, 101, RISK_TIER_HIGH, 1.0),
    (90, 95, RISK_TIER_NORMAL, 0.8),
    (80, 90, RISK_TIER_REDUCED, 0.5),
    (70, 80, RISK_TIER_SMALL, 0.3),
    (60, 70, RISK_TIER_VERY_SMALL, 0.15),
    (0, 60, RISK_TIER_NO_TRADE, 0.0),
]

MAX_CONSECUTIVE_LOSSES_BEFORE_REDUCE = 3
MAX_DAILY_DRAWDOWN_PCT = 5.0
RECOVERY_TRADES_NEEDED = 3


class AIRiskGovernor:
    """
    Adaptive risk governor that adjusts position sizing based on
    confidence, recent performance, drawdown, and streak analysis.
    """

    def __init__(self):
        self._base_risk_pct: float = 1.0
        self._consecutive_losses: int = 0
        self._daily_pnl: float = 0.0
        self._peak_balance: float = 10000.0
        self._current_balance: float = 10000.0
        self._trades_today: int = 0
        self._recovery_counter: int = 0
        self._in_recovery: bool = False

    def get_position_size_factor(
        self,
        confidence: int,
        account_balance: float,
        daily_pnl: float = 0.0,
        consecutive_losses: int = 0,
        peak_balance: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Calculate position size factor based on confidence and risk state.

        Args:
            confidence: Signal confidence score (0-100)
            account_balance: Current account balance
            daily_pnl: Today's PnL
            consecutive_losses: Current consecutive loss streak
            peak_balance: Historical peak balance

        Returns:
            Dict with risk_tier, factor, max_risk_amount, reason.
        """
        self._current_balance = account_balance
        if peak_balance is not None:
            self._peak_balance = max(self._peak_balance, peak_balance)
        self._daily_pnl = daily_pnl
        if consecutive_losses > 0:
            self._consecutive_losses = consecutive_losses

        # Find confidence tier
        tier_label = RISK_TIER_NO_TRADE
        tier_factor = 0.0
        for lo, hi, label, factor in CONFIDENCE_TIERS:
            if lo <= confidence < hi:
                tier_label = label
                tier_factor = factor
                break

        # Drawdown penalty
        drawdown_pct = self._get_drawdown_pct()
        if drawdown_pct > MAX_DAILY_DRAWDOWN_PCT:
            tier_label = RISK_TIER_NO_TRADE
            tier_factor = 0.0

        # Consecutive loss penalty
        loss_penalty = max(0, 1.0 - (self._consecutive_losses - 1) * 0.25)
        if self._consecutive_losses >= MAX_CONSECUTIVE_LOSSES_BEFORE_REDUCE:
            loss_penalty = 0.0

        # Recovery mode
        if self._in_recovery:
            tier_factor *= 0.5
            self._recovery_counter += 1
            if self._recovery_counter >= RECOVERY_TRADES_NEEDED:
                self._in_recovery = False
                self._recovery_counter = 0
                log.info("Risk Governor: Recovery complete, normal risk resumed")

        # Apply penalties
        final_factor = tier_factor * loss_penalty

        # Cap max risk per trade
        max_risk_amount = account_balance * (final_factor * self._base_risk_pct / 100)

        return {
            'risk_tier': tier_label,
            'base_factor': tier_factor,
            'loss_penalty': round(loss_penalty, 2),
            'final_factor': round(final_factor, 3),
            'max_risk_amount': round(max_risk_amount, 2),
            'max_risk_pct': round(final_factor * self._base_risk_pct, 2),
            'drawdown_pct': round(drawdown_pct, 1),
            'in_recovery': self._in_recovery,
            'recovery_trades_remaining': RECOVERY_TRADES_NEEDED - self._recovery_counter if self._in_recovery else 0,
            'consecutive_losses': self._consecutive_losses,
        }

    def record_trade_result(self, pnl: float) -> None:
        """Update risk state after a trade."""
        self._daily_pnl += pnl
        self._current_balance += pnl
        self._trades_today += 1

        if pnl <= 0:
            self._consecutive_losses += 1
            if self._consecutive_losses >= MAX_CONSECUTIVE_LOSSES_BEFORE_REDUCE:
                self._in_recovery = True
                self._recovery_counter = 0
                log.info(f"Risk Governor: {self._consecutive_losses} consecutive losses, entering recovery mode")
        else:
            if self._consecutive_losses > 0:
                self._recovery_counter += 1
                if self._recovery_counter >= RECOVERY_TRADES_NEEDED:
                    self._consecutive_losses = 0
                    self._in_recovery = False
                    self._recovery_counter = 0
                    log.info("Risk Governor: Recovery complete after winning trades")

        if self._current_balance > self._peak_balance:
            self._peak_balance = self._current_balance

    def _get_drawdown_pct(self) -> float:
        if self._peak_balance <= 0:
            return 0.0
        return (self._peak_balance - self._current_balance) / self._peak_balance * 100

    def reset_daily(self):
        """Reset daily counters."""
        self._daily_pnl = 0.0
        self._trades_today = 0

    def get_state(self) -> Dict[str, Any]:
        return {
            'balance': round(self._current_balance, 2),
            'peak_balance': round(self._peak_balance, 2),
            'drawdown_pct': round(self._get_drawdown_pct(), 1),
            'consecutive_losses': self._consecutive_losses,
            'daily_pnl': round(self._daily_pnl, 2),
            'trades_today': self._trades_today,
            'in_recovery': self._in_recovery,
        }


_governor: Optional[AIRiskGovernor] = None


def get_risk_governor() -> AIRiskGovernor:
    global _governor
    if _governor is None:
        _governor = AIRiskGovernor()
    return _governor


if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    if '--test' in sys.argv:
        rg = get_risk_governor()
        for confidence in [95, 85, 75, 65, 55]:
            result = rg.get_position_size_factor(confidence, 10000)
            print(f"Conf {confidence}: tier={result['risk_tier']} factor={result['final_factor']} max_risk=${result['max_risk_amount']}")

        rg.record_trade_result(-100)
        rg.record_trade_result(-150)
        rg.record_trade_result(-200)
        state = rg.get_state()
        print(f"After 3 losses: {state}")

        result = rg.get_position_size_factor(85, 9550)
        print(f"After drawdown: {result}")

        rg.record_trade_result(50)
        rg.record_trade_result(75)
        rg.record_trade_result(100)
        state = rg.get_state()
        print(f"After recovery: {state}")

        print("AIRiskGovernor OK")
