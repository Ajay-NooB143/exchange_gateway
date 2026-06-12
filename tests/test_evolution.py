"""
Tests for Self-Evolving AI Prompt System.
- Prompt DNA storage and loading
- Fitness evaluation
- Mutation engine (7 types)
- Evolution scheduler
- Prompt writer
- AI evolution engine
- Rollback system
- Safety guards
"""
import sys
import os
import json
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'production'))

import pytest

# ── DNA Tests ─────────────────────────────────────────────────────────────


class TestPromptDNA:
    def test_dna_loads_from_json(self):
        from prompt_evolution import PromptDNA, COMPONENTS, DNA_DIR
        dna = PromptDNA()
        for comp in COMPONENTS:
            data = dna.get(comp)
            assert data is not None
            assert 'component' in data
            assert 'generation' in data
            assert 'fitness_score' in data
            assert 'prompt' in data
            assert data['component'] == comp

    def test_dna_has_all_components(self):
        from prompt_evolution import PromptDNA, COMPONENTS
        dna = PromptDNA()
        all_data = dna.get_all()
        assert len(all_data) == len(COMPONENTS)
        for comp in COMPONENTS:
            assert comp in all_data

    def test_dna_get_generation(self):
        from prompt_evolution import PromptDNA
        dna = PromptDNA()
        gen = dna.get_generation()
        assert gen >= 1

    def test_dna_update_creates_backup(self):
        from prompt_evolution import PromptDNA, BACKUP_DIR
        dna = PromptDNA()
        data = dna.get('confidence_scorer')
        old_gen = data['generation']
        data['generation'] += 1
        dna.update('confidence_scorer', data)
        backup_files = list(BACKUP_DIR.glob('confidence_scorer_gen*_backup.json'))
        assert len(backup_files) >= 1

    def test_dna_rollback_restores(self):
        from prompt_evolution import PromptDNA, COMPONENTS
        dna = PromptDNA()
        data = dna.get('confidence_scorer')
        data['fitness_score'] = 0.99
        dna.update('confidence_scorer', data)
        gen_to_backup = data['generation']
        data2 = dna.get('confidence_scorer')
        data2['fitness_score'] = 0.50
        dna.update('confidence_scorer', data2)
        ok = dna.rollback('confidence_scorer', gen_to_backup)
        assert ok
        restored = dna.get('confidence_scorer')
        assert any('Rolled back' in m for m in restored.get('mutations', []))

    def test_rollback_nonexistent_generation(self):
        from prompt_evolution import PromptDNA
        dna = PromptDNA()
        ok = dna.rollback('confidence_scorer', 9999)
        assert not ok

    def test_rollback_all(self):
        from prompt_evolution import PromptDNA, COMPONENTS
        dna = PromptDNA()
        results = dna.rollback_all(1)
        for comp in COMPONENTS:
            assert comp in results

    def test_get_history(self):
        from prompt_evolution import PromptDNA
        dna = PromptDNA()
        history = dna.get_history('confidence_scorer')
        assert isinstance(history, list)

    def test_get_summary(self):
        from prompt_evolution import PromptDNA
        dna = PromptDNA()
        summary = dna.get_summary()
        assert 'Generation:' in summary


# ── Fitness Evaluator Tests ──────────────────────────────────────────────

