"""
Risk Manager - OMNI BRAIN V2
Dynamic position sizing, Kelly Criterion, daily risk limits, drawdown protection.
"""
import os
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Tuple
from pathlib import Path

log = logging.getLogger('RiskManager')
LOG_DIR = Path(__file__).parent / 'logs'


def _env_float(key: str, default: float) -> float:
    """
    Read a float from the environment, gracefully handling empty strings
    (e.g. ``ACCOUNT_BALANCE=`` in .env) by returning *default*.
    """
    raw = os.environ.get(key, '')
    if raw is None or raw.strip() == '':
        return default
    try:
        return float(raw)
    except (ValueError, TypeError):
        log.debug("Invalid float for %s=%r, using default %s", key, raw, default)
        return default


class RiskManager:
    """Dynamic position sizing and risk controls."""

    def __init__(self):
        self.balance = _env_float('ACCOUNT_BALANCE', 10000.0)
        self.risk_pct = _env_float('RISK_PCT', 1.0)
        self.max_daily_loss_pct = _env_float('MAX_DAILY_LOSS_PCT', 3.0)
        self.max_trades_per_pair = int(_env_float('MAX_TRADES_PER_PAIR', 6.0))
        self.max_concurrent = int(_env_float('MAX_CONCURRENT_TRADES', 2.0))
        self.drawdown_limit_pct = _env_float('DRAWDOWN_LIMIT_PCT', 10.0)
        self.max_spread_pips = _env_float('SPREAD_MAX_PIPS', 3.0)

        self.trades_today: Dict[str, int] = {}
        self.daily_pnl: float = 0.0
        self.peak_balance: float = self.balance
        self.open_trades: int = 0
        self.halted_until: Optional[datetime] = None
        self._load_state()

    def _load_state(self):
        path = LOG_DIR / 'risk_state.json'
        if path.exists():
            try:
                with open(path) as f:
                    data = json.load(f)
                if data.get('date') == datetime.now(timezone.utc).strftime('%Y-%m-%d'):
                    self.trades_today = data.get('trades_today', {})
                    self.daily_pnl = data.get('daily_pnl', 0.0)
                    self.peak_balance = data.get('peak_balance', self.balance)
                    self.open_trades = data.get('open_trades', 0)
                    halted = data.get('halted_until')
                    if halted:
                        self.halted_until = datetime.fromisoformat(halted)
            except Exception as e:
                log.debug(f"Failed to load risk state: {e}")

    def _save_state(self):
        try:
            with open(LOG_DIR / 'risk_state.json', 'w') as f:
                json.dump({
                    'date': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
                    'trades_today': self.trades_today,
                    'daily_pnl': self.daily_pnl,
                    'peak_balance': self.peak_balance,
                    'open_trades': self.open_trades,
                    'halted_until': self.halted_until.isoformat() if self.halted_until else None,
                    'updated': datetime.now(timezone.utc).isoformat()
                }, f, indent=2)
        except Exception as e:
            log.debug(f"Failed to save risk state: {e}")

    def check_halts(self) -> Tuple[bool, str]:
        """Check if trading is halted."""
        if self.halted_until and datetime.now(timezone.utc) < self.halted_until:
            remaining = (self.halted_until - datetime.now(timezone.utc)).seconds // 60
            return True, f"Drawdown halt: {remaining}m remaining"

        current_dd_pct = (self.peak_balance - self.balance) / self.peak_balance * 100
        if current_dd_pct > self.drawdown_limit_pct:
            self.halted_until = datetime.now(timezone.utc) + timedelta(hours=24)
            self._save_state()
            return True, f"Drawdown {current_dd_pct:.1f}% > {self.drawdown_limit_pct}% - halted 24h"

        daily_loss_pct = abs(self.daily_pnl) / self.balance * 100 if self.daily_pnl < 0 else 0
        if daily_loss_pct > self.max_daily_loss_pct:
            self.halted_until = datetime.now(timezone.utc).replace(hour=23, minute=59, second=59)
            self._save_state()
            return True, f"Daily loss {daily_loss_pct:.1f}% > {self.max_daily_loss_pct}% - halted until EOD"

        return False, "OK"

    def calculate_position_size(self, symbol: str, entry: float, sl: float, win_rate: float = 0.5, rr: float = 2.0) -> Dict:
        """
        Calculate position size using Kelly Criterion and fixed-fractional.
        Returns dict with lot sizes and risk metrics.
        """
        sl_pips = abs(entry - sl)
        pip_value = 10.0 if symbol in ('XAUUSD', 'SP500', 'US30', 'NAS100') else 1.0
        dollar_risk = self.balance * (self.risk_pct / 100)

        fixed_lots = dollar_risk / (sl_pips * pip_value) if sl_pips * pip_value > 0 else 0.01
        fixed_lots = max(0.01, min(10.0, round(fixed_lots, 2)))

        kelly_pct = (rr * win_rate - (1 - win_rate)) / rr if rr > 0 else 0
        kelly_pct = max(0, min(0.25, kelly_pct))
        half_kelly = kelly_pct / 2
        kelly_dollar_risk = self.balance * half_kelly
        kelly_lots = kelly_dollar_risk / (sl_pips * pip_value) if sl_pips * pip_value > 0 else 0.01
        kelly_lots = max(0.01, min(10.0, round(kelly_lots, 2)))

        return {
            'account_balance': self.balance,
            'risk_percent': self.risk_pct,
            'dollar_risk': round(dollar_risk, 2),
            'sl_pips': sl_pips,
            'pip_value': pip_value,
            'fixed_lots': fixed_lots,
            'kelly_pct': round(kelly_pct * 100, 1),
            'half_kelly_pct': round(half_kelly * 100, 1),
            'kelly_lots': kelly_lots,
            'recommended_lots': min(fixed_lots, kelly_lots) if kelly_lots > 0 else fixed_lots
        }

    def check_trade_limits(self, symbol: str) -> Tuple[bool, str]:
        """Check if we can take a new trade."""
        if self.open_trades >= self.max_concurrent:
            return False, f"Max concurrent trades ({self.max_concurrent}) reached"
        trades_today = self.trades_today.get(symbol, 0)
        if trades_today >= self.max_trades_per_pair:
            return False, f"Max trades/day ({self.max_trades_per_pair}) for {symbol}"
        return True, "OK"

    def record_trade(self, symbol: str, pnl: float = 0.0):
        """Record a trade for daily tracking."""
        self.trades_today[symbol] = self.trades_today.get(symbol, 0) + 1
        self.daily_pnl += pnl
        if self.balance + pnl > self.peak_balance:
            self.peak_balance = self.balance + pnl
        self._save_state()

    def check_spread(self, bid: float, ask: float, symbol: str) -> Tuple[bool, float, str]:
        """Check if spread is within limits."""
        spread = abs(ask - bid)
        pip_mult = 10000 if symbol not in ('XAUUSD', 'SP500', 'US30', 'NAS100', 'USOIL') else 100
        spread_pips = spread * pip_mult
        if spread_pips > self.max_spread_pips:
            return False, spread_pips, f"Spread {spread_pips:.1f}pips > max {self.max_spread_pips}pips ❌ BLOCKED"
        return True, spread_pips, f"Spread {spread_pips:.1f}pips ✅"

    def get_status(self) -> Dict:
        halted, reason = self.check_halts()
        return {
            'balance': self.balance,
            'daily_pnl': round(self.daily_pnl, 2),
            'open_trades': self.open_trades,
            'trades_today': dict(self.trades_today),
            'halted': halted,
            'halt_reason': reason if halted else None,
            'drawdown_pct': round((self.peak_balance - self.balance) / self.peak_balance * 100, 1) if self.peak_balance > 0 else 0,
        }

    def format_terminal(self) -> str:
        status = self.get_status()
        return (f"[RISK] Balance: ${status['balance']:.0f} | "
                f"Daily PnL: ${status['daily_pnl']:.0f} | "
                f"Open: {status['open_trades']} | "
                f"DD: {status['drawdown_pct']:.1f}% | "
                f"{'⛔ HALTED' if status['halted'] else '✅ ACTIVE'}")


_risk_mgr: Optional[RiskManager] = None
def get_risk_manager() -> RiskManager:
    global _risk_mgr
    if _risk_mgr is None:
        _risk_mgr = RiskManager()
    return _risk_mgr
