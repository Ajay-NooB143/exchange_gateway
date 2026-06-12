"""
Prompt DNA Evolution System - OMNI BRAIN V2
============================================
Self-evolving AI prompt system with DNA storage, mutation engine,
evolution scheduler, and rollback capability.

DNA Directory: logs/prompt_dna/
"""

import os
import sys
import json
import time
import copy
import random
import logging
import threading
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path

log = logging.getLogger('PromptEvolution')

BASE_DIR = Path(__file__).parent
LOG_DIR = BASE_DIR / 'logs'
DNA_DIR = LOG_DIR / 'prompt_dna'
BACKUP_DIR = DNA_DIR / 'backups'
EVOLVED_DIR = LOG_DIR / 'evolved_prompts'
DNA_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
EVOLVED_DIR.mkdir(parents=True, exist_ok=True)

COMPONENTS = [
    'confidence_scorer', 'pattern_engine', 'mtf_confirmation',
    'signal_filter', 'entry_rules', 'risk_rules'
]

ASSETS = ['XAUUSD', 'EURUSD', 'GBPUSD', 'SP500', 'BTCUSD']

DEFAULT_DNA = {
    'confidence_scorer': {
        'component': 'confidence_scorer',
        'version': 1,
        'generation': 1,
        'fitness_score': 0.71,
        'created_at': 'UTC',
        'parent_version': None,
        'mutations': [],
        'prompt': {
            'ob_weight': 20, 'fvg_weight': 20, 'sweep_weight': 30,
            'vwap_weight': 15, 'session_weight': 15,
            'execute_threshold': 75, 'wait_threshold': 50,
            'rules': [
                'Block if news in 30min',
                'Boost sweep weight in London',
                'Reduce FVG weight on crypto'
            ]
        },
        'performance': {
            'win_rate': 0.71, 'total_signals': 147, 'execute_count': 52,
            'avg_score': 68.4, 'best_asset': 'XAUUSD', 'worst_asset': 'SP500'
        }
    },
    'pattern_engine': {
        'component': 'pattern_engine',
        'version': 1, 'generation': 1, 'fitness_score': 0.68,
        'created_at': 'UTC', 'parent_version': None, 'mutations': [],
        'prompt': {
            'min_candles': 12, 'min_volume_ratio': 1.5,
            'propulsion_score': 7, 'rejection_score': 5,
            'breaker_score': 5, 'equilibrium_score': 3,
            'execute_threshold': 75, 'wait_threshold': 50,
            'rules': [
                'Require volume confirmation',
                'Check premium discount zone',
                'Multi-TF confirmation required'
            ]
        },
        'performance': {
            'win_rate': 0.68, 'total_signals': 98, 'execute_count': 38,
            'avg_score': 65.2, 'best_asset': 'XAUUSD', 'worst_asset': 'SP500'
        }
    },
    'mtf_confirmation': {
        'component': 'mtf_confirmation',
        'version': 1, 'generation': 1, 'fitness_score': 0.73,
        'created_at': 'UTC', 'parent_version': None, 'mutations': [],
        'prompt': {
            'm15_weight': 15, 'h1_weight': 30, 'h4_weight': 35, 'd1_weight': 20,
            'alignment_bonus': 20, 'conflict_penalty': -15,
            'execute_threshold': 75, 'wait_threshold': 50,
            'rules': [
                'M15 must align with H1',
                'H4 trend must support direction',
                'D1 conflict hard blocks'
            ]
        },
        'performance': {
            'win_rate': 0.73, 'total_signals': 112, 'execute_count': 45,
            'avg_score': 70.1, 'best_asset': 'EURUSD', 'worst_asset': 'BTCUSD'
        }
    },
    'signal_filter': {
        'component': 'signal_filter',
        'version': 1, 'generation': 1, 'fitness_score': 0.65,
        'created_at': 'UTC', 'parent_version': None, 'mutations': [],
        'prompt': {
            'min_spread_pips': 1.0, 'max_spread_pips': 5.0,
            'min_volume': 100, 'max_volume_ratio': 10.0,
            'min_signal_strength': 50,
            'rules': [
                'Block if spread > 2x avg',
                'Block if volume spike anomaly',
                'Allow only during active sessions'
            ]
        },
        'performance': {
            'win_rate': 0.65, 'total_signals': 203, 'execute_count': 71,
            'avg_score': 62.8, 'best_asset': 'GBPUSD', 'worst_asset': 'BTCUSD'
        }
    },
    'entry_rules': {
        'component': 'entry_rules',
        'version': 1, 'generation': 1, 'fitness_score': 0.70,
        'created_at': 'UTC', 'parent_version': None, 'mutations': [],
        'prompt': {
            'max_concurrent_trades': 3, 'max_daily_trades': 10,
            'min_time_between_trades': 300,
            'max_trades_per_pair': 3,
            'rules': [
                'Wait for pullback to OB',
                'Enter only after sweep + confirmation',
                'No entry in first 15min of session'
            ]
        },
        'performance': {
            'win_rate': 0.70, 'total_signals': 165, 'execute_count': 58,
            'avg_score': 66.0, 'best_asset': 'XAUUSD', 'worst_asset': 'SP500'
        }
    },
    'risk_rules': {
        'component': 'risk_rules',
        'version': 1, 'generation': 1, 'fitness_score': 0.75,
        'created_at': 'UTC', 'parent_version': None, 'mutations': [],
        'prompt': {
            'risk_per_trade_pct': 1.0, 'max_daily_risk_pct': 3.0,
            'max_drawdown_pct': 5.0,
            'max_spread_pips': 3.0,
            'rules': [
                'Use half-Kelly position sizing',
                'Hard stop at 3% daily loss',
                'No trading 30min before high impact news'
            ]
        },
        'performance': {
            'win_rate': 0.75, 'total_signals': 89, 'execute_count': 40,
            'avg_score': 72.3, 'best_asset': 'EURUSD', 'worst_asset': 'BTCUSD'
        }
    }
}

