"""Tests for forex_factory_news.py and news_lockout.py - OMNI BRAIN V2"""
import sys, os, json, time, threading
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'production'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import pytest

from forex_factory_news import ForexFactoryNews, CURRENCY_TO_PAIRS


class TestForexFactoryNews:
    def make_news(self):
        fn = ForexFactoryNews()
        fn.calendar = []
        fn.history = []
        fn.last_full_fetch = time.time() + 3600
        fn.last_today_fetch = time.time() + 3600
        return fn

    def test_fallback_calendar_returns_real_dates(self):
        fn = self.make_news()
        cal = fn._fallback_calendar()
        assert len(cal) >= 3
        assert cal[0]['event'] == 'Fed Interest Rate Decision'
        for event in cal:
            assert 'timestamp' in event
            assert 'ts_unix' in event
            assert isinstance(event['ts_unix'], float)

    def test_check_signal_block_clear(self):
        fn = self.make_news()
        future = time.time() + 86400 * 7
        fn.calendar = [{'event': 'NFP', 'currency': 'USD', 'impact': 'HIGH',
                        'ts_unix': future}]
        blocked, reason = fn.check_signal_block('XAUUSD')
        assert not blocked
        assert 'clear' in reason

    def test_check_signal_block_high_impact(self):
        fn = self.make_news()
        fn.last_today_fetch = time.time() + 3600
        soon = time.time() + 300
        fn.calendar = [{'event': 'NFP', 'currency': 'USD', 'impact': 'HIGH',
                        'ts_unix': soon}]
        blocked, reason = fn.check_signal_block('XAUUSD')
        assert blocked
        assert 'BLOCKED' in reason

    def test_get_upcoming_high_impact_returns_real_events(self):
        fn = self.make_news()
        t = time.time() + 3600
        fn.calendar = [
            {'event': 'NFP', 'currency': 'USD', 'impact': 'HIGH', 'ts_unix': t},
            {'event': 'CPI', 'currency': 'EUR', 'impact': 'MEDIUM', 'ts_unix': t + 7200},
        ]
        upcoming = fn.get_upcoming_high_impact(3)
        assert len(upcoming) > 0
        for ev in upcoming:
            assert isinstance(ev['minutes_until'], int)
            assert ev['ts_unix'] > time.time()

    def test_currency_to_pairs_mapping(self):
        assert 'XAUUSD' in CURRENCY_TO_PAIRS['USD']
        assert 'EURUSD' in CURRENCY_TO_PAIRS['EUR']
        assert 'GBPUSD' in CURRENCY_TO_PAIRS['GBP']
        assert 'USDJPY' in CURRENCY_TO_PAIRS['JPY']
        assert 'BTCUSD' in CURRENCY_TO_PAIRS['BTC']

    def test_pre_high_impact_alerts(self):
        fn = self.make_news()
        soon = time.time() + 28 * 60
        fn.calendar = [{'event': 'NFP', 'currency': 'USD', 'impact': 'HIGH',
                        'ts_unix': soon, 'timestamp': '2026-06-11T12:00:00'}]
        alerts = fn.get_pre_high_impact_alerts()
        assert len(alerts) > 0
        assert alerts[0]['event'] == 'NFP'
        assert 'affected_pairs' in alerts[0]

    def test_format_telegram_pre_alert(self):
        fn = self.make_news()
        alert = {'event': 'NFP', 'currency': 'USD', 'minutes_until': 28,
                 'affected_pairs': ['XAUUSD', 'EURUSD', 'GBPUSD'],
                 'block_until': '13:45 UTC', 'timestamp': '2026-06-11T13:00:00'}
        msg = fn.format_telegram_pre_alert(alert)
        assert 'HIGH IMPACT' in msg
        assert 'NFP' in msg
        assert 'XAUUSD' in msg

    def test_format_telegram_release(self):
        fn = self.make_news()
        event = {'event': 'NFP', 'currency': 'USD', 'forecast': '180K',
                 'actual': '256K', 'result': 'BEAT', 'direction': 'BULLISH',
                 'affected_pairs': ['XAUUSD', 'EURUSD', 'GBPUSD']}
        msg = fn.format_telegram_release(event)
        assert 'NEWS RELEASED' in msg
        assert 'BULLISH' in msg

    def test_format_terminal(self):
        fn = self.make_news()
        output = fn.format_terminal()
        assert isinstance(output, str)


class TestNewsLockout:
    def make_lockout(self):
        from news_lockout import get_news_lockout
        nl = get_news_lockout()
        nl._emergency_mode = False
        nl._emergency_until = None
        nl._volatility_spike = False
        nl._active_lock = None
        return nl

    def test_check_not_locked_by_default(self):
        nl = self.make_lockout()
        r = nl.check('XAUUSD')
        assert isinstance(r, dict)
        assert 'locked' in r

    def test_emergency_mode(self):
        nl = self.make_lockout()
        em = nl.trigger_emergency('Test emergency')
        assert em['locked'] is True
        assert em['lock_type'] == 'EMERGENCY'
        r = nl.check('XAUUSD')
        assert r['locked'] is True
        assert r['lock_type'] == 'EMERGENCY'

    def test_volatility_spike(self):
        nl = self.make_lockout()
        r = nl.check('XAUUSD', volatility=15.0, atr=5.0)
        assert r['volatility_spike'] is True
        assert r['locked'] is True
        assert r['lock_type'] == 'VOLATILITY'

    def test_load_events_fallback(self):
        from news_lockout import NewsLockoutEngine
        nle = NewsLockoutEngine()
        events = nle._load_events()
        assert len(events) >= 3
        for ev in events:
            assert 'title' in ev
            assert 'timestamp' in ev
            assert 'impact' in ev

    def test_default_events(self):
        from news_lockout import NewsLockoutEngine
        nle = NewsLockoutEngine()
        defaults = nle._default_events()
        assert len(defaults) >= 3
        titles = [e['title'] for e in defaults]
        assert 'NFP' in titles
        assert 'CPI' in titles
        assert 'FOMC' in titles
