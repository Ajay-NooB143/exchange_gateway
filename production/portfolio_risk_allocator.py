"""Portfolio Risk Allocator

Dynamic capital allocation across strategies (Scalp, Intraday, Swing,
Recovery, Breakout, Reversal). Uses volatility, win rate, correlation,
drawdown, exposure, and risk budget to compute allocation %,
lot multiplier, risk multiplier, and strategy priority.
"""

import logging
import math
from typing import List, Dict, Optional, Any
from datetime import datetime, timezone

log = logging.getLogger(__name__)

DEFAULT_RISK_BUDGET = 0.02
MAX_STRATEGIES = 6
MIN_ALLOCATION = 0.0

STRATEGY_DEFAULTS = [
    'SCALP', 'INTRADAY', 'SWING', 'RECOVERY', 'BREAKOUT', 'REVERSAL',
]


class PortfolioRiskAllocator:
    """Dynamic multi-strategy risk allocation engine."""

    def __init__(self):
        self._strategies: Dict[str, Dict[str, Any]] = {}
        self._last_allocation: Optional[Dict[str, Any]] = None
        self._total_exposure = 0.0

    def register_strategy(self, name: str, win_rate: float = 0.5,
                          avg_rr: float = 1.5, volatility: float = 1.0,
                          correlation: float = 0.5, enabled: bool = True) -> None:
        self._strategies[name.upper()] = {
            'win_rate': max(0, min(1, win_rate)),
            'avg_rr': max(0.1, avg_rr),
            'volatility': max(0.1, volatility),
            'correlation': max(-1, min(1, correlation)),
            'enabled': enabled,
            'current_exposure': 0.0,
            'current_allocation': 0.0,
        }

    def update_exposure(self, strategy: str, exposure: float) -> None:
        key = strategy.upper()
        if key in self._strategies:
            self._strategies[key]['current_exposure'] = max(0, exposure)

    def allocate(self, account_balance: float = 10000.0,
                 risk_budget: float = DEFAULT_RISK_BUDGET,
                 current_drawdown: float = 0.0,
                 volatility_multiplier: float = 1.0) -> Dict[str, Any]:
        result = {
            'allocations': {},
            'total_risk': 0,
            'within_budget': True,
            'lot_multiplier': 1.0,
            'risk_multiplier': 1.0,
            'strategy_priority': [],
            'reason': '',
        }
        try:
            # Ensure defaults are registered
            for s in STRATEGY_DEFAULTS:
                if s not in self._strategies:
                    self.register_strategy(s)

            enabled = {k: v for k, v in self._strategies.items() if v.get('enabled', True)}
            if not enabled:
                result['reason'] = 'No strategies enabled'
                return result

            # Score each strategy
            scored: List[tuple] = []
            for name, cfg in enabled.items():
                score = self._score_strategy(cfg, current_drawdown, volatility_multiplier)
                scored.append((score, name, cfg))

            scored.sort(key=lambda x: x[0], reverse=True)
            total_score = sum(s[0] for s in scored) or 1

            # Allocate capital
            risk_mult = self._compute_risk_multiplier(current_drawdown)
            lot_mult = self._compute_lot_multiplier(volatility_multiplier)

            remaining_budget = risk_budget * risk_mult
            allocations = {}
            strategy_priority = []
            allocated_risk = 0

            for score, name, cfg in scored:
                weight = score / total_score
                alloc = weight * remaining_budget
                alloc_pct = alloc * 100
                alloc_pct = max(MIN_ALLOCATION, min(100, alloc_pct))

                # Adjust for correlation penalty
                corr = abs(cfg.get('correlation', 0.5))
                corr_penalty = 1.0 - (corr * 0.3)
                alloc_pct *= corr_penalty

                strategy_risk = alloc_pct / 100
                allocated_risk += strategy_risk

                allocations[name] = {
                    'allocation_pct': round(alloc_pct, 1),
                    'risk_contribution': round(strategy_risk * 100, 2),
                    'lot_multiplier': round(lot_mult * (1 + (score / total_score - 0.5) * 0.2), 3),
                    'priority': len(strategy_priority) + 1,
                }
                strategy_priority.append(name)

            # Normalize to risk budget
            if allocated_risk > risk_budget * risk_mult:
                scale = (risk_budget * risk_mult) / allocated_risk
                for name in allocations:
                    allocations[name]['allocation_pct'] = round(
                        allocations[name]['allocation_pct'] * scale, 1)
                    allocations[name]['risk_contribution'] = round(
                        allocations[name]['risk_contribution'] * scale, 2)
                allocated_risk *= scale

            total_risk_pct = round(allocated_risk * 100, 2)

            result['allocations'] = allocations
            result['total_risk'] = total_risk_pct
            result['within_budget'] = total_risk_pct <= risk_budget * 100
            result['lot_multiplier'] = round(lot_mult, 3)
            result['risk_multiplier'] = round(risk_mult, 3)
            result['strategy_priority'] = strategy_priority
            result['total_exposure'] = round(
                sum(v.get('current_exposure', 0) for v in enabled.values()), 2)

            if result['within_budget']:
                result['reason'] = (f"Allocated {len(allocations)} strategies, "
                                    f"total risk {total_risk_pct}% within budget")
            else:
                result['reason'] = (f"Risk budget exceeded: {total_risk_pct}% "
                                    f"> {risk_budget * 100}%")

            self._last_allocation = result

        except Exception as e:
            log.warning(f"PortfolioRiskAllocator.allocate error: {e}")
            result['error'] = str(e)

        return result

    def get_last_allocation(self) -> Dict[str, Any]:
        return dict(self._last_allocation) if self._last_allocation else {}

    def get_strategy(self, name: str) -> Optional[Dict[str, Any]]:
        return self._strategies.get(name.upper())

    def reset(self) -> None:
        self._strategies.clear()
        self._last_allocation = None

    # ---- Internal ----

    def _score_strategy(self, cfg: Dict[str, Any],
                        drawdown: float, vol_mult: float) -> float:
        wr = cfg.get('win_rate', 0.5)
        rr = cfg.get('avg_rr', 1.5)
        vol = cfg.get('volatility', 1.0)

        expectancy = wr * rr - (1 - wr)
        if vol > 0:
            vol_adj = 1.0 / max(0.5, vol * vol_mult)
        else:
            vol_adj = 1.0

        dd_penalty = max(0, 1.0 - (drawdown / 20))
        score = max(0, expectancy * 50 + wr * 30) * vol_adj * dd_penalty
        return max(0, score)

    def _compute_risk_multiplier(self, drawdown: float) -> float:
        if drawdown <= 0:
            return 1.0
        if drawdown > 15:
            return 0.2
        if drawdown > 10:
            return 0.4
        if drawdown > 5:
            return 0.7
        return max(0.5, 1.0 - drawdown * 0.05)

    def _compute_lot_multiplier(self, vol_mult: float) -> float:
        if vol_mult <= 0:
            return 1.0
        if vol_mult > 2.0:
            return 0.4
        if vol_mult > 1.5:
            return 0.7
        return max(0.5, 1.0 / vol_mult)


_portfolio_allocator: Optional[PortfolioRiskAllocator] = None


def get_portfolio_allocator() -> PortfolioRiskAllocator:
    global _portfolio_allocator
    if _portfolio_allocator is None:
        _portfolio_allocator = PortfolioRiskAllocator()
    return _portfolio_allocator


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    pa = get_portfolio_allocator()
    pa.register_strategy('SCALP', win_rate=0.55, avg_rr=0.8, volatility=1.2, correlation=0.3)
    pa.register_strategy('SWING', win_rate=0.65, avg_rr=2.5, volatility=0.8, correlation=0.2)
    pa.register_strategy('INTRADAY', win_rate=0.50, avg_rr=1.5, volatility=1.0, correlation=0.4)
    result = pa.allocate(10000, risk_budget=0.02, current_drawdown=3.0)
    print(f"Total risk: {result['total_risk']}%")
    print(f"Within budget: {result['within_budget']}")
    for name, alloc in result['allocations'].items():
        print(f"  {name}: {alloc['allocation_pct']}% (priority {alloc['priority']})")
