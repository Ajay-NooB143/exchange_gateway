"""
Evolution Log Generator
========================
Continuous Self-Evolution Module 4: Documentation & Logging

Generates structured EVOLUTION_LOG.md documenting all evolution attempts.
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional
import logging

log = logging.getLogger('EvolutionLog')


class EvolutionLogGenerator:
    """
    Generates structured evolution logs for transparency.
    
    Output: EVOLUTION_LOG.md in evolution directory
    """
    
    def __init__(self, output_dir: str = "/opt/trading-bridge/data/evolution"):
        self.output_dir = output_dir
        self.log_file = os.path.join(output_dir, 'EVOLUTION_LOG.md')
        os.makedirs(output_dir, exist_ok=True)
    
    def log_evolution_attempt(
        self,
        generation: int,
        candidates_generated: int,
        best_candidate_id: str,
        battle_result: Dict,
        regime: str,
        metrics_before: Dict,
        metrics_after: Optional[Dict] = None
    ):
        """
        Log an evolution attempt to EVOLUTION_LOG.md
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        entry = f"""
---

## Evolution Attempt - Generation {generation}

**Timestamp:** {timestamp}
**Market Regime:** {regime}

### Performance Before Evolution

| Metric | Value |
|--------|-------|
| Edge Score | {metrics_before.get('edge_score', 'N/A')}/100 |
| Win Rate | {metrics_before.get('win_rate', 0):.1%} |
| Profit Factor | {metrics_before.get('profit_factor', 0):.2f} |
| Sharpe Ratio | {metrics_before.get('sharpe_ratio', 0):.2f} |
| Max Drawdown | {metrics_before.get('max_drawdown_pct', 0):.1f}% |

### Evolution Details

- **Candidates Generated:** {candidates_generated}
- **Best Candidate:** {best_candidate_id}
- **Battle Verdict:** {battle_result.get('verdict', 'N/A')}

### Battle Metrics

| Metric | Champion | Challenger | Margin |
|--------|----------|------------|--------|
| Profit Factor | {battle_result.get('champion_pf', 0):.2f} | {battle_result.get('challenger_pf', 0):.2f} | {battle_result.get('pf_margin', 0):+.2f} |
| Sharpe Ratio | {battle_result.get('champion_sharpe', 0):.2f} | {battle_result.get('challenger_sharpe', 0):.2f} | {battle_result.get('sharpe_margin', 0):+.2f} |
| Max Drawdown | {battle_result.get('champion_dd', 0):.1f}% | {battle_result.get('challenger_dd', 0):.1f}% | {battle_result.get('dd_margin', 0):+.1f}% |

### Decision

"""
        
        verdict = battle_result.get('verdict', '')
        if verdict == 'challenger_wins':
            entry += f"""**✓ CHALLENGER PROMOTED TO CHAMPION**

The challenger has demonstrated superior performance across the required metrics.
Parameters have been updated in the live system.

**Reason:** {battle_result.get('reason', 'N/A')}
"""
        elif verdict == 'challenger_fails':
            entry += f"""**✗ CHALLENGER DISCARDED**

The challenger failed to beat the champion in the required metrics.
No changes were made to the live system.

**Reason:** {battle_result.get('reason', 'N/A')}
"""
        else:
            entry += f"""**⚠ INCONCLUSIVE**

The battle was inconclusive. No changes were made.

**Reason:** {battle_result.get('reason', 'N/A')}
"""
        
        # Performance after (if promoted)
        if metrics_after:
            entry += f"""
### Performance After Evolution

| Metric | Value |
|--------|-------|
| Edge Score | {metrics_after.get('edge_score', 'N/A')}/100 |
| Win Rate | {metrics_after.get('win_rate', 0):.1%} |
| Profit Factor | {metrics_after.get('profit_factor', 0):.2f} |
| Sharpe Ratio | {metrics_after.get('sharpe_ratio', 0):.2f} |
| Max Drawdown | {metrics_after.get('max_drawdown_pct', 0):.1f}% |
"""
        
        entry += """
### Mathematical Edge Analysis

The evolution process optimizes for the following mathematical edges:

1. **Profit Factor Optimization**: Maximizing gross profits / gross losses
2. **Risk-Adjusted Returns**: Sharpe ratio ensures returns justify volatility
3. **Capital Preservation**: Max drawdown limits protect against ruin
4. **Regime Adaptation**: Parameters adjust to current market conditions

---
"""
        
        # Append to log file
        self._append_to_log(entry)
        
        log.info(f"Logged evolution attempt: Gen {generation}, Verdict: {verdict}")
    
    def log_daily_summary(self, summary: Dict):
        """Log daily summary"""
        timestamp = datetime.now().strftime("%Y-%m-%d")
        
        entry = f"""
## Daily Summary - {timestamp}

### Trading Performance

- **Total Trades:** {summary.get('total_trades', 0)}
- **Win Rate:** {summary.get('win_rate', 0):.1%}
- **Total P&L:** ${summary.get('total_pnl', 0):.2f}
- **Edge Score:** {summary.get('edge_score', 0)}/100

### Evolution Activity

- **Evolutions Attempted:** {summary.get('evolutions_attempted', 0)}
- **Challengers Promoted:** {summary.get('challengers_promoted', 0)}
- **Current Generation:** {summary.get('current_generation', 0)}

### Market Conditions

- **Regime:** {summary.get('regime', 'unknown')}
- **Volatility:** {summary.get('volatility', 'normal')}

"""
        
        self._append_to_log(entry)
    
    def log_system_status(self, status: Dict):
        """Log system status"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        entry = f"""
