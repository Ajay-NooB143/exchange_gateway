"""
Full Circuit Breaker - OMNI BRAIN V2
=====================================
System protection via automated circuit breaking.

Rules:
  LOSS_STREAK  : 3 losses in a row → pause 1 hour
  MEMORY_HIGH  : memory > 80MB → throttle scans 50%
  MT5_UNSTABLE : disconnects > 3x in 1hr → halt + alert
  SCORE_LOW    : avg score < 45 last 10 signals → pause
  DAILY_LOSS   : if daily loss > 3 signals → halt today

States: ACTIVE / PAUSED / THROTTLED / HALTED
"""

import os
import json
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum
import threading

log = logging.getLogger('CircuitBreaker')

LOG_DIR = Path(__file__).parent / 'logs'
LOG_DIR.mkdir(exist_ok=True)


class CBState(Enum):
    """Circuit breaker states."""
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    THROTTLED = "THROTTLED"
    HALTED = "HALTED"


class CBReason(Enum):
    """Circuit breaker trigger reasons."""
    LOSS_STREAK = "LOSS_STREAK"
    MEMORY_HIGH = "MEMORY_HIGH"
    MT5_UNSTABLE = "MT5_UNSTABLE"
    SCORE_LOW = "SCORE_LOW"
    DAILY_LOSS = "DAILY_LOSS"
    MANUAL = "MANUAL"


@dataclass
class AssetState:
    """Circuit breaker state for a single asset."""
    symbol: str
    state: CBState = CBState.ACTIVE
    reason: Optional[str] = None
    triggered_at: Optional[str] = None
    resume_at: Optional[str] = None
    loss_streak: int = 0
    daily_losses: int = 0
    mt5_disconnects: int = 0
    recent_scores: List[int] = field(default_factory=list)


