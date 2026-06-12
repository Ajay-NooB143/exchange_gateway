"""
Paper Trader - OMNI BRAIN V2
=============================
Virtual trading account for proof-of-concept paper trading.
Tracks every EXECUTE signal as a virtual trade with TP/SL monitoring.

Features:
  - Virtual account with starting balance from PAPER_BALANCE env
  - Auto-open trade on each EXECUTE signal
  - 15-min price check for TP/SL hits
  - Partial TP close (33% @ TP1, 33% @ TP2, 34% @ TP3)
  - Full SL hit close
  - P&L calculation and balance update
  - Daily P&L summary via Telegram
  - Weekly performance card
  - All trades stored in logs/paper_trades.json
"""

import os
import sys
import json
import time
import uuid
import logging
import threading
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path

log = logging.getLogger('PaperTrader')

LOG_DIR = Path(__file__).parent / 'logs'
LOG_DIR.mkdir(exist_ok=True)

TRADES_FILE = LOG_DIR / 'paper_trades.json'
WEEKLY_DIR = Path(__file__).parent.parent / 'content' / 'weekly'
MONTHLY_DIR = Path(__file__).parent.parent / 'content' / 'monthly'
WEEKLY_DIR.mkdir(parents=True, exist_ok=True)
MONTHLY_DIR.mkdir(parents=True, exist_ok=True)

PIP_VALUE_MAP = {
    'XAUUSD': 10.0, 'SP500': 10.0, 'US30': 10.0, 'NAS100': 10.0, 'USOIL': 10.0,
    'EURUSD': 1.0, 'GBPUSD': 1.0, 'USDJPY': 1.0, 'USDCHF': 1.0,
    'AUDUSD': 1.0, 'NZDUSD': 1.0, 'USDCAD': 1.0, 'EURJPY': 1.0,
}