RULE_LIBRARY = [
    'Yield inverted: gold +10',
    'F&G < 25: reduce equities',
    'London/NY overlap: -5 threshold',
    '3 losses: +10 threshold',
    'BTC > 60k: crypto boost',
    'Spread > 2x avg: block',
    'D1 MTF conflict: hard block',
    'NY open 30min: sweep boost',
    'Pre-FOMC 1hr: block SP500',
    'DXY rising fast: gold bearish',
    'Asian session: reduce crypto',
    'Friday 20 UTC: reduce all',
    'Monday open: boost threshold',
    'High VIX: reduce equities',
    'Low VIX: boost equities',
    'NFP 2hr block: all pairs USD',
    'CPI release: block 1hr before',
    'Triple witching: reduce all 50%',
    'Month end rebalancing: boost',
    'Central bank speech: block FX',
    'Oil spike: boost CAD pairs',
    'Risk on mode: boost SP500',
    'Risk off mode: boost XAUUSD',
    'DXY > 105: gold bearish bias',
    'DXY < 100: gold bullish bias',
    '10Y yield spike: reduce bonds',
    '2Y-10Y steepening: bank boost',
    'VIX > 30: block all equities',
    'VIX < 12: normal equities',
    'BTC dominance > 60: altcoin weak',
    'ETH gas > 100: crypto risk on',
    'US session high vol: boost all',
    'Asian session low vol: reduce',
    'London fix: boost XAUUSD',
    'CO reports: adjust positions',
    'Quarter end: reduce risk 50%',
    'Holiday session: block 50%',
    'Gap open: wait 15min',
    'Consecutive win 3: scale +25%',
    'Consecutive loss 2: reduce 50%',
    'ATR > 2x avg: reduce size 50%',
    'ATR < 0.5x avg: reduce size 25%',
    'OB + FVG + Sweep alignment: boost',
    'Divergence + OB: strong signal',
    'Pattern + Sweep: confirm entry',
    'Correlation divergence: reduce',
    'News cluster: block 2hr window',
    'Bias alignment 3TF+: execute',
    'Bias conflict 2TF+: wait',
    'Weekend gap: assess Monday open',
]


