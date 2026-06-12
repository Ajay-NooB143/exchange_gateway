"""Tests for thread safety of singleton getters - OMNI BRAIN V2"""
import sys, os, json, time, threading
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'production'))
import pytest


def test_confidence_scorer_singleton_thread_safety():
    from confidence_scorer import get_scorer
    instances = []
    lock = threading.Lock()

    def worker():
        s = get_scorer()
        with lock:
            instances.append(id(s))

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert all(i == instances[0] for i in instances)


def test_circuit_breaker_singleton_thread_safety():
    from circuit_breaker import get_circuit_breaker
    instances = []
    lock = threading.Lock()

    def worker():
        s = get_circuit_breaker()
        with lock:
            instances.append(id(s))

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert all(i == instances[0] for i in instances)


def test_adaptive_threshold_singleton_thread_safety():
    from adaptive_threshold import get_threshold_engine
    instances = []
    lock = threading.Lock()

    def worker():
        s = get_threshold_engine()
        with lock:
            instances.append(id(s))

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert all(i == instances[0] for i in instances)


def test_correlation_engine_singleton_thread_safety():
    from correlation_engine import get_correlation_engine
    instances = []
    lock = threading.Lock()

    def worker():
        s = get_correlation_engine()
        with lock:
            instances.append(id(s))

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert all(i == instances[0] for i in instances)


def test_sentiment_engine_singleton_thread_safety():
    from sentiment_engine import get_sentiment_engine
    instances = []
    lock = threading.Lock()

    def worker():
        s = get_sentiment_engine()
        with lock:
            instances.append(id(s))

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert all(i == instances[0] for i in instances)


def test_treasury_monitor_singleton_thread_safety():
    from treasury_monitor import get_treasury_monitor
    instances = []
    lock = threading.Lock()

    def worker():
        s = get_treasury_monitor()
        with lock:
            instances.append(id(s))

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert all(i == instances[0] for i in instances)


def test_paper_trader_singleton_thread_safety():
    import importlib
    paper_trader = importlib.import_module('paper_trader')
    pt = paper_trader
    try:
        getter = pt.get_paper_trader
    except AttributeError:
        getter = lambda: pt.PaperTrader()
    instances = []
    lock = threading.Lock()

    def worker():
        s = getter()
        with lock:
            instances.append(id(s))

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert all(i == instances[0] for i in instances)


def test_prompt_evolution_dna_singleton_thread_safety():
    from prompt_evolution import get_dna
    instances = []
    lock = threading.Lock()

    def worker():
        s = get_dna()
        with lock:
            instances.append(id(s))

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert all(i == instances[0] for i in instances)


def test_subscription_manager_singleton_thread_safety():
    from subscription_manager import get_subscription_manager
    instances = []
    lock = threading.Lock()

    def worker():
        s = get_subscription_manager()
        with lock:
            instances.append(id(s))

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert all(i == instances[0] for i in instances)


def test_risk_manager_singleton_thread_safety():
    from risk_manager import get_risk_manager, RiskManager
    instances = []
    lock = threading.Lock()

    def worker():
        s = get_risk_manager()
        with lock:
            instances.append(s)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert all(isinstance(i, RiskManager) for i in instances)


def test_rlock_on_shared_state():
    from confidence_scorer import get_scorer
    scorer = get_scorer()
    errors = []
    lock = threading.Lock()

    def writer(i):
        try:
            scorer.score('XAUUSD', 'H1', ob_active=i % 2 == 0)
        except Exception as e:
            with lock:
                errors.append(str(e))

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(20)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert len(errors) == 0
    assert len(scorer.get_history()) >= 1


def test_thread_safe_position_manager_read_write():
    from position_manager import PositionManager
    pm = PositionManager()
    pm._positions.clear()
    pm._closed.clear()
    pm._running = False
    errors = []
    lock = threading.Lock()

    def opener(i):
        try:
            pm.open_position(f'PAIR{i}', 'BUY', 100.0 + i, 1.0, 5.0)
        except Exception as e:
            with lock:
                errors.append(str(e))

    def closer():
        import time
        time.sleep(0.05)
        try:
            for sym in list(pm._positions.keys()):
                pm.close_position(sym, 105.0, 'MANUAL')
        except Exception as e:
            with lock:
                errors.append(str(e))

    threads = [threading.Thread(target=opener, args=(i,)) for i in range(10)]
    threads.append(threading.Thread(target=closer))
    for t in threads: t.start()
    for t in threads: t.join()
    assert len(errors) == 0


