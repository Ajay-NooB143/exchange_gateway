"""
Alpha Agent Parameter Evolution Engine
=======================================
Continuous Self-Evolution Module 2: Dynamic Parameter Tuning

Evolves strategy parameters using:
- Bayesian-inspired optimization
- Regime-adaptive adjustments
- Historical performance feedback

SAFETY: Outputs only new files, never overwrites production.
"""

import json
import os
import time
import random
import math
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime
from enum import Enum
import logging

log = logging.getLogger('AlphaEvolution')


# ══════════════════════════════════════════════════════════════════════════════
# PARAMETER SPACE
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ParameterRange:
    """Defines evolution range for a parameter"""
    name: str
    current_value: float
    min_value: float
    max_value: float
    step_size: float
    param_type: str = "float"  # "float", "int", "bool"
    
    def random_value(self) -> float:
        """Generate random value within range"""
        if self.param_type == "int":
            return float(random.randint(int(self.min_value), int(self.max_value)))
        return random.uniform(self.min_value, self.max_value)
    
    def clip(self, value: float) -> float:
        """Clip value to valid range"""
        value = max(self.min_value, min(self.max_value, value))
        if self.param_type == "int":
            return float(round(value))
        return value


# Default parameter space for XAUUSD trading
DEFAULT_PARAMETER_SPACE = {
    # Risk Management
    'atr_sl_mult': ParameterRange(
        name='atr_sl_mult', current_value=1.0,
        min_value=0.3, max_value=2.5, step_size=0.1
    ),
    'atr_tp_mult': ParameterRange(
        name='atr_tp_mult', current_value=2.0,
        min_value=1.0, max_value=4.0, step_size=0.2
    ),
    'risk_per_trade_pct': ParameterRange(
        name='risk_per_trade_pct', current_value=1.0,
        min_value=0.5, max_value=2.0, step_size=0.1
    ),
    
    # Signal Generation
    'obi_threshold': ParameterRange(
        name='obi_threshold', current_value=1.5,
        min_value=1.0, max_value=3.0, step_size=0.1
    ),
    'volume_percentile': ParameterRange(
        name='volume_percentile', current_value=90.0,
        min_value=70.0, max_value=99.0, step_size=1.0
    ),
    'volume_ma_period': ParameterRange(
        name='volume_ma_period', current_value=20,
        min_value=5, max_value=50, step_size=1.0, param_type="int"
    ),
    
    # Smart Money Matrix
    'ob_lookback': ParameterRange(
        name='ob_lookback', current_value=100,
        min_value=20, max_value=200, step_size=10.0, param_type="int"
    ),
    'fvg_min_gap_atr': ParameterRange(
        name='fvg_min_gap_atr', current_value=0.2,
        min_value=0.05, max_value=0.5, step_size=0.05
    ),
    'sweep_min_wick_atr': ParameterRange(
        name='sweep_min_wick_atr', current_value=0.3,
        min_value=0.1, max_value=0.8, step_size=0.05
    ),
    
    # Execution
    'limit_offset_pips': ParameterRange(
        name='limit_offset_pips', current_value=0.5,
        min_value=0.0, max_value=2.0, step_size=0.1
    ),
    'max_slippage_pips': ParameterRange(
        name='max_slippage_pips', current_value=2.0,
        min_value=0.5, max_value=5.0, step_size=0.5
    ),
    
    # Time Filter
    'session_start_hour': ParameterRange(
        name='session_start_hour', current_value=13.0,
        min_value=0.0, max_value=23.0, step_size=1.0, param_type="int"
    ),
    'session_end_hour': ParameterRange(
        name='session_end_hour', current_value=16.0,
        min_value=0.0, max_value=23.0, step_size=1.0, param_type="int"
    ),
}


# ══════════════════════════════════════════════════════════════════════════════
# EVOLUTION STRATEGIES
# ══════════════════════════════════════════════════════════════════════════════

class EvolutionStrategy(Enum):
    """Available evolution strategies"""
    RANDOM_SEARCH = "random_search"
    GRID_SEARCH = "grid_search"
    BAYESIAN = "bayesian"
    REGIME_ADAPTIVE = "regime_adaptive"
    MUTATION = "mutation"