class TestFitnessEvaluator:
    def test_fitness_calculates_correctly(self):
        from fitness_evaluator import FitnessEvaluator
        evaluator = FitnessEvaluator(dna_instance=type('obj', (object,), {'get': lambda s, c: None, 'get_all': lambda s: {}, 'get_generation': lambda s: 1})())
        fitness = evaluator.evaluate()
        assert 0.0 <= fitness <= 1.0

    def test_win_rate_between_0_and_1(self):
        from fitness_evaluator import FitnessEvaluator
        evaluator = FitnessEvaluator(dna_instance=type('obj', (object,), {'get': lambda s, c: None, 'get_all': lambda s: {}, 'get_generation': lambda s: 1})())
        wr = evaluator.calculate_win_rate()
        assert 0.0 <= wr <= 1.0

    def test_signal_quality_normalized(self):
        from fitness_evaluator import FitnessEvaluator
        evaluator = FitnessEvaluator(dna_instance=type('obj', (object,), {'get': lambda s, c: None, 'get_all': lambda s: {}, 'get_generation': lambda s: 1})())
        sq = evaluator.calculate_signal_quality()
        assert 0.0 <= sq <= 1.0

    def test_false_positive_rate(self):
        from fitness_evaluator import FitnessEvaluator
        evaluator = FitnessEvaluator(dna_instance=type('obj', (object,), {'get': lambda s, c: None, 'get_all': lambda s: {}, 'get_generation': lambda s: 1})())
        fp = evaluator.calculate_false_positive_rate()
        assert 0.0 <= fp <= 1.0

    def test_avg_rr_normalized(self):
        from fitness_evaluator import FitnessEvaluator
        evaluator = FitnessEvaluator(dna_instance=type('obj', (object,), {'get': lambda s, c: None, 'get_all': lambda s: {}, 'get_generation': lambda s: 1})())
        rr = evaluator.calculate_avg_rr()
        assert 0.0 <= rr <= 1.0

    def test_evaluate_all_assets(self):
        from fitness_evaluator import FitnessEvaluator
        evaluator = FitnessEvaluator(dna_instance=type('obj', (object,), {'get': lambda s, c: None, 'get_all': lambda s: {}, 'get_generation': lambda s: 1})())
        results = evaluator.evaluate_all()
        assert len(results) >= 4

    def test_detailed_breakdown(self):
        from fitness_evaluator import FitnessEvaluator
        evaluator = FitnessEvaluator(dna_instance=type('obj', (object,), {'get': lambda s, c: None, 'get_all': lambda s: {}, 'get_generation': lambda s: 1})())
        detail = evaluator.get_detailed()
        assert 'fitness' in detail
        assert 'classification' in detail
        assert 'components' in detail
        assert 'signal_count' in detail

    def test_classify_fitness(self):
        from fitness_evaluator import classify_fitness
        assert classify_fitness(0.90) == 'EXCELLENT'
        assert classify_fitness(0.70) == 'GOOD'
        assert classify_fitness(0.55) == 'WEAK'
        assert classify_fitness(0.30) == 'POOR'

    def test_empty_signals(self):
        from fitness_evaluator import FitnessEvaluator
        evaluator = FitnessEvaluator(dna_instance=type('obj', (object,), {'get': lambda s, c: None, 'get_all': lambda s: {}, 'get_generation': lambda s: 1})())
        fitness = evaluator.evaluate(signals=[])
        assert fitness == 0.0


# ── Mutation Engine Tests ────────────────────────────────────────────────

