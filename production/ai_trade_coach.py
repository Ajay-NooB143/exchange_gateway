"""
Module 11 — AI Trade Coach
============================
After every trade: analyze win/loss reasons, detect errors
(early entry, late entry, wrong regime, poor liquidity, trap,
overtrading, weak confirmation), generate improvement report,
estimate expected win-rate improvement after corrections,
build personalized learning recommendations.
"""

import logging
import math
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass, field

log = logging.getLogger('AITradeCoach')

ERROR_EARLY_ENTRY = 'Early entry'
ERROR_LATE_ENTRY = 'Late entry'
ERROR_WRONG_REGIME = 'Wrong regime'
ERROR_POOR_LIQUIDITY = 'Poor liquidity'
ERROR_TRAP = 'Trap'
ERROR_OVERTRADING = 'Overtrading'
ERROR_WEAK_CONFIRMATION = 'Weak confirmation'


@dataclass
class TradeAnalysis:
    symbol: str
    direction: str
    outcome: str  # WIN or LOSS
    pnl: float
    errors: List[str] = field(default_factory=list)
    strengths: List[str] = field(default_factory=list)
    score: int = 0  # 0-100 trade quality score
    estimated_improvement: float = 0.0
    recommendation: str = ''
    timestamp: str = ''

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class AITradeCoach:
    """
    Post-trade analysis and coaching system.

    Analyzes why trades won/lost, detects behavioral errors,
    estimates improvement potential, and builds learning plans.
    """

    def __init__(self):
        self._analyses: List[TradeAnalysis] = []
        self._error_counts: Dict[str, int] = {}

    def analyze_trade(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        exit_price: float,
        pnl: float,
        confidence: float,
        session: str = '',
        regime: str = '',
        liquidity_tier: str = '',
        trap_probability: int = 0,
        sweep_score: int = 0,
        orderflow_pressure: str = '',
        duration_minutes: float = 0.0,
        fvg_present: bool = False,
        ob_present: bool = False,
        news_active: bool = False,
        was_managed: bool = False,
    ) -> TradeAnalysis:
        """
        Analyze a completed trade and generate coaching insights.

        Args:
            symbol: Trading symbol
            direction: Trade direction
            entry_price: Entry price
            exit_price: Exit price
            pnl: Trade PnL
            confidence: Signal confidence at entry
            session: Trading session
            regime: Market regime
            liquidity_tier: Liquidity quality tier
            trap_probability: Trap probability at entry
            sweep_score: Sweep score at entry
            orderflow_pressure: Order flow pressure
            duration_minutes: Trade duration
            fvg_present: FVG present at entry
            ob_present: OB present at entry
            news_active: News active during trade
            was_managed: Whether position manager was used

        Returns:
            TradeAnalysis with errors, strengths, and recommendations.
        """
        errors = []
        strengths = []
        outcome = 'WIN' if pnl > 0 else 'LOSS'

        # Error analysis
        if outcome == 'LOSS':
            errors.extend(self._analyze_loss_reasons(
                entry_price, exit_price, direction, confidence,
                session, regime, liquidity_tier, trap_probability,
                sweep_score, pnl, duration_minutes, news_active,
            ))
        else:
            strengths.extend(self._analyze_win_reasons(
                confidence, session, regime, liquidity_tier,
                sweep_score, orderflow_pressure, fvg_present,
                ob_present, was_managed,
            ))

        # Always check for behavioral errors
        behavioral_errors = self._detect_behavioral_errors(
            confidence, trap_probability, news_active, duration_minutes,
        )
        errors.extend(behavioral_errors)

        # Trade quality score (0-100)
        score = self._compute_trade_score(
            outcome, confidence, errors, strengths,
            trap_probability, liquidity_tier, was_managed,
        )

        # Estimated improvement if errors are fixed
        improvement = self._estimate_improvement(errors)

        # Recommendation
        recommendation = self._build_recommendation(errors, strengths, score)

        analysis = TradeAnalysis(
            symbol=symbol,
            direction=direction,
            outcome=outcome,
            pnl=pnl,
            errors=errors,
            strengths=strengths,
            score=score,
            estimated_improvement=improvement,
            recommendation=recommendation,
        )

        self._analyses.append(analysis)

        # Track error frequency
        for err in errors:
            self._error_counts[err] = self._error_counts.get(err, 0) + 1

        return analysis

    def _analyze_loss_reasons(
        self,
        entry: float, exit: float, direction: str,
        confidence: float, session: str, regime: str,
        liquidity_tier: str, trap_probability: int,
        sweep_score: int, pnl: float, duration: float,
        news_active: bool,
    ) -> List[str]:
        reasons = []

        if duration < 15:
            reasons.append(ERROR_EARLY_ENTRY)
        if duration > 480 and abs(pnl) < abs(entry * 0.002):
            reasons.append(ERROR_LATE_ENTRY)
        if regime in ('COMPRESSION', 'TRAP') and confidence < 80:
            reasons.append(ERROR_WRONG_REGIME)
        if liquidity_tier in ('LOW', 'MODERATE') and trap_probability > 50:
            reasons.append(ERROR_POOR_LIQUIDITY)
        if trap_probability > 70:
            reasons.append(ERROR_TRAP)
        if news_active:
            reasons.append(ERROR_WEAK_CONFIRMATION)

        if not reasons:
            reasons.append(ERROR_WEAK_CONFIRMATION)

        return reasons

    def _analyze_win_reasons(self, confidence: float, session: str, regime: str,
                              liquidity_tier: str, sweep_score: int,
                              orderflow_pressure: str, fvg_present: bool,
                              ob_present: bool, was_managed: bool) -> List[str]:
        strengths = []
        if confidence >= 85:
            strengths.append('High confidence entry')
        if session in ('LONDON_OPEN', 'NY_OPEN'):
            strengths.append('Optimal session')
        if regime == 'EXPANSION':
            strengths.append('Expansion regime momentum')
        if liquidity_tier in ('HIGH', 'INSTITUTIONAL'):
            strengths.append('Strong liquidity context')
        if sweep_score >= 60:
            strengths.append('Valid liquidity sweep confirmed')
        if orderflow_pressure in ('BULLISH', 'BEARISH'):
            strengths.append('Order flow alignment')
        if fvg_present and ob_present:
            strengths.append('SMC confluence (FVG + OB)')
        if was_managed:
            strengths.append('Managed position (adaptive exits)')
        return strengths

    def _detect_behavioral_errors(self, confidence: float, trap_probability: int,
                                   news_active: bool, duration: float) -> List[str]:
        errors = []
        recent_losses = sum(1 for a in self._analyses[-5:] if a.outcome == 'LOSS')

        if recent_losses >= 3:
            errors.append(ERROR_OVERTRADING)
        if confidence < 65:
            errors.append(ERROR_WEAK_CONFIRMATION)
        if news_active and confidence > 0:
            errors.append(ERROR_WEAK_CONFIRMATION)

        return errors

    def _compute_trade_score(self, outcome: str, confidence: float,
                              errors: List[str], strengths: List[str],
                              trap_probability: int, liquidity_tier: str,
                              was_managed: bool) -> int:
        score = 50  # Base

        if outcome == 'WIN':
            score += 25
        else:
            score -= 10

        score += min(confidence // 5, 10)
        score -= len(errors) * 8
        score += len(strengths) * 5

        if trap_probability > 70:
            score -= 10
        if liquidity_tier in ('HIGH', 'INSTITUTIONAL'):
            score += 5
        if was_managed:
            score += 5

        return max(0, min(100, score))

    def _estimate_improvement(self, errors: List[str]) -> float:
        improvement_map = {
            ERROR_EARLY_ENTRY: 5.0,
            ERROR_LATE_ENTRY: 3.0,
            ERROR_WRONG_REGIME: 8.0,
            ERROR_POOR_LIQUIDITY: 6.0,
            ERROR_TRAP: 10.0,
            ERROR_OVERTRADING: 12.0,
            ERROR_WEAK_CONFIRMATION: 7.0,
        }
        total = sum(improvement_map.get(e, 0) for e in errors)
        return min(total, 25.0)  # Cap at 25%

    def _build_recommendation(self, errors: List[str], strengths: List[str],
                               score: int) -> str:
        if score >= 80:
            return 'Excellent trade execution. Continue current approach.'
        elif score >= 60:
            return 'Good trade with minor improvements available. Focus on consistency.'
        elif score >= 40:
            base = 'Needs improvement. '
            if errors:
                base += f'Key issues: {", ".join(errors[:2])}. '
            base += 'Review trade plan before next entry.'
            return base
        else:
            base = 'Poor execution. '
            if ERROR_OVERTRADING in errors:
                base += 'Take a break. Step away from the charts. '
            if ERROR_TRAP in errors:
                base += 'Wait for trap confirmation before entering. '
            base += 'Consider paper trading until patterns improve.'
            return base

    def get_most_common_errors(self, top_n: int = 5) -> List[Tuple[str, int]]:
        sorted_errors = sorted(self._error_counts.items(), key=lambda x: -x[1])
        return sorted_errors[:top_n]

    def get_improvement_plan(self) -> str:
        """Generate a personalized learning plan based on error history."""
        if not self._error_counts:
            return 'No trades analyzed yet. Start trading to receive coaching.'

        total = sum(self._error_counts.values())
        lines = ['📚 PERSONALIZED LEARNING PLAN', '────────────────────']

        for error, count in sorted(self._error_counts.items(), key=lambda x: -x[1]):
            pct = count / max(total, 1) * 100
            fix = self._get_fix_for_error(error)
            lines.append(f'• {error} ({pct:.0f}% of errors)')
            lines.append(f'  Fix: {fix}')

        overall_improvement = self._estimate_improvement(list(self._error_counts.keys()))
        lines.append(f'\nEstimated win-rate improvement: +{overall_improvement:.0f}%')
        lines.append(f'Total trades analyzed: {len(self._analyses)}')

        return '\n'.join(lines)

    def _get_fix_for_error(self, error: str) -> str:
        fixes = {
            ERROR_EARLY_ENTRY: 'Wait for candle close confirmation before entry. Use limit orders at key levels.',
            ERROR_LATE_ENTRY: 'Set price alerts at key levels. Use pending orders for breakout entries.',
            ERROR_WRONG_REGIME: 'Check regime detector first. Avoid COMPRESSION for directional trades. Trade with regime, not against.',
            ERROR_POOR_LIQUIDITY: 'Only trade during London/NY sessions. Check killzone quality score before entry.',
            ERROR_TRAP: 'Confirm trap probability < 60. Wait for reclaim of swept level before entry.',
            ERROR_OVERTRADING: 'After 3 consecutive losses, stop trading for 24h. Stick to highest-confidence setups only.',
            ERROR_WEAK_CONFIRMATION: 'Require minimum 3 confluences: OB/FVG + Session + Regime + Sweep. Never trade on a single indicator.',
        }
        return fixes.get(error, 'Review trade plan and follow system rules.')

    def get_win_rate_with_corrections(self) -> float:
        """Estimate win rate if all detected errors were fixed."""
        recent = self._analyses[-50:]
        if not recent:
            return 0.0

        current_wins = sum(1 for a in recent if a.outcome == 'WIN')
        current_wr = current_wins / max(len(recent), 1)

        avg_improvement = sum(a.estimated_improvement for a in recent) / max(len(recent), 1)
        corrected_wr = current_wr + (avg_improvement / 100) * (1 - current_wr)

        return min(corrected_wr, 1.0)


_coach: Optional[AITradeCoach] = None


def get_trade_coach() -> AITradeCoach:
    global _coach
    if _coach is None:
        _coach = AITradeCoach()
    return _coach


if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    if '--test' in sys.argv:
        coach = get_trade_coach()

        # Simulate some trades
        result = coach.analyze_trade('XAUUSD', 'BUY', 2350, 2330, -20, 72,
                                     session='ASIAN', regime='COMPRESSION',
                                     liquidity_tier='LOW', trap_probability=75,
                                     sweep_score=30, duration_minutes=10)
        print(f"Trade: {result.outcome} | Score: {result.score} | Errors: {result.errors}")
        print(f"Recommendation: {result.recommendation}")

        result = coach.analyze_trade('XAUUSD', 'BUY', 2355, 2375, 20, 92,
                                     session='LONDON_OPEN', regime='EXPANSION',
                                     liquidity_tier='HIGH', trap_probability=25,
                                     sweep_score=70, duration_minutes=120, was_managed=True)
        print(f"\nTrade: {result.outcome} | Score: {result.score} | Strengths: {result.strengths}")

        print(f"\nCommon errors: {coach.get_most_common_errors()}")
        print(f"\n{coach.get_improvement_plan()}")
        print("\nAITradeCoach OK")
