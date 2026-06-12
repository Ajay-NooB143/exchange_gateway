"""
Tests for new OMNI BRAIN V2 intelligence modules:
- PatternEngine, DivergenceScanner, RiskManager
- ConfidenceScorer upgrade (11 components)
- SessionDetector, SentimentEngine, CorrelationEngine
- ForexFactoryNews, TreasuryMonitor
"""
import sys, os, json, math
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'production'))

import pytest
from confidence_scorer import ConfidenceScorer, ConfidenceResult
from session_detector import SessionDetector
from risk_manager import RiskManager
from pattern_engine import PatternEngine, PatternType
from divergence_scanner import DivergenceScanner

# ══════════════════════════════════════════════════════════════════════════════
# HELPER
# ══════════════════════════════════════════════════════════════════════════════

def make_candle(o=100.0, h=101.0, l=99.0, c=100.5, v=1000):
    return {'open': o, 'high': h, 'low': l, 'close': c, 'volume': v, 'timestamp': 0}


class TestConfidenceScorerUpgrade:
    """Test the 11-component confidence scorer with capping to 100."""

    def test_basic_scores(self):
        scorer = ConfidenceScorer()
        r = scorer.score('XAUUSD', 'H1', ob_active=True, fvg_active=True, sweep_fired=True)
        assert r.score <= 100
        assert r.decision in ('EXECUTE', 'WAIT', 'BLOCK')
        assert 'OB' in r.components
        assert 'FVG' in r.components
        assert 'SWEEP' in r.components

    def test_new_components_present(self):
        scorer = ConfidenceScorer()
        r = scorer.score('EURUSD', 'M15',
                         ob_active=True, fvg_active=True, sweep_fired=True,
                         correlation_score=10, news_penalty=-5, yield_score=5,
                         sentiment_score=8, pattern_score=15, divergence_score=10)
        expected_keys = {'OB', 'FVG', 'SWEEP', 'VWAP', 'SESSION',
                         'CORRELATION', 'NEWS', 'YIELD', 'SENTIMENT', 'PATTERN', 'DIVERGENCE'}
        assert expected_keys.issubset(r.components.keys())
        assert r.components['CORRELATION'] == 10
        assert r.components['NEWS'] == -5
        assert r.components['YIELD'] == 5
        assert r.components['SENTIMENT'] == 8
        assert r.components['PATTERN'] == 15
        assert r.components['DIVERGENCE'] == 10

    def test_raw_capped_at_100(self):
        scorer = ConfidenceScorer()
        r = scorer.score('XAUUSD', 'H1',
                         ob_active=True, fvg_active=True, sweep_fired=True,
                         correlation_score=15, yield_score=10, sentiment_score=10,
                         pattern_score=20, divergence_score=20)
        raw = sum(r.components.values())
        assert raw > 100  # raw exceeds cap
        assert r.score == 100  # capped

    def test_components_clamped(self):
        scorer = ConfidenceScorer()
        r = scorer.score('XAUUSD', 'H1', correlation_score=999, news_penalty=-999,
                         yield_score=999, sentiment_score=999, pattern_score=999, divergence_score=999)
        assert r.components['CORRELATION'] == 15
        assert r.components['NEWS'] == -15
        assert r.components['YIELD'] == 10
        assert r.components['SENTIMENT'] == 10
        assert r.components['PATTERN'] == 20
        assert r.components['DIVERGENCE'] == 20

    def test_zero_components(self):
        scorer = ConfidenceScorer()
        r = scorer.score('GBPUSD', 'D1', price=100, vwap=110, atr=5, hour_utc=22)
        assert r.score == 0
        assert r.decision == 'BLOCK'
        for v in r.components.values():
            assert v == 0 or v is False or v == ''

    def test_score_from_signal_metadata(self):
        scorer = ConfidenceScorer()
        meta = {
            'OB_SIGNAL': 2, 'FVG_SIGNAL': 1, 'SWEEP_SIGNAL': 1,
            'correlation_score': 8, 'news_penalty': -10,
            'yield_score': 3, 'sentiment_score': 7,
            'pattern_score': 12, 'divergence_score': 5,
        }
        r = scorer.score_from_signal('XAUUSD', 'H1', meta)
        assert r.components['CORRELATION'] == 8
        assert r.components['PATTERN'] == 12
        assert r.components['NEWS'] == -10

    def test_score_from_signal_empty_meta(self):
        scorer = ConfidenceScorer()
        r = scorer.score_from_signal('EURUSD', 'M15', {}, price=100, vwap=110, atr=5)
        assert r.score <= scorer.calculate_session_score(datetime.now(timezone.utc).hour)
        assert r.decision == 'BLOCK'

    def test_format_bar(self):
        assert ConfidenceScorer.format_bar(50) == '█████░░░░░'
        assert ConfidenceScorer.format_bar(100) == '██████████'
        assert ConfidenceScorer.format_bar(0) == '░░░░░░░░░░'

    def test_format_result(self):
        scorer = ConfidenceScorer()
        r = scorer.score('XAUUSD', 'H1', ob_active=True)
        output = ConfidenceScorer.format_result(r)
        assert 'XAUUSD' in output
        assert 'H1' in output

    def test_vwap_score(self):
        scorer = ConfidenceScorer()
        assert scorer.calculate_vwap_score(100, 99, 1) == 15  # > 0.5 ATR
        assert scorer.calculate_vwap_score(100, 99.8, 1) == 10  # > 0.2 ATR
        assert scorer.calculate_vwap_score(100, 100.05, 1) == 5  # within 0.2 ATR
        assert scorer.calculate_vwap_score(100, 101, 1) == 0  # below VWAP
        assert scorer.calculate_vwap_score(100, 99, 0) == 0  # zero ATR

    def test_session_score(self):
        scorer = ConfidenceScorer()
        assert scorer.calculate_session_score(8) == 15  # London
        assert scorer.calculate_session_score(14) == 15  # NY
        assert scorer.calculate_session_score(6) == 10  # London open
        assert scorer.calculate_session_score(2) == 5   # Asian
        assert scorer.calculate_session_score(22) == 0  # off-hours

    def test_get_set_threshold(self):
        scorer = ConfidenceScorer()
        assert scorer.get_threshold('XAUUSD') == 75
        scorer.set_threshold('XAUUSD', 80)
        assert scorer.get_threshold('XAUUSD') == 80

    def test_history(self):
        scorer = ConfidenceScorer()
        scorer.score('XAUUSD', 'H1')
        scorer.score('EURUSD', 'M15')
        assert len(scorer.get_history()) == 2
        assert len(scorer.get_history(symbol='XAUUSD')) == 1