class PromptDNA:
    """Prompt DNA storage and management."""

    def __init__(self):
        self._lock = threading.Lock()
        self._cache = {}
        self._current_generation = 1
        self._load_all()

    def _dna_path(self, component: str) -> Path:
        return DNA_DIR / f'{component}_dna.json'

    def _load_all(self):
        for comp in COMPONENTS:
            path = self._dna_path(comp)
            if path.exists():
                try:
                    with open(path, 'r') as f:
                        data = json.load(f)
                    self._cache[comp] = data
                    gen = data.get('generation', 1)
                    if gen > self._current_generation:
                        self._current_generation = gen
                except Exception as e:
                    log.error(f"Failed to load DNA for {comp}: {e}")
                    self._cache[comp] = copy.deepcopy(DEFAULT_DNA.get(comp, {}))
            else:
                self._cache[comp] = copy.deepcopy(DEFAULT_DNA.get(comp, {}))
                self._save(comp)

    def _save(self, component: str):
        path = self._dna_path(component)
        try:
            with open(path, 'w') as f:
                json.dump(self._cache[component], f, indent=2, default=str)
        except Exception as e:
            log.error(f"Failed to save DNA for {component}: {e}")

    def get(self, component: str) -> Optional[Dict[str, Any]]:
        return self._cache.get(component)

    def get_all(self) -> Dict[str, Dict[str, Any]]:
        return dict(self._cache)

    def get_generation(self) -> int:
        return self._current_generation

    def update(self, component: str, data: Dict[str, Any]):
        with self._lock:
            data['created_at'] = datetime.now(timezone.utc).isoformat()
            self._cache[component] = data
            gen = data.get('generation', 1)
            if gen > self._current_generation:
                self._current_generation = gen
            self._save(component)
            self._backup(component)

    def _backup(self, component: str):
        data = self._cache[component]
        gen = data.get('generation', 1)
        path = BACKUP_DIR / f'{component}_gen{gen}_backup.json'
        try:
            with open(path, 'w') as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            log.error(f"Backup failed for {component} gen {gen}: {e}")

    def rollback(self, component: str, generation: int) -> bool:
        path = BACKUP_DIR / f'{component}_gen{generation}_backup.json'
        if not path.exists():
            log.error(f"No backup found for {component} gen {generation}")
            return False
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            with self._lock:
                data['generation'] = self._current_generation + 1
                data['mutations'] = data.get('mutations', []) + [
                    f"Rolled back to generation {generation}"
                ]
                self._cache[component] = data
                self._save(component)
            log.info(f"Rolled back {component} to generation {generation}")
            return True
        except Exception as e:
            log.error(f"Rollback failed: {e}")
            return False

    def rollback_all(self, generation: int) -> Dict[str, bool]:
        results = {}
        for comp in COMPONENTS:
            results[comp] = self.rollback(comp, generation)
        return results

    def get_history(self, component: str = None) -> List[Dict[str, Any]]:
        history = []
        target = [component] if component else COMPONENTS
        for comp in target:
            backup_files = sorted(BACKUP_DIR.glob(f'{comp}_gen*_backup.json'))
            for bf in backup_files:
                try:
                    with open(bf, 'r') as f:
                        history.append(json.load(f))
                except Exception:
                    pass
        return history

    def get_summary(self) -> str:
        lines = [f"Generation: {self._current_generation}"]
        for comp in COMPONENTS:
            data = self._cache.get(comp, {})
            fit = data.get('fitness_score', 0)
            gen = data.get('generation', 1)
            mutations = len(data.get('mutations', []))
            emoji = '🟢' if fit > 0.80 else '🟡' if fit > 0.65 else '🟠' if fit > 0.50 else '🔴'
            lines.append(f"  {emoji} {comp:<25} gen={gen} fitness={fit:.2f} mutations={mutations}")
        return '\n'.join(lines)