@dataclass
class EvolutionCandidate:
    """A parameter set to be evaluated"""
    id: str
    parameters: Dict[str, float]
    source: str  # "mutation", "crossover", "regime_adjustment"
    generation: int
    parent_id: Optional[str] = None
    fitness: float = 0.0
    backtest_results: Optional[Dict] = None


# ══════════════════════════════════════════════════════════════════════════════
# PARAMETER EVOLVER
# ══════════════════════════════════════════════════════════════════════════════

class ParameterEvolver:
    """
    Evolves strategy parameters based on performance feedback.
    
    Strategies:
    1. Random Search: Explore parameter space randomly
    2. Mutation: Small perturbations of best parameters
    3. Regime-Adaptive: Adjust based on market regime
    4. Crossover: Combine good parameters from different candidates
    """
    
    def __init__(
        self,
        parameter_space: Dict[str, ParameterRange] = None,
        evolution_dir: str = "/opt/trading-bridge/data/evolution"
    ):
        self.parameter_space = parameter_space or DEFAULT_PARAMETER_SPACE
        self.evolution_dir = evolution_dir
        os.makedirs(evolution_dir, exist_ok=True)
        
        self.generation = 0
        self.best_candidates: List[EvolutionCandidate] = []
        self.history: List[EvolutionCandidate] = []
        
        # Load state if exists
        self._load_state()
    
    def evolve(
        self,
        current_metrics: Dict,
        regime: str,
        strategy: EvolutionStrategy = EvolutionStrategy.MUTATION,
        n_candidates: int = 5
    ) -> List[EvolutionCandidate]:
        """
        Generate new parameter candidates.
        
        Args:
            current_metrics: Current performance metrics
            regime: Current market regime
            strategy: Evolution strategy to use
            n_candidates: Number of candidates to generate
            
        Returns:
            List of EvolutionCandidate objects
        """
        self.generation += 1
        candidates = []
        
        if strategy == EvolutionStrategy.RANDOM_SEARCH:
            candidates = self._random_search(n_candidates)
        elif strategy == EvolutionStrategy.MUTATION:
            candidates = self._mutation(n_candidates, current_metrics)
        elif strategy == EvolutionStrategy.REGIME_ADAPTIVE:
            candidates = self._regime_adaptive(n_candidates, regime)
        elif strategy == EvolutionStrategy.CROSSOVER:
            candidates = self._crossover(n_candidates)
        else:
            candidates = self._random_search(n_candidates)
        
        # Save state
        self._save_state()
        
        log.info(f"Generated {len(candidates)} candidates (gen {self.generation})")
        
        return candidates
    
    def update_fitness(self, candidate_id: str, fitness: float, backtest_results: Dict):
        """Update fitness score for a candidate after backtesting"""
        for candidate in self.best_candidates + self.history:
            if candidate.id == candidate_id:
                candidate.fitness = fitness
                candidate.backtest_results = backtest_results
                
                # Add to best if better
                if len(self.best_candidates) < 10:
                    self.best_candidates.append(candidate)
                    self.best_candidates.sort(key=lambda c: c.fitness, reverse=True)
                    self.best_candidates = self.best_candidates[:10]
                elif fitness > self.best_candidates[-1].fitness:
                    self.best_candidates[-1] = candidate
                    self.best_candidates.sort(key=lambda c: c.fitness, reverse=True)
                
                log.info(f"Updated candidate {candidate_id}: fitness={fitness:.3f}")
                break
        
        self._save_state()
    
    def get_best_parameters(self) -> Dict[str, float]:
        """Get current best parameters"""
        if self.best_candidates:
            return self.best_candidates[0].parameters.copy()
        return {k: v.current_value for k, v in self.parameter_space.items()}
    
    def _random_search(self, n: int) -> List[EvolutionCandidate]:
        """Random search in parameter space"""
        candidates = []
        
        for i in range(n):
            params = {}
            for name, prange in self.parameter_space.items():
                params[name] = prange.random_value()
            
            candidate = EvolutionCandidate(
                id=f"gen{self.generation}_rand{i}",
                parameters=params,
                source="random_search",
                generation=self.generation
            )
            candidates.append(candidate)
            self.history.append(candidate)
        
        return candidates
    
    def _mutation(self, n: int, metrics: Dict) -> List[EvolutionCandidate]:
        """Mutate best parameters"""
        candidates = []
        base_params = self.get_best_parameters()
        
        # Determine mutation strength based on performance
        win_rate = metrics.get('win_rate', 0.5)
        profit_factor = metrics.get('profit_factor', 1.0)
        
        # If doing well, smaller mutations; if doing poorly, larger mutations
        if profit_factor > 1.5 and win_rate > 0.55:
            mutation_strength = 0.1  # Fine-tuning
        elif profit_factor > 1.0:
            mutation_strength = 0.2  # Moderate exploration
        else:
            mutation_strength = 0.3  # Aggressive exploration
        
        for i in range(n):
            params = base_params.copy()
            
            # Randomly mutate 2-4 parameters
            n_mutations = random.randint(2, 4)
            mutated_keys = random.sample(list(params.keys()), min(n_mutations, len(params)))
            
            for key in mutated_keys:
                if key in self.parameter_space:
                    prange = self.parameter_space[key]
                    current = params[key]
                    
                    # Gaussian mutation
                    delta = random.gauss(0, mutation_strength * (prange.max_value - prange.min_value))
                    new_value = current + delta
                    params[key] = prange.clip(new_value)
            
            candidate = EvolutionCandidate(
                id=f"gen{self.generation}_mut{i}",
                parameters=params,
                source="mutation",
                generation=self.generation,
                parent_id=self.best_candidates[0].id if self.best_candidates else None
            )
            candidates.append(candidate)
            self.history.append(candidate)
        
        return candidates
    
    def _regime_adaptive(self, n: int, regime: str) -> List[EvolutionCandidate]:
        """Generate regime-adaptive parameters"""
        candidates = []
        base_params = self.get_best_parameters()
        
        # Regime-specific adjustments
        adjustments = {
            'trending_up': {
                'atr_sl_mult': 1.2,
                'atr_tp_mult': 2.2,
                'volume_ma_period': 25
            },
            'trending_down': {
                'atr_sl_mult': 1.1,
                'atr_tp_mult': 1.8,
                'volume_ma_period': 25
            },
            'ranging': {
                'atr_sl_mult': 0.7,
                'atr_tp_mult': 1.2,
                'obi_threshold': 1.2
            },
            'high_volatility': {
                'atr_sl_mult': 1.5,
                'atr_tp_mult': 2.8,
                'risk_per_trade_pct': 0.7,
                'max_slippage_pips': 3.0
            },
            'low_volatility': {
                'atr_sl_mult': 0.8,
                'atr_tp_mult': 1.3,
                'risk_per_trade_pct': 1.2,
                'obi_threshold': 1.3
            }
        }
        
        regime_adj = adjustments.get(regime, {})
        
        for i in range(n):
            params = base_params.copy()
            
            # Apply regime adjustments with variation
            for key, adjustment in regime_adj.items():
                if key in params and key in self.parameter_space:
                    prange = self.parameter_space[key]
                    base_value = params[key]
                    
                    # Add small random variation to adjustment
                    variation = random.gauss(0, 0.1 * (prange.max_value - prange.min_value))
                    new_value = adjustment * (1 + variation)
                    params[key] = prange.clip(new_value)
            
            # Add some random mutations
            n_extra_mutations = random.randint(1, 3)
            extra_keys = random.sample(
                [k for k in params.keys() if k not in regime_adj],
                min(n_extra_mutations, len(params) - len(regime_adj))
            )
            
            for key in extra_keys:
                if key in self.parameter_space:
                    prange = self.parameter_space[key]
                    delta = random.gauss(0, 0.15 * (prange.max_value - prange.min_value))
                    params[key] = prange.clip(params[key] + delta)
            
            candidate = EvolutionCandidate(
                id=f"gen{self.generation}_reg{i}",
                parameters=params,
                source=f"regime_adaptive_{regime}",
                generation=self.generation
            )
            candidates.append(candidate)
            self.history.append(candidate)
        
        return candidates
    
    def _crossover(self, n: int) -> List[EvolutionCandidate]:
        """Crossover best parameters"""
        candidates = []
        
        if len(self.best_candidates) < 2:
            return self._mutation(n, {})
        
        for i in range(n):
            # Select two parents
            parent1, parent2 = random.sample(self.best_candidates[:5], 2)
            
            params = {}
            for key in self.parameter_space:
                # Randomly inherit from one parent
                if random.random() < 0.5:
                    params[key] = parent1.parameters.get(key, self.parameter_space[key].current_value)
                else:
                    params[key] = parent2.parameters.get(key, self.parameter_space[key].current_value)
            
            candidate = EvolutionCandidate(
                id=f"gen{self.generation}_cross{i}",
                parameters=params,
                source="crossover",
                generation=self.generation,
                parent_id=f"{parent1.id}+{parent2.id}"
            )
            candidates.append(candidate)
            self.history.append(candidate)
        
        return candidates
    
    def _save_state(self):
        """Save evolution state"""
        state = {
            'generation': self.generation,
            'best_candidates': [
                {
                    'id': c.id,
                    'parameters': c.parameters,
                    'fitness': c.fitness,
                    'source': c.source
                }
                for c in self.best_candidates[:10]
            ],
            'history_size': len(self.history),
            'timestamp': datetime.now().isoformat()
        }
        
        state_file = os.path.join(self.evolution_dir, 'evolution_state.json')
        with open(state_file, 'w') as f:
            json.dump(state, f, indent=2)
    
    def _load_state(self):
        """Load evolution state"""
        state_file = os.path.join(self.evolution_dir, 'evolution_state.json')
        
        if os.path.exists(state_file):
            try:
                with open(state_file, 'r') as f:
                    state = json.load(f)
                
                self.generation = state.get('generation', 0)
                
                # Reconstruct best candidates
                for c_data in state.get('best_candidates', []):
                    candidate = EvolutionCandidate(
                        id=c_data['id'],
                        parameters=c_data['parameters'],
                        fitness=c_data.get('fitness', 0),
                        source=c_data.get('source', 'unknown'),
                        generation=self.generation
                    )
                    self.best_candidates.append(candidate)
                
                log.info(f"Loaded evolution state: gen {self.generation}, {len(self.best_candidates)} best")
            except Exception as e:
                log.error(f"Error loading evolution state: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# CHALLENGER GENERATOR
# ══════════════════════════════════════════════════════════════════════════════

class ChallengerGenerator:
    """
    Generates challenger parameter sets for Champion vs Challenger protocol.
    
    SAFETY: Only outputs new files, never modifies production.
    """
    
    def __init__(self, output_dir: str = "/home/userland/api_workspace/evolution_engine/challengers"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
    
    def generate_challenger(
        self,
        parameters: Dict[str, float],
        generation: int,
        source: str,
        metrics: Dict
    ) -> str:
        """
        Generate a challenger configuration file.
        
        Returns:
            Path to generated challenger file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"challenger_gen{generation}_{source}_{timestamp}.json"
        filepath = os.path.join(self.output_dir, filename)
        
        challenger = {
            'metadata': {
                'id': f"challenger_gen{generation}_{timestamp}",
                'generation': generation,
                'source': source,
                'created_at': datetime.now().isoformat(),
                'parent_metrics': metrics
            },
            'parameters': parameters,
            'status': 'pending_backtest'
        }
        
        with open(filepath, 'w') as f:
            json.dump(challenger, f, indent=2)
        
        log.info(f"Generated challenger: {filename}")
        
        return filepath
    
    def promote_to_champion(self, challenger_path: str) -> str:
        """
        Promote a winning challenger to champion status.
        
        Creates a new champion file (never overwrites directly).
        """
        with open(challenger_path, 'r') as f:
            challenger = json.load(f)
        
        # Update status
        challenger['status'] = 'champion'
        challenger['promoted_at'] = datetime.now().isoformat()
        
        # Save as new champion
        champion_path = os.path.join(self.output_dir, 'current_champion.json')
        
        # Backup old champion
        if os.path.exists(champion_path):
            backup_path = os.path.join(
                self.output_dir, 
                f"champion_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )
            os.rename(champion_path, backup_path)
        
        with open(champion_path, 'w') as f:
            json.dump(challenger, f, indent=2)
        
        log.info(f"Challenger promoted to champion: {challenger['metadata']['id']}")
        
        return champion_path


# ══════════════════════════════════════════════════════════════════════════════
# MAIN EVOLUTION ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class AlphaEvolutionEngine:
    """
    Main evolution engine orchestrating parameter tuning.
    
    Usage:
        engine = AlphaEvolutionEngine()
        candidates = engine.evolve(current_metrics, regime)
    """
    
    def __init__(self, evolution_dir: str = "/opt/trading-bridge/data/evolution"):
        self.evolver = ParameterEvolver(evolution_dir=evolution_dir)
        self.challenger_gen = ChallengerGenerator()
    
    def evolve(
        self,
        current_metrics: Dict,
        regime: str,
        n_candidates: int = 5
    ) -> List[Dict]:
        """
        Generate evolved parameter candidates.
        
        Args:
            current_metrics: Current performance metrics
            regime: Current market regime
            n_candidates: Number of candidates to generate
            
        Returns:
            List of candidate dicts with parameters and metadata
        """
        # Choose evolution strategy based on performance
        profit_factor = current_metrics.get('profit_factor', 1.0)
        
        if profit_factor > 1.5:
            # Doing well - fine-tune with mutation
            strategy = EvolutionStrategy.MUTATION
        elif profit_factor > 1.0:
            # Marginal - explore with regime adaptation
            strategy = EvolutionStrategy.REGIME_ADAPTIVE
        else:
            # Doing poorly - aggressive exploration
            strategy = EvolutionStrategy.RANDOM_SEARCH
        
        # Generate candidates
        candidates = self.evolver.evolve(
            current_metrics=current_metrics,
            regime=regime,
            strategy=strategy,
            n_candidates=n_candidates
        )
        
        # Generate challenger files
        results = []
        for candidate in candidates:
            filepath = self.challenger_gen.generate_challenger(
                parameters=candidate.parameters,
                generation=candidate.generation,
                source=candidate.source,
                metrics=current_metrics
            )
            
            results.append({
                'candidate_id': candidate.id,
                'filepath': filepath,
                'parameters': candidate.parameters,
                'source': candidate.source,
                'generation': candidate.generation
            })
        
        return results
    
    def record_backtest_result(self, candidate_id: str, fitness: float, results: Dict):
        """Record backtest results for a candidate"""
        self.evolver.update_fitness(candidate_id, fitness, results)
    
    def get_best_parameters(self) -> Dict[str, float]:
        """Get current best parameters"""
        return self.evolver.get_best_parameters()


# ══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE
# ══════════════════════════════════════════════════════════════════════════════

def run_evolution(current_metrics: Dict, regime: str, n_candidates: int = 5) -> List[Dict]:
    """Quick evolution run"""
    engine = AlphaEvolutionEngine()
    return engine.evolve(current_metrics, regime, n_candidates)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 70)
    print("  ALPHA AGENT PARAMETER EVOLUTION ENGINE")
    print("=" * 70)
    
    # Example metrics
    example_metrics = {
        'win_rate': 0.52,
        'profit_factor': 1.35,
        'sharpe_ratio': 1.2,
        'max_drawdown_pct': 4.5,
        'avg_latency_ms': 45
    }
    
    candidates = run_evolution(example_metrics, 'ranging', n_candidates=3)
    
    print(f"\n  Generated {len(candidates)} candidates:")
    for c in candidates:
        print(f"    - {c['candidate_id']}: {c['source']}")
        print(f"      ATR SL: {c['parameters']['atr_sl_mult']:.2f}")
        print(f"      ATR TP: {c['parameters']['atr_tp_mult']:.2f}")
        print(f"      OBI: {c['parameters']['obi_threshold']:.2f}")
    
    print("=" * 70)