## System Status - {timestamp}

### Component Status

| Component | Status |
|-----------|--------|
| Analysis Engine | {status.get('analysis_engine', 'unknown')} |
| Evolution Engine | {status.get('evolution_engine', 'unknown')} |
| Champion/Challenger | {status.get('champion_challenger', 'unknown')} |
| Backtest Engine | {status.get('backtest_engine', 'unknown')} |

### Resource Usage

- **Evolution History Size:** {status.get('history_size', 0)}
- **Best Candidates Stored:** {status.get('best_candidates', 0)}
- **Last Evolution:** {status.get('last_evolution', 'never')}

"""
        
        self._append_to_log(entry)
    
    def initialize_log(self):
        """Initialize the evolution log file"""
        if not os.path.exists(self.log_file):
            header = """# Alpha Agent Evolution Log

This document tracks all evolution attempts of the trading strategy.

## Evolution Protocol

1. **Analysis Phase**: Ingest execution logs and compute metrics
2. **Evolution Phase**: Generate parameter candidates
3. **Battle Phase**: Compare candidates against champion
4. **Decision Phase**: Promote or discard based on backtest results

## Safety Protocol

- **NEVER** overwrites live production files directly
- All challengers tested via backtest before promotion
- Champion must be explicitly promoted after winning
- Full audit trail maintained

## Metrics Tracked

- **Profit Factor**: Gross profits / Gross losses
- **Sharpe Ratio**: Risk-adjusted returns
- **Max Drawdown**: Maximum peak-to-trough decline
- **Win Rate**: Percentage of winning trades
- **Expectancy**: Expected value per trade

---

## Evolution History

"""
            
            with open(self.log_file, 'w') as f:
                f.write(header)
            
            log.info("Initialized evolution log")
    
    def _append_to_log(self, content: str):
        """Append content to log file"""
        # Initialize if doesn't exist
        if not os.path.exists(self.log_file):
            self.initialize_log()
        
        with open(self.log_file, 'a') as f:
            f.write(content)
    
    def read_log(self) -> str:
        """Read the full evolution log"""
        if not os.path.exists(self.log_file):
            return "No evolution log found."
        
        with open(self.log_file, 'r') as f:
            return f.read()
    
    def get_summary(self) -> Dict:
        """Get evolution summary statistics"""
        if not os.path.exists(self.log_file):
            return {'total_evolutions': 0, 'promotions': 0, 'failures': 0}
        
        content = self.read_log()
        
        # Count key events
        total_evolutions = content.count('## Evolution Attempt')
        promotions = content.count('CHALLENGER PROMOTED')
        failures = content.count('CHALLENGER DISCARDED')
        
        return {
            'total_evolutions': total_evolutions,
            'promotions': promotions,
            'failures': failures,
            'success_rate': promotions / total_evolutions if total_evolutions > 0 else 0
        }


# ══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE
# ══════════════════════════════════════════════════════════════════════════════

def log_evolution(**kwargs):
    """Quick evolution logging"""
    generator = EvolutionLogGenerator()
    generator.log_evolution_attempt(**kwargs)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 70)
    print("  EVOLUTION LOG GENERATOR")
    print("=" * 70)
    
    generator = EvolutionLogGenerator()
    generator.initialize_log()
    
    # Example log entry
    generator.log_evolution_attempt(
        generation=1,
        candidates_generated=5,
        best_candidate_id="gen1_mut0",
        battle_result={
            'verdict': 'challenger_wins',
            'champion_pf': 1.35,
            'challenger_pf': 1.52,
            'champion_sharpe': 1.2,
            'challenger_sharpe': 1.45,
            'champion_dd': 4.5,
            'challenger_dd': 3.8,
            'pf_margin': 0.17,
            'sharpe_margin': 0.25,
            'dd_margin': 0.7,
            'reason': 'Challenger wins: PF: 1.52 > 1.35; Sharpe: 1.45 > 1.20; DD: 3.8% < 4.5%'
        },
        regime='ranging',
        metrics_before={'edge_score': 65, 'win_rate': 0.52, 'profit_factor': 1.35, 'sharpe_ratio': 1.2, 'max_drawdown_pct': 4.5}
    )
    
    print("\n  Evolution log created at: /opt/trading-bridge/data/evolution/EVOLUTION_LOG.md")
    print("=" * 70)