class MutationEngine:
    """7 mutation types for prompt DNA evolution."""

    def __init__(self, dna: PromptDNA):
        self.dna = dna

    def _backup_before(self, component: str):
        self.dna._backup(component)

    def weight_shift(self, component: str) -> bool:
        data = self.dna.get(component)
        if not data or 'prompt' not in data:
            return False
        self._backup_before(component)
        prompt = data['prompt']
        weight_keys = [k for k in prompt if k.endswith('_weight') or k.endswith('_pct')
                       or k == 'risk_per_trade_pct' or k == 'max_daily_risk_pct']
        if not weight_keys:
            weight_keys = [k for k in prompt if isinstance(prompt[k], (int, float))
                           and k != 'execute_threshold' and k != 'wait_threshold']
        if not weight_keys:
            return False
        key = random.choice(weight_keys)
        shift = random.choice([-5, -3, 3, 5])
        old_val = prompt[key]
        new_val = max(5, min(50, old_val + shift))
        prompt[key] = new_val
        data['generation'] += 1
        data['mutations'].append(f"WEIGHT_SHIFT: {key} {old_val}->{new_val}")
        self.dna.update(component, data)
        log.info(f"Weight shift: {component}.{key} {old_val} -> {new_val}")
        return True

    def threshold_drift(self, component: str) -> bool:
        data = self.dna.get(component)
        if not data or 'prompt' not in data:
            return False
        self._backup_before(component)
        prompt = data['prompt']
        threshold_keys = [k for k in prompt if 'threshold' in k.lower()]
        if not threshold_keys:
            return False
        key = random.choice(threshold_keys)
        shift = random.choice([-2, -1, 1, 2])
        old_val = prompt[key]
        new_val = max(60, min(90, old_val + shift))
        prompt[key] = new_val
        data['generation'] += 1
        data['mutations'].append(f"THRESHOLD_DRIFT: {key} {old_val}->{new_val}")
        self.dna.update(component, data)
        log.info(f"Threshold drift: {component}.{key} {old_val} -> {new_val}")
        return True

    def rule_injection(self, component: str) -> bool:
        data = self.dna.get(component)
        if not data or 'prompt' not in data:
            return False
        self._backup_before(component)
        rules = data['prompt'].setdefault('rules', [])
        available = [r for r in RULE_LIBRARY if r not in rules]
        if not available:
            return False
        rule = random.choice(available)
        rules.append(rule)
        data['generation'] += 1
        data['mutations'].append(f"RULE_INJECTION: {rule}")
        self.dna.update(component, data)
        log.info(f"Rule injection: {component} <- {rule}")
        return True

    def rule_deletion(self, component: str) -> bool:
        data = self.dna.get(component)
        if not data or 'prompt' not in data:
            return False
        rules = data['prompt'].get('rules', [])
        if len(rules) <= 5:
            log.info(f"Cannot delete: {component} has minimum rules ({len(rules)})")
            return False
        self._backup_before(component)
        removed = rules.pop(-1)
        data['generation'] += 1
        data['mutations'].append(f"RULE_DELETION: {removed}")
        self.dna.update(component, data)
        log.info(f"Rule deletion: {component} -> removed {removed}")
        return True

    def asset_specialization(self, component: str, asset: str = None) -> bool:
        data = self.dna.get(component)
        if not data or 'prompt' not in data:
            return False
        self._backup_before(component)
        asset = asset or random.choice(ASSETS)
        prompt = data['prompt'].copy()
        prompt['rules'] = list(prompt.get('rules', []))
        prompt['rules'].append(f"Asset-specific: {asset} specialization")
        prompt['specialized_asset'] = asset
        data['prompt'] = prompt
        data['generation'] += 1
        data['mutations'].append(f"ASSET_SPECIALIZATION: {asset}")
        per_asset = data.setdefault('per_asset', {})
        per_asset[asset] = {'generation': data['generation'], 'prompt': prompt}
        self.dna.update(component, data)
        log.info(f"Asset specialization: {component} for {asset}")
        return True

    def crossover(self, component_a: str, component_b: str) -> bool:
        data_a = self.dna.get(component_a)
        data_b = self.dna.get(component_b)
        if not data_a or not data_b:
            return False
        if 'prompt' not in data_a or 'prompt' not in data_b:
            return False
        self._backup_before(component_a)
        self._backup_before(component_b)
        pa, pb = data_a['prompt'], data_b['prompt']
        for key in pa:
            if isinstance(pa[key], (int, float)) and key in pb and isinstance(pb[key], (int, float)):
                if random.random() < 0.5:
                    pa[key], pb[key] = pb[key], pa[key]
        rules_a = pa.get('rules', [])
        rules_b = pb.get('rules', [])
        split = len(rules_a) // 2
        pa['rules'] = rules_a[:split] + rules_b[split:]
        pb['rules'] = rules_b[:split] + rules_a[split:]
        data_a['generation'] += 1
        data_b['generation'] += 1
        data_a['mutations'].append(f"CROSSOVER: with {component_b}")
        data_b['mutations'].append(f"CROSSOVER: with {component_a}")
        self.dna.update(component_a, data_a)
        self.dna.update(component_b, data_b)
        log.info(f"Crossover: {component_a} <-> {component_b}")
        return True

    def full_reset(self, component: str) -> bool:
        data = self.dna.get(component)
        if not data:
            return False
        self._backup_before(component)
        default = copy.deepcopy(DEFAULT_DNA.get(component, {}))
        default['generation'] = data.get('generation', 1) + 1
        default['mutations'] = data.get('mutations', []) + ["FULL_RESET: emergency reset to safe defaults"]
        default['fitness_score'] = 0.50
        default['created_at'] = datetime.now(timezone.utc).isoformat()
        self.dna.update(component, default)
        log.warning(f"Full reset: {component} reset to safe defaults")
        return True

    def mutate(self, component: str, mutation_type: str = None, **kwargs) -> bool:
        if mutation_type is None:
            mutation_type = random.choice([
                'weight_shift', 'threshold_drift', 'rule_injection',
                'rule_deletion', 'asset_specialization'
            ])
        mutators = {
            'weight_shift': self.weight_shift,
            'threshold_drift': self.threshold_drift,
            'rule_injection': self.rule_injection,
            'rule_deletion': self.rule_deletion,
            'asset_specialization': self.asset_specialization,
            'crossover': lambda c: self.crossover(c, random.choice([x for x in COMPONENTS if x != c])),
            'full_reset': self.full_reset,
        }
        if mutation_type not in mutators:
            log.error(f"Unknown mutation type: {mutation_type}")
            return False
        func = mutators[mutation_type]
        if mutation_type == 'crossover':
            other = kwargs.get('other_component')
            if other:
                return self.crossover(component, other)
            return func(component)
        if mutation_type == 'asset_specialization':
            asset = kwargs.get('asset')
            if asset:
                return self.asset_specialization(component, asset)
            return func(component)
        return func(component)