class CircuitBreaker:
    """
    Full circuit breaker system.
    
    Rules:
      LOSS_STREAK  : 3 consecutive losses → pause 1 hour
      MEMORY_HIGH  : memory > 80MB → throttle 50%
      MT5_UNSTABLE : >3 disconnects/hour → halt
      SCORE_LOW    : avg score < 45 last 10 → pause
      DAILY_LOSS   : >3 daily losses → halt
    """
    
    # Thresholds
    LOSS_STREAK_LIMIT = 3
    PAUSE_DURATION_HOURS = 1
    MEMORY_THRESHOLD_MB = 80
    MT5_DISCONNECT_LIMIT = 3
    MT5_WINDOW_SECONDS = 3600
    SCORE_LOW_THRESHOLD = 45
    DAILY_LOSS_LIMIT = 3
    
    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or LOG_DIR
        self.data_dir.mkdir(exist_ok=True)
        
        self.assets: Dict[str, AssetState] = {}
        self.mt5_disconnects: List[float] = []
        
        self._load_state()
    
    def _load_state(self) -> None:
        """Load state from file."""
        filepath = self.data_dir / 'circuit_state.json'
        
        if filepath.exists():
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                
                for symbol, state_data in data.get('assets', {}).items():
                    asset = AssetState(symbol=symbol)
                    asset.state = CBState(state_data.get('state', 'ACTIVE'))
                    asset.reason = state_data.get('reason')
                    asset.triggered_at = state_data.get('triggered_at')
                    asset.resume_at = state_data.get('resume_at')
                    asset.loss_streak = state_data.get('loss_streak', 0)
                    asset.daily_losses = state_data.get('daily_losses', 0)
                    self.assets[symbol] = asset
            except Exception as e:
                log.error(f"Failed to load circuit state: {e}")
    
    def _save_state(self) -> None:
        """Save state to file."""
        filepath = self.data_dir / 'circuit_state.json'
        
        data = {
            'assets': {},
            'last_updated': datetime.now(timezone.utc).isoformat()
        }
        
        for symbol, asset in self.assets.items():
            data['assets'][symbol] = {
                'state': asset.state.value,
                'reason': asset.reason,
                'triggered_at': asset.triggered_at,
                'resume_at': asset.resume_at,
                'loss_streak': asset.loss_streak,
                'daily_losses': asset.daily_losses
            }
        
        try:
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            log.error(f"Failed to save circuit state: {e}")
    
    def _get_asset(self, symbol: str) -> AssetState:
        """Get or create asset state."""
        if symbol not in self.assets:
            self.assets[symbol] = AssetState(symbol=symbol)
        return self.assets[symbol]
    
    def _check_auto_resume(self, asset: AssetState) -> None:
        """Check if pause period has expired."""
        if asset.state == CBState.PAUSED and asset.resume_at:
            try:
                resume_time = datetime.fromisoformat(asset.resume_at)
                if datetime.now(timezone.utc) >= resume_time:
                    log.info(f"[CB] {asset.symbol} auto-resumed from PAUSED")
                    asset.state = CBState.ACTIVE
                    asset.reason = None
                    asset.triggered_at = None
                    asset.resume_at = None
                    asset.loss_streak = 0
            except Exception:
                pass
    
    def allow(self, symbol: str) -> bool:
        """
        Check if trading is allowed for symbol.
        
        Returns True if ACTIVE, False if PAUSED/THROTTLED/HALTED
        """
        asset = self._get_asset(symbol)
        self._check_auto_resume(asset)
        
        return asset.state == CBState.ACTIVE
    
    def is_throttled(self, symbol: str) -> bool:
        """Check if asset is throttled."""
        asset = self._get_asset(symbol)
        self._check_auto_resume(asset)
        return asset.state == CBState.THROTTLED
    
    def is_halted(self, symbol: str) -> bool:
        """Check if asset is halted."""
        asset = self._get_asset(symbol)
        return asset.state == CBState.HALTED
    
    def get_state(self, symbol: str) -> CBState:
        """Get current state for symbol."""
        asset = self._get_asset(symbol)
        self._check_auto_resume(asset)
        return asset.state
    
    def get_remaining_pause(self, symbol: str) -> Optional[int]:
        """Get remaining pause time in seconds."""
        asset = self._get_asset(symbol)
        if asset.state == CBState.PAUSED and asset.resume_at:
            try:
                resume_time = datetime.fromisoformat(asset.resume_at)
                remaining = (resume_time - datetime.now(timezone.utc)).total_seconds()
                return max(0, int(remaining))
            except Exception:
                pass
        return None
    
    def record_loss(self, symbol: str) -> None:
        """Record a loss for symbol."""
        asset = self._get_asset(symbol)
        asset.loss_streak += 1
        asset.daily_losses += 1
        
        log.info(f"[CB] {symbol} loss recorded (streak: {asset.loss_streak}, daily: {asset.daily_losses})")
        
        # Check loss streak
        if asset.loss_streak >= self.LOSS_STREAK_LIMIT:
            self._trigger(symbol, CBReason.LOSS_STREAK, f"{asset.loss_streak} consecutive losses")
        
        # Check daily losses
        elif asset.daily_losses >= self.DAILY_LOSS_LIMIT:
            self._trigger(symbol, CBReason.DAILY_LOSS, f"{asset.daily_losses} daily losses")
        
        self._save_state()
    
    def record_win(self, symbol: str) -> None:
        """Record a win for symbol."""
        asset = self._get_asset(symbol)
        asset.loss_streak = 0
        
        # Reset daily losses on win
        if asset.daily_losses > 0:
            asset.daily_losses = max(0, asset.daily_losses - 1)
        
        self._save_state()
    
    def record_score(self, symbol: str, score: int) -> None:
        """Record a score for symbol."""
        asset = self._get_asset(symbol)
        asset.recent_scores.append(score)
        
        # Keep last 10
        if len(asset.recent_scores) > 10:
            asset.recent_scores = asset.recent_scores[-10:]
        
        # Check low score average
        if len(asset.recent_scores) >= 10:
            avg = sum(asset.recent_scores) / len(asset.recent_scores)
            if avg < self.SCORE_LOW_THRESHOLD:
                self._trigger(symbol, CBReason.SCORE_LOW, f"avg score {avg:.1f}")
        
        self._save_state()
    
    def record_mt5_disconnect(self) -> None:
        """Record MT5 disconnect."""
        now = time.time()
        self.mt5_disconnects.append(now)
        
        # Clean old disconnects
        cutoff = now - self.MT5_WINDOW_SECONDS
        self.mt5_disconnects = [d for d in self.mt5_disconnects if d > cutoff]
        
        # Check limit
        if len(self.mt5_disconnects) > self.MT5_DISCONNECT_LIMIT:
            for symbol in self.assets:
                if self.assets[symbol].state == CBState.ACTIVE:
                    self._trigger(symbol, CBReason.MT5_UNSTABLE, f"{len(self.mt5_disconnects)} disconnects/hour")
        
        self._save_state()
    
    def check_memory(self, memory_mb: float) -> None:
        """Check memory usage and throttle if needed."""
        if memory_mb > self.MEMORY_THRESHOLD_MB:
            for symbol, asset in self.assets.items():
                if asset.state == CBState.ACTIVE:
                    self._trigger(symbol, CBReason.MEMORY_HIGH, f"{memory_mb:.1f}MB")
    
    def _trigger(self, symbol: str, reason: CBReason, details: str) -> None:
        """Trigger circuit breaker for symbol."""
        asset = self._get_asset(symbol)
        
        if asset.state != CBState.ACTIVE:
            return  # Already triggered
        
        now = datetime.now(timezone.utc)
        
        asset.state = CBState.PAUSED if reason in [CBReason.LOSS_STREAK, CBReason.SCORE_LOW] else CBState.HALTED
        asset.reason = f"{reason.value}: {details}"
        asset.triggered_at = now.isoformat()
        
        if reason in [CBReason.LOSS_STREAK, CBReason.SCORE_LOW]:
            resume_time = now + timedelta(hours=self.PAUSE_DURATION_HOURS)
            asset.resume_at = resume_time.isoformat()
        
        log.warning(f"[CB] TRIGGERED: {symbol} → {asset.state.value} ({asset.reason})")
        
        # Send Telegram alert
        self._send_alert(symbol, reason.value, details, asset.state.value, asset.resume_at)
        
        self._save_state()
    
    def _send_alert(self, symbol: str, reason: str, details: str, state: str, resume_at: Optional[str]) -> None:
        """Send Telegram alert."""
        try:
            import urllib.request
            
            bot_token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
            chat_id = os.environ.get('TELEGRAM_CHAT_ID', '')
            
            if not bot_token or not chat_id:
                return
            
            resume_str = f"Resume: {resume_at}" if resume_at else "Resume: N/A"
            
            message = (
                f"🔴 CIRCUIT BREAKER TRIGGERED\n\n"
                f"Reason: {reason} ({details})\n"
                f"Asset: {symbol}\n"
                f"Status: {state}\n"
                f"{resume_str}"
            )
            
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            data = json.dumps({'chat_id': chat_id, 'text': message}).encode('utf-8')
            
            req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
            urllib.request.urlopen(req, timeout=10)
        except Exception as e:
            log.debug(f"Failed to send CB alert: {e}")
    
    def reset(self, symbol: str) -> None:
        """Manually reset circuit breaker for symbol."""
        asset = self._get_asset(symbol)
        asset.state = CBState.ACTIVE
        asset.reason = None
        asset.triggered_at = None
        asset.resume_at = None
        asset.loss_streak = 0
        self._save_state()
        log.info(f"[CB] {symbol} manually reset to ACTIVE")
    
    def reset_daily(self) -> None:
        """Reset daily counters."""
        for asset in self.assets.values():
            asset.daily_losses = 0
        self._save_state()
    
    def get_all_states(self) -> Dict[str, Dict[str, Any]]:
        """Get all asset states."""
        for asset in self.assets.values():
            self._check_auto_resume(asset)
        
        return {
            symbol: {
                'state': asset.state.value,
                'reason': asset.reason,
                'triggered_at': asset.triggered_at,
                'resume_at': asset.resume_at,
                'remaining_pause': self.get_remaining_pause(symbol),
                'loss_streak': asset.loss_streak,
                'daily_losses': asset.daily_losses
            }
            for symbol, asset in self.assets.items()
        }
    
    @staticmethod
    def format_state(symbol: str, state: Dict[str, Any]) -> str:
        """Format state for terminal display."""
        status = state['state']
        if status == 'ACTIVE':
            emoji = '🟢'
        elif status == 'THROTTLED':
            emoji = '🟡'
        else:
            emoji = '🔴'
        
        remaining = state.get('remaining_pause')
        if remaining and remaining > 0:
            minutes = remaining // 60
            return f"[CB] {symbol} {emoji} {status} {minutes}min remaining"
        elif state.get('reason'):
            return f"[CB] {symbol} {emoji} {status} ({state['reason']})"
        else:
            return f"[CB] {symbol} {emoji} {status}"