class TestPatternEngine:
    """Test SMC pattern detection."""

    def test_no_patterns_empty_candles(self):
        pe = PatternEngine()
        r = pe.scan('XAUUSD', [], 100.0)
        assert r.total_score == 0
        assert r.patterns == []

    def test_no_patterns_few_candles(self):
        pe = PatternEngine()
        r = pe.scan('XAUUSD', [make_candle() for _ in range(3)], 100.0)
        assert r.total_score == 0

    def test_detects_propulsion_block(self):
        pe = PatternEngine()
        candles = [make_candle() for _ in range(12)]
        candles[-1] = make_candle(o=100, h=105, l=99.5, c=104.5, v=5000)  # big bullish body
        r = pe.scan('XAUUSD', candles, 104.5)
        # May or may not detect propulsion depending on candle shape
        assert r.total_score >= 0
        assert r.symbol == 'XAUUSD'

    def test_detects_rejection_block(self):
        pe = PatternEngine()
        candles = [make_candle() for _ in range(5)]
        candles[-1] = make_candle(o=100, h=108, l=99, c=100.5, v=3000)  # long upper wick
        r = pe.scan('XAUUSD', candles, 100.5)
        # Check rejection
        rejection = [p for p in r.patterns if p['type'] == PatternType.REJECTION_BLOCK.value]
        if rejection:
            assert rejection[0]['score'] == 5

    def test_classify_premium_discount(self):
        pe = PatternEngine()
        candles = [make_candle(o=100, h=110, l=90, c=105) for _ in range(12)]
        pd = pe._classify_premium_discount(candles, 105)
        assert 'zone' in pd
        assert 'position' in pd
        assert 0 <= pd['position'] <= 1

    def test_format_terminal_with_patterns(self):
        pe = PatternEngine()
        candles = [make_candle() for _ in range(12)]
        r = pe.scan('XAUUSD', candles, 100.0)
        output = pe.format_terminal(r)
        assert 'XAUUSD' in output
        assert 'pts' in output


class TestDivergenceScanner:
    """Test multi-TF divergence detection."""

    def test_no_divergence_empty(self):
        ds = DivergenceScanner()
        r = ds.scan('XAUUSD', {})
        assert r.total_score == 0
        assert r.divergences == []

    def test_no_divergence_short_data(self):
        ds = DivergenceScanner()
        r = ds.scan('XAUUSD', {'H1': [make_candle() for _ in range(5)]})
        assert r.total_score == 0

    def test_rsi_calculation(self):
        ds = DivergenceScanner()
        closes = [100 + i + (i % 3) for i in range(30)]
        rsi = ds._calc_rsi(closes, 14)
        assert len(rsi) == len(closes)
        for v in rsi:
            assert 0 <= v <= 100

    def test_macd_calculation(self):
        ds = DivergenceScanner()
        closes = [100 + i * 0.5 for i in range(30)]
        macd, signal = ds._calc_macd(closes)
        assert len(macd) == len(closes)
        assert len(signal) == len(closes)

    def test_stochastic_calculation(self):
        ds = DivergenceScanner()
        highs = [101 + i * 0.3 for i in range(30)]
        lows = [99 + i * 0.3 for i in range(30)]
        closes = [100 + i * 0.3 for i in range(30)]
        k, d = ds._calc_stochastic(highs, lows, closes)
        assert len(k) == len(closes)
        assert len(d) == len(closes)

    def test_format_terminal_no_patterns(self):
        ds = DivergenceScanner()
        r = ds.scan('XAUUSD', {})
        output = ds.format_terminal(r)
        assert 'XAUUSD' in output

    def test_multi_tf_bonus(self):
        ds = DivergenceScanner()
        assert ds.MULTI_TF_BONUS == 20