class EvolutionScheduler:
    """Scheduler for MICRO, MACRO, and EMERGENCY evolution cycles."""

    def __init__(self, dna: PromptDNA, mutation_engine: MutationEngine):
        self.dna = dna
        self.mutation_engine = mutation_engine
        self.last_micro_run = None
        self.last_macro_run = None
        self.loss_streak = 0
        self._lock = threading.Lock()

    def evaluate_fitness(self, component: str) -> float:
        try:
            sys.path.insert(0, str(BASE_DIR))
            from fitness_evaluator import FitnessEvaluator
            evaluator = FitnessEvaluator(self.dna)
            return evaluator.evaluate(component)
        except Exception as e:
            log.debug(f"Fitness evaluation error: {e}")
            return 0.50

    def run_micro_evolution(self, force: bool = False) -> Dict[str, Any]:
        report = {'trigger': 'MICRO', 'changes': [], 'timestamp': datetime.now(timezone.utc).isoformat()}
        for comp in COMPONENTS:
            current_fitness = self.evaluate_fitness(comp)
            data = self.dna.get(comp)
            if not data:
                continue
            prev_fitness = data.get('fitness_score', 0.50)
            drop = prev_fitness - current_fitness
            if force or drop > 0.05:
                if current_fitness > 0.80:
                    mutation_type = 'threshold_drift'
                elif current_fitness > 0.65:
                    mutation_type = random.choice(['weight_shift', 'threshold_drift', 'rule_injection'])
                elif current_fitness > 0.50:
                    mutation_type = random.choice(['weight_shift', 'rule_injection', 'rule_deletion'])
                else:
                    if current_fitness < 0.40:
                        mutation_type = 'full_reset'
                    else:
                        mutation_type = random.choice(['weight_shift', 'rule_injection', 'rule_deletion'])
                success = self.mutation_engine.mutate(comp, mutation_type)
                if success:
                    data = self.dna.get(comp)
                    if data:
                        data['fitness_score'] = current_fitness
                        self.dna.update(comp, data)
                    report['changes'].append({
                        'component': comp,
                        'mutation': mutation_type,
                        'fitness': {'old': prev_fitness, 'new': current_fitness}
                    })
                    log.info(f"MICRO: {comp} {mutation_type} (fitness {prev_fitness:.2f}->{current_fitness:.2f})")
            else:
                data = self.dna.get(comp)
                if data:
                    data['fitness_score'] = current_fitness
                    self.dna.update(comp, data)
        self.last_micro_run = datetime.now(timezone.utc)
        return report

    def run_macro_evolution(self) -> Dict[str, Any]:
        report = {'trigger': 'MACRO', 'changes': [], 'timestamp': datetime.now(timezone.utc).isoformat()}
        best = sorted(COMPONENTS, key=lambda c: self.dna.get(c).get('fitness_score', 0) if self.dna.get(c) else 0, reverse=True)
        if len(best) >= 2:
            success = self.mutation_engine.crossover(best[0], best[1])
            if success:
                report['changes'].append({
                    'type': 'CROSSOVER',
                    'components': [best[0], best[1]]
                })
        for comp in COMPONENTS:
            success = self.mutation_engine.mutate(comp, 'asset_specialization')
            if success:
                report['changes'].append({
                    'component': comp,
                    'mutation': 'ASSET_SPECIALIZATION'
                })
        self.last_macro_run = datetime.now(timezone.utc)
        return report

    def trigger_emergency(self, reason: str) -> Dict[str, Any]:
        report = {'trigger': 'EMERGENCY', 'reason': reason, 'changes': [], 'timestamp': datetime.now(timezone.utc).isoformat()}
        if 'loss' in reason.lower() and self.loss_streak >= 3:
            for comp in COMPONENTS:
                data = self.dna.get(comp)
                if data:
                    prompt = data.get('prompt', {})
                    old = prompt.get('execute_threshold', 75)
                    prompt['execute_threshold'] = min(90, old + 5)
                    data['mutations'].append(f"EMERGENCY: threshold +5 ({reason})")
                    self.dna.update(comp, data)
                    report['changes'].append({'component': comp, 'action': 'threshold+5', 'reason': reason})
        if 'win_rate' in reason.lower():
            for comp in COMPONENTS:
                self.mutation_engine.full_reset(comp)
                report['changes'].append({'component': comp, 'action': 'FULL_RESET', 'reason': reason})
        self.loss_streak = 0
        return report

    def format_evolution_report(self, report: Dict[str, Any]) -> str:
        gen = self.dna.get_generation()
        lines = [
            '🧬 DNA EVOLUTION REPORT',
            '─────────────────────────',
            f'Generation: {gen} → {gen + 1}',
            f'Trigger: {report.get("trigger", "UNKNOWN")}',
            f'Time: {report.get("timestamp", "N/A")}',
            '─────────────────────────',
            'Changes:',
        ]
        for change in report.get('changes', []):
            comp = change.get('component', change.get('components', ['?']))
            mut = change.get('mutation', change.get('type', '?'))
            fit = change.get('fitness', {})
            if isinstance(comp, list):
                comp = ' + '.join(comp)
            if fit:
                lines.append(f'  {comp}: {mut} ({fit.get("old", "?"):.2f}→{fit.get("new", "?"):.2f})')
            else:
                lines.append(f'  {comp}: {mut}')
        if 'reason' in report:
            lines.append(f'Reason: {report["reason"]}')
        lines.append(f'─────────────────────────')
        return '\n'.join(lines)

    def get_report(self) -> Dict[str, Any]:
        return {
            'generation': self.dna.get_generation(),
            'last_micro': self.last_micro_run.isoformat() if self.last_micro_run else None,
            'last_macro': self.last_macro_run.isoformat() if self.last_macro_run else None,
            'components': {c: {'fitness': self.dna.get(c).get('fitness_score', 0) if self.dna.get(c) else 0,
                                'generation': self.dna.get(c).get('generation', 1) if self.dna.get(c) else 1,
                                'mutations': len(self.dna.get(c).get('mutations', [])) if self.dna.get(c) else 0}
                           for c in COMPONENTS},
            'loss_streak': self.loss_streak
        }


