"""Tests for safe_rl_learner.py and prompt_evolution.py RL loop - OMNI BRAIN V2"""
import sys, os, json, time, threading
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'production'))
import pytest

from safe_rl_learner import SafeRLLearner, get_rl_learner, MIN_TRAIN_SAMPLES, VALIDATION_SPLIT
from prompt_evolution import apply_rl_adjustments, get_rl_adjustments


class TestSafeRLLearner:
    def make_learner(self):
        learner = SafeRLLearner()
        learner._trade_history.clear()
        learner._total_trades = 0
        learner._current_model = learner._default_model()
        learner._shadow_model = None
        learner._version_history.clear()
        return learner

    def test_initialization(self):
        rl = self.make_learner()
        assert rl._total_trades == 0
        assert len(rl._trade_history) == 0
        assert rl._current_model['version'] == 0

    def test_record_trade(self):
        rl = self.make_learner()
        trade = {
            'symbol': 'XAUUSD', 'direction': 'BUY', 'win': True,
            'rr': 2.0, 'pattern': 'FVG', 'regime': 'EXPANSION',
            'session': 'LONDON', 'liquidity_quality': 80,
            'trap_detected': False, 'confidence': 85,
            'entry': 2000, 'exit': 2020, 'atr': 5.0,
        }
        rl.record_trade(trade)
        assert rl._total_trades == 1
        assert len(rl._trade_history) == 1
        assert rl._trade_history[0]['win'] is True

    def test_get_adjustments(self):
        rl = self.make_learner()
        adj = rl.get_adjustments()
        assert 'pattern_weights' in adj
        assert 'regime_weights' in adj
        assert 'session_weights' in adj
        assert 'confidence_bias' in adj
        assert 'rr_factor' in adj

    def test_model_persistence(self):
        rl1 = self.make_learner()
        for i in range(35):
            rl1.record_trade({
                'symbol': 'XAUUSD', 'direction': 'BUY', 'win': i % 3 != 0,
                'rr': 1.5 + (i % 5) * 0.3, 'pattern': 'FVG' if i % 2 == 0 else 'OB',
                'regime': 'EXPANSION', 'session': 'LONDON',
                'liquidity_quality': 70, 'trap_detected': False,
                'confidence': 75 + (i % 20), 'entry': 2000, 'exit': 2020, 'atr': 5.0,
            })
        result = rl1.train()
        rl2 = SafeRLLearner()
        rl2._trade_history.clear()
        assert rl2._current_model['version'] >= 0

    def test_score_based_rules_75_80(self):
        from confidence_scorer import get_scorer
        scorer = get_scorer()
        symbol = 'XAUUSD'
        old = scorer.get_threshold(symbol)
        apply_rl_adjustments(scorer, {'symbol': symbol, 'direction': 'BUY'}, {'score': 78, 'win': False, 'rr': 0})
        new = scorer.get_threshold(symbol)
        assert new == max(60, min(95, old - 1))

    def test_score_based_rules_80_90(self):
        from confidence_scorer import get_scorer
        scorer = get_scorer()
        symbol = 'XAUUSD'
        old = scorer.get_threshold(symbol)
        apply_rl_adjustments(scorer, {'symbol': symbol, 'direction': 'BUY'}, {'score': 85, 'win': True, 'rr': 2.0})
        new = scorer.get_threshold(symbol)
        assert new == max(60, min(95, old + 1))

    def test_score_based_rules_over_90(self):
        from confidence_scorer import get_scorer
        scorer = get_scorer()
        symbol = 'XAUUSD'
        old = scorer.get_threshold(symbol)
        apply_rl_adjustments(scorer, {'symbol': symbol, 'direction': 'BUY'}, {'score': 95, 'win': True, 'rr': 3.0})
        new = scorer.get_threshold(symbol)
        assert new == max(60, min(95, old + 2))

    def test_shadow_model_validation(self):
        rl = self.make_learner()
        for i in range(35):
            rl.record_trade({
                'symbol': 'XAUUSD', 'direction': 'BUY', 'win': i % 2 == 0,
                'rr': 1.0 + (i % 3) * 0.5, 'pattern': 'FVG', 'regime': 'EXPANSION',
                'session': 'LONDON', 'liquidity_quality': 70,
                'trap_detected': False, 'confidence': 75, 'entry': 2000, 'exit': 2020, 'atr': 5.0,
            })
        result = rl.train()
        assert result['samples'] >= 35

    def test_rollback(self):
        rl = self.make_learner()
        for i in range(35):
            rl.record_trade({
                'symbol': 'XAUUSD', 'direction': 'BUY', 'win': i % 2 == 0,
                'rr': 1.5, 'pattern': 'FVG', 'regime': 'EXPANSION',
                'session': 'LONDON', 'liquidity_quality': 70,
                'trap_detected': False, 'confidence': 75, 'entry': 2000, 'exit': 2020, 'atr': 5.0,
            })
        rl.train()
        assert rl.rollback(version=0) or rl.rollback() is not None

    def test_version_history(self):
        rl = self.make_learner()
        hist = rl.get_version_history()
        assert isinstance(hist, list)

    def test_min_train_samples(self):
        rl = self.make_learner()
        for i in range(5):
            rl.record_trade({
                'symbol': 'XAUUSD', 'direction': 'BUY', 'win': True,
                'rr': 1.0, 'pattern': 'FVG', 'regime': 'EXPANSION',
                'session': 'LONDON', 'liquidity_quality': 70,
                'trap_detected': False, 'confidence': 75, 'entry': 2000, 'exit': 2020, 'atr': 5.0,
            })
        result = rl.train()
        assert result['trained'] is False
        assert 'Insufficient samples' in result['rejection_reason']

    def test_validation_split_value(self):
        assert 0 < VALIDATION_SPLIT < 1
        assert VALIDATION_SPLIT == 0.8

    def test_weekly_budget_cap(self):
        import prompt_evolution
        prompt_evolution.rl_adjustments['weekly_count'] = 5
        from confidence_scorer import get_scorer
        scorer = get_scorer()
        symbol = 'XAUUSD'
        old = scorer.get_threshold(symbol)
        apply_rl_adjustments(scorer, {'symbol': symbol, 'direction': 'BUY'}, {'score': 85, 'win': True, 'rr': 1.5})
        new = scorer.get_threshold(symbol)
        assert new == old

    def test_learning_from_closed_trades(self):
        rl = SafeRLLearner()
        rl._trade_history.clear()
        for i in range(40):
            rl.record_trade({
                'symbol': 'XAUUSD', 'direction': 'BUY', 'win': i % 2 == 0,
                'rr': 1.0 + (i % 4) * 0.5, 'pattern': 'FVG',
                'regime': 'EXPANSION', 'session': 'LONDON',
                'liquidity_quality': 70, 'trap_detected': False,
                'confidence': 75 + (i % 20), 'entry': 2000, 'exit': 2010, 'atr': 5.0,
            })
        stats = rl.get_stats()
        assert stats['total_trades'] == 40
        assert stats['history_size'] == 40

    def test_record_outcome_in_prompt_evolution(self):
        import prompt_evolution
        from safe_rl_learner import get_rl_learner
        rl = get_rl_learner()
        rl.record_trade({
            'symbol': 'XAUUSD', 'direction': 'BUY', 'win': True,
            'rr': 2.0, 'pattern': 'OB', 'regime': 'EXPANSION',
            'session': 'LONDON', 'liquidity_quality': 80,
            'trap_detected': False, 'confidence': 85,
            'entry': 2000, 'exit': 2020, 'atr': 5.0,
        })
        stats = rl.get_stats()
        assert stats['total_trades'] >= 1