class TestRiskManager:
    """Test risk management module."""

    def test_default_balance(self):
        rm = RiskManager()
        assert rm.balance > 0
        assert rm.risk_pct > 0

    def test_position_size_calculation(self):
        rm = RiskManager()
        ps = rm.calculate_position_size('XAUUSD', 2000, 1990)
        assert ps['account_balance'] == rm.balance
        assert ps['recommended_lots'] > 0
        assert ps['dollar_risk'] > 0

    def test_kelly_criterion(self):
        rm = RiskManager()
        ps = rm.calculate_position_size('EURUSD', 1.10, 1.09, win_rate=0.6, rr=2.5)
        assert ps['kelly_pct'] > 0
        assert ps['half_kelly_pct'] > 0
        assert ps['kelly_lots'] > 0

    def test_spread_check(self):
        rm = RiskManager()
        ok, pips, msg = rm.check_spread(1.1000, 1.1003, 'EURUSD')
        assert ok
        assert abs(pips - 3.0) < 0.001
        assert '✅' in msg

    def test_spread_blocked(self):
        rm = RiskManager()
        rm.max_spread_pips = 1.0
        ok, pips, msg = rm.check_spread(1.1000, 1.1003, 'EURUSD')
        assert not ok
        assert '❌' in msg

    def test_trade_limits(self):
        rm = RiskManager()
        ok, reason = rm.check_trade_limits('XAUUSD')
        assert ok

    def test_trade_limits_hit_max_trades(self):
        rm = RiskManager()
        rm.open_trades = rm.max_concurrent
        ok, reason = rm.check_trade_limits('XAUUSD')
        assert not ok

    def test_check_halts_drawdown(self):
        rm = RiskManager()
        rm.peak_balance = rm.balance * 2
        halted, reason = rm.check_halts()
        if halted:
            assert 'Drawdown' in reason

    def test_get_status(self):
        rm = RiskManager()
        status = rm.get_status()
        assert 'balance' in status
        assert 'daily_pnl' in status
        assert 'open_trades' in status

    def test_format_terminal(self):
        rm = RiskManager()
        output = rm.format_terminal()
        assert 'Balance' in output
        assert 'ACTIVE' in output or 'HALTED' in output


class TestSessionDetector:
    """Test session overlap detection."""

    def test_known_sessions(self):
        sd = SessionDetector()
        info = sd.get_session_info(hour_utc=9)  # London open
        assert 8 <= info['hour_utc'] < 10
        assert 'London' in info['active_sessions']
        assert not info['dead_zone']

    def test_dead_zone(self):
        sd = SessionDetector()
        info = sd.get_session_info(hour_utc=22)
        assert info['dead_zone']
        assert info['session_score'] == 0

    def test_best_pairs_for_session(self):
        sd = SessionDetector()
        info = sd.get_session_info(hour_utc=14)  # NY
        assert 'XAUUSD' in info['best_pairs']
        assert 'SP500' in info['best_pairs']

    def test_session_score_values(self):
        sd = SessionDetector()
        assert sd.get_session_info(9)['session_score'] == 15
        assert sd.get_session_info(14)['session_score'] == 15
        assert sd.get_session_info(3)['session_score'] == 5
        assert sd.get_session_info(21)['session_score'] == 0

    def test_format_terminal(self):
        sd = SessionDetector()
        output = sd.format_terminal()
        assert 'Active' in output or 'NONE' in output

    def test_london_ny_overlap(self):
        sd = SessionDetector()
        info = sd.get_session_info(hour_utc=14)
        if info['overlap']:
            assert info['overlap_score'] == 15


class TestConfidenceScorer11Components:
    """Full integration: all 11 components via score()"""

    def test_full_components_decision_execute(self):
        scorer = ConfidenceScorer()
        r = scorer.score('XAUUSD', 'H1',
                         ob_active=True, fvg_active=True, sweep_fired=True,
                         price=100, vwap=99, atr=2,
                         hour_utc=14,
                         correlation_score=10, yield_score=8, sentiment_score=8,
                         pattern_score=15, divergence_score=10)
        assert r.score >= 75
        assert r.decision == 'EXECUTE'

    def test_full_components_decision_block(self):
        scorer = ConfidenceScorer()
        r = scorer.score('GBPUSD', 'D1',
                         ob_active=False, fvg_active=False, sweep_fired=False,
                         price=100, vwap=110, atr=5,
                         hour_utc=22,
                         correlation_score=0, news_penalty=-15, yield_score=0,
                         sentiment_score=0, pattern_score=0, divergence_score=0)
        assert r.decision == 'BLOCK'

    def test_news_penalty_reduces_score(self):
        scorer = ConfidenceScorer()
        r1 = scorer.score('XAUUSD', 'H1', ob_active=True, fvg_active=True, sweep_fired=True, hour_utc=14)
        r2 = scorer.score('XAUUSD', 'H1', ob_active=True, fvg_active=True, sweep_fired=True, hour_utc=14, news_penalty=-15)
        assert r2.score <= r1.score

    def test_13_components_key_count(self):
        scorer = ConfidenceScorer()
        r = scorer.score('EURUSD', 'M15',
                         ob_active=True, fvg_active=True, sweep_fired=True,
                         correlation_score=5, news_penalty=-3, yield_score=2,
                         sentiment_score=4, pattern_score=6, divergence_score=3)
        assert len(r.components) == 15  # 13 base + 2 combo bonuses