_dna_instance = None
_mutation_instance = None
_scheduler_instance = None
_dna_lock = threading.Lock()
_mutation_lock = threading.Lock()
_scheduler_lock = threading.Lock()


def get_dna() -> PromptDNA:
    global _dna_instance
    if _dna_instance is None:
        with _dna_lock:
            if _dna_instance is None:
                _dna_instance = PromptDNA()
    return _dna_instance


def get_mutation_engine() -> MutationEngine:
    global _mutation_instance
    if _mutation_instance is None:
        with _mutation_lock:
            if _mutation_instance is None:
                _mutation_instance = MutationEngine(get_dna())
    return _mutation_instance


def get_evolution_scheduler() -> EvolutionScheduler:
    global _scheduler_instance
    if _scheduler_instance is None:
        with _scheduler_lock:
            if _scheduler_instance is None:
                _scheduler_instance = EvolutionScheduler(get_dna(), get_mutation_engine())
    return _scheduler_instance


def get_evolution_status() -> Dict[str, Any]:
    dna = get_dna()
    scheduler = get_evolution_scheduler()
    return {
        'generation': dna.get_generation(),
        'dna': dna.get_all(),
        'scheduler': scheduler.get_report(),
        'summary': dna.get_summary()
    }


# ── RL Self-Learning Loop ─────────────────────────────────────────────────