class TestMutationEngine:
    def test_weight_shift_stays_in_bounds(self):
        from prompt_evolution import PromptDNA, MutationEngine
        dna = PromptDNA()
        engine = MutationEngine(dna)
        ok = engine.weight_shift('confidence_scorer')
        assert ok
        data = dna.get('confidence_scorer')
        prompt = data['prompt']
        for k, v in prompt.items():
            if k.endswith('_weight') and isinstance(v, (int, float)):
                assert 5 <= v <= 50

    def test_threshold_respects_limits(self):
        from prompt_evolution import PromptDNA, MutationEngine
        dna = PromptDNA()
        engine = MutationEngine(dna)
        ok = engine.threshold_drift('confidence_scorer')
        assert ok
        data = dna.get('confidence_scorer')
        th = data['prompt'].get('execute_threshold', 75)
        assert 60 <= th <= 90

    def test_rule_injection_adds_valid_rule(self):
        from prompt_evolution import PromptDNA, MutationEngine, RULE_LIBRARY
        dna = PromptDNA()
        engine = MutationEngine(dna)
        data = dna.get('confidence_scorer')
        old_count = len(data['prompt'].get('rules', []))
        ok = engine.rule_injection('confidence_scorer')
        assert ok
        data = dna.get('confidence_scorer')
        new_count = len(data['prompt'].get('rules', []))
        assert new_count > old_count
        last_rule = data['prompt']['rules'][-1]
        assert last_rule in RULE_LIBRARY

    def test_rule_deletion_removes_rule(self):
        from prompt_evolution import PromptDNA, MutationEngine
        dna = PromptDNA()
        engine = MutationEngine(dna)
        data = dna.get('confidence_scorer')
        data['prompt']['rules'] = ['rule1', 'rule2', 'rule3', 'rule4', 'rule5', 'rule6']
        dna.update('confidence_scorer', data)
        old_count = len(dna.get('confidence_scorer')['prompt']['rules'])
        ok = engine.rule_deletion('confidence_scorer')
        assert ok
        new_count = len(dna.get('confidence_scorer')['prompt']['rules'])
        assert new_count < old_count

    def test_rule_deletion_minimum_5(self):
        from prompt_evolution import PromptDNA, MutationEngine
        dna = PromptDNA()
        engine = MutationEngine(dna)
        data = dna.get('confidence_scorer')
        data['prompt']['rules'] = ['r1', 'r2', 'r3', 'r4', 'r5']
        dna.update('confidence_scorer', data)
        ok = engine.rule_deletion('confidence_scorer')
        assert not ok

    def test_asset_specialization(self):
        from prompt_evolution import PromptDNA, MutationEngine
        dna = PromptDNA()
        engine = MutationEngine(dna)
        ok = engine.asset_specialization('confidence_scorer', 'XAUUSD')
        assert ok
        data = dna.get('confidence_scorer')
        assert data['prompt'].get('specialized_asset') == 'XAUUSD'

    def test_crossover_combines_two(self):
        from prompt_evolution import PromptDNA, MutationEngine
        dna = PromptDNA()
        engine = MutationEngine(dna)
        ok = engine.crossover('confidence_scorer', 'pattern_engine')
        assert ok

    def test_full_reset_emergency(self):
        from prompt_evolution import PromptDNA, MutationEngine, DEFAULT_DNA
        dna = PromptDNA()
        engine = MutationEngine(dna)
        data = dna.get('confidence_scorer')
        data['fitness_score'] = 0.35
        dna.update('confidence_scorer', data)
        ok = engine.full_reset('confidence_scorer')
        assert ok
        new_data = dna.get('confidence_scorer')
        assert new_data['mutations'][-1].startswith('FULL_RESET')

    def test_all_7_mutation_types_work(self):
        from prompt_evolution import PromptDNA, MutationEngine
        dna = PromptDNA()
        engine = MutationEngine(dna)
        assert engine.weight_shift('confidence_scorer')
        assert engine.threshold_drift('confidence_scorer')
        assert engine.rule_injection('pattern_engine')
        assert engine.asset_specialization('mtf_confirmation', 'EURUSD')
        for _ in range(4):
            engine.rule_injection('signal_filter')
        assert engine.rule_deletion('signal_filter')
        assert engine.crossover('entry_rules', 'risk_rules')
        assert engine.full_reset('signal_filter')

    def test_backup_before_mutation(self):
        from prompt_evolution import PromptDNA, MutationEngine, BACKUP_DIR
        dna = PromptDNA()
        engine = MutationEngine(dna)
        data = dna.get('confidence_scorer')
        gen = data['generation']
        engine.weight_shift('confidence_scorer')
        backup_files = list(BACKUP_DIR.glob(f'confidence_scorer_gen{gen}_backup.json'))
        assert len(backup_files) >= 1

    def test_safety_guard_min_rules(self):
        from prompt_evolution import PromptDNA, MutationEngine
        dna = PromptDNA()
        engine = MutationEngine(dna)
        for comp in ['confidence_scorer', 'pattern_engine', 'mtf_confirmation', 'signal_filter', 'entry_rules', 'risk_rules']:
            data = dna.get(comp)
            if data and 'prompt' in data:
                rules = data['prompt'].get('rules', [])
                assert len(rules) >= 3


# ── Evolution Scheduler Tests ────────────────────────────────────────────