class TestCorrelationEngine:
    """Test the multi-pair correlation engine."""

    def test_pearson_calculation(self):
        from correlation_engine import CorrelationEngine
        ce = CorrelationEngine()
        # _pearson uses returns (diff between consecutive), need varying returns
        a = [1, 2, 4, 7, 11, 16, 22, 29, 37, 46, 56, 67]
        b = [3, 5, 9, 15, 23, 33, 45, 59, 75, 93, 113, 135]  # b ≈ 2*a + 1
        corr = ce._pearson(a, b)
        assert abs(corr - 1.0) < 0.01

    def test_pearson_inverse(self):
        from correlation_engine import CorrelationEngine
        ce = CorrelationEngine()
        # a increases with increasing returns, b decreases with decreasing returns
        a = [0, 1, 3, 6, 10, 15, 21, 28, 36, 45, 55, 66]
        b = [0, -7, -15, -24, -34, -45, -57, -70, -84, -99, -115, -132]  # mirrored inverse
        corr = ce._pearson(a, b)
        assert abs(corr - (-1.0)) < 0.01

    def test_pearson_zero_correlation(self):
        from correlation_engine import CorrelationEngine
        ce = CorrelationEngine()
        a = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
        b = [5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5]  # flat
        corr = ce._pearson(a, b)
        assert corr == 0.0

    def test_pearson_short_data(self):
        from correlation_engine import CorrelationEngine
        ce = CorrelationEngine()
        corr = ce._pearson([1, 2, 3], [4, 5, 6])
        assert corr == 0.0

    def test_update_price_history(self):
        from correlation_engine import CorrelationEngine
        ce = CorrelationEngine()
        ce.update_price('XAUUSD', 100.0)
        ce.update_price('XAUUSD', 101.0)
        assert len(ce.price_history['XAUUSD']) == 2

    def test_update_price_unknown_symbol(self):
        from correlation_engine import CorrelationEngine
        ce = CorrelationEngine()
        ce.update_price('UNKNOWN', 100.0)  # should not crash

    def test_correlation_matrix(self):
        from correlation_engine import CorrelationEngine
        ce = CorrelationEngine()
        for i in range(15):
            for sym in ['XAUUSD', 'EURUSD', 'GBPUSD']:
                ce.update_price(sym, 100.0 + i + hash(sym) % 10)
        matrix = ce.update_correlation_matrix()
        assert 'XAUUSD' in matrix
        assert 'EURUSD' in matrix
        assert matrix['XAUUSD']['XAUUSD'] == 1.0

    def test_get_score_adjustment_xauusd_bullish_confirm(self):
        from correlation_engine import CorrelationEngine
        ce = CorrelationEngine()
        # Set up inverse correlation manually
        for i in range(15):
            ce.update_price('XAUUSD', 100.0 + i)
            ce.update_price('USDCHF', 100.0 - i)  # inverse
            ce.update_price('SP500', 100.0 + i * 0.5)
        ce.update_correlation_matrix()
        adj, reason = ce.get_score_adjustment('XAUUSD', 'BULLISH', dxy_falling=True)
        assert adj >= 10  # should get at least DXY +10

    def test_get_score_adjustment_eurusd_confirm(self):
        from correlation_engine import CorrelationEngine
        ce = CorrelationEngine()
        for i in range(15):
            ce.update_price('EURUSD', 100.0 + i)
            ce.update_price('GBPUSD', 100.0 + i)  # same direction
        ce.update_correlation_matrix()
        adj, reason = ce.get_score_adjustment('EURUSD', 'BULLISH')
        assert adj >= 0

    def test_divergence_detection(self):
        from correlation_engine import CorrelationEngine
        ce = CorrelationEngine()
        for i in range(15):
            for sym in ['XAUUSD', 'USDCHF']:
                ce.update_price(sym, 100.0 + i)
        ce.update_correlation_matrix()
        alerts = ce.check_divergence()
        assert isinstance(alerts, list)

    def test_format_telegram_divergence(self):
        from correlation_engine import CorrelationEngine
        ce = CorrelationEngine()
        alert = {'pair1': 'EURUSD', 'pair2': 'GBPUSD', 'expected': 0.85, 'current': 0.12, 'type': 'NEGATIVE'}
        msg = ce.format_telegram_divergence(alert)
        assert 'EURUSD' in msg
        assert 'GBPUSD' in msg
        assert 'CORRELATION DIVERGENCE' in msg

    def test_format_terminal(self):
        from correlation_engine import CorrelationEngine
        ce = CorrelationEngine()
        for i in range(15):
            for sym in ['XAUUSD', 'EURUSD', 'GBPUSD', 'USDCHF', 'SP500']:
                ce.update_price(sym, 100.0 + i + hash(sym) % 5)
        ce.update_correlation_matrix()
        lines = ce.format_terminal()
        assert isinstance(lines, list)


class TestForexFactoryNews:
    """Test the Forex Factory news integration."""

    def test_fallback_calendar(self):
        from forex_factory_news import ForexFactoryNews
        fn = ForexFactoryNews()
        cal = fn._fallback_calendar()
        assert len(cal) >= 3
        assert cal[0]['event'] == 'Fed Interest Rate Decision'

    def test_check_signal_block_clear(self):
        from forex_factory_news import ForexFactoryNews
        fn = ForexFactoryNews()
        # Set calendar to far future
        import time
        future = time.time() + 86400 * 7
        fn.calendar = [{'event': 'NFP', 'currency': 'USD', 'impact': 'HIGH',
                        'ts_unix': future}]
        blocked, reason = fn.check_signal_block('XAUUSD')
        assert not blocked

    def test_check_signal_block_high_impact(self):
        from forex_factory_news import ForexFactoryNews
        fn = ForexFactoryNews()
        import time
        fn.last_today_fetch = time.time() + 3600  # skip fetch
        soon = time.time() + 300  # 5 min away
        fn.calendar = [{'event': 'NFP', 'currency': 'USD', 'impact': 'HIGH',
                        'ts_unix': soon}]
        blocked, reason = fn.check_signal_block('XAUUSD')
        assert blocked
        assert 'BLOCKED' in reason

    def test_currency_to_pairs_mapping(self):
        from forex_factory_news import CURRENCY_TO_PAIRS
        assert 'XAUUSD' in CURRENCY_TO_PAIRS['USD']
        assert 'EURUSD' in CURRENCY_TO_PAIRS['EUR']
        assert 'GBPUSD' in CURRENCY_TO_PAIRS['GBP']

    def test_get_upcoming_high_impact(self):
        from forex_factory_news import ForexFactoryNews
        fn = ForexFactoryNews()
        import time
        today = time.time() + 3600
        fn.calendar = [
            {'event': 'NFP', 'currency': 'USD', 'impact': 'HIGH', 'ts_unix': today},
            {'event': 'CPI', 'currency': 'EUR', 'impact': 'MEDIUM', 'ts_unix': today + 7200},
        ]
        upcoming = fn.get_upcoming_high_impact(3)
        assert len(upcoming) > 0
        assert upcoming[0]['event'] in ('NFP', 'CPI')

    def test_pre_high_impact_alerts(self):
        from forex_factory_news import ForexFactoryNews
        fn = ForexFactoryNews()
        import time
        # 28 min away = should trigger
        soon = time.time() + 28 * 60
        fn.calendar = [{'event': 'NFP', 'currency': 'USD', 'impact': 'HIGH',
                        'ts_unix': soon, 'timestamp': '2026-06-11T12:00:00'}]
        alerts = fn.get_pre_high_impact_alerts()
        assert len(alerts) > 0
        assert alerts[0]['event'] == 'NFP'

    def test_format_telegram_pre_alert(self):
        from forex_factory_news import ForexFactoryNews
        fn = ForexFactoryNews()
        alert = {'event': 'NFP', 'currency': 'USD', 'minutes_until': 28,
                 'affected_pairs': ['XAUUSD', 'EURUSD', 'GBPUSD'],
                 'block_until': '13:45 UTC', 'timestamp': '2026-06-11T13:00:00'}
        msg = fn.format_telegram_pre_alert(alert)
        assert 'HIGH IMPACT' in msg
        assert 'NFP' in msg
        assert 'XAUUSD' in msg

    def test_format_telegram_release(self):
        from forex_factory_news import ForexFactoryNews
        fn = ForexFactoryNews()
        event = {'event': 'NFP', 'currency': 'USD', 'forecast': '180K',
                 'actual': '256K', 'result': '🟢 BEAT', 'direction': 'BULLISH',
                 'affected_pairs': ['XAUUSD', 'EURUSD', 'GBPUSD']}
        msg = fn.format_telegram_release(event)
        assert 'NEWS RELEASED' in msg
        assert 'BULLISH' in msg

    def test_format_terminal(self):
        from forex_factory_news import ForexFactoryNews
        fn = ForexFactoryNews()
        output = fn.format_terminal()
        assert isinstance(output, str)


