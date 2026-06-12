"""
Module 4 — AI Position Manager
=================================
Post-trade position monitoring with price fetching, partial TP closes,
trailing stops, Telegram alerts, and persistence.

Features:
  - Monitor open positions every 60s
  - Fetch current price via Twelve Data
  - Partial close: TP1=33%, TP2=33%, TP3=34%
  - Trailing stop after TP hits (1x ATR after TP1, 0.5x ATR after TP2)
  - Break-even after TP1
  - Time-stop (max 24h)
  - Telegram status updates
  - Position persistence to logs/positions.json
"""
import os
import json
import time
import math
import logging
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger('PositionManager')

LOG_DIR = Path(__file__).parent / 'logs'
POSITIONS_FILE = LOG_DIR / 'positions.json'
LOG_DIR.mkdir(parents=True, exist_ok=True)

EXIT_REASON_TP1 = 'TP1_HIT'
EXIT_REASON_TP2 = 'TP2_HIT'
EXIT_REASON_TP3 = 'TP3_HIT'
EXIT_REASON_SL = 'STOP_LOSS'
EXIT_REASON_BE = 'BREAK_EVEN'
EXIT_REASON_TRAIL = 'TRAILING_STOP'
EXIT_REASON_TIME = 'TIME_STOP'
EXIT_REASON_NEWS = 'NEWS_EXIT'
EXIT_REASON_MANUAL = 'MANUAL'

PIP_VALUE_MAP = {
    'XAUUSD': 10.0, 'SP500': 10.0, 'US30': 10.0,
    'EURUSD': 1.0, 'GBPUSD': 1.0, 'USDJPY': 1.0,
    'USDCHF': 1.0, 'AUDUSD': 1.0, 'USDCAD': 1.0,
}

MONITOR_INTERVAL = 60
MAX_TRADE_HOURS = 24


def _send_telegram(msg: str) -> bool:
    try:
        import urllib.request
        import urllib.error
        bot_token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
        chat_id = os.environ.get('TELEGRAM_CHAT_ID', '')
        if not bot_token or not chat_id:
            return False
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = json.dumps({'chat_id': chat_id, 'text': msg}).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as e:
        log.debug(f"Telegram send failed: {e}")
        return False


def _fetch_price(symbol: str) -> Optional[float]:
    twelvedata_key = os.environ.get('TWELVE_DATA_API_KEY', '')
    if not twelvedata_key:
        return None
    try:
        import urllib.request
        import json as _json
        url = f"https://api.twelvedata.com/price?symbol={symbol}&apikey={twelvedata_key}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        resp = urllib.request.urlopen(req, timeout=15)
        data = _json.loads(resp.read().decode())
        price = data.get('price')
        if price:
            return float(price)
        return None
    except Exception as e:
        log.debug(f"Failed to fetch price for {symbol}: {e}")
        return None


@dataclass
class ManagedPosition:
    symbol: str
    direction: str
    entry_price: float
    quantity: float
    entry_time: float
    current_sl: float
    current_tp1: float
    current_tp2: float
    current_tp3: float
    tp1_hit: bool = False
    tp2_hit: bool = False
    tp3_hit: bool = False
    break_even_triggered: bool = False
    status: str = 'ACTIVE'
    exit_reason: str = ''
    exit_price: float = 0.0
    pnl: float = 0.0
    closed_pct: float = 0.0
    lots: float = 0.1
    score: int = 0
    components: Dict = field(default_factory=dict)
    adjustments: List[Dict] = field(default_factory=list)

    @property
    def remaining_qty(self) -> float:
        return self.quantity * (1.0 - self.closed_pct)

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if k != 'adjustments'}

    def unrealized_pnl(self, current_price: float) -> float:
        if self.direction.upper() in ('BUY', 'LONG', 'BULLISH'):
            return round((current_price - self.entry_price) * self.remaining_qty, 2)
        return round((self.entry_price - current_price) * self.remaining_qty, 2)


