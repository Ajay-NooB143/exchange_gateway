"""
Alpha Agent Evolution Orchestrator
====================================
Continuous Self-Evolution Module 5: Main Loop

Runs the complete evolution loop every 24 hours:
1. Analyze current performance
2. Detect market regime
3. Generate evolved parameters
4. Run Champion vs Challenger battles
5. Promote winners or log failures
6. Generate evolution log

SAFETY: Never overwrites live production files directly.
"""

import os
import sys
import json
import time
import signal
from datetime import datetime, timedelta
from typing import Dict, Optional
import logging

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from analysis_engine import AlphaAnalysisEngine, PerformanceMetrics, RegimeAnalysis
from parameter_evolution import AlphaEvolutionEngine, EvolutionStrategy
from champion_challenger import ChampionChallengerProtocol, Verdict
from evolution_log import EvolutionLogGenerator

log = logging.getLogger('AlphaOrchestrator')


# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

class EvolutionConfig:
    """Configuration for evolution orchestrator"""
    
    # Timing
    EVOLUTION_INTERVAL_HOURS = 24
    BACKTEST_DAYS = 30
    
    # Evolution
    CANDIDATES_PER_EVOLUTION = 5
    MIN_TRADES_FOR_EVOLUTION = 30
    
    # Paths
    LOG_DIR = "/opt/trading-bridge/data"
    EVOLUTION_DIR = "/opt/trading-bridge/data/evolution"
    CHALLENGERS_DIR = "/home/userland/api_workspace/evolution_engine/challengers"
    
    # Safety
    MAX_EVOLUTIONS_PER_DAY = 3
    COOLDOWN_HOURS_BETWEEN_EVOLUTIONS = 6


# ══════════════════════════════════════════════════════════════════════════════
# ORCHESTRATOR
# ══════════════════════════════════════════════════════════════════════════════