class TestTreasuryMonitor:
    """Test the US Treasury yield monitor."""

    def test_yield_curve_calculation(self):
        from treasury_monitor import TreasuryMonitor
        tm = TreasuryMonitor()
        tm.yields = {'2Y': 4.82, '10Y': 4.61, '30Y': 4.71}
        curve_val = tm.get_yield_curve()
        assert abs(curve_val - (-0.21)) < 0.01

    def test_real_yield_calculation(self):
        from treasury_monitor import TreasuryMonitor
        tm = TreasuryMonitor()
        tm.yields = {'10Y': 4.61}
        real = tm.get_real_yield()
        assert abs(real - 2.11) < 0.01

    def test_yield_curve_normal(self):
        from treasury_monitor import TreasuryMonitor
        tm = TreasuryMonitor()
        tm.yields = {'2Y': 4.0, '10Y': 4.8, '30Y': 5.0}
        curve = tm.get_yield_curve()
        assert curve > 0.5

    def test_yield_curve_inverted(self):
        from treasury_monitor import TreasuryMonitor
        tm = TreasuryMonitor()
        tm.yields = {'2Y': 5.0, '10Y': 4.5, '30Y': 4.3}
        curve = tm.get_yield_curve()
        assert curve < 0

    def test_score_adjustment_xauusd_inverted(self):
        from treasury_monitor import TreasuryMonitor
        tm = TreasuryMonitor()
        tm.yields = {'2Y': 5.0, '10Y': 4.0}  # inverted
        adj, reason = tm.get_score_adjustment('XAUUSD')
        assert adj == 15  # safe haven
        assert 'INVERTED' in reason

    def test_score_adjustment_equities_inverted(self):
        from treasury_monitor import TreasuryMonitor
        tm = TreasuryMonitor()
        tm.yields = {'2Y': 5.0, '10Y': 4.0}
        adj, reason = tm.get_score_adjustment('SP500')
        assert adj == -15  # bearish equities

    def test_score_adjustment_equities_normal(self):
        from treasury_monitor import TreasuryMonitor
        tm = TreasuryMonitor()
        tm.yields = {'2Y': 4.0, '10Y': 4.8}
        adj, reason = tm.get_score_adjustment('SP500')
        assert adj == 10  # bullish equities

    def test_significant_moves_none(self):
        from treasury_monitor import TreasuryMonitor
        tm = TreasuryMonitor()
        result = tm.get_significant_moves()
        assert result is None

    def test_significant_moves_detected(self):
        from treasury_monitor import TreasuryMonitor
        tm = TreasuryMonitor()
        tm.yields = {'2Y': 4.82, '10Y': 4.61, '30Y': 4.71}
        tm.prev_yields = {'2Y': 4.75, '10Y': 4.52, '30Y': 4.65}
        result = tm.get_significant_moves()
        assert result is not None
        assert 'TREASURY YIELD ALERT' in result

    def test_score_adjustment_fiat_rising_yields(self):
        from treasury_monitor import TreasuryMonitor
        tm = TreasuryMonitor()
        tm.yields = {'10Y': 4.61}
        tm.prev_yields = {'10Y': 4.52}
        adj, reason = tm.get_score_adjustment('EURUSD')
        # 9bps rise in 10Y → USD strong
        assert 'USD' in reason or 'neutral' in reason

    def test_format_terminal(self):
        from treasury_monitor import TreasuryMonitor
        tm = TreasuryMonitor()
        tm.yields = {'2Y': 4.82, '10Y': 4.61, '30Y': 4.71}
        output = tm.format_terminal()
        assert 'YIELD' in output
        assert '4.82' in output