rl_adjustments = {
    'adjustments': [],
    'total_adjustments': 0,
    'weekly_count': 0,
    'last_adjustment_time': None,
    'model_version': 0,
}


def apply_rl_adjustments(scorer, signal: Dict[str, Any], result: Dict[str, Any]) -> None:
    """Wire RL self-learning loop into the scoring pipeline.

    1. Record the trade outcome with SafeRLLearner
    2. Get RL model adjustments
    3. Apply score-based threshold rules
    4. Enforce weekly adjustment budget (max ±5)
    """
    from safe_rl_learner import get_rl_learner

    rl = get_rl_learner()
    symbol = signal.get('symbol', 'XAUUSD')

    trade = {
        'symbol': symbol,
        'direction': signal.get('direction', ''),
        'win': result.get('win', False),
        'rr': result.get('rr', 0),
        'pattern': signal.get('pattern', ''),
        'regime': signal.get('regime', ''),
        'session': signal.get('session', ''),
        'liquidity_quality': signal.get('liquidity_quality', 50),
        'trap_detected': signal.get('trap_detected', False),
        'confidence': result.get('score', 50),
        'entry': signal.get('entry', 0),
        'exit': result.get('exit', 0),
        'atr': signal.get('atr', 5.0),
        'timestamp': time.time(),
    }
    rl.record_trade(trade)

    adjustments = rl.get_adjustments()
    if adjustments:
        scorer.apply_adjustments(adjustments)
        log.info(f"RL model adjustments applied: v{adjustments.get('model_version', 0)}")

    # Score-based threshold adjustment rules
    score = result.get('score', 0)
    if score < 75:
        return

    global rl_adjustments
    if rl_adjustments['weekly_count'] >= 5:
        log.warning("RL: Weekly adjustment limit reached (5/5)")
        return

    if 75 <= score <= 80:
        delta = -1  # SL: reduce weight — lower threshold slightly
    elif 80 < score <= 90:
        delta = 1   # TP: increase weight — raise threshold
    else:
        delta = 2   # TP2/3: boost sweep +2

    old = scorer.get_threshold(symbol)
    new = max(60, min(95, old + delta))
    scorer.set_threshold(symbol, new)

    rl_adjustments['adjustments'].append({
        'symbol': symbol,
        'score': score,
        'delta': delta,
        'old_threshold': old,
        'new_threshold': new,
        'timestamp': datetime.now(timezone.utc).isoformat(),
    })
    rl_adjustments['total_adjustments'] += 1
    rl_adjustments['weekly_count'] += 1
    rl_adjustments['last_adjustment_time'] = datetime.now(timezone.utc).isoformat()
    rl_adjustments['model_version'] = adjustments.get('model_version', 0)

    log.info(f"RL applied: threshold {old} -> {new} for {symbol} (score={score})")


