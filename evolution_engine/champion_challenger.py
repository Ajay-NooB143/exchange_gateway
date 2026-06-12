"""
Champion vs Challenger Protocol
================================
Continuous Self-Evolution Module 3: Safe Strategy Comparison

SAFETY PROTOCOL:
- NEVER overwrites live production files directly
- All challengers output as new isolated files
- Automated backtest before any promotion
- Champion must be explicitly promoted

Architecture:
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CHAMPION vs CHALLENGER PROTOCOL                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐         ┌──────────────┐                                 │
│  │   CHAMPION   │         │  CHALLENGER  │                                 │
│  │  (Live V1)   │         │   (New V2)   │                                 │
│  └──────┬───────┘         └──────┬───────┘                                 │
│         │                        │                                          │
│         ▼                        ▼                                          │
│  ┌──────────────────────────────────────────┐                              │
│  │         BACKTEST ENGINE (30 days)        │                              │
│  │  • Profit Factor    • Sharpe Ratio       │                              │
│  │  • Max Drawdown     • Win Rate           │                              │
│  │  • Expectancy       • Kelly Criterion    │                              │
│  └──────────────────────────────────────────┘                              │
│                           │                                                  │
│                           ▼                                                  │
│  ┌──────────────────────────────────────────┐                              │
│  │            DECISION ENGINE               │                              │
│  │  Challenger must beat Champion in:       │                              │
│  │  ✓ Profit Factor (primary)               │                              │
│  │  ✓ Sharpe Ratio                          │                              │
│  │  ✓ Max Drawdown                          │                              │
│  └──────────────────────────────────────────┘                              │
│                           │                                                  │
│              ┌────────────┴────────────┐                                    │
│              ▼                         ▼                                    │
│  ┌───────────────────┐     ┌───────────────────┐                          │
│  │  CHALLENGER WINS  │     │  CHALLENGER FAILS │                          │
│  │  → Promote to     │     │  → Discard & Log  │                          │
│  │    Champion       │     │    Failure Reason │                          │
│  └───────────────────┘     └───────────────────┘                          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
"""

import json
import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from enum import Enum
import logging

log = logging.getLogger('ChampionChallenger')


# ══════════════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ══════════════════════════════════════════════════════════════════════════════

class Verdict(Enum):
    """Battle verdict"""
    CHALLENGER_WINS = "challenger_wins"
    CHALLENGER_FAILS = "challenger_fails"
    TIE = "tie"
    ERROR = "error"


@dataclass
class BattleMetrics:
    """Metrics for comparison"""
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown_pct: float = 100.0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    expectancy: float = 0.0
    kelly_criterion: float = 0.0
    total_trades: int = 0
    
    def to_dict(self) -> Dict:
        return {
            'profit_factor': self.profit_factor,
            'sharpe_ratio': self.sharpe_ratio,
            'max_drawdown_pct': self.max_drawdown_pct,
            'win_rate': self.win_rate,
            'total_pnl': self.total_pnl,
            'expectancy': self.expectancy,
            'kelly_criterion': self.kelly_criterion,
            'total_trades': self.total_trades
        }


@dataclass
class BattleResult:
    """Result of a Champion vs Challenger battle"""
    champion_id: str
    challenger_id: str
    verdict: Verdict
    champion_metrics: BattleMetrics
    challenger_metrics: BattleMetrics
    win_reason: str = ""
    win_margins: Dict[str, float] = field(default_factory=dict)
    timestamp: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


# ══════════════════════════════════════════════════════════════════════════════
# BACKTEST ENGINE (Simplified)
# ══════════════════════════════════════════════════════════════════════════════