class PaperTrader:
    """Virtual paper trading account."""

    def __init__(self):
        self.balance = float(os.environ.get('PAPER_BALANCE', '10000'))
        self.starting_balance = self.balance
        self.peak_balance = self.balance
        self.trades: List[Dict[str, Any]] = []
        self.open_trades: List[Dict[str, Any]] = []
        self.closed_trades: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._monitor_thread: Optional[threading.Thread] = None
        self._running = False
        self._load_state()

    def _load_state(self):
        if TRADES_FILE.exists():
            try:
                with open(TRADES_FILE) as f:
                    data = json.load(f)
                self.balance = data.get('balance', self.balance)
                self.starting_balance = data.get('starting_balance', self.starting_balance)
                self.peak_balance = data.get('peak_balance', self.peak_balance)
                self.trades = data.get('trades', [])
                self.open_trades = [t for t in self.trades if t.get('status') == 'OPEN']
                self.closed_trades = [t for t in self.trades if t.get('status') != 'OPEN']
            except Exception:
                pass

    def _save_state(self):
        try:
            with open(TRADES_FILE, 'w') as f:
                json.dump({
                    'balance': self.balance,
                    'starting_balance': self.starting_balance,
                    'peak_balance': self.peak_balance,
                    'trades': self.trades,
                    'updated': datetime.now(timezone.utc).isoformat()
                }, f, indent=2, default=str)
        except Exception as e:
            log.error(f"Failed to save paper trades: {e}")

    def _get_pip_value(self, symbol: str) -> float:
        return PIP_VALUE_MAP.get(symbol, 1.0)

    def open_trade(self, symbol: str, direction: str, entry: float, sl: float,
                   tp1: float, tp2: float, tp3: float, lots: float,
                   score: int, components: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
        """Open a virtual paper trade on EXECUTE signal."""
        with self._lock:
            trade = {
                'id': str(uuid.uuid4())[:8],
                'symbol': symbol,
                'direction': direction,
                'entry': entry,
                'sl': sl,
                'tp1': tp1,
                'tp2': tp2,
                'tp3': tp3,
                'lots': lots,
                'score': score,
                'components': components or {},
                'opened_at': datetime.now(timezone.utc).isoformat(),
                'status': 'OPEN',
                'pnl': 0.0,
                'remaining_lots': lots,
                'partials_closed': [],
                'close_price': None,
                'closed_at': None,
            }
            self.trades.append(trade)
            self.open_trades.append(trade)
            self._save_state()
            log.info(f"PAPER TRADE OPENED: {symbol} {direction} @ {entry} x{lots}")
            return trade

    def close_trade(self, trade_id: str, close_price: float, reason: str = 'SL_HIT') -> Optional[Dict[str, Any]]:
        """Close a trade fully (all remaining lots)."""
        with self._lock:
            trade = next((t for t in self.open_trades if t['id'] == trade_id), None)
            if not trade:
                return None

            remaining = trade['remaining_lots']
            if remaining <= 0:
                return trade

            pip_value = self._get_pip_value(trade['symbol'])
            direction_mult = 1 if trade['direction'] in ('BULLISH', 'LONG', 'BUY') else -1
            pnl = (close_price - trade['entry']) * direction_mult * remaining * pip_value

            trade['pnl'] += pnl
            trade['remaining_lots'] = 0
            trade['close_price'] = close_price
            trade['closed_at'] = datetime.now(timezone.utc).isoformat()
            trade['status'] = 'CLOSED'
            trade['close_reason'] = reason

            self.balance += pnl
            if self.balance > self.peak_balance:
                self.peak_balance = self.balance

            self.open_trades = [t for t in self.open_trades if t['id'] != trade_id]
            self.closed_trades.append(trade)
            self._save_state()

            emoji = '\u2705' if pnl > 0 else '\u274c'
            log.info(f"PAPER TRADE CLOSED: {trade['symbol']} {reason} PnL=${pnl:.2f} {emoji}")
            return trade

    def check_prices(self, price_fetcher: Optional[callable] = None) -> List[Dict[str, Any]]:
        """Check all open trades against SL/TP levels. Call every 15 min."""
        results = []
        with self._lock:
            for trade in list(self.open_trades):
                price = None
                if price_fetcher:
                    try:
                        price = price_fetcher(trade['symbol'])
                    except Exception:
                        pass

                if price is None:
                    continue

                direction_mult = 1 if trade['direction'] in ('BULLISH', 'LONG', 'BUY') else -1
                pip_value = self._get_pip_value(trade['symbol'])
                remaining = trade['remaining_lots']

                if remaining <= 0:
                    continue

                sl_hit = (price <= trade['sl']) if direction_mult > 0 else (price >= trade['sl'])
                tp1_hit = (price >= trade['tp1']) if direction_mult > 0 else (price <= trade['tp1'])
                tp2_hit = (price >= trade['tp2']) if direction_mult > 0 else (price <= trade['tp2'])
                tp3_hit = (price >= trade['tp3']) if direction_mult > 0 else (price <= trade['tp3'])

                if sl_hit:
                    pnl = (trade['sl'] - trade['entry']) * direction_mult * remaining * pip_value
                    trade['pnl'] += pnl
                    trade['remaining_lots'] = 0
                    trade['close_price'] = trade['sl']
                    trade['closed_at'] = datetime.now(timezone.utc).isoformat()
                    trade['status'] = 'CLOSED'
                    trade['close_reason'] = 'SL_HIT'
                    self.balance += pnl
                    self.open_trades = [t for t in self.open_trades if t['id'] != trade['id']]
                    self.closed_trades.append(trade)
                    results.append({'id': trade['id'], 'symbol': trade['symbol'], 'action': 'SL_HIT', 'pnl': pnl})
                    log.info(f"PAPER SL HIT: {trade['symbol']} PnL=${pnl:.2f}")

                elif tp3_hit and 'TP3' not in [p.get('level') for p in trade.get('partials_closed', [])]:
                    close_lots = remaining  # close remaining
                    pnl = (trade['tp3'] - trade['entry']) * direction_mult * close_lots * pip_value
                    trade['pnl'] += pnl
                    trade['remaining_lots'] = 0
                    trade['close_price'] = trade['tp3']
                    trade['closed_at'] = datetime.now(timezone.utc).isoformat()
                    trade['status'] = 'CLOSED'
                    trade['close_reason'] = 'TP3_HIT'
                    trade['partials_closed'].append({'level': 'TP3', 'lots': close_lots, 'pnl': pnl, 'price': trade['tp3']})
                    self.balance += pnl
                    self.open_trades = [t for t in self.open_trades if t['id'] != trade['id']]
                    self.closed_trades.append(trade)
                    results.append({'id': trade['id'], 'symbol': trade['symbol'], 'action': 'TP3_HIT', 'pnl': pnl})
                    log.info(f"PAPER TP3 HIT: {trade['symbol']} PnL=${pnl:.2f}")

                elif tp2_hit and 'TP2' not in [p.get('level') for p in trade.get('partials_closed', [])]:
                    close_lots = remaining * 0.5  # close 50% of remaining (33% of original)
                    pnl = (trade['tp2'] - trade['entry']) * direction_mult * close_lots * pip_value
                    trade['pnl'] += pnl
                    trade['remaining_lots'] -= close_lots
                    trade['partials_closed'].append({'level': 'TP2', 'lots': close_lots, 'pnl': pnl, 'price': trade['tp2']})
                    self.balance += pnl
                    results.append({'id': trade['id'], 'symbol': trade['symbol'], 'action': 'TP2_HIT', 'pnl': pnl})
                    log.info(f"PAPER TP2 HIT: {trade['symbol']} PnL=${pnl:.2f}")

                elif tp1_hit and 'TP1' not in [p.get('level') for p in trade.get('partials_closed', [])]:
                    close_lots = remaining * 0.33  # close 33% of remaining
                    pnl = (trade['tp1'] - trade['entry']) * direction_mult * close_lots * pip_value
                    trade['pnl'] += pnl
                    trade['remaining_lots'] -= close_lots
                    trade['partials_closed'].append({'level': 'TP1', 'lots': close_lots, 'pnl': pnl, 'price': trade['tp1']})
                    self.balance += pnl
                    results.append({'id': trade['id'], 'symbol': trade['symbol'], 'action': 'TP1_HIT', 'pnl': pnl})
                    log.info(f"PAPER TP1 HIT: {trade['symbol']} PnL=${pnl:.2f}")

            self._save_state()
        return results

    def get_daily_pnl(self, date: Optional[str] = None) -> Dict[str, Any]:
        """Get daily P&L summary."""
        if date is None:
            date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        day_trades = [t for t in self.closed_trades
                      if t.get('closed_at', '').startswith(date)]
        day_opens = [t for t in self.trades
                     if t.get('opened_at', '').startswith(date) and t['status'] == 'OPEN']

        winners = [t for t in day_trades if t['pnl'] > 0]
        losers = [t for t in day_trades if t['pnl'] <= 0]
        total_pnl = sum(t['pnl'] for t in day_trades)

        best = max(day_trades, key=lambda t: t['pnl']) if day_trades else None
        worst = min(day_trades, key=lambda t: t['pnl']) if day_trades else None

        return {
            'date': date,
            'trades_opened': len(day_opens),
            'trades_closed': len(day_trades),
            'winners': len(winners),
            'losers': len(losers),
            'win_rate': round(len(winners) / len(day_trades) * 100, 1) if day_trades else 0,
            'gross_pnl': round(total_pnl, 2),
            'balance': round(self.balance, 2),
            'daily_roi': round(total_pnl / (self.balance - total_pnl) * 100, 2) if (self.balance - total_pnl) > 0 else 0,
            'best_trade': f"{best['symbol']} +${best['pnl']:.0f}" if best else 'N/A',
            'worst_trade': f"{worst['symbol']} ${worst['pnl']:.0f}" if worst else 'N/A',
            'open_trades': len(self.open_trades),
        }

    def get_weekly_pnl(self, week_num: Optional[int] = None) -> Dict[str, Any]:
        """Get weekly performance summary."""
        from datetime import date as dt_date
        today = dt_date.today()
        if week_num is None:
            week_num = today.isocalendar()[1]
        week_start = today - timedelta(days=today.weekday())

        week_trades = []
        for t in self.closed_trades:
            closed_date = t.get('closed_at', '')[:10]
            if closed_date:
                try:
                    cd = datetime.strptime(closed_date, '%Y-%m-%d').date()
                    if week_start <= cd <= today:
                        week_trades.append(t)
                except ValueError:
                    continue

        winners = [t for t in week_trades if t['pnl'] > 0]
        losers = [t for t in week_trades if t['pnl'] <= 0]
        total_pnl = sum(t['pnl'] for t in week_trades)
        best = max(week_trades, key=lambda t: t['pnl']) if week_trades else None

        start_date_str = week_start.strftime('%Y-%m-%d')
        end_date_str = today.strftime('%Y-%m-%d')

        return {
            'week': week_num,
            'date_range': f"{start_date_str} to {end_date_str}",
            'signals_executed': len(week_trades),
            'winners': len(winners),
            'losers': len(losers),
            'win_rate': round(len(winners) / len(week_trades) * 100, 1) if week_trades else 0,
            'total_pnl': round(total_pnl, 2),
            'roi': round(total_pnl / self.starting_balance * 100, 2) if self.starting_balance > 0 else 0,
            'best_trade': f"{best['symbol']} +${best['pnl']:.0f}" if best else 'N/A',
            'balance': round(self.balance, 2),
        }

    def get_monthly_track_record(self) -> Dict[str, Any]:
        """Generate full monthly track record."""
        monthly = {}
        for t in self.closed_trades:
            month_key = t.get('closed_at', '')[:7]
            if month_key:
                monthly.setdefault(month_key, []).append(t)

        records = []
        all_pnls = []
        for month, trades in sorted(monthly.items()):
            total_pnl = sum(t['pnl'] for t in trades)
            wins = sum(1 for t in trades if t['pnl'] > 0)
            avg_pnl = total_pnl / len(trades) if trades else 0
            all_pnls.extend([t['pnl'] for t in trades])

            returns = [t['pnl'] / self.starting_balance for t in trades]
            avg_return = sum(returns) / len(returns) if returns else 0
            std_return = (sum((r - avg_return)**2 for r in returns) / len(returns))**0.5 if returns else 0
            sharpe = (avg_return / std_return * (252**0.5)) if std_return > 0 else 0

            peak = self.starting_balance
            max_dd = 0
            running = self.starting_balance
            for t in trades:
                running += t['pnl']
                if running > peak:
                    peak = running
                dd = (peak - running) / peak * 100
                max_dd = max(max_dd, dd)

            records.append({
                'month': month,
                'trades': len(trades),
                'wins': wins,
                'losses': len(trades) - wins,
                'win_rate': round(wins / len(trades) * 100, 1) if trades else 0,
                'total_pnl': round(total_pnl, 2),
                'avg_pnl': round(avg_pnl, 2),
                'sharpe': round(sharpe, 2),
                'max_drawdown_pct': round(max_dd, 2),
            })

        return {
            'records': records,
            'total_trades': len(self.closed_trades),
            'total_pnl': round(sum(t['pnl'] for t in self.closed_trades), 2),
            'current_balance': round(self.balance, 2),
            'overall_roi': round((self.balance - self.starting_balance) / self.starting_balance * 100, 2),
        }

    def format_daily_pnl_message(self, date: Optional[str] = None) -> str:
        """Format daily P&L for Telegram."""
        dpnl = self.get_daily_pnl(date)
        return (
            f"\U0001f4b0 PAPER TRADING DAILY P&L\n"
            f"Date: {dpnl['date']}\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"Trades opened : {dpnl['trades_opened']}\n"
            f"Trades closed : {dpnl['trades_closed']}\n"
            f"Winners       : {dpnl['winners']} ({dpnl['win_rate']}%)\n"
            f"Losers        : {dpnl['losers']} ({100-dpnl['win_rate']:.1f}%)\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"Gross P&L     : {'+' if dpnl['gross_pnl'] >= 0 else ''}${dpnl['gross_pnl']:.2f}\n"
            f"Balance       : ${dpnl['balance']:.2f}\n"
            f"Daily ROI     : {'+' if dpnl['daily_roi'] >= 0 else ''}{dpnl['daily_roi']:.2f}%\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"Best trade    : {dpnl['best_trade']}\n"
            f"Worst trade   : {dpnl['worst_trade']}\n"
            f"Open trades   : {dpnl['open_trades']} (pending)\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        )

    def save_weekly_report(self) -> Dict[str, Any]:
        """Save weekly performance report to JSON."""
        report = self.get_weekly_pnl()
        report_path = WEEKLY_DIR / f'week_{report["week"]}.json'
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        log.info(f"Weekly report saved: {report_path}")
        return report

    def format_weekly_message(self) -> str:
        """Format weekly performance for Telegram."""
        wpnl = self.get_weekly_pnl()
        return (
            f"\U0001f4ca WEEKLY PERFORMANCE CARD\n"
            f"Week {wpnl['week']} \u2014 {wpnl['date_range']}\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"Signals       : {wpnl['signals_executed']} executed\n"
            f"Winners       : {wpnl['winners']} ({wpnl['win_rate']}%)\n"
            f"Losers        : {wpnl['losers']} ({100-wpnl['win_rate']:.1f}%)\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"P&L           : {'+' if wpnl['total_pnl'] >= 0 else ''}${wpnl['total_pnl']:.2f}\n"
            f"ROI           : {'+' if wpnl['roi'] >= 0 else ''}{wpnl['roi']:.2f}%\n"
            f"Balance       : ${wpnl['balance']:.2f}\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"Best trade    : {wpnl['best_trade']}\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get paper trader stats for dashboard."""
        total = len(self.closed_trades)
        winners = sum(1 for t in self.closed_trades if t['pnl'] > 0)
        return {
            'balance': round(self.balance, 2),
            'starting_balance': round(self.starting_balance, 2),
            'total_pnl': round(sum(t['pnl'] for t in self.closed_trades), 2),
            'roi': round((self.balance - self.starting_balance) / self.starting_balance * 100, 2),
            'open_trades': len(self.open_trades),
            'total_closed': total,
            'winners': winners,
            'win_rate': round(winners / total * 100, 1) if total > 0 else 0,
            'best_score': max((t.get('score', 0) for t in self.closed_trades), default=0),
        }

    def start_monitoring(self, price_fetcher: Optional[callable] = None, interval: int = 900):
        """Start background thread to monitor open trades."""
        self._running = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            args=(price_fetcher, interval),
            daemon=True
        )
        self._monitor_thread.start()
        log.info(f"Paper trade monitoring started (interval={interval}s)")

    def stop_monitoring(self):
        self._running = False

    def _monitor_loop(self, price_fetcher: Optional[callable], interval: int):
        while self._running:
            try:
                self.check_prices(price_fetcher)
            except Exception as e:
                log.debug(f"Monitor check error: {e}")
            for _ in range(interval // 5):
                if not self._running:
                    return
                time.sleep(5)


_paper_trader: Optional[PaperTrader] = None
_lock = threading.Lock()


def get_paper_trader() -> PaperTrader:
    global _paper_trader
    if _paper_trader is None:
        with _lock:
            if _paper_trader is None:
                _paper_trader = PaperTrader()
    return _paper_trader


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

    if '--test' in sys.argv:
        print("=" * 60)
        print("  PAPER TRADER - TEST")
        print("=" * 60)

        pt = PaperTrader()
        print(f"  Balance: ${pt.balance:.2f}")

        trade = pt.open_trade('XAUUSD', 'BULLISH', 2350.50, 2338.10,
                              2352.30, 2359.10, 2365.90,
                              0.67, 85)
        print(f"  Trade opened: {trade['id']} {trade['symbol']} @ {trade['entry']}")

        trade2 = pt.open_trade('EURUSD', 'BEARISH', 1.0850, 1.0900,
                               1.0820, 1.0780, 1.0740,
                               0.5, 72)
        print(f"  Trade opened: {trade2['id']} {trade2['symbol']} @ {trade2['entry']}")

        result = pt.close_trade(trade['id'], 2365.90, 'TP3_HIT')
        print(f"  Trade closed: {result['symbol']} PnL=${result['pnl']:.2f}")

        result2 = pt.close_trade(trade2['id'], 1.0780, 'TP2_HIT')
        print(f"  Trade closed: {result2['symbol']} PnL=${result2['pnl']:.2f}")

        dpnl = pt.get_daily_pnl()
        print(f"  Daily PnL: ${dpnl['gross_pnl']:.2f}")
        print(f"  Balance: ${dpnl['balance']:.2f}")
        print(f"  Win rate: {dpnl['win_rate']}%")

        print(f"\n  Daily message:\n{pt.format_daily_pnl_message()}")

        stats = pt.get_stats()
        print(f"  Stats: {stats}")

        print("\n" + "=" * 60)

    elif '--background' in sys.argv:
        pt = get_paper_trader()
        pt.start_monitoring()
        print("Paper trader monitor running...")
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            pt.stop_monitoring()
    else:
        print("Usage:")
        print("  python paper_trader.py --test          # Run tests")
        print("  python paper_trader.py --background    # Start monitor")