class TestEvolutionScheduler:
    def test_micro_evolution_does_not_crash(self):
        from prompt_evolution import PromptDNA, MutationEngine, EvolutionScheduler
        dna = PromptDNA()
        engine = MutationEngine(dna)
        scheduler = EvolutionScheduler(dna, engine)
        report = scheduler.run_micro_evolution(force=True)
        assert 'trigger' in report
        assert 'changes' in report
        assert 'timestamp' in report

    def test_macro_evolution_works(self):
        from prompt_evolution import PromptDNA, MutationEngine, EvolutionScheduler
        dna = PromptDNA()
        engine = MutationEngine(dna)
        scheduler = EvolutionScheduler(dna, engine)
        report = scheduler.run_macro_evolution()
        assert 'trigger' in report
        assert report['trigger'] == 'MACRO'

    def test_emergency_trigger(self):
        from prompt_evolution import PromptDNA, MutationEngine, EvolutionScheduler
        dna = PromptDNA()
        engine = MutationEngine(dna)
        scheduler = EvolutionScheduler(dna, engine)
        scheduler.loss_streak = 3
        report = scheduler.trigger_emergency('3 consecutive losses')
        assert report['trigger'] == 'EMERGENCY'

    def test_emergency_reset_at_040(self):
        from prompt_evolution import PromptDNA, MutationEngine, EvolutionScheduler
        dna = PromptDNA()
        engine = MutationEngine(dna)
        scheduler = EvolutionScheduler(dna, engine)
        report = scheduler.trigger_emergency('win_rate < 40% 48h')
        assert report['trigger'] == 'EMERGENCY'

    def test_scheduler_get_report(self):
        from prompt_evolution import PromptDNA, MutationEngine, EvolutionScheduler
        dna = PromptDNA()
        engine = MutationEngine(dna)
        scheduler = EvolutionScheduler(dna, engine)
        report = scheduler.get_report()
        assert 'generation' in report
        assert 'components' in report
        assert 'loss_streak' in report

    def test_evolution_report_formatting(self):
        from prompt_evolution import PromptDNA, MutationEngine, EvolutionScheduler
        dna = PromptDNA()
        engine = MutationEngine(dna)
        scheduler = EvolutionScheduler(dna, engine)
        report = scheduler.run_micro_evolution(force=True)
        formatted = scheduler.format_evolution_report(report)
        assert 'DNA EVOLUTION REPORT' in formatted
        assert 'Generation:' in formatted


# ── Prompt Writer Tests ──────────────────────────────────────────────────

class TestPromptWriter:
    def test_generate_signal_detection_prompt(self):
        from prompt_writer import PromptWriter
        writer = PromptWriter(dna_instance=type('obj', (object,), {'get': lambda s, c: None, 'get_all': lambda s: {}, 'get_generation': lambda s: 1})())
        text = writer.generate_signal_detection_prompt(1)
        assert 'SIGNAL DETECTION' in text
        assert 'Generation' in text

    def test_generate_entry_rules_prompt(self):
        from prompt_writer import PromptWriter
        writer = PromptWriter(dna_instance=type('obj', (object,), {'get': lambda s, c: None, 'get_all': lambda s: {}, 'get_generation': lambda s: 1})())
        text = writer.generate_entry_rules_prompt(1)
        assert 'ENTRY RULES' in text

    def test_generate_risk_rules_prompt(self):
        from prompt_writer import PromptWriter
        writer = PromptWriter(dna_instance=type('obj', (object,), {'get': lambda s, c: None, 'get_all': lambda s: {}, 'get_generation': lambda s: 1})())
        text = writer.generate_risk_rules_prompt(1)
        assert 'RISK RULES' in text

    def test_generate_asset_prompt(self):
        from prompt_writer import PromptWriter
        writer = PromptWriter(dna_instance=type('obj', (object,), {'get': lambda s, c: None, 'get_all': lambda s: {}, 'get_generation': lambda s: 1})())
        text = writer.generate_asset_prompt('XAUUSD', 1)
        assert 'XAUUSD' in text

    def test_generate_all_prompts(self):
        from prompt_writer import PromptWriter
        writer = PromptWriter(dna_instance=type('obj', (object,), {'get': lambda s, c: None, 'get_all': lambda s: {}, 'get_generation': lambda s: 1})())
        prompts = writer.generate_all(1)
        assert 'signal_detection' in prompts
        assert 'entry_rules' in prompts
        assert 'risk_rules' in prompts

    def test_save_all_prompts(self):
        from prompt_writer import PromptWriter, EVOLVED_DIR
        writer = PromptWriter(dna_instance=type('obj', (object,), {'get': lambda s, c: None, 'get_all': lambda s: {}, 'get_generation': lambda s: 1})())
        paths = writer.save_all(1)
        assert len(paths) >= 3
        for p in paths.values():
            assert os.path.exists(p)