class AlphaEvolutionOrchestrator:
    """
    Main orchestrator for continuous self-evolution.
    
    Usage:
        orchestrator = AlphaEvolutionOrchestrator()
        orchestrator.run()  # Runs one evolution cycle
        # or
        orchestrator.run_loop()  # Runs continuously
    """
    
    def __init__(self, config: EvolutionConfig = None):
        self.config = config or EvolutionConfig()
        self.running = False
        
        # Initialize components
        self.analysis_engine = AlphaAnalysisEngine(self.config.LOG_DIR)
        self.evolution_engine = AlphaEvolutionEngine(self.config.EVOLUTION_DIR)
        self.champion_challenger = ChampionChallengerProtocol(
            self.config.EVOLUTION_DIR,
            self.config.BACKTEST_DAYS
        )
        self.log_generator = EvolutionLogGenerator(self.config.EVOLUTION_DIR)
        
        # State
        self.last_evolution_time = None
        self.evolutions_today = 0
        self.current_date = None
        
        # Load state
        self._load_state()
    
    def run(self) -> Dict:
        """
        Run one complete evolution cycle.
        
        Returns:
            Dict with evolution results
        """
        log.info("=" * 70)
        log.info("  EVOLUTION CYCLE STARTING")
        log.info("=" * 70)
        
        result = {
            'timestamp': datetime.now().isoformat(),
            'status': 'started',
            'cycle_results': {}
        }
        
        try:
            # Step 1: Analyze current performance
            log.info("\n[1/6] Analyzing current performance...")
            analysis = self.analysis_engine.analyze(days=7)
            result['cycle_results']['analysis'] = {
                'edge_score': analysis['metrics'].edge_score,
                'win_rate': analysis['metrics'].win_rate,
                'profit_factor': analysis['metrics'].profit_factor,
                'regime': analysis['regime'].current_regime.value,
                'bottlenecks': len(analysis['bottlenecks'])
            }
            
            # Check if we have enough data
            if analysis['total_trades'] < self.config.MIN_TRADES_FOR_EVOLUTION:
                log.warning(f"Insufficient trades: {analysis['total_trades']} < {self.config.MIN_TRADES_FOR_EVOLUTION}")
                result['status'] = 'skipped_insufficient_data'
                return result
            
            # Check cooldown
            if not self._check_cooldown():
                log.warning("Cooldown active, skipping evolution")
                result['status'] = 'skipped_cooldown'
                return result
            
            # Step 2: Detect regime
            log.info("\n[2/6] Detecting market regime...")
            regime = analysis['regime'].current_regime.value
            result['cycle_results']['regime'] = regime
            
            # Step 3: Generate evolved parameters
            log.info("\n[3/6] Generating evolved parameters...")
            current_metrics = {
                'win_rate': analysis['metrics'].win_rate,
                'profit_factor': analysis['metrics'].profit_factor,
                'sharpe_ratio': analysis['metrics'].sharpe_ratio,
                'max_drawdown_pct': analysis['metrics'].max_drawdown_pct,
                'edge_score': analysis['metrics'].edge_score
            }
            
            candidates = self.evolution_engine.evolve(
                current_metrics=current_metrics,
                regime=regime,
                n_candidates=self.config.CANDIDATES_PER_EVOLUTION
            )
            result['cycle_results']['candidates_generated'] = len(candidates)
            
            # Step 4: Run Champion vs Challenger battles
            log.info("\n[4/6] Running Champion vs Challenger battles...")
            battle_results = []
            winner = None
            
            for candidate in candidates:
                log.info(f"  Testing candidate: {candidate['candidate_id']}")
                
                battle_result = self.champion_challenger.battle(
                    challenger_params=candidate['parameters'],
                    challenger_id=candidate['candidate_id'],
                    challenger_source=candidate['source']
                )
                
                battle_results.append({
                    'candidate_id': candidate['candidate_id'],
                    'verdict': battle_result.verdict.value,
                    'reason': battle_result.win_reason,
                    'champion_pf': battle_result.champion_metrics.profit_factor,
                    'challenger_pf': battle_result.challenger_metrics.profit_factor,
                    'champion_sharpe': battle_result.champion_metrics.sharpe_ratio,
                    'challenger_sharpe': battle_result.challenger_metrics.sharpe_ratio,
                    'champion_dd': battle_result.champion_metrics.max_drawdown_pct,
                    'challenger_dd': battle_result.challenger_metrics.max_drawdown_pct
                })
                
                if battle_result.verdict == Verdict.CHALLENGER_WINS:
                    if winner is None or battle_result.challenger_metrics.profit_factor > winner['challenger_pf']:
                        winner = {
                            'candidate_id': candidate['candidate_id'],
                            'parameters': candidate['parameters'],
                            'battle_result': battle_result
                        }
            
            result['cycle_results']['battles'] = battle_results
            result['cycle_results']['winner_found'] = winner is not None
            
            # Step 5: Promote winner if found
            log.info("\n[5/6] Promoting winner...")
            if winner:
                success = self.champion_challenger.promote_challenger(
                    challenger_params=winner['parameters'],
                    challenger_id=winner['candidate_id'],
                    battle_result=winner['battle_result']
                )
                
                result['cycle_results']['promotion'] = {
                    'success': success,
                    'winner_id': winner['candidate_id']
                }
                
                # Log evolution attempt
                self.log_generator.log_evolution_attempt(
                    generation=self.evolution_engine.evolver.generation,
                    candidates_generated=len(candidates),
                    best_candidate_id=winner['candidate_id'],
                    battle_result={
                        'verdict': 'challenger_wins',
                        **{k: v for k, v in battle_results[0].items() if k != 'candidate_id'}
                    },
                    regime=regime,
                    metrics_before=current_metrics
                )
            else:
                # Log failed evolution
                battle_data = battle_results[0] if battle_results else {}
                filtered_data = {k: v for k, v in battle_data.items() if k != 'candidate_id'}
                
                self.log_generator.log_evolution_attempt(
                    generation=self.evolution_engine.evolver.generation,
                    candidates_generated=len(candidates),
                    best_candidate_id=candidates[0]['candidate_id'] if candidates else 'none',
                    battle_result={
                        'verdict': 'challenger_fails',
                        'reason': 'No challenger beat the champion',
                        **filtered_data
                    },
                    regime=regime,
                    metrics_before=current_metrics
                )
            
            # Step 6: Update state
            log.info("\n[6/6] Updating state...")
            self.last_evolution_time = datetime.now()
            self.evolutions_today += 1
            self._save_state()
            
            result['status'] = 'completed'
            
        except Exception as e:
            log.error(f"Evolution cycle failed: {e}")
            result['status'] = 'failed'
            result['error'] = str(e)
        
        log.info("\n" + "=" * 70)
        log.info("  EVOLUTION CYCLE COMPLETE")
        log.info(f"  Status: {result['status']}")
        log.info("=" * 70)
        
        return result
    
    def run_loop(self):
        """Run evolution loop continuously"""
        log.info("Starting evolution loop...")
        log.info(f"Evolution interval: {self.config.EVOLUTION_INTERVAL_HOURS} hours")
        
        self.running = True
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        while self.running:
            try:
                # Run evolution cycle
                result = self.run()
                
                # Log daily summary if new day
                self._check_daily_summary()
                
                # Wait for next cycle
                if self.running:
                    wait_seconds = self.config.EVOLUTION_INTERVAL_HOURS * 3600
                    log.info(f"\nWaiting {self.config.EVOLUTION_INTERVAL_HOURS} hours until next evolution...")
                    time.sleep(wait_seconds)
                    
            except KeyboardInterrupt:
                log.info("Evolution loop interrupted by user")
                break
            except Exception as e:
                log.error(f"Error in evolution loop: {e}")
                time.sleep(300)  # Wait 5 minutes before retrying
        
        log.info("Evolution loop stopped")
    
    def _check_cooldown(self) -> bool:
        """Check if cooldown has elapsed"""
        if self.last_evolution_time is None:
            return True
        
        elapsed = datetime.now() - self.last_evolution_time
        cooldown = timedelta(hours=self.config.COOLDOWN_HOURS_BETWEEN_EVOLUTIONS)
        
        return elapsed >= cooldown
    
    def _check_daily_summary(self):
        """Check if we should log daily summary"""
        today = datetime.now().date()
        
        if self.current_date != today:
            # New day - log summary
            analysis = self.analysis_engine.analyze(days=1)
            
            self.log_generator.log_daily_summary({
                'total_trades': analysis['total_trades'],
                'win_rate': analysis['metrics'].win_rate,
                'total_pnl': analysis['metrics'].total_pnl,
                'edge_score': analysis['metrics'].edge_score,
                'evolutions_attempted': self.evolutions_today,
                'challengers_promoted': 0,  # Would track this
                'current_generation': self.evolution_engine.evolver.generation,
                'regime': analysis['regime'].current_regime.value,
                'volatility': analysis['regime'].volatility_percentile
            })
            
            # Reset daily counter
            self.evolutions_today = 0
            self.current_date = today
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        log.info(f"Received signal {signum}, shutting down...")
        self.running = False
    
    def _save_state(self):
        """Save orchestrator state"""
        state = {
            'last_evolution_time': self.last_evolution_time.isoformat() if self.last_evolution_time else None,
            'evolutions_today': self.evolutions_today,
            'current_date': self.current_date.isoformat() if self.current_date else None
        }
        
        state_file = os.path.join(self.config.EVOLUTION_DIR, 'orchestrator_state.json')
        with open(state_file, 'w') as f:
            json.dump(state, f, indent=2)
    
    def _load_state(self):
        """Load orchestrator state"""
        state_file = os.path.join(self.config.EVOLUTION_DIR, 'orchestrator_state.json')
        
        if os.path.exists(state_file):
            try:
                with open(state_file, 'r') as f:
                    state = json.load(f)
                
                if state.get('last_evolution_time'):
                    self.last_evolution_time = datetime.fromisoformat(state['last_evolution_time'])
                
                self.evolutions_today = state.get('evolutions_today', 0)
                
                if state.get('current_date'):
                    self.current_date = datetime.fromisoformat(state['current_date']).date()
                
                log.info(f"Loaded orchestrator state: last evolution {self.last_evolution_time}")
            except Exception as e:
                log.error(f"Error loading state: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

def main():
    """CLI entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Alpha Agent Evolution Orchestrator')
    parser.add_argument('--mode', choices=['run', 'loop', 'status'], default='run',
                       help='Run mode: run (single cycle), loop (continuous), status')
    parser.add_argument('--log-dir', default='/opt/trading-bridge/data',
                       help='Directory containing trading logs')
    parser.add_argument('--evolution-dir', default='/opt/trading-bridge/data/evolution',
                       help='Directory for evolution data')
    parser.add_argument('--interval', type=int, default=24,
                       help='Evolution interval in hours (for loop mode)')
    parser.add_argument('--backtest-days', type=int, default=30,
                       help='Days of historical data for backtesting')
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(os.path.join(args.evolution_dir, 'evolution.log'))
        ]
    )
    
    # Create config
    config = EvolutionConfig()
    config.LOG_DIR = args.log_dir
    config.EVOLUTION_DIR = args.evolution_dir
    config.EVOLUTION_INTERVAL_HOURS = args.interval
    config.BACKTEST_DAYS = args.backtest_days
    
    # Create orchestrator
    orchestrator = AlphaEvolutionOrchestrator(config)
    
    if args.mode == 'run':
        result = orchestrator.run()
        print(json.dumps(result, indent=2))
        
    elif args.mode == 'loop':
        orchestrator.run_loop()
        
    elif args.mode == 'status':
        analysis = orchestrator.analysis_engine.analyze(days=7)
        print("=" * 70)
        print("  ALPHA AGENT STATUS")
        print("=" * 70)
        print(f"\n  Edge Score: {analysis['metrics'].edge_score}/100")
        print(f"  Win Rate: {analysis['metrics'].win_rate:.1%}")
        print(f"  Profit Factor: {analysis['metrics'].profit_factor:.2f}")
        print(f"  Sharpe Ratio: {analysis['metrics'].sharpe_ratio:.2f}")
        print(f"  Max Drawdown: {analysis['metrics'].max_drawdown_pct:.1f}%")
        print(f"  Regime: {analysis['regime'].current_regime.value}")
        print(f"\n  Bottlenecks: {len(analysis['bottlenecks'])}")
        for b in analysis['bottlenecks']:
            print(f"    [{b.severity}] {b.component}: {b.recommendation}")
        print("=" * 70)


if __name__ == "__main__":
    main()
