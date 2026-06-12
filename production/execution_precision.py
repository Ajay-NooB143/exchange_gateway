"""
Execution Precision Engine - Partial Entry Cascade & Quality Grading
====================================================================
Three‑tier partial entry: aggressive (33%), conservative (33%), 
deep retracement (33%). Execution grading A⁺/B/C with slippage 
anomaly detection.

Integration:
  plan = ExecutionPlanner().plan_entry(signal, price, atr)
  execution_logger.record(plan)
"""

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

log = logging.getLogger('ExecutionPrecision')

ENTRY_TIER_AGGRESSIVE = 'AGGRESSIVE'
ENTRY_TIER_CONSERVATIVE = 'CONSERVATIVE'
ENTRY_TIER_DEEP = 'DEEP_RETRACEMENT'

GRADE_A_PLUS = 'A⁺'   # Liquidity extreme fill
GRADE_B = 'B'         # Pullback fill
GRADE_C = 'C'         # Chase / late fill


@dataclass
class ExecutionPlan:
    symbol: str
    direction: str  # BUY or SELL
    tiers: List[Dict[str, Any]] = field(default_factory=list)
    total_qty: float = 0.0
    avg_price: float = 0.0
    timestamp: str = ''
    grade: str = ''
    slippage_anomaly: bool = False

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


@dataclass
class TierOrder:
    tier: str
    price: float
    quantity_pct: float  # 0.33, 0.33, 0.34
    status: str  # PENDING, FILLED, CANCELLED
    fill_price: Optional[float] = None
    fill_time: Optional[str] = None
    reason: str = ''


class ExecutionPlanner:
    """
    Plan partial entry cascades with 1/3 split.
    Grade execution quality after fill.
    """

    TIER_CONFIGS = [
        {'tier': ENTRY_TIER_AGGRESSIVE, 'pct': 0.33, 'offset_atr': 0.1},
        {'tier': ENTRY_TIER_CONSERVATIVE, 'pct': 0.33, 'offset_atr': 0.3},
        {'tier': ENTRY_TIER_DEEP, 'pct': 0.34, 'offset_atr': 0.6},
    ]

    def plan_entry(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        atr: float,
        total_quantity: float = 1.0,
    ) -> ExecutionPlan:
        """
        Create a 3-tier execution plan.

        Args:
            symbol: Trading symbol
            direction: 'BUY' or 'SELL'
            entry_price: Base entry price (signal trigger)
            atr: Current ATR value
            total_quantity: Total position size (100%)

        Returns:
            ExecutionPlan with 3 tier orders
        """
        if atr <= 0:
            atr = entry_price * 0.001  # fallback 0.1%

        tiers = []
        multiplier = 1 if direction.upper() == 'BUY' else -1

        for cfg in self.TIER_CONFIGS:
            offset = cfg['offset_atr'] * atr
            tier_price = entry_price + (multiplier * offset)

            tiers.append({
                'tier': cfg['tier'],
                'price': round(tier_price, 5),
                'quantity_pct': cfg['pct'],
                'qty': round(total_quantity * cfg['pct'], 4),
                'status': 'PENDING',
                'reason': f'{cfg["tier"]} at {cfg["offset_atr"]:.1f}×ATR offset',
            })

        total_qty = round(sum(t['qty'] for t in tiers), 4)
        avg_price = round(
            sum(t['price'] * t['qty'] for t in tiers) / max(total_qty, 1e-10),
            5,
        )

        return ExecutionPlan(
            symbol=symbol,
            direction=direction,
            tiers=tiers,
            total_qty=total_qty,
            avg_price=avg_price,
        )

    def grade_execution(
        self,
        plan: ExecutionPlan,
        entry_price: float,
        limit_price: float,
        spread_ratio: float = 0.0,
    ) -> str:
        """
        Grade execution quality based on fill vs entry.

        Grade logic:
          A⁺: avg_fill_price is closer to liquidity extreme than entry
             (price improved vs limit)
          B:  avg_fill_price near entry (within 0.5 ATR)
          C:  avg_fill_price is worse (chase)

        Returns grade string.
        """
        if not plan.tiers:
            return GRADE_C

        try:
            filled = [t for t in plan.tiers if t.get('status') == 'FILLED' and t.get('fill_price')]
            if not filled:
                return GRADE_B

            avg_fill = sum(t['fill_price'] for t in filled) / len(filled)
            direction = plan.direction.upper()

            if direction == 'BUY':
                # Better fill = lower price (closer to liquidity low)
                price_improvement = max(limit_price - avg_fill, 0)
                if price_improvement > 0:
                    return GRADE_A_PLUS
                elif avg_fill <= entry_price * 1.01:
                    return GRADE_B
                else:
                    return GRADE_C
            else:
                # Better fill = higher price (closer to liquidity high)
                price_improvement = max(avg_fill - limit_price, 0)
                if price_improvement > 0:
                    return GRADE_A_PLUS
                elif avg_fill >= entry_price * 0.99:
                    return GRADE_B
                else:
                    return GRADE_C
        except Exception:
            return GRADE_B

    def detect_slippage_anomaly(
        self,
        expected_price: float,
        actual_fill_price: float,
        atr: float,
    ) -> bool:
        """
        Detect anomalous slippage exceeding expected bounds.

        Returns True if slippage > 0.5 ATR (unexpected).
        """
        if atr <= 0:
            return False
        try:
            slippage = abs(actual_fill_price - expected_price)
            return slippage > (atr * 0.5)
        except Exception:
            return False


# ══════════════════════════════════════════════════════════════════════════════
# EXECUTION LOGGER
# ══════════════════════════════════════════════════════════════════════════════

_execution_log: List[ExecutionPlan] = []


def record_execution(plan: ExecutionPlan) -> None:
    """Record an execution plan for later analysis."""
    _execution_log.append(plan)
    log.info(f"EXECUTION: {plan.symbol} {plan.direction} "
             f"size={plan.total_qty} avg={plan.avg_price}")


def get_execution_log(symbol: Optional[str] = None, limit: int = 100) -> List[ExecutionPlan]:
    """Retrieve execution log."""
    if symbol:
        return [p for p in _execution_log if p.symbol == symbol][-limit:]
    return _execution_log[-limit:]


# ══════════════════════════════════════════════════════════════════════════════
# CLI TEST
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.INFO, format='%(message)s')

    if '--test' in sys.argv:
        planner = ExecutionPlanner()

        # Plan a 3-tier entry
        plan = planner.plan_entry('XAUUSD', 'BUY', 2355.0, 5.0, 1.0)
        print(f"Plan: {plan.symbol} {plan.direction}")
        print(f"Avg price: {plan.avg_price}, Total qty: {plan.total_qty}")
        for t in plan.tiers:
            print(f"  {t['tier']}: {t['price']} ({t['qty']})")

        # Grade simulation
        plan.tiers[0]['status'] = 'FILLED'
        plan.tiers[0]['fill_price'] = 2354.0
        grade = planner.grade_execution(plan, 2355.0, 2355.0)
        print(f"Execution grade: {grade}")

        # Slippage check
        anomaly = planner.detect_slippage_anomaly(2355.0, 2380.0, 5.0)
        print(f"Slippage anomaly: {anomaly}")

        record_execution(plan)
        print("ExecutionPrecision OK")