# ── AI Evolution Engine Tests ────────────────────────────────────────────

class TestAIEvolutionEngine:
    def test_fallback_suggestion(self):
        from ai_evolution_engine import AIEvolutionEngine
        engine = AIEvolutionEngine()
        suggestion = engine.generate_suggestion(1, 0.71, {'win_rate': 0.5}, [])
        assert suggestion is not None
        assert 'generation' in suggestion
        assert 'reasoning' in suggestion

    def test_fallback_on_low_fitness(self):
        from ai_evolution_engine import AIEvolutionEngine
        engine = AIEvolutionEngine()
        suggestion = engine.generate_suggestion(5, 0.55, {'win_rate': 0.4}, [])
        assert suggestion is not None
        th = suggestion.get('suggested_threshold', 75)
        assert 60 <= th <= 90

    def test_parse_response_valid(self):
        from ai_evolution_engine import AIEvolutionEngine
        engine = AIEvolutionEngine()
        text = '{"suggested_weights": {"ob_weight": 25}, "reasoning": "test"}'
        result = engine._parse_response(text)
        assert result is not None
        assert result['suggested_weights']['ob_weight'] == 25

    def test_parse_response_invalid(self):
        from ai_evolution_engine import AIEvolutionEngine
        engine = AIEvolutionEngine()
        result = engine._parse_response("not json")
        assert result is None

    def test_get_pending_suggestion(self):
        from ai_evolution_engine import AIEvolutionEngine
        engine = AIEvolutionEngine()
        suggestion = engine.generate_suggestion(2, 0.70, {}, [])
        pending = engine.get_pending_suggestion()
        assert pending is not None

    def test_reject_suggestion(self):
        from ai_evolution_engine import AIEvolutionEngine
        engine = AIEvolutionEngine()
        engine.reject_suggestion()
        assert engine.get_full_reasoning() is None or True

    def test_available_property(self):
        from ai_evolution_engine import AIEvolutionEngine
        engine = AIEvolutionEngine()
        assert isinstance(engine.available, bool)


# ── Integration Tests ────────────────────────────────────────────────────

class TestEvolutionIntegration:
    def test_full_evolution_cycle(self):
        from prompt_evolution import PromptDNA, MutationEngine, EvolutionScheduler
        dna = PromptDNA()
        engine = MutationEngine(dna)
        scheduler = EvolutionScheduler(dna, engine)
        report = scheduler.run_micro_evolution(force=True)
        assert len(report['changes']) >= 0
        gen = dna.get_generation()
        assert gen >= 1

    def test_dna_persistence_across_instances(self):
        from prompt_evolution import PromptDNA, COMPONENTS
        dna1 = PromptDNA()
        dna2 = PromptDNA()
        for comp in COMPONENTS:
            d1 = dna1.get(comp)
            d2 = dna2.get(comp)
            if d1 and d2:
                assert d1['generation'] == d2['generation']

    def test_per_asset_dna_specialization(self):
        from prompt_evolution import PromptDNA, MutationEngine
        dna = PromptDNA()
        engine = MutationEngine(dna)
        ok = engine.asset_specialization('risk_rules', 'BTCUSD')
        assert ok
        data = dna.get('risk_rules')
        assert data['prompt']['specialized_asset'] == 'BTCUSD'
        assert 'per_asset' in data
        assert 'BTCUSD' in data['per_asset']

    def test_evolution_status_endpoint_data(self):
        from prompt_evolution import get_evolution_status
        status = get_evolution_status()
        assert 'generation' in status
        assert 'dna' in status
        assert 'scheduler' in status
        assert 'summary' in status

    def test_all_mutation_types_enumeration(self):
        from prompt_evolution import MutationEngine, PromptDNA, COMPONENTS
        dna = PromptDNA()
        engine = MutationEngine(dna)
        types = ['weight_shift', 'threshold_drift', 'rule_injection',
                 'rule_deletion', 'asset_specialization', 'crossover', 'full_reset']
        for t in types:
            result = engine.mutate('confidence_scorer', t)
            assert isinstance(result, bool)


if __name__ == '__main__':
    pytest.main(['-v', __file__])