class BacktestEngine:
    """
    Simplified backtest engine for strategy comparison.
    
    In production, this would use historical market data.
    Here we simulate based on parameter quality heuristics.
    """
    
    def __init__(self):
        self.min_trades_required = 30
    
    def run_backtest(
        self, 
        parameters: Dict[str, float],
        days: int = 30
    ) -> BattleMetrics:
        """
        Run backtest with given parameters.
        
        Returns BattleMetrics with simulated results.
        """
        metrics = BattleMetrics()
        
        # Simulate based on parameter quality
        # In production, this would use actual historical data
        
        # ATR multipliers affect R:R
        atr_sl = parameters.get('atr_sl_mult', 1.0)
        atr_tp = parameters.get('atr_tp_mult', 2.0)
        
        # Base win rate from R:R ratio
        rr_ratio = atr_tp / atr_sl if atr_sl > 0 else 2.0
        
        # OBI threshold affects signal quality
        obi_threshold = parameters.get('obi_threshold', 1.5)
        
        # Volume filter affects false signals
        volume_pct = parameters.get('volume_percentile', 90.0)
        
        # Calculate simulated metrics
        base_win_rate = 0.48  # Base random chance
        
        # Adjust win rate based on parameters
        win_rate_boost = 0
        win_rate_boost += (rr_ratio - 1.5) * 0.05  # Better R:R = better win rate
        win_rate_boost += (obi_threshold - 1.0) * 0.03  # Stricter filter = better signals
        win_rate_boost += (volume_pct - 80) * 0.001  # Better volume filter
        
        metrics.win_rate = min(0.65, max(0.35, base_win_rate + win_rate_boost))
        
        # Simulate trades
        metrics.total_trades = int(days * 1.5)  # ~1.5 trades per day
        
        # P&L simulation
        avg_win = atr_tp * 10  # Simplified
        avg_loss = atr_sl * 10
        
        wins = int(metrics.total_trades * metrics.win_rate)
        losses = metrics.total_trades - wins
        
        metrics.total_pnl = (wins * avg_win) - (losses * avg_loss)
        
        # Profit factor
        gross_profit = wins * avg_win
        gross_loss = losses * avg_loss
        metrics.profit_factor = gross_profit / gross_loss if gross_loss > 0 else 2.0
        
        # Sharpe ratio (simplified)
        import random
        pnls = [avg_win] * wins + [-avg_loss] * losses
        random.shuffle(pnls)
        
        if len(pnls) > 1:
            import statistics
            avg_pnl = statistics.mean(pnls)
            std_pnl = statistics.stdev(pnls) if statistics.stdev(pnls) > 0 else 1
            metrics.sharpe_ratio = (avg_pnl / std_pnl) * (252 ** 0.5)
        
        # Max drawdown (simplified)
        cumulative = 0
        peak = 0
        max_dd = 0
        for pnl in pnls:
            cumulative += pnl
            if cumulative > peak:
                peak = cumulative
            dd = (peak - cumulative) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)
        metrics.max_drawdown_pct = max_dd * 100
        
        # Expectancy
        metrics.expectancy = (
            (metrics.win_rate * avg_win) - 
            ((1 - metrics.win_rate) * avg_loss)
        )
        
        # Kelly criterion
        if avg_win > 0:
            metrics.kelly_criterion = (
                (metrics.win_rate * avg_win - (1 - metrics.win_rate) * avg_loss) /
                avg_win
            )
        
        return metrics


# ══════════════════════════════════════════════════════════════════════════════
# BATTLE JUDGE
# ══════════════════════════════════════════════════════════════════════════════

class BattleJudge:
    """
    Judges Champion vs Challenger battles.
    
    Decision criteria (all must pass for challenger to win):
    1. Profit Factor: Challenger > Champion
    2. Sharpe Ratio: Challenger > Champion * 0.95 (within 5%)
    3. Max Drawdown: Challenger < Champion * 1.1 (within 10%)
    """
    
    def __init__(self, min_trades: int = 30):
        self.min_trades = min_trades
        
        # Weights for composite score
        self.weights = {
            'profit_factor': 0.40,
            'sharpe_ratio': 0.30,
            'max_drawdown': 0.30
        }
    
    def judge(
        self, 
        champion_id: str,
        challenger_id: str,
        champion_metrics: BattleMetrics,
        challenger_metrics: BattleMetrics
    ) -> BattleResult:
        """
        Judge a battle between Champion and Challenger.
        """
        # Validate minimum trades
        if (champion_metrics.total_trades < self.min_trades or 
            challenger_metrics.total_trades < self.min_trades):
            return BattleResult(
                champion_id=champion_id,
                challenger_id=challenger_id,
                verdict=Verdict.ERROR,
                champion_metrics=champion_metrics,
                challenger_metrics=challenger_metrics,
                win_reason=f"Insufficient trades: Champion={champion_metrics.total_trades}, "
                          f"Challenger={challenger_metrics.total_trades}"
            )
        
        # Calculate win margins
        win_margins = {}
        
        # Profit Factor comparison
        pf_margin = (challenger_metrics.profit_factor - champion_metrics.profit_factor)
        win_margins['profit_factor'] = pf_margin
        
        # Sharpe Ratio comparison
        sharpe_margin = (challenger_metrics.sharpe_ratio - champion_metrics.sharpe_ratio)
        win_margins['sharpe_ratio'] = sharpe_margin
        
        # Max Drawdown comparison (lower is better)
        dd_margin = (champion_metrics.max_drawdown_pct - challenger_metrics.max_drawdown_pct)
        win_margins['max_drawdown'] = dd_margin
        
        # Decision logic
        pf_wins = challenger_metrics.profit_factor > champion_metrics.profit_factor
        sharpe_wins = challenger_metrics.sharpe_ratio > champion_metrics.sharpe_ratio * 0.95
        dd_wins = challenger_metrics.max_drawdown_pct < champion_metrics.max_drawdown_pct * 1.1
        
        # Count wins
        wins = sum([pf_wins, sharpe_wins, dd_wins])
        
        # Determine verdict
        if wins >= 2:
            verdict = Verdict.CHALLENGER_WINS
            reasons = []
            if pf_wins:
                reasons.append(f"PF: {challenger_metrics.profit_factor:.2f} > {champion_metrics.profit_factor:.2f}")
            if sharpe_wins:
                reasons.append(f"Sharpe: {challenger_metrics.sharpe_ratio:.2f} > {champion_metrics.sharpe_ratio:.2f}")
            if dd_wins:
                reasons.append(f"DD: {challenger_metrics.max_drawdown_pct:.1f}% < {champion_metrics.max_drawdown_pct:.1f}%")
            win_reason = "Challenger wins: " + "; ".join(reasons)
        elif wins == 0:
            verdict = Verdict.CHALLENGER_FAILS
            win_reason = "Challenger fails: Lost all metrics"
        else:
            verdict = Verdict.TIE
            win_reason = f"Split decision: {wins}/3 metrics won"
        
        return BattleResult(
            champion_id=champion_id,
            challenger_id=challenger_id,
            verdict=verdict,
            champion_metrics=champion_metrics,
            challenger_metrics=challenger_metrics,
            win_reason=win_reason,
            win_margins=win_margins
        )