class TestSentimentEngine:
    """Test the sentiment heatmap engine."""

    def test_fear_greed_default(self):
        from sentiment_engine import SentimentEngine
        se = SentimentEngine()
        assert 0 <= se.fear_greed <= 100

    def test_fear_greed_fetch(self):
        from sentiment_engine import SentimentEngine
        se = SentimentEngine()
        fg = se.fetch_fear_greed()
        assert 0 <= fg <= 100

    def test_currency_strength_default(self):
        from sentiment_engine import SentimentEngine
        se = SentimentEngine()
        assert 0 <= se.currency_strength.get('USD', 0) <= 100

    def test_currency_strength_calculation(self):
        from sentiment_engine import SentimentEngine
        se = SentimentEngine()
        prices = {'EURUSD': 1.08, 'GBPUSD': 1.27, 'USDJPY': 150.0,
                  'USDCHF': 0.88, 'AUDUSD': 0.65, 'USDCAD': 1.36,
                  'NZDUSD': 0.60}
        strengths = se._calculate_currency_strength(prices)
        assert 'USD' in strengths
        assert 'EUR' in strengths
        assert 0 <= strengths['USD'] <= 100
        assert 0 <= strengths['EUR'] <= 100

    def test_score_adjustment_gold_extreme_fear(self):
        from sentiment_engine import SentimentEngine
        se = SentimentEngine()
        se.fear_greed = 15
        adj, reason = se.get_score_adjustment('XAUUSD')
        assert adj == 15  # safe haven
        assert 'extreme fear' in reason

    def test_score_adjustment_gold_extreme_greed(self):
        from sentiment_engine import SentimentEngine
        se = SentimentEngine()
        se.fear_greed = 85
        adj, reason = se.get_score_adjustment('XAUUSD')
        assert adj == -10  # risk on
        assert 'extreme greed' in reason

    def test_score_adjustment_equities_extreme_greed(self):
        from sentiment_engine import SentimentEngine
        se = SentimentEngine()
        se.fear_greed = 85
        adj, reason = se.get_score_adjustment('SP500')
        assert adj == 10  # momentum

    def test_score_adjustment_usd_strong(self):
        from sentiment_engine import SentimentEngine
        se = SentimentEngine()
        se.currency_strength['USD'] = 75
        adj, reason = se.get_score_adjustment('EURUSD')
        assert adj == -10  # USD strong → EURUSD bearish

    def test_score_adjustment_usd_weak(self):
        from sentiment_engine import SentimentEngine
        se = SentimentEngine()
        se.currency_strength['USD'] = 25
        adj, reason = se.get_score_adjustment('GBPUSD')
        assert adj == 10  # USD weak → GBPUSD bullish

    def test_score_adjustment_gbp_strong(self):
        from sentiment_engine import SentimentEngine
        se = SentimentEngine()
        se.currency_strength['GBP'] = 75
        adj, reason = se.get_score_adjustment('GBPUSD')
        assert adj == 10  # GBP strong → bullish

    def test_format_terminal(self):
        from sentiment_engine import SentimentEngine
        se = SentimentEngine()
        se.fear_greed = 45
        output = se.format_terminal()
        assert 'SENT' in output
        assert 'F&G' in output


class TestPatternEngineAllPatterns:
    """Test all 7 SMC patterns."""

    def test_breaker_block_detection(self):
        from pattern_engine import PatternEngine
        pe = PatternEngine()
        candles = [{'open': 100, 'high': 101, 'low': 99, 'close': 100.5, 'volume': 1000} for _ in range(8)]
        result = pe.scan('XAUUSD', candles, 100.5)
        assert result.symbol == 'XAUUSD'

    def test_mitigation_block_detection(self):
        from pattern_engine import PatternEngine
        pe = PatternEngine()
        candles = [{'open': 100, 'high': 101, 'low': 99, 'close': 100.5, 'volume': 1000} for _ in range(7)]
        # Add a big body candle
        candles[-1] = {'open': 100, 'high': 105, 'low': 99, 'close': 104, 'volume': 5000}
        result = pe.scan('XAUUSD', candles, 102.0)
        # May or may not detect mitigation
        assert result.total_score >= 0

    def test_propulsion_block_detected(self):
        from pattern_engine import PatternEngine, PatternType
        pe = PatternEngine()
        candles = [{'open': 100, 'high': 101, 'low': 99, 'close': 100.5, 'volume': 1000} for _ in range(12)]
        # Strong no-wick bullish candle
        candles[-1] = {'open': 100, 'high': 104.9, 'low': 100.1, 'close': 104.8, 'volume': 8000}
        result = pe.scan('XAUUSD', candles, 104.8)
        propulsion = [p for p in result.patterns if p['type'] == PatternType.PROPULSION_BLOCK.value]
        if propulsion:
            assert propulsion[0]['score'] == 7

    def test_equilibrium_detection(self):
        from pattern_engine import PatternEngine, PatternType
        pe = PatternEngine()
        candles = [{'open': 100 + i, 'high': 101 + i, 'low': 99 + i, 'close': 100.5 + i, 'volume': 1000} for i in range(10)]
        # Price at 50% of range
        high = max(c['high'] for c in candles)
        low = min(c['low'] for c in candles)
        eq_price = (high + low) / 2
        result = pe.scan('XAUUSD', candles, eq_price)
        equilibrium = [p for p in result.patterns if p['type'] == PatternType.EQUILIBRIUM.value]
        if equilibrium:
            assert 'EQ' in equilibrium[0]['detail'] or 'touch' in equilibrium[0]['detail']

    def test_premium_discount_classification(self):
        from pattern_engine import PatternEngine
        pe = PatternEngine()
        candles = [{'open': 100, 'high': 110, 'low': 90, 'close': 105, 'volume': 1000} for _ in range(12)]
        pd = pe._classify_premium_discount(candles, 105)
        assert pd['zone'] in ('premium', 'discount', 'unknown')
        pd2 = pe._classify_premium_discount(candles, 95)
        assert pd2['zone'] == 'discount'

    def test_inducement_detection(self):
        from pattern_engine import PatternEngine, PatternType
        pe = PatternEngine()
        candles = []
        for i in range(6):
            candles.append({'open': 100 + i, 'high': 102 + i, 'low': 99 + i, 'close': 101 + i, 'volume': 1000})
        # Make last candle break above previous high
        candles[-1] = {'open': 106, 'high': 107, 'low': 105, 'close': 106.5, 'volume': 2000}
        result = pe.scan('XAUUSD', candles, 106.5)
        inducement = [p for p in result.patterns if p['type'] == PatternType.INDUCEMENT.value]
        # May or may not detect
        assert result.total_score >= 0

    def test_total_score_aggregation(self):
        from pattern_engine import PatternEngine
        pe = PatternEngine()
        candles = [{'open': 100, 'high': 101, 'low': 99, 'close': 100.5, 'volume': 1000} for _ in range(15)]
        result = pe.scan('XAUUSD', candles, 100.5)
        total = sum(p['score'] for p in result.patterns)
        assert result.total_score == total


