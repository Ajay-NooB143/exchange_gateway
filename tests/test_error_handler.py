"""Tests for error_handler.py - OMNI BRAIN V2"""
import sys, os, json, time, threading
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'production'))
import pytest

from error_handler import ErrorHandler, get_error_handler, safe_call


class TestErrorHandler:
    def make_handler(self):
        h = ErrorHandler()
        h._errors.clear()
        h._error_counts.clear()
        return h

    def test_record_error(self):
        eh = self.make_handler()
        entry = eh.record('test_module', 'test_op', ValueError('bad value'))
        assert entry['module'] == 'test_module'
        assert entry['operation'] == 'test_op'
        assert entry['error_type'] == 'ValueError'
        assert entry['severity'] == 'ERROR'

    def test_get_recent(self):
        eh = self.make_handler()
        eh.record('mod', 'op1', ValueError('e1'))
        eh.record('mod', 'op2', RuntimeError('e2'))
        recent = eh.get_recent()
        assert len(recent) == 2

    def test_get_counts(self):
        eh = self.make_handler()
        eh.record('mod', 'op', ValueError('e'))
        eh.record('mod', 'op', ValueError('e2'))
        counts = eh.get_counts()
        assert counts['mod.op'] == 2

    def test_get_dashboard(self):
        eh = self.make_handler()
        eh.record('mod', 'op', ValueError('e'))
        dash = eh.get_dashboard()
        assert 'total_errors' in dash
        assert 'unique_types' in dash
        assert 'recent' in dash
        assert 'counts' in dash
        assert dash['total_errors'] >= 1

    def test_alert_throttling_same_error_within_5min(self):
        eh = self.make_handler()
        r1 = eh.record('mod', 'op', ValueError('e'), severity='CRITICAL', send_alert=True)
        assert r1['alerted'] is True
        r2 = eh.record('mod', 'op', ValueError('e'), severity='CRITICAL', send_alert=True)
        assert r2['alerted'] is False

    def test_clear(self):
        eh = self.make_handler()
        eh.record('mod', 'op', ValueError('e'))
        assert len(eh.get_recent()) == 1
        eh.clear()
        assert len(eh.get_recent()) == 0
        assert len(eh.get_counts()) == 0

    def test_safe_call_success(self):
        result = safe_call('mod', 'op', lambda x: x + 1, 5)
        assert result == 6

    def test_safe_call_failure(self):
        def failing(x):
            raise ValueError('failed')
        result = safe_call('mod', 'op', failing, 5, default=None)
        assert result is None

    def test_error_persistence(self):
        eh1 = self.make_handler()
        eh1.record('mod', 'op', ValueError('persist'))
        eh2 = ErrorHandler()
        recent = eh2.get_recent()
        found = any(e['operation'] == 'op' and e['error'] == 'persist' for e in recent)
        assert found

    def test_severity_levels(self):
        eh = self.make_handler()
        for sev in ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'):
            entry = eh.record('mod', 'op', ValueError(sev), severity=sev)
            assert entry['severity'] == sev

    def test_multiple_error_types(self):
        eh = self.make_handler()
        eh.record('mod', 'a', ValueError('v'))
        eh.record('mod', 'b', TypeError('t'))
        eh.record('mod', 'c', RuntimeError('r'))
        assert len(eh.get_counts()) == 3

    def test_traceback_capture(self):
        eh = self.make_handler()
        try:
            raise ValueError('traceback test')
        except ValueError as e:
            entry = eh.record('mod', 'op', e, exc_info=True)
        assert 'traceback' in entry
        assert 'traceback test' in entry['traceback']

    def test_max_stored_errors_limit(self):
        from error_handler import MAX_STORED_ERRORS
        eh = ErrorHandler()
        eh._errors.clear()
        eh._error_counts.clear()
        EH_LOG = Path(__file__).parent.parent / 'production' / 'logs' / 'errors.json'
        EH_LOG.write_text('[]')
        for i in range(MAX_STORED_ERRORS + 50):
            eh.record('mod', 'op', ValueError(f'error_{i}'))
        saved = json.loads(EH_LOG.read_text())
        assert len(saved) <= MAX_STORED_ERRORS

    def test_concurrent_recording(self):
        eh = self.make_handler()
        errors = []

        def worker(i):
            try:
                raise ValueError(f'thread_{i}')
            except ValueError as e:
                eh.record(f'mod_{i}', 'op', e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads: t.start()
        for t in threads: t.join()
        recent = eh.get_recent()
        assert len(recent) >= 20

    def test_singleton(self):
        h1 = get_error_handler()
        h2 = get_error_handler()
        assert h1 is h2