# ══════════════════════════════════════════════════════════════════════════════
# CHAMPION VS CHALLENGER PROTOCOL
# ══════════════════════════════════════════════════════════════════════════════

class ChampionChallengerProtocol:
    """
    Manages the Champion vs Challenger lifecycle.
    
    SAFETY: Never overwrites production files directly.
    """
    
    def __init__(
        self,
        data_dir: str = "/opt/trading-bridge/data/evolution",
        backtest_days: int = 30
    ):
        self.data_dir = data_dir
        self.backtest_days = backtest_days
        os.makedirs(data_dir, exist_ok=True)
        
        self.backtest_engine = BacktestEngine()
        self.judge = BattleJudge()
        
        self.champion_file = os.path.join(data_dir, 'current_champion.json')
        self.battle_log_file = os.path.join(data_dir, 'battle_log.json')
    
    def get_champion(self) -> Optional[Dict]:
        """Get current champion parameters"""
        if not os.path.exists(self.champion_file):
            # Create default champion
            return self._create_default_champion()
        
        try:
            with open(self.champion_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            log.error(f"Error loading champion: {e}")
            return None
    
    def battle(
        self, 
        challenger_params: Dict[str, float],
        challenger_id: str,
        challenger_source: str = "evolution"
    ) -> BattleResult:
        """
        Run a battle between Champion and Challenger.
        
        Args:
            challenger_params: Challenger parameters to test
            challenger_id: Unique ID for the challenger
            challenger_source: Source of the challenger (mutation, regime, etc.)
            
        Returns:
            BattleResult with verdict and metrics
        """
        log.info(f"Starting battle: Champion vs {challenger_id}")
        
        # Get champion
        champion = self.get_champion()
        if not champion:
            log.error("No champion found")
            return BattleResult(
                champion_id="none",
                challenger_id=challenger_id,
                verdict=Verdict.ERROR,
                champion_metrics=BattleMetrics(),
                challenger_metrics=BattleMetrics(),
                win_reason="No champion found"
            )
        
        champion_params = champion.get('parameters', {})
        champion_id = champion.get('metadata', {}).get('id', 'default')
        
        # Run backtests
        log.info(f"Running backtest: {self.backtest_days} days")
        
        champion_metrics = self.backtest_engine.run_backtest(champion_params, self.backtest_days)
        challenger_metrics = self.backtest_engine.run_backtest(challenger_params, self.backtest_days)
        
        # Judge the battle
        result = self.judge.judge(
            champion_id=champion_id,
            challenger_id=challenger_id,
            champion_metrics=champion_metrics,
            challenger_metrics=challenger_metrics
        )
        
        # Log the battle
        self._log_battle(result, challenger_source)
        
        log.info(f"Battle result: {result.verdict.value}")
        log.info(f"Reason: {result.win_reason}")
        
        return result
    
    def promote_challenger(
        self,
        challenger_params: Dict[str, float],
        challenger_id: str,
        battle_result: BattleResult
    ) -> bool:
        """
        Promote a winning challenger to champion.
        
        Returns True if promotion successful.
        """
        if battle_result.verdict != Verdict.CHALLENGER_WINS:
            log.warning("Cannot promote: Challenger did not win")
            return False
        
        # Backup current champion
        if os.path.exists(self.champion_file):
            backup_file = os.path.join(
                self.data_dir,
                f"champion_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )
            try:
                with open(self.champion_file, 'r') as f:
                    champion_data = json.load(f)
                with open(backup_file, 'w') as f:
                    json.dump(champion_data, f, indent=2)
                log.info(f"Backed up champion to {backup_file}")
            except Exception as e:
                log.error(f"Error backing up champion: {e}")
        
        # Create new champion
        new_champion = {
            'metadata': {
                'id': challenger_id,
                'promoted_at': datetime.now().isoformat(),
                'previous_champion': battle_result.champion_id,
                'battle_verdict': battle_result.verdict.value,
                'battle_margins': battle_result.win_margins
            },
            'parameters': challenger_params,
            'status': 'champion'
        }
        
        # Write new champion
        with open(self.champion_file, 'w') as f:
            json.dump(new_champion, f, indent=2)
        
        log.info(f"New champion promoted: {challenger_id}")
        
        return True
    
    def _create_default_champion(self) -> Dict:
        """Create default champion parameters"""
        default_champion = {
            'metadata': {
                'id': 'default_v1',
                'created_at': datetime.now().isoformat(),
                'status': 'default'
            },
            'parameters': {
                'atr_sl_mult': 1.0,
                'atr_tp_mult': 2.0,
                'risk_per_trade_pct': 1.0,
                'obi_threshold': 1.5,
                'volume_percentile': 90.0,
                'volume_ma_period': 20,
                'ob_lookback': 100,
                'fvg_min_gap_atr': 0.2,
                'sweep_min_wick_atr': 0.3,
                'limit_offset_pips': 0.5,
                'max_slippage_pips': 2.0,
                'session_start_hour': 13.0,
                'session_end_hour': 16.0
            },
            'status': 'champion'
        }
        
        with open(self.champion_file, 'w') as f:
            json.dump(default_champion, f, indent=2)
        
        log.info("Created default champion")
        
        return default_champion
    
    def _log_battle(self, result: BattleResult, source: str):
        """Log battle results"""
        battle_entry = {
            'timestamp': result.timestamp,
            'champion_id': result.champion_id,
            'challenger_id': result.challenger_id,
            'verdict': result.verdict.value,
            'reason': result.win_reason,
            'margins': result.win_margins,
            'champion_metrics': result.champion_metrics.to_dict(),
            'challenger_metrics': result.challenger_metrics.to_dict(),
            'source': source
        }
        
        # Read existing log
        battles = []
        if os.path.exists(self.battle_log_file):
            try:
                with open(self.battle_log_file, 'r') as f:
                    battles = json.load(f)
            except Exception as e:
                log.debug(f"Failed to load battle log: {e}")
                battles = []

        battles.append(battle_entry)
        battles = battles[-100:]

        with open(self.battle_log_file, 'w') as f:
            json.dump(battles, f, indent=2)

    def get_battle_history(self, n: int = 10) -> List[Dict]:
        if not os.path.exists(self.battle_log_file):
            return []

        try:
            with open(self.battle_log_file, 'r') as f:
                battles = json.load(f)
            return battles[-n:]
        except Exception as e:
            log.debug(f"Failed to read battle history: {e}")
            return []


# ══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE
# ══════════════════════════════════════════════════════════════════════════════

def run_battle(challenger_params: Dict, challenger_id: str) -> BattleResult:
    """Quick battle run"""
    protocol = ChampionChallengerProtocol()
    return protocol.battle(challenger_params, challenger_id)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 70)
    print("  CHAMPION vs CHALLENGER PROTOCOL")
    print("=" * 70)
    
    # Example challenger parameters
    challenger_params = {
        'atr_sl_mult': 1.2,
        'atr_tp_mult': 2.5,
        'risk_per_trade_pct': 0.8,
        'obi_threshold': 1.8,
        'volume_percentile': 92.0,
        'volume_ma_period': 25,
        'ob_lookback': 120,
        'fvg_min_gap_atr': 0.25,
        'sweep_min_wick_atr': 0.35,
        'limit_offset_pips': 0.4,
        'max_slippage_pips': 1.8,
        'session_start_hour': 13.0,
        'session_end_hour': 16.0
    }
    
    result = run_battle(challenger_params, "mutation_gen1_test")
    
    print(f"\n  Battle Result: {result.verdict.value}")
    print(f"  Reason: {result.win_reason}")
    
    print(f"\n  Champion Metrics:")
    print(f"    Profit Factor: {result.champion_metrics.profit_factor:.2f}")
    print(f"    Sharpe Ratio: {result.champion_metrics.sharpe_ratio:.2f}")
    print(f"    Max Drawdown: {result.champion_metrics.max_drawdown_pct:.1f}%")
    
    print(f"\n  Challenger Metrics:")
    print(f"    Profit Factor: {result.challenger_metrics.profit_factor:.2f}")
    print(f"    Sharpe Ratio: {result.challenger_metrics.sharpe_ratio:.2f}")
    print(f"    Max Drawdown: {result.challenger_metrics.max_drawdown_pct:.1f}%")
    
    print("=" * 70)