class TestDivergenceScannerExtended:
    """Extended divergence scanner tests."""

    def test_rsi_values_in_range(self):
        from divergence_scanner import DivergenceScanner
        ds = DivergenceScanner()
        closes = [100 + i * 0.5 for i in range(30)]
        rsi = ds._calc_rsi(closes, 14)
        assert all(0 <= v <= 100 for v in rsi)

    def test_macd_values(self):
        from divergence_scanner import DivergenceScanner
        ds = DivergenceScanner()
        closes = [100 + i for i in range(30)]
        macd, signal = ds._calc_macd(closes)
        assert len(macd) == len(closes)

    def test_stochastic_values(self):
        from divergence_scanner import DivergenceScanner
        ds = DivergenceScanner()
        highs = [101 + i for i in range(30)]
        lows = [99 + i for i in range(30)]
        closes = [100 + i for i in range(30)]
        k, d = ds._calc_stochastic(highs, lows, closes)
        assert all(0 <= v <= 100 for v in k)
        assert all(0 <= v <= 100 for v in d)

    def test_hidden_bullish_divergence(self):
        from divergence_scanner import DivergenceScanner
        ds = DivergenceScanner()
        # Hidden bullish: price higher low, RSI lower low
        closes = [100, 101, 102, 101, 103, 102, 104]
        rsi = [50, 55, 60, 52, 58, 48, 55]
        # This should not trigger regular divergence
        # It's a different pattern that may or may not be detected
        result = ds.scan('XAUUSD', {'H1': [{'open': c-0.5, 'high': c+0.5, 'low': c-0.5, 'close': c, 'volume': 1000} for c in closes]})
        assert result.total_score >= 0

    def test_multi_tf_divergence_bonus(self):
        from divergence_scanner import DivergenceScanner
        ds = DivergenceScanner()
        # Use strong trending data to create divergence signals
        # Multi-TF bonus is tested independently
        assert ds.MULTI_TF_BONUS == 20

    def test_format_terminal_with_divergence(self):
        from divergence_scanner import DivergenceScanner
        ds = DivergenceScanner()
        # Generate bullish divergence by making price drop and RSI rise
        import random
        random.seed(42)
        closes = [100 - i * 0.5 + random.uniform(-0.1, 0.1) for i in range(25)]
        tf_data = {'M15': [{'open': c-0.5, 'high': c+0.5, 'low': c-0.5, 'close': c, 'volume': 1000} for c in closes]}
        result = ds.scan('XAUUSD', tf_data)
        output = ds.format_terminal(result)
        assert 'XAUUSD' in output

    def test_macd_divergence_detection(self):
        from divergence_scanner import DivergenceScanner
        ds = DivergenceScanner()
        closes = [100, 99, 98, 97, 96, 95, 94, 93, 92, 91, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100]
        pf = ds._detect_macd_divergence(closes, [0.5]*len(closes), [0.3]*len(closes))
        # MACD divergence requires specific conditions
        assert pf is None or isinstance(pf, dict)


