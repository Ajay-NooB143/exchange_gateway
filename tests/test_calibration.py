"""Tests for calibration_engine.py - OMNI BRAIN V2"""
import sys
import os
import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'production'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest


class TestCalibrationEngine:
    def test_initial_state(self):
        from calibration_engine import CalibrationEngine
        ce = CalibrationEngine(fresh=True)
        assert ce.state['signals_recorded'] == 0
        assert ce.state['signals_checked'] == 0
        assert ce.state['total_wins'] == 0
        assert ce.state['total_losses'] == 0
        assert ce.state['day'] == 0

    def test_record_signal(self):
        from calibration_engine import CalibrationEngine
        ce = CalibrationEngine(fresh=True)
        ce.state['day'] = 0
        ce.record_signal('XAUUSD', 'H1', 'LONG', 2000.0, 85,
                         {'OB': 20, 'FVG': 20, 'SWEEP': 30}, atr=5.0)
        assert ce.state['signals_recorded'] == 1
        assert ce.state['per_asset']['XAUUSD']['total'] == 1

    def test_check_outcome_win(self):
        from calibration_engine import CalibrationEngine
        ce = CalibrationEngine(fresh=True)
        signal = {
            'symbol': 'XAUUSD', 'tf': 'H1', 'direction': 'LONG',
            'entry_price': 2000.0, 'score': 85,
            'components': {'OB': 20, 'FVG': 20},
            'atr': 5.0, 'checked': False, 'win': None,
        }
        result = ce.check_outcome(signal)
        assert result['checked'] is True
        assert 'outcome' in result

    def test_win_tracking_updates(self):
        from calibration_engine import CalibrationEngine
        ce = CalibrationEngine(fresh=True)
        signal = {
            'symbol': 'XAUUSD', 'tf': 'H1', 'direction': 'LONG',
            'entry_price': 2000.0, 'score': 85,
            'components': {'OB': 20, 'FVG': 20},
            'atr': 5.0, 'checked': False, 'win': None,
        }
        ce.check_outcome(signal)
        assert 'OB' in ce.component_accuracy
        assert 'FVG' in ce.component_accuracy

    def test_component_accuracy_structure(self):
        from calibration_engine import CalibrationEngine
        ce = CalibrationEngine(fresh=True)
        signal = {
            'symbol': 'XAUUSD', 'tf': 'H1', 'direction': 'LONG',
            'entry_price': 2000.0, 'score': 85,
            'components': {'OB': 20, 'FVG': 20},
            'atr': 5.0, 'checked': False, 'win': None,
        }
        ce.check_outcome(signal)
        for key in ['OB', 'FVG']:
            assert 'total' in ce.component_accuracy[key]
            assert 'wins' in ce.component_accuracy[key]
            assert 'win_rate' in ce.component_accuracy[key]
            assert 'avg_contribution' in ce.component_accuracy[key]

    def test_weight_calibration_high_winrate(self):
        from calibration_engine import CalibrationEngine
        ce = CalibrationEngine(fresh=True)
        ce.component_accuracy['SWEEP'] = {
            'total': 10, 'wins': 9, 'win_rate': 0.9,
            'total_contribution': 280, 'avg_contribution': 28.0,
        }
        result = ce.calibrate_weights()
        assert result['weights']['SWEEP'] > 30 or result['weights']['SWEEP'] == 30

    def test_weight_calibration_low_winrate(self):
        from calibration_engine import CalibrationEngine
        ce = CalibrationEngine(fresh=True)
        ce.component_accuracy['FVG'] = {
            'total': 10, 'wins': 4, 'win_rate': 0.4,
            'total_contribution': 160, 'avg_contribution': 16.0,
        }
        current = ce.state['current_weights']['FVG']
        result = ce.calibrate_weights()
        assert result['weights']['FVG'] <= current

    def test_weight_bounds_min(self):
        from calibration_engine import CalibrationEngine
        ce = CalibrationEngine(fresh=True)
        ce.state['current_weights']['FVG'] = 6
        ce.component_accuracy['FVG'] = {
            'total': 10, 'wins': 0, 'win_rate': 0.0,
            'total_contribution': 0, 'avg_contribution': 0.0,
        }
        result = ce.calibrate_weights()
        assert result['weights']['FVG'] >= 5

    def test_weight_bounds_max(self):
        from calibration_engine import CalibrationEngine
        ce = CalibrationEngine(fresh=True)
        ce.state['current_weights']['SWEEP'] = 34
        ce.component_accuracy['SWEEP'] = {
            'total': 10, 'wins': 10, 'win_rate': 1.0,
            'total_contribution': 300, 'avg_contribution': 30.0,
        }
        result = ce.calibrate_weights()
        assert result['weights']['SWEEP'] <= 35

    def test_report_formatting(self):
        from calibration_engine import CalibrationEngine
        ce = CalibrationEngine(fresh=True)
        ce.state['signals_checked'] = 47
        ce.state['total_wins'] = 32
        ce.state['total_losses'] = 15
        report = ce.format_report()
        assert 'CALIBRATION REPORT' in report
        assert '47' in report
        assert 'weights' in report.lower()

    def test_get_component_accuracy(self):
        from calibration_engine import CalibrationEngine
        ce = CalibrationEngine(fresh=True)
        signal = {
            'symbol': 'XAUUSD', 'tf': 'H1', 'direction': 'LONG',
            'entry_price': 2000.0, 'score': 85,
            'components': {'OB': 20, 'SWEEP': 30},
            'atr': 5.0, 'checked': False, 'win': None,
        }
        ce.check_outcome(signal)
        data = ce.get_component_accuracy()
        assert 'component_accuracy' in data
        assert 'current_weights' in data
        assert 'win_rate' in data

    def test_get_status(self):
        from calibration_engine import CalibrationEngine
        ce = CalibrationEngine(fresh=True)
        status = ce.get_status()
        assert 'day' in status
        assert 'calibration_day' in status
        assert 'calibration_ready' in status
        assert 'signals_recorded' in status

    def test_get_weight_history(self):
        from calibration_engine import CalibrationEngine
        ce = CalibrationEngine(fresh=True)
        history = ce.get_weight_history()
        assert isinstance(history, list)

    def test_multiple_components_tracked(self):
        from calibration_engine import CalibrationEngine
        ce = CalibrationEngine(fresh=True)
        components = {'OB': 20, 'FVG': 20, 'SWEEP': 30, 'VWAP': 15,
                      'SESSION': 15, 'PATTERN': 20, 'DIVERGENCE': 20}
        signal = {
            'symbol': 'XAUUSD', 'tf': 'H1', 'direction': 'LONG',
            'entry_price': 2000.0, 'score': 85,
            'components': components,
            'atr': 5.0, 'checked': False, 'win': None,
        }
        ce.check_outcome(signal)
        for key in components:
            assert key in ce.component_accuracy

    def test_per_asset_tracking(self):
        from calibration_engine import CalibrationEngine
        ce = CalibrationEngine(fresh=True)
        ce.record_signal('XAUUSD', 'H1', 'LONG', 2000.0, 85, {'OB': 20}, atr=5.0)
        ce.record_signal('EURUSD', 'H1', 'LONG', 1.10, 75, {'OB': 20}, atr=0.001)
        assert 'XAUUSD' in ce.state['per_asset']
        assert 'EURUSD' in ce.state['per_asset']
        assert ce.state['per_asset']['XAUUSD']['total'] == 1

    def test_per_timeframe_tracking(self):
        from calibration_engine import CalibrationEngine
        ce = CalibrationEngine(fresh=True)
        ce.record_signal('XAUUSD', 'H1', 'LONG', 2000.0, 85, {'OB': 20}, atr=5.0)
        ce.record_signal('XAUUSD', 'M15', 'LONG', 2000.0, 70, {'OB': 20}, atr=5.0)
        assert 'H1' in ce.state['per_timeframe']
        assert 'M15' in ce.state['per_timeframe']

    def test_singleton(self):
        from calibration_engine import get_calibration_engine
        from calibration_engine import _calibration
        old = _calibration
        _calibration = None
        try:
            ce1 = get_calibration_engine()
            ce2 = get_calibration_engine()
            assert ce1 is ce2
        finally:
            _calibration = old

    def test_win_rate_calculation(self):
        from calibration_engine import CalibrationEngine
        ce = CalibrationEngine(fresh=True)
        ce.state['total_wins'] = 30
        ce.state['total_losses'] = 10
        wr = ce._win_rate()
        assert abs(wr - 0.75) < 0.01

    def test_check_pending_empty(self):
        from calibration_engine import CalibrationEngine
        ce = CalibrationEngine(fresh=True)
        checked = ce.check_pending_signals()
        assert checked >= 0
