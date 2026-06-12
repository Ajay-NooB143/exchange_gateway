"""Tests for position_manager.py - OMNI BRAIN V2"""
import sys, os, json, time, threading
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'production'))
import pytest

from position_manager import (
    PositionManager, ManagedPosition, get_position_manager, get_positions_api,
    EXIT_REASON_TP1, EXIT_REASON_TP2, EXIT_REASON_TP3, EXIT_REASON_SL,
    EXIT_REASON_TIME, EXIT_REASON_MANUAL,
)


class TestPositionManager:
    @pytest.fixture(autouse=True)
    def clear_state(self):
        pos_file = Path(__file__).parent.parent / 'production' / 'logs' / 'positions.json'
        if pos_file.exists():
            pos_file.write_text(json.dumps({'active': [], 'closed': [], 'updated': ''}))
        global_mgr = get_position_manager()
        global_mgr._positions.clear()
        global_mgr._closed.clear()

    def make_pos_mgr(self):
        mgr = PositionManager()
        mgr._positions.clear()
        mgr._closed.clear()
        mgr._running = False
        return mgr

    def test_open_position(self):
        pm = self.make_pos_mgr()
        pos = pm.open_position('XAUUSD', 'BUY', 2000.0, 1.0, 10.0)
        assert pos.symbol == 'XAUUSD'
        assert pos.direction == 'BUY'
        assert pos.entry_price == 2000.0
        assert pos.status == 'ACTIVE'
        assert pm.get_position('XAUUSD') is pos

    def test_close_position(self):
        pm = self.make_pos_mgr()
        pm.open_position('EURUSD', 'SELL', 1.1000, 1.0, 0.005)
        r = pm.close_position('EURUSD', 1.0950, EXIT_REASON_MANUAL)
        assert r['status'] == 'CLOSED'
        assert pm.get_position('EURUSD') is None
        assert len(pm.get_closed_positions()) == 1

    def test_tp1_hit(self):
        pm = self.make_pos_mgr()
        pos = pm.open_position('XAUUSD', 'BUY', 2000.0, 1.0, 10.0,
                               tp1=2010.0, tp2=2020.0, tp3=2030.0)
        r = pm._handle_tp1(pos, 2010.0)
        assert r['event'] == 'TP1'
        assert pos.tp1_hit is True
        assert pos.closed_pct == 0.33
        assert pos.break_even_triggered is True
        assert pos.current_sl == pos.entry_price
        assert r['profit'] > 0

    def test_tp2_hit(self):
        pm = self.make_pos_mgr()
        pos = pm.open_position('XAUUSD', 'BUY', 2000.0, 1.0, 10.0,
                               tp1=2010.0, tp2=2020.0, tp3=2030.0)
        pos.tp1_hit = True
        pos.closed_pct = 0.33
        pos.current_sl = 2000.0
        r = pm._handle_tp2(pos, 2020.0)
        assert r['event'] == 'TP2'
        assert pos.tp2_hit is True
        assert pos.closed_pct == 0.66
        assert r['profit'] > 0

    def test_tp3_hit(self):
        pm = self.make_pos_mgr()
        pos = pm.open_position('XAUUSD', 'BUY', 2000.0, 1.0, 10.0,
                               tp1=2010.0, tp2=2020.0, tp3=2030.0)
        pos.tp1_hit = True
        pos.tp2_hit = True
        pos.closed_pct = 0.66
        r = pm._handle_tp3(pos, 2030.0)
        assert r['status'] == 'CLOSED'
        assert r.get('exit_reason') == EXIT_REASON_TP3

    def test_sl_hit(self):
        pm = self.make_pos_mgr()
        pm.open_position('XAUUSD', 'BUY', 2000.0, 1.0, 10.0,
                         sl=1985.0)
        r = pm.close_position('XAUUSD', 1985.0, EXIT_REASON_SL)
        assert r['status'] == 'CLOSED'
        assert r['exit_reason'] == EXIT_REASON_SL

    def test_time_stop(self):
        pm = self.make_pos_mgr()
        pos = pm.open_position('XAUUSD', 'BUY', 2000.0, 1.0, 10.0)
        pos.entry_time = time.time() - 86401
        r = pm.close_position('XAUUSD', 1990.0, EXIT_REASON_TIME)
        assert r['status'] == 'CLOSED'
        assert r['exit_reason'] == EXIT_REASON_TIME

    def test_persistence(self):
        pm1 = self.make_pos_mgr()
        pm1.open_position('XAUUSD', 'BUY', 2000.0, 1.0, 10.0)
        pm1.open_position('EURUSD', 'SELL', 1.1000, 1.0, 0.005)
        pm2 = self.make_pos_mgr()
        positions_file = Path(__file__).parent.parent / 'production' / 'logs' / 'positions.json'
        saved = json.loads(positions_file.read_text())
        assert len(saved['active']) >= 2
        symbols = {p['symbol'] for p in saved['active']}
        assert 'XAUUSD' in symbols
        assert 'EURUSD' in symbols

    def test_get_all_positions(self):
        pm = self.make_pos_mgr()
        assert len(pm.get_all_positions()) == 0
        pm.open_position('XAUUSD', 'BUY', 2000.0, 1.0, 10.0)
        assert len(pm.get_all_positions()) == 1
        assert 'XAUUSD' in pm.get_all_positions()

    def test_get_closed_positions(self):
        pm = self.make_pos_mgr()
        pm.open_position('XAUUSD', 'BUY', 2000.0, 1.0, 10.0)
        pm.close_position('XAUUSD', 2010.0, EXIT_REASON_MANUAL)
        closed = pm.get_closed_positions()
        assert len(closed) == 1
        assert closed[0].status == 'CLOSED'

    def test_get_position(self):
        pm = self.make_pos_mgr()
        assert pm.get_position('XAUUSD') is None
        pm.open_position('XAUUSD', 'BUY', 2000.0, 1.0, 10.0)
        p = pm.get_position('XAUUSD')
        assert p is not None
        assert p.symbol == 'XAUUSD'

    def test_get_daily_summary(self):
        pm = self.make_pos_mgr()
        summary = pm.get_daily_summary()
        assert 'OPEN POSITIONS' in summary
        pm.open_position('XAUUSD', 'BUY', 2000.0, 1.0, 10.0)
        summary2 = pm.get_daily_summary()
        assert 'XAUUSD' in summary2

    def test_get_positions_api(self):
        pm = self.make_pos_mgr()
        data = get_positions_api()
        assert 'active' in data
        assert 'closed' in data
        assert 'total_pnl' in data
        assert 'daily_summary' in data
        assert 'timestamp' in data

    def test_singleton(self):
        pm1 = get_position_manager()
        pm2 = get_position_manager()
        assert pm1 is pm2

    def test_to_dict(self):
        pm = self.make_pos_mgr()
        pos = pm.open_position('XAUUSD', 'BUY', 2000.0, 1.0, 10.0)
        d = pos.to_dict()
        assert d['symbol'] == 'XAUUSD'
        assert d['direction'] == 'BUY'
        assert d['entry_price'] == 2000.0
        assert 'adjustments' not in d

    def test_parallel_operations(self):
        pm = self.make_pos_mgr()
        errors = []
        lock = threading.Lock()

        def worker(sym):
            try:
                pm.open_position(sym, 'BUY', 2000.0, 1.0, 10.0)
            except Exception as e:
                with lock:
                    errors.append(str(e))

        threads = [threading.Thread(target=worker, args=(f'PAIR{i}',)) for i in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(errors) == 0
        assert len(pm.get_all_positions()) == 10

    def test_partial_close_percentages(self):
        pm = self.make_pos_mgr()
        pos = pm.open_position('XAUUSD', 'BUY', 2000.0, 1.0, 10.0,
                               tp1=2010.0, tp2=2020.0, tp3=2030.0)
        pm._handle_tp1(pos, 2010.0)
        assert pos.closed_pct == 0.33
        pm._handle_tp2(pos, 2020.0)
        assert pos.closed_pct == 0.66
        pm._handle_tp3(pos, 2030.0)
        assert pos.closed_pct == 1.0

    def test_trailing_stop_logic(self):
        pm = self.make_pos_mgr()
        pos = pm.open_position('XAUUSD', 'BUY', 2000.0, 1.0, 10.0,
                               tp1=2010.0, tp2=2020.0, tp3=2030.0)
        pos.tp1_hit = True
        old_sl = pos.current_sl
        pm._handle_tp2(pos, 2020.0)
        assert pos.current_sl > old_sl

    def test_break_even_logic(self):
        pm = self.make_pos_mgr()
        pos = pm.open_position('XAUUSD', 'BUY', 2000.0, 1.0, 10.0,
                               tp1=2010.0, tp2=2020.0, tp3=2030.0,
                               sl=1985.0)
        pm._handle_tp1(pos, 2010.0)
        assert pos.current_sl == pos.entry_price
        assert pos.break_even_triggered is True

    def test_pnl_calculation(self):
        pm = self.make_pos_mgr()
        pos = pm.open_position('XAUUSD', 'BUY', 2000.0, 1.0, 10.0)
        pm._handle_tp1(pos, 2010.0)
        pm._handle_tp2(pos, 2020.0)
        pm._handle_tp3(pos, 2030.0)
        assert pos.pnl > 0
        total = pos.pnl
        assert total > 0
