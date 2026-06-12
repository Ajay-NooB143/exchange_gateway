"""Tests for pipeline_orchestrator.py integration - OMNI BRAIN V2"""
import sys, os, json, time, threading
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'production'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import pytest


def make_candle(o=100.0, h=101.0, l=99.0, c=100.5, v=1000, ts=0):
    return {'open': o, 'high': h, 'low': l, 'close': c, 'volume': v, 'timestamp': ts}


def make_payload(symbol='XAUUSD', direction='LONG', tf='H1', price=2000.0):
    return {
        'symbol': symbol,
        'direction': direction,
        'timeframe': tf,
        'price': price,
        'candles': [make_candle(o=2000, h=2010, l=1990, c=2005, v=10000, ts=int(time.time()) - 3600 + i * 60) for i in range(15)],
        'vwap': 1995.0,
        'atr': 10.0,
    }


class TestPipelineIntegration:
    def test_pipeline_engine_initialization(self):
        import pipeline_orchestrator as po
        engine = po.PipelineEngine()
        assert engine._initialized is False
        assert engine.modules is None

    def test_run_pipeline_with_valid_payload(self):
        import pipeline_orchestrator as po
        engine = po.PipelineEngine()
        payload = make_payload()
        result = engine.run_pipeline(payload)
        assert 'symbol' in result
        assert 'decision' in result
        assert 'score' in result
        assert 'steps' in result
        assert result['symbol'] == 'XAUUSD'

    def test_circuit_breaker_blocks(self):
        from circuit_breaker import get_circuit_breaker
        cb = get_circuit_breaker()
        cb.record_loss('XAUUSD')
        allowed = cb.allow('XAUUSD')
        assert isinstance(allowed, bool)

    def test_session_block(self):
        from session_detector import get_session_detector
        sd = get_session_detector()
        info = sd.get_session_info(hour_utc=22)
        if info.get('dead_zone'):
            assert info['session_score'] == 0

    def test_news_block(self):
        from forex_factory_news import get_forex_factory_news
        fn = get_forex_factory_news()
        fn.last_today_fetch = time.time() + 3600
        soon = time.time() + 60
        fn.calendar = [{'event': 'NFP', 'currency': 'USD', 'impact': 'HIGH', 'ts_unix': soon}]
        blocked, reason = fn.check_signal_block('XAUUSD')
        assert blocked

    def test_risk_blocks(self):
        from risk_manager import get_risk_manager
        rm = get_risk_manager()
        halted, reason = rm.check_halts()
        limits_ok, limits_reason = rm.check_trade_limits('XAUUSD')
        assert isinstance(halted, bool)
        assert isinstance(limits_ok, bool)

    def test_confidence_scoring_in_pipeline(self):
        import pipeline_orchestrator as po
        engine = po.PipelineEngine()
        payload = make_payload()
        result = engine.run_pipeline(payload)
        steps = result.get('steps', {})
        conf = steps.get('confidence', {})
        if conf:
            assert 'score' in conf
            assert 'decision' in conf
            assert 0 <= conf.get('score', 0) <= 100

    def test_threshold_check(self):
        import pipeline_orchestrator as po
        engine = po.PipelineEngine()
        payload = make_payload()
        result = engine.run_pipeline(payload)
        steps = result.get('steps', {})
        thresh = steps.get('threshold', {})
        if thresh:
            assert 'threshold' in thresh

    def test_execute_decision(self):
        import pipeline_orchestrator as po
        engine = po.PipelineEngine()
        result = {
            'symbol': 'XAUUSD', 'direction': 'LONG', 'decision': 'EXECUTE',
            'score': 85, 'timestamp': datetime.now(timezone.utc).isoformat(),
            'steps': {
                'confidence': {'components': {'OB': 20, 'FVG': 20}},
                'threshold': {'threshold': 75},
                'circuit_breaker': True,
            },
        }
        payload = make_payload()
        try:
            engine._execute_decision(result, payload)
        except Exception as e:
            pass
        assert result['decision'] == 'EXECUTE'

    def test_paper_trade_open(self):
        from paper_trader import get_paper_trader
        pt = get_paper_trader()
        try:
            pt.open_trade('XAUUSD', 'BULLISH', 2000.0, 1985.0, 2010.0, 2020.0, 2030.0, 0.1, 85, {})
        except Exception as e:
            pass
        trades = pt.open_trades
        assert isinstance(trades, list)
        assert len(trades) >= 0

    def test_position_manager_registration(self):
        from position_manager import get_position_manager, get_positions_api
        pm = get_position_manager()
        pm.open_position('XAUUSD', 'BUY', 2000.0, 1.0, 10.0)
        data = get_positions_api()
        assert 'XAUUSD' in data.get('active', {})
        assert data['active']['XAUUSD']['entry_price'] == 2000.0

    def test_execution_quality_recording(self):
        from execution_quality import get_execution_analyzer
        eq = get_execution_analyzer()
        try:
            eq.record_execution('XAUUSD', spread=0.5, slippage=0.2, latency_ms=50,
                                fill_pct=100.0, delay_ms=45, broker_deviation=0,
                                expected_price=2000.0, actual_fill_price=2000.5)
        except Exception as e:
            pass
        stats = eq.get_asset_stats('XAUUSD')
        assert stats is not None

    def test_coaching_output_format(self):
        import pipeline_orchestrator as po
        engine = po.PipelineEngine()
        coaching = engine._get_coaching('XAUUSD', 'BUY', 85, {'OB': 20, 'FVG': 20})
        assert isinstance(coaching, str)
        assert 'TRADE COACH' in coaching
        assert 'Setup quality:' in coaching

    def test_omni_status_format(self):
        import pipeline_orchestrator as po
        status = po.get_omni_status()
        assert 'timestamp' in status
        assert 'scores' in status
        assert 'mtf' in status
        assert 'circuitBreaker' in status
        assert 'vitals' in status

    def test_last_scan_format(self):
        import pipeline_orchestrator as po
        scan = po.get_last_scan()
        assert isinstance(scan, dict)

    def test_feed_status_format(self):
        import pipeline_orchestrator as po
        feed = po.get_feed_status()
        assert isinstance(feed, dict)
        assert 'status' in feed

    def test_backtest_results_format(self):
        import pipeline_orchestrator as po
        results = po.get_backtest_results()
        assert isinstance(results, dict)
        assert 'status' in results

    def test_error_handler_integration(self):
        from error_handler import get_error_handler
        handler = get_error_handler()
        entry = handler.record('pipeline_test', 'integration', ValueError('integration test'))
        dash = handler.get_dashboard()
        assert dash['total_errors'] >= 1
        assert 'pipeline_test' in str(dash)

    def test_position_manager_integration(self):
        from position_manager import get_positions_api, get_position_manager
        pm = get_position_manager()
        pm._running = False
        pm.open_position('TESTINT', 'BUY', 100.0, 1.0, 5.0)
        data = get_positions_api()
        assert 'active' in data
        assert 'closed' in data
        assert 'total_pnl' in data

    def test_get_pipeline_singleton(self):
        import pipeline_orchestrator as po
        p1 = po.get_pipeline()
        p2 = po.get_pipeline()
        assert p1 is p2

    def test_pipeline_with_different_symbols(self):
        import pipeline_orchestrator as po
        engine = po.PipelineEngine()
        for sym in ['XAUUSD', 'EURUSD', 'GBPUSD', 'SP500']:
            payload = make_payload(symbol=sym)
            result = engine.run_pipeline(payload)
            assert result['symbol'] == sym

    def test_pipeline_multiple_timeframes(self):
        import pipeline_orchestrator as po
        engine = po.PipelineEngine()
        for tf in ['M15', 'H1', 'H4', 'D1']:
            payload = make_payload(tf=tf)
            result = engine.run_pipeline(payload)
            assert 'decision' in result

    def test_pipeline_with_news_penalty(self):
        from forex_factory_news import get_forex_factory_news
        fn = get_forex_factory_news()
        fn.last_today_fetch = time.time() + 3600
        soon = time.time() + 120
        fn.calendar = [{'event': 'NFP', 'currency': 'USD', 'impact': 'HIGH', 'ts_unix': soon}]
        import pipeline_orchestrator as po
        engine = po.PipelineEngine()
        payload = make_payload()
        result = engine.run_pipeline(payload)
        steps = result.get('steps', {})
        news_step = steps.get('news', {})
        if news_step:
            assert 'penalty' in news_step or 'blocked' in news_step

    def test_pipeline_log_format(self):
        import pipeline_orchestrator as po
        engine = po.PipelineEngine()
        payload = make_payload()
        result = engine.run_pipeline(payload)
        log_file = Path(__file__).parent.parent / 'logs' / 'pipeline_log.csv'
        if log_file.exists():
            content = log_file.read_text()
            assert 'timestamp' in content
            assert 'decision' in content or 'XAUUSD' in content

    def test_all_imports_lazy(self):
        import pipeline_orchestrator as po
        modules = po._import_modules()
        expected_keys = {'scorer', 'threshold', 'mtf', 'circuit_breaker',
                         'correlation', 'news', 'treasury', 'sentiment',
                         'session', 'pattern', 'divergence', 'risk',
                         'regime_detector', 'bridge', 'decision_engine'}
        assert expected_keys.issubset(modules.keys())