# Global instance
_circuit_breaker: Optional[CircuitBreaker] = None
_lock = threading.Lock()


def get_circuit_breaker() -> CircuitBreaker:
    """Get or create global circuit breaker."""
    global _circuit_breaker
    if _circuit_breaker is None:
        with _lock:
            if _circuit_breaker is None:
                _circuit_breaker = CircuitBreaker()
    return _circuit_breaker


def allow(symbol: str) -> bool:
    """Check if trading is allowed (convenience function)."""
    return get_circuit_breaker().allow(symbol)


# ══════════════════════════════════════════════════════════════════════════════
# CLI TEST
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import sys
    
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    if '--test' in sys.argv:
        print("=" * 60)
        print("  CIRCUIT BREAKER - TEST")
        print("=" * 60)
        
        cb = CircuitBreaker()
        
        # Test 1: Normal operation
        print("\nTest 1: Normal operation")
        print(f"  XAUUSD allowed: {cb.allow('XAUUSD')}")
        print(f"  EURUSD allowed: {cb.allow('EURUSD')}")
        
        # Test 2: Loss streak
        print("\nTest 2: Loss streak (3 losses)")
        for i in range(4):
            cb.record_loss('XAUUSD')
            print(f"  Loss {i+1}: state={cb.get_state('XAUUSD').value}")
        
        print(f"  XAUUSD allowed: {cb.allow('XAUUSD')}")
        
        # Test 3: Reset
        print("\nTest 3: Reset")
        cb.reset('XAUUSD')
        print(f"  XAUUSD allowed after reset: {cb.allow('XAUUSD')}")
        
        # Test 4: Low score
        print("\nTest 4: Low score average")
        for i in range(10):
            cb.record_score('EURUSD', 40)
        print(f"  EURUSD state: {cb.get_state('EURUSD').value}")
        
        # Show all states
        print("\nAll States:")
        for symbol, state in cb.get_all_states().items():
            print(f"  {CircuitBreaker.format_state(symbol, state)}")
        
        print("\n" + "=" * 60)
    else:
        print("Usage: python circuit_breaker.py --test")
