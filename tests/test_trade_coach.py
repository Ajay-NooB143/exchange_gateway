"""Tests for ai_trade_coach.py - OMNI BRAIN V2"""
import sys, os, json, time, threading
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'production'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import pytest

from ai_trade_coach import AITradeCoach, get_trade_coach
from ai_trade_coach import (
    ERROR_EARLY_ENTRY, ERROR_LATE_ENTRY, ERROR_WRONG_REGIME,
    ERROR_POOR_LIQUIDITY, ERROR_TRAP, ERROR_OVERTRADING, ERROR_WEAK_CONFIRMATION,
)


class TestAITradeCoach:
    def make_coach(self):
        return AITradeCoach()

    def test_initialization(self):
        coach = self.make_coach()
        assert coach._analyses == []
        assert coach._error_counts == {}

    def test_analyze_trade(self):
        coach = self.make_coach()
        result = coach.analyze_trade(
            'XAUUSD', 'BUY', 2350, 2330, -20, 72,
            session='ASIAN', regime='COMPRESSION',
            liquidity_tier='LOW', trap_probability=75,
            sweep_score=30, duration_minutes=10,
        )
        assert result.symbol == 'XAUUSD'
        assert result.outcome == 'LOSS'
        assert isinstance(result.score, int)
        assert 0 <= result.score <= 100

    def test_get_coaching_in_pipeline(self):
        import pipeline_orchestrator as po
        pipeline = po.PipelineEngine()
        coaching = pipeline._get_coaching('XAUUSD', 'BUY', 85, {'OB': 20, 'FVG': 20})
        assert 'TRADE COACH' in coaching
        assert 'Setup quality:' in coaching

    def test_format_telegram_coaching(self):
        coach = self.make_coach()
        result = coach.analyze_trade(
            'EURUSD', 'BUY', 1.10, 1.09, -10, 70,
            session='ASIAN', regime='COMPRESSION',
            liquidity_tier='LOW', trap_probability=80,
            duration_minutes=8,
        )
        msg = (
            f"\U0001f393 TRADE COACH\n"
            f"Setup quality: {'A' if result.score >= 80 else 'B' if result.score >= 60 else 'C'}\n"
            f"Best similar trade: {result.recommendation}\n"
            f"Confidence: {result.score}%"
        )
        assert 'TRADE COACH' in msg
        assert f"Confidence: {result.score}%" in msg

    def test_error_detection_early_entry(self):
        coach = self.make_coach()
        result = coach.analyze_trade(
            'XAUUSD', 'BUY', 2350, 2330, -20, 70,
            duration_minutes=5, trap_probability=30,
        )
        assert ERROR_EARLY_ENTRY in result.errors

    def test_error_detection_wrong_regime(self):
        coach = self.make_coach()
        result = coach.analyze_trade(
            'XAUUSD', 'BUY', 2350, 2330, -20, 70,
            regime='COMPRESSION', duration_minutes=30,
        )
        assert ERROR_WRONG_REGIME in result.errors

    def test_error_detection_trap(self):
        coach = self.make_coach()
        result = coach.analyze_trade(
            'XAUUSD', 'BUY', 2350, 2330, -20, 70,
            trap_probability=80, duration_minutes=30,
        )
        assert ERROR_TRAP in result.errors

    def test_win_analysis(self):
        coach = self.make_coach()
        result = coach.analyze_trade(
            'XAUUSD', 'BUY', 2350, 2375, 25, 92,
            session='LONDON_OPEN', regime='EXPANSION',
            liquidity_tier='HIGH', sweep_score=70,
            duration_minutes=120, was_managed=True,
        )
        assert result.outcome == 'WIN'
        assert len(result.strengths) >= 1
        assert result.score >= 60

    def test_loss_analysis(self):
        coach = self.make_coach()
        result = coach.analyze_trade(
            'XAUUSD', 'BUY', 2350, 2320, -30, 60,
            session='ASIAN', regime='COMPRESSION',
            liquidity_tier='LOW', trap_probability=85,
            duration_minutes=8, news_active=True,
        )
        assert result.outcome == 'LOSS'
        assert len(result.errors) >= 1

    def test_improvement_recommendations(self):
        coach = self.make_coach()
        result = coach.analyze_trade(
            'XAUUSD', 'BUY', 2350, 2320, -30, 55,
            duration_minutes=10, trap_probability=85,
        )
        assert isinstance(result.recommendation, str)
        assert len(result.recommendation) > 0
        assert result.estimated_improvement > 0

    def test_grade_calculation(self):
        coach = self.make_coach()
        r1 = coach.analyze_trade('XAUUSD', 'BUY', 2350, 2375, 25, 92,
                                 session='LONDON_OPEN', regime='EXPANSION',
                                 liquidity_tier='HIGH', was_managed=True,
                                 duration_minutes=120)
        r2 = coach.analyze_trade('XAUUSD', 'BUY', 2350, 2320, -30, 50,
                                 duration_minutes=5)
        assert r1.score >= 60
        assert r2.score < 60

    def test_coach_score_range(self):
        coach = self.make_coach()
        for _ in range(10):
            r = coach.analyze_trade('XAUUSD', 'BUY', 2350, 2340, -10, 50 + _ * 5,
                                    duration_minutes=30 + _)
            assert 0 <= r.score <= 100