def get_rl_adjustments() -> Dict[str, Any]:
    """Return current RL adjustment state."""
    return dict(rl_adjustments)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Prompt DNA Evolution System')
    parser.add_argument('--init', action='store_true', help='Initialize DNA files')
    parser.add_argument('--status', action='store_true', help='Show current status')
    parser.add_argument('--mutate', type=str, help='Mutate a component', nargs='+')
    parser.add_argument('--rollback', type=int, help='Rollback to generation')
    parser.add_argument('--micro', action='store_true', help='Run micro evolution')
    parser.add_argument('--macro', action='store_true', help='Run macro evolution')
    args = parser.parse_args()

    if args.init:
        dna = get_dna()
        print(f"DNA initialized for {len(COMPONENTS)} components")
        print(dna.get_summary())

    if args.status:
        dna = get_dna()
        print(dna.get_summary())

    if args.mutate:
        dna = get_dna()
        engine = MutationEngine(dna)
        for comp in args.mutate:
            if comp in COMPONENTS:
                engine.mutate(comp)
                print(f"Mutated {comp}")
            else:
                print(f"Unknown component: {comp}")

    if args.rollback:
        dna = get_dna()
        results = dna.rollback_all(args.rollback)
        for comp, ok in results.items():
            print(f"{'OK' if ok else 'FAIL'}: {comp} -> gen {args.rollback}")

    if args.micro:
        scheduler = get_evolution_scheduler()
        report = scheduler.run_micro_evolution()
        print(scheduler.format_evolution_report(report))

    if args.macro:
        scheduler = get_evolution_scheduler()
        report = scheduler.run_macro_evolution()
        print(scheduler.format_evolution_report(report))
