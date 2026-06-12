"""
Module 9 — Monte Carlo Risk Lab
=================================
Every weekend: replay historical trades, run thousands of randomized
simulations to compute risk of ruin, max expected DD, expected monthly return,
Sharpe estimate, recovery factor, win/loss streaks.

Recommendations: Increase / Maintain / Reduce risk.
"""

import logging
import math
import random
import statistics
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone

log = logging.getLogger('MonteCarloLab')

DEFAULT_SIMULATIONS = 5000
DEFAULT_TRADES_PER_SIM = 100


class MonteCarloLab:
    """
    Monte Carlo risk simulation using historical trade data.

    Runs thousands of randomized resamples of trade outcomes to
    estimate risk metrics and recommend position sizing adjustments.
    """

    def __init__(self):
        self._last_results: Dict[str, Any] = {}

    def run_simulation(
        self,
        trade_pnls: List[float],
        trade_rrs: List[float],
        initial_balance: float = 10000.0,
        risk_per_trade: float = 1.0,
        num_simulations: int = DEFAULT_SIMULATIONS,
        trades_per_sim: int = DEFAULT_TRADES_PER_SIM,
    ) -> Dict[str, Any]:
        """
        Run Monte Carlo simulation on historical trades.

        Args:
            trade_pnls: List of historical trade PnL values
            trade_rrs: List of historical R:R values
            initial_balance: Starting account balance
            risk_per_trade: Risk per trade as % of balance
            num_simulations: Number of Monte Carlo runs
            trades_per_sim: Number of trades per simulation

        Returns:
            Dict with risk metrics and recommendation.
        """
        if not trade_pnls:
            return {'error': 'No trade data', 'recommendation': 'MAINTAIN'}

        final_balances = []
        max_dd_list = []
        max_dd_pct_list = []
        ruin_count = 0
        win_streaks = []
        loss_streaks = []
        monthly_returns = []
        sharpe_ratios = []

        for sim in range(num_simulations):
            balance = initial_balance
            peak = balance
            max_dd = 0
            streak = 0
            max_win_streak = 0
            max_loss_streak = 0

            for _ in range(trades_per_sim):
                # Random trade from historical pool
                idx = random.randint(0, len(trade_pnls) - 1)
                pnl_pct = trade_pnls[idx] / max(initial_balance, 1)

                risk_amount = balance * (risk_per_trade / 100)
                trade_result = pnl_pct * risk_amount * 100  # Scale to actual

                balance += trade_result
                if balance <= 0:
                    ruin_count += 1
                    balance = 0
                    break

                if balance > peak:
                    peak = balance

                dd = peak - balance
                if dd > max_dd:
                    max_dd = dd

                # Streaks
                if trade_result > 0:
                    streak = streak + 1 if streak > 0 else 1
                    max_win_streak = max(max_win_streak, streak)
                else:
                    streak = streak - 1 if streak < 0 else -1
                    max_loss_streak = max(max_loss_streak, abs(streak))

            final_balances.append(balance)
            dd_pct = max_dd / max(peak, 1) * 100
            max_dd_list.append(max_dd)
            max_dd_pct_list.append(dd_pct)
            win_streaks.append(max_win_streak)
            loss_streaks.append(max_loss_streak)

            # Monthly return approximation (20 trades = ~1 month)
            monthly_return = (balance - initial_balance) / initial_balance * 100
            monthly_returns.append(monthly_return)

        # Compute statistics
        mean_final = statistics.mean(final_balances) if final_balances else initial_balance
        median_final = statistics.median(final_balances) if final_balances else initial_balance
        std_final = statistics.stdev(final_balances) if len(final_balances) > 1 else 0
        avg_max_dd = statistics.mean(max_dd_pct_list) if max_dd_pct_list else 0
        max_possible_dd = max(max_dd_pct_list) if max_dd_pct_list else 0
        avg_win_streak = statistics.mean(win_streaks) if win_streaks else 0
        avg_loss_streak = statistics.mean(loss_streaks) if loss_streaks else 0
        avg_monthly_return = statistics.mean(monthly_returns) if monthly_returns else 0
        std_monthly = statistics.stdev(monthly_returns) if len(monthly_returns) > 1 else 1

        risk_of_ruin = ruin_count / max(num_simulations, 1)
        sharpe = avg_monthly_return / max(std_monthly, 0.01) * math.sqrt(12) if std_monthly > 0 else 0
        recovery_factor = avg_monthly_return / max(avg_max_dd, 0.01) if avg_max_dd > 0 else 0

        # Confidence intervals (95%)
        ci_lower = initial_balance
        ci_upper = initial_balance
        if final_balances:
            sorted_b = sorted(final_balances)
            lower_idx = max(0, int(len(sorted_b) * 0.025))
            upper_idx = min(len(sorted_b) - 1, int(len(sorted_b) * 0.975))
            ci_lower = sorted_b[lower_idx]
            ci_upper = sorted_b[upper_idx]

        # Recommendation
        recommendation = self._get_recommendation(
            risk_of_ruin, sharpe, avg_max_dd, avg_monthly_return,
        )

        self._last_results = {
            'simulations': num_simulations,
            'trades_per_sim': trades_per_sim,
            'initial_balance': initial_balance,
            'mean_final_balance': round(mean_final, 2),
            'median_final_balance': round(median_final, 2),
            'std_final_balance': round(std_final, 2),
            'ci_95_lower': round(ci_lower, 2),
            'ci_95_upper': round(ci_upper, 2),
            'avg_max_drawdown_pct': round(avg_max_dd, 2),
            'max_possible_drawdown_pct': round(max_possible_dd, 2),
            'risk_of_ruin': round(risk_of_ruin, 4),
            'avg_monthly_return_pct': round(avg_monthly_return, 2),
            'sharpe_ratio': round(sharpe, 2),
            'recovery_factor': round(recovery_factor, 2),
            'avg_win_streak': round(avg_win_streak, 1),
            'avg_loss_streak': round(avg_loss_streak, 1),
            'risk_per_trade_used': risk_per_trade,
            'recommendation': recommendation,
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }

        return self._last_results

    def _get_recommendation(
        self,
        risk_of_ruin: float,
        sharpe: float,
        avg_dd_pct: float,
        avg_monthly_return: float,
    ) -> str:
        if risk_of_ruin > 0.05:
            return 'REDUCE'
        if sharpe > 2.0 and avg_dd_pct < 10 and avg_monthly_return > 5:
            return 'INCREASE'
        if sharpe > 1.0 and avg_dd_pct < 15:
            return 'MAINTAIN'
        return 'REDUCE'

    def get_last_results(self) -> Dict[str, Any]:
        return dict(self._last_results)


_lab: Optional[MonteCarloLab] = None


def get_monte_carlo_lab() -> MonteCarloLab:
    global _lab
    if _lab is None:
        _lab = MonteCarloLab()
    return _lab


if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    if '--test' in sys.argv:
        mc = get_monte_carlo_lab()
        # 100 trades with ~60% win rate
        pnls = [random.choice([10, 15, 20, -8, -10, -12]) for _ in range(100)]
        rrs = [random.choice([1.5, 2.0, 2.5, -1.0, -1.2]) for _ in range(100)]
        results = mc.run_simulation(pnls, rrs, 10000, 1.0, num_simulations=1000, trades_per_sim=100)
        print(f"Mean final: ${results['mean_final_balance']}")
        print(f"Risk of ruin: {results['risk_of_ruin']:.2%}")
        print(f"Sharpe: {results['sharpe_ratio']}")
        print(f"Avg DD: {results['avg_max_drawdown_pct']}%")
        print(f"Recommendation: {results['recommendation']}")
        print("MonteCarloLab OK")