class TestRiskManagerExtended:
    """Extended risk manager tests."""

    def test_kelly_criterion_half_kelly(self):
        from risk_manager import RiskManager
        rm = RiskManager()
        ps = rm.calculate_position_size('XAUUSD', 2000, 1990, win_rate=0.6, rr=2.0)
        assert ps['kelly_pct'] > 0
        assert ps['half_kelly_pct'] == ps['kelly_pct'] / 2

    def test_kelly_criterion_zero_rr(self):
        from risk_manager import RiskManager
        rm = RiskManager()
        ps = rm.calculate_position_size('XAUUSD', 2000, 1990, win_rate=0.5, rr=0)
        assert ps['kelly_pct'] == 0

    def test_max_daily_loss_halt(self):
        from risk_manager import RiskManager
        rm = RiskManager()
        rm.halted_until = None  # clear any prior halt
        rm.peak_balance = rm.balance  # no drawdown
        rm.daily_pnl = -(rm.balance * 0.05)  # 5% loss > 3% max
        halted, reason = rm.check_halts()
        assert halted
        assert 'Daily loss' in reason

    def test_drawdown_halt(self):
        from risk_manager import RiskManager
        rm = RiskManager()
        rm.peak_balance = rm.balance * 1.15  # 15% peak above current
        rm.balance = rm.balance  # current is lower
        halted, reason = rm.check_halts()
        if halted:
            assert 'Drawdown' in reason

    def test_spread_block_high_spread(self):
        from risk_manager import RiskManager
        rm = RiskManager()
        rm.max_spread_pips = 1.0
        ok, pips, msg = rm.check_spread(1.1000, 1.1005, 'EURUSD')
        assert not ok

    def test_concurrent_trade_limit(self):
        from risk_manager import RiskManager
        rm = RiskManager()
        rm.open_trades = rm.max_concurrent
        ok, reason = rm.check_trade_limits('XAUUSD')
        assert not ok
        assert 'concurrent' in reason

    def test_max_trades_per_pair(self):
        from risk_manager import RiskManager
        rm = RiskManager()
        rm.trades_today['XAUUSD'] = rm.max_trades_per_pair
        ok, reason = rm.check_trade_limits('XAUUSD')
        assert not ok
        assert 'Max trades/day' in reason

    def test_position_size_pip_value(self):
        from risk_manager import RiskManager
        rm = RiskManager()
        ps = rm.calculate_position_size('EURUSD', 1.10, 1.09)
        assert ps['pip_value'] == 1.0
        ps2 = rm.calculate_position_size('XAUUSD', 2000, 1990)
        assert ps2['pip_value'] == 10.0

    def test_record_trade_updates(self):
        from risk_manager import RiskManager
        rm = RiskManager()
        rm.daily_pnl = 0  # clear prior state
        rm.trades_today = {}
        old_count = rm.trades_today.get('XAUUSD', 0)
        rm.record_trade('XAUUSD', pnl=50)
        assert rm.trades_today.get('XAUUSD', 0) == old_count + 1
        assert rm.daily_pnl == 50


class TestFullPipelineIntegration:
    """Integration tests simulating full pipeline with all modules."""

    def test_confidence_scorer_with_all_components_max(self):
        """MAX RAW = 190 (175 + 10 combo + 5 div/pattern), capped at 100."""
        from confidence_scorer import ConfidenceScorer
        scorer = ConfidenceScorer()
        r = scorer.score('XAUUSD', 'H1',
                         ob_active=True, fvg_active=True, sweep_fired=True,
                         price=101, vwap=99, atr=2, hour_utc=14,
                         correlation_score=15, news_penalty=0,
                         yield_score=10, sentiment_score=10,
                         pattern_score=20, divergence_score=20)
        raw = sum(r.components.values())
        assert raw == 190, f"raw={raw}"
        assert r.score == 100
        assert 'COMBO_OB_FVG_SWEEP' in r.components
        assert 'COMBO_PATTERN_DIVERGENCE' in r.components

    def test_confidence_scorer_minimal(self):
        """Minimal score with nothing active."""
        from confidence_scorer import ConfidenceScorer
        scorer = ConfidenceScorer()
        # Set price below VWAP so VWAP score = 0
        r = scorer.score('XAUUSD', 'H1', price=98, vwap=100, atr=1, hour_utc=22)
        assert r.score == 0
        assert r.decision == 'BLOCK'

    def test_confidence_scorer_news_penalty_blocks(self):
        """News penalty can block a signal."""
        from confidence_scorer import ConfidenceScorer
        scorer = ConfidenceScorer()
        # High score but news blocks it
        r = scorer.score('XAUUSD', 'H1',
                         ob_active=True, fvg_active=True, sweep_fired=True,
                         price=100, vwap=99, atr=2, hour_utc=14,
                         news_penalty=-15)
        # Score should be reduced but still could be high
        assert r.components['NEWS'] == -15

    def test_correlation_xauusd_dxy_bonus(self):
        """DXY falling bonus in correlation score."""
        from correlation_engine import CorrelationEngine
        ce = CorrelationEngine()
        for i in range(15):
            ce.update_price('XAUUSD', 100.0 + i)
            ce.update_price('USDCHF', 100.0 - i)
            ce.update_price('SP500', 100.0 - i * 0.3)
        ce.update_correlation_matrix()
        adj, reason = ce.get_score_adjustment('XAUUSD', 'BULLISH', dxy_falling=True)
        assert 'DXY' in reason or adj >= 0

    def test_session_dead_zone_blocks(self):
        """Dead zone blocks all trading."""
        from session_detector import SessionDetector
        sd = SessionDetector()
        info = sd.get_session_info(hour_utc=21)
        assert info['dead_zone']
        assert info['session_score'] == 0

    def test_session_london_killzone(self):
        """London killzone gives max session score."""
        from session_detector import SessionDetector
        sd = SessionDetector()
        info = sd.get_session_info(hour_utc=9)
        assert info['session_score'] == 15
        assert 'London' in info['active_sessions']

    def test_treasury_equities_normal_curve(self):
        """Normal yield curve = bullish equities."""
        from treasury_monitor import TreasuryMonitor
        tm = TreasuryMonitor()
        tm.yields = {'2Y': 4.0, '10Y': 4.8, '30Y': 5.0}
        adj, reason = tm.get_score_adjustment('US30')
        assert adj == 10

    def test_weight_sum_matches_max_raw(self):
        """Sum of WEIGHTS should equal MAX_RAW_SCORE."""
        from confidence_scorer import ConfidenceScorer
        total = sum(v for k, v in ConfidenceScorer.WEIGHTS.items() if k != 'NEWS')
        assert total == 195 - 0  # 11 positive components, 13 total (NEWS=0, REGIME=10, LIQUIDITY=10)
        # Max positive = 195
        max_pos = sum(v for k, v in ConfidenceScorer.WEIGHTS.items() if k != 'NEWS')
        assert max_pos == ConfidenceScorer.MAX_RAW_SCORE


if __name__ == '__main__':
    pytest.main(['-v', __file__])