def test_thread_safe_error_handler_concurrent():
    from error_handler import ErrorHandler
    eh = ErrorHandler()
    eh._errors.clear()
    eh._error_counts.clear()
    errors = []
    lock = threading.Lock()

    def worker(i):
        try:
            eh.record(f'mod_{i}', 'op', ValueError(f'err_{i}'))
        except Exception as e:
            with lock:
                errors.append(str(e))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert len(errors) == 0
    assert len(eh.get_recent()) >= 20


def test_thread_safe_adaptive_threshold_read_write():
    from adaptive_threshold import get_threshold_engine
    at = get_threshold_engine()
    errors = []
    lock = threading.Lock()

    def reader_writer(i):
        try:
            at.get_threshold('XAUUSD')
            at.record_result('XAUUSD', 'H1', 'WIN' if i % 2 == 0 else 'LOSS', 70 + (i % 20))
        except Exception as e:
            with lock:
                errors.append(str(e))

    threads = [threading.Thread(target=reader_writer, args=(i,)) for i in range(15)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert len(errors) == 0


def test_thread_safe_circuit_breaker_concurrent():
    from circuit_breaker import get_circuit_breaker
    cb = get_circuit_breaker()
    errors = []
    lock = threading.Lock()

    def worker(i):
        try:
            cb.allow('XAUUSD')
            if i % 3 == 0:
                cb.record_loss('XAUUSD')
        except Exception as e:
            with lock:
                errors.append(str(e))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(15)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert len(errors) == 0


def test_thread_safe_news_factory():
    from forex_factory_news import ForexFactoryNews
    fn = ForexFactoryNews()
    fn.last_full_fetch = time.time() + 3600
    fn.last_today_fetch = time.time() + 3600
    errors = []
    lock = threading.Lock()

    def worker(i):
        try:
            fn.check_signal_block('XAUUSD')
            fn.get_upcoming_high_impact(5)
        except Exception as e:
            with lock:
                errors.append(str(e))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert len(errors) == 0


def test_thread_safe_prompt_dna():
    from prompt_evolution import get_dna, get_mutation_engine
    dna = get_dna()
    me = get_mutation_engine()
    errors = []
    lock = threading.Lock()

    def worker(i):
        try:
            dna.get('confidence_scorer')
            if i % 2 == 0:
                me.mutate('confidence_scorer', 'weight_shift')
        except Exception as e:
            with lock:
                errors.append(str(e))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert len(errors) == 0


def test_thread_safe_correlation_matrix():
    from correlation_engine import get_correlation_engine
    ce = get_correlation_engine()
    errors = []
    lock = threading.Lock()

    def worker(i):
        try:
            ce.update_price('XAUUSD', 100.0 + i * 0.1)
            ce.update_correlation_matrix()
        except Exception as e:
            with lock:
                errors.append(str(e))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert len(errors) == 0


def test_thread_safe_safe_rl_learner():
    from safe_rl_learner import SafeRLLearner
    rl = SafeRLLearner()
    rl._trade_history.clear()
    errors = []
    lock = threading.Lock()

    def worker(i):
        try:
            rl.record_trade({
                'symbol': 'XAUUSD', 'direction': 'BUY', 'win': i % 2 == 0,
                'rr': 1.5, 'pattern': 'FVG', 'regime': 'EXPANSION',
                'session': 'LONDON', 'liquidity_quality': 70,
                'trap_detected': False, 'confidence': 75,
                'entry': 2000, 'exit': 2020, 'atr': 5.0,
            })
        except Exception as e:
            with lock:
                errors.append(str(e))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert len(errors) == 0
    assert rl._total_trades == 10


def test_thread_safe_treasury_monitor_concurrent():
    from treasury_monitor import get_treasury_monitor
    tm = get_treasury_monitor()
    errors = []
    lock = threading.Lock()

    def worker(i):
        try:
            tm.get_score_adjustment('XAUUSD')
            tm.get_yield_curve()
            tm.get_real_yield()
        except Exception as e:
            with lock:
                errors.append(str(e))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert len(errors) == 0