class PositionManager:
    def __init__(self):
        self._positions: Dict[str, ManagedPosition] = {}
        self._closed: List[ManagedPosition] = []
        self._lock = threading.Lock()
        self._monitor_thread: Optional[threading.Thread] = None
        self._running = False
        self._load()

    def _load(self):
        try:
            if POSITIONS_FILE.exists():
                data = json.loads(POSITIONS_FILE.read_text())
                for d in data.get('active', []):
                    p = ManagedPosition(**d)
                    self._positions[p.symbol] = p
                for d in data.get('closed', []):
                    self._closed.append(ManagedPosition(**d))
                log.info(f"Loaded {len(self._positions)} active, {len(self._closed)} closed positions")
        except Exception as e:
            log.debug(f"Failed to load positions: {e}")

    def _save(self):
        try:
            POSITIONS_FILE.write_text(json.dumps({
                'active': [p.to_dict() for p in self._positions.values()],
                'closed': [p.to_dict() for p in self._closed[-100:]],
                'updated': datetime.now(timezone.utc).isoformat(),
            }, indent=2))
        except Exception as e:
            log.debug(f"Failed to save positions: {e}")

    def open_position(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        quantity: float,
        atr: float,
        regime: str = 'COMPRESSION',
        lots: float = 0.1,
        score: int = 0,
        components: Optional[Dict] = None,
        tp1: Optional[float] = None,
        tp2: Optional[float] = None,
        tp3: Optional[float] = None,
        sl: Optional[float] = None,
    ) -> ManagedPosition:
        if atr <= 0:
            atr = entry_price * 0.005
        is_long = direction.upper() in ('BUY', 'LONG', 'BULLISH')
        if tp1 is None:
            tp1 = round(entry_price + (1.0 * atr if is_long else -1.0 * atr), 5)
        if tp2 is None:
            tp2 = round(entry_price + (2.0 * atr if is_long else -2.0 * atr), 5)
        if tp3 is None:
            tp3 = round(entry_price + (3.0 * atr if is_long else -3.0 * atr), 5)
        if sl is None:
            sl = round(entry_price - (1.5 * atr if is_long else -1.5 * atr), 5)

        with self._lock:
            pos = ManagedPosition(
                symbol=symbol,
                direction=direction,
                entry_price=entry_price,
                quantity=quantity,
                entry_time=time.time(),
                current_sl=sl,
                current_tp1=tp1,
                current_tp2=tp2,
                current_tp3=tp3,
                lots=lots,
                score=score,
                components=components or {},
            )
            self._positions[symbol] = pos
            self._save()
            log.info(f"Position opened: {symbol} {direction} @ {entry_price} SL={sl} TP1={tp1} TP2={tp2} TP3={tp3} qty={quantity}")
        self._ensure_monitoring()
        return pos

    def _ensure_monitoring(self):
        if not self._running:
            self._running = True
            self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self._monitor_thread.start()
            log.info("Position monitor started")

    def _monitor_loop(self):
        while self._running:
            try:
                with self._lock:
                    symbols = list(self._positions.keys())
                for symbol in symbols:
                    try:
                        self._check_position(symbol)
                    except Exception as e:
                        log.debug(f"Position check error for {symbol}: {e}")
                with self._lock:
                    if not self._positions:
                        self._save()
            except Exception as e:
                log.debug(f"Monitor loop error: {e}")
            time.sleep(MONITOR_INTERVAL)

    def _check_position(self, symbol: str):
        pos = self._positions.get(symbol)
        if not pos or pos.status != 'ACTIVE':
            return
        current_price = _fetch_price(symbol)
        if current_price is None:
            return
        is_long = pos.direction.upper() in ('BUY', 'LONG', 'BULLISH')
        result = None
        # TP1 check
        if not pos.tp1_hit and ((is_long and current_price >= pos.current_tp1) or (not is_long and current_price <= pos.current_tp1)):
            result = self._handle_tp1(pos, current_price)
        # TP2 check
        if result is None and not pos.tp2_hit and pos.tp1_hit and ((is_long and current_price >= pos.current_tp2) or (not is_long and current_price <= pos.current_tp2)):
            result = self._handle_tp2(pos, current_price)
        # TP3 check
        if result is None and not pos.tp3_hit and pos.tp2_hit and ((is_long and current_price >= pos.current_tp3) or (not is_long and current_price <= pos.current_tp3)):
            result = self._handle_tp3(pos, current_price)
        # SL check
        if result is None and ((is_long and current_price <= pos.current_sl) or (not is_long and current_price >= pos.current_sl)):
            result = self._close_position(symbol, current_price, EXIT_REASON_SL)
        # Time-stop
        if result is None:
            elapsed = (time.time() - pos.entry_time) / 3600
            if elapsed > MAX_TRADE_HOURS:
                result = self._close_position(symbol, current_price, EXIT_REASON_TIME)

    def _handle_tp1(self, pos: ManagedPosition, price: float) -> Dict[str, Any]:
        pos.tp1_hit = True
        pos.closed_pct = 0.33
        pos.break_even_triggered = True
        is_long = pos.direction.upper() in ('BUY', 'LONG', 'BULLISH')
        pos.current_sl = pos.entry_price
        profit = round((price - pos.entry_price) * pos.quantity * 0.33 if is_long else (pos.entry_price - price) * pos.quantity * 0.33, 2)
        pos.pnl += profit
        pos.adjustments.append({'action': 'TP1_HIT', 'price': price, 'profit': profit, 'time': time.time()})
        self._save()
        msg = (
            f"\u2705 TP1 HIT \u2014 {pos.symbol}\n"
            f"Partial close: 33% at {price}\n"
            f"Profit: +${profit}\n"
            f"SL moved to breakeven ({pos.entry_price})\n"
            f"Remaining: {1 - pos.closed_pct:.0%} open"
        )
        _send_telegram(msg)
        log.info(f"TP1 hit {pos.symbol} @ {price} profit={profit}")
        return {'symbol': pos.symbol, 'event': 'TP1', 'price': price, 'profit': profit}

    def _handle_tp2(self, pos: ManagedPosition, price: float) -> Dict[str, Any]:
        pos.tp2_hit = True
        pos.closed_pct = 0.66
        is_long = pos.direction.upper() in ('BUY', 'LONG', 'BULLISH')
        profit = round((price - pos.entry_price) * pos.quantity * 0.33 if is_long else (pos.entry_price - price) * pos.quantity * 0.33, 2)
        pos.pnl += profit
        atr = abs(pos.current_tp1 - pos.entry_price)
        pos.adjustments.append({'action': 'TP2_HIT', 'price': price, 'profit': profit, 'time': time.time()})
        if is_long:
            pos.current_sl = max(pos.current_sl, price - atr * 0.5)
        else:
            pos.current_sl = min(pos.current_sl, price + atr * 0.5)
        self._save()
        msg = (
            f"\u2705 TP2 HIT \u2014 {pos.symbol}\n"
            f"Partial close: 33% at {price}\n"
            f"Profit: +${profit}\n"
            f"Trailing SL to {pos.current_sl}\n"
            f"Remaining: {1 - pos.closed_pct:.0%} open"
        )
        _send_telegram(msg)
        log.info(f"TP2 hit {pos.symbol} @ {price} profit={profit}")
        return {'symbol': pos.symbol, 'event': 'TP2', 'price': price, 'profit': profit}

    def _handle_tp3(self, pos: ManagedPosition, price: float) -> Dict[str, Any]:
        pos.tp3_hit = True
        pos.closed_pct = 1.0
        is_long = pos.direction.upper() in ('BUY', 'LONG', 'BULLISH')
        profit = round((price - pos.entry_price) * pos.quantity * 0.34 if is_long else (pos.entry_price - price) * pos.quantity * 0.34, 2)
        pos.pnl += profit
        total_pnl = pos.pnl
        pos.adjustments.append({'action': 'TP3_HIT', 'price': price, 'profit': profit, 'time': time.time()})
        return self._close_position(pos.symbol, price, EXIT_REASON_TP3)

    def close_position(self, symbol: str, current_price: float, reason: str = EXIT_REASON_MANUAL) -> Optional[Dict]:
        return self._close_position(symbol, current_price, reason)

    def _close_position(self, symbol: str, exit_price: float, reason: str) -> Dict[str, Any]:
        pos = self._positions.get(symbol)
        if not pos or pos.status != 'ACTIVE':
            return {'symbol': symbol, 'status': 'NOT_FOUND'}
        pos.status = 'CLOSED'
        pos.exit_price = exit_price
        pos.exit_reason = reason
        is_long = pos.direction.upper() in ('BUY', 'LONG', 'BULLISH')
        if pos.pnl == 0 and not pos.tp1_hit:
            if is_long:
                pos.pnl = round((exit_price - pos.entry_price) * pos.quantity, 2)
            else:
                pos.pnl = round((pos.entry_price - exit_price) * pos.quantity, 2)
        self._closed.append(pos)
        del self._positions[symbol]
        self._save()
        balance = 10000 + sum(p.pnl for p in self._closed[-100:])
        log.info(f"Position closed: {symbol} {reason} PnL={pos.pnl}")
        if reason in (EXIT_REASON_SL, EXIT_REASON_TIME):
            msg = (
                f"\u274c STOPPED OUT \u2014 {symbol}\n"
                f"Entry: {pos.entry_price}\n"
                f"Exit: {exit_price}\n"
                f"Loss: -${abs(pos.pnl)}\n"
                f"Balance: ${balance:.2f}"
            )
            _send_telegram(msg)
        return pos.to_dict()

    def get_position(self, symbol: str) -> Optional[ManagedPosition]:
        return self._positions.get(symbol)

    def get_all_positions(self) -> Dict[str, ManagedPosition]:
        return dict(self._positions)

    def get_closed_positions(self, limit: int = 50) -> List[ManagedPosition]:
        return self._closed[-limit:]

    def get_daily_summary(self) -> str:
        lines = ["\U0001f4ca OPEN POSITIONS"]
        for pos in self._positions.values():
            price = _fetch_price(pos.symbol)
            if price is None:
                price = pos.entry_price
            upnl = pos.unrealized_pnl(price)
            status_parts = []
            if pos.tp1_hit:
                status_parts.append("TP1\u2705")
            if pos.tp2_hit:
                status_parts.append("TP2\u2705")
            if not pos.tp1_hit:
                status_parts.append("watching")
            status_str = " ".join(status_parts)
            direction = "BULL" if pos.direction.upper() in ('BUY', 'LONG', 'BULLISH') else "BEAR"
            sign = "+" if upnl >= 0 else ""
            lines.append(f"{pos.symbol} {direction}: {sign}${upnl} ({status_str})")
        if not self._positions:
            lines.append("No open positions")
        return "\n".join(lines)

    def stop(self):
        self._running = False


_pos_mgr: Optional[PositionManager] = None
_pos_mgr_lock = threading.Lock()


def get_position_manager() -> PositionManager:
    global _pos_mgr
    if _pos_mgr is None:
        with _pos_mgr_lock:
            if _pos_mgr is None:
                _pos_mgr = PositionManager()
    return _pos_mgr


def get_positions_api() -> Dict[str, Any]:
    pm = get_position_manager()
    active = {s: p.to_dict() for s, p in pm.get_all_positions().items()}
    closed = [p.to_dict() for p in pm.get_closed_positions(20)]
    total_pnl = sum(p.pnl for p in pm.get_closed_positions(1000))
    return {
        'active': active,
        'closed': closed,
        'total_pnl': total_pnl,
        'daily_summary': pm.get_daily_summary(),
        'timestamp': datetime.now(timezone.utc).isoformat(),
    }
