"""
Telegram Signal Alerts - OMNI BRAIN V2
======================================
Live trading signal notifications via Telegram.

Features:
  A) EXECUTE alert when score >= threshold + MTF confirmed + CB active
  B) WAIT alert when score >= 65 (condensed)
  C) BLOCK alert only after previous EXECUTE (anti-spam)
  D) Signal outcome tracker (1H, 4H, 24H checks)
  E) Anti-spam rules (4 EXECUTE/hr, 2 WAIT/hr, 30min cooldown, quiet hours)
  F) Telegram bot command polling (/status, /score, /cb, etc.)

Architecture:
  TelegramSignalService
    ├── AlertRateLimiter      (anti-spam rules)
    ├── TelegramBot           (send/recv via urllib)
    ├── SignalAlertSender     (format messages)
    ├── SignalOutcomeTracker  (outcome checks)
    └── CommandHandler        (bot commands)

Usage:
  python telegram_signals.py --test
  python telegram_signals.py --background
"""

import os
import sys
import json
import time
import logging
import threading
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from pathlib import Path

# Load .env at module level so PM2 processes pick it up
_env_path = Path(__file__).parent.parent / '.env'
if _env_path.exists():
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith('#') and '=' in _line:
                _k, _v = _line.split('=', 1)
                os.environ.setdefault(_k.strip(), _v.strip())

log = logging.getLogger('TelegramSignals')

LOG_DIR = Path(__file__).parent / 'logs'
LOG_DIR.mkdir(exist_ok=True)

PENDING_FILE = LOG_DIR / 'pending_telegram.json'
BOT_USERNAME = 'omnibrainsignals_free'

ASSETS = ['XAUUSD', 'EURUSD', 'GBPUSD', 'SP500']
TIMEFRAMES = ['M15', 'H1', 'H4', 'D1']


# ══════════════════════════════════════════════════════════════════════════════
# CHAT ID DISCOVERY
# ══════════════════════════════════════════════════════════════════════════════

def get_chat_id(bot_token: str = None) -> Optional[str]:
    """Discover chat_id by polling getUpdates.
    
    Call this after the user sends /start to the bot.
    Returns the first chat_id found, or None.
    """
    if bot_token is None:
        bot_token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
    if not bot_token:
        log.warning("No TELEGRAM_BOT_TOKEN set")
        return None

    try:
        import urllib.request
        import urllib.parse
        url = f"https://api.telegram.org/bot{bot_token}/getUpdates?timeout=5"
        req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read().decode())
        
        if not result.get('ok'):
            log.warning(f"getUpdates failed: {result.get('description', 'unknown')}")
            return None
        
        updates = result.get('result', [])
        found = set()
        for update in updates:
            msg = update.get('message', {}) or update.get('callback_query', {}).get('message', {})
            chat = msg.get('chat', {})
            cid = chat.get('id')
            if cid:
                found.add(str(cid))
        
        if found:
            cid = list(found)[0]
            log.info(f"Chat ID found: {cid}")
            # Auto-update .env
            env_path = Path(__file__).parent.parent / '.env'
            if env_path.exists():
                content = env_path.read_text()
                if 'TELEGRAM_CHAT_ID=' in content:
                    import re
                    content = re.sub(
                        r'TELEGRAM_CHAT_ID=.*',
                        f'TELEGRAM_CHAT_ID={cid}',
                        content
                    )
                    env_path.write_text(content)
                    log.info(f"Updated .env with TELEGRAM_CHAT_ID={cid}")
            return cid
        else:
            log.warning(f"No chat IDs found. Send /start to @{BOT_USERNAME} first.")
            return None
    except Exception as e:
        log.warning(f"get_chat_id failed: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# PENDING MESSAGE QUEUE
# ══════════════════════════════════════════════════════════════════════════════

class PendingMessageQueue:
    """Queue failed messages and retry every 60 seconds."""
    
    def __init__(self, filepath: Path = PENDING_FILE):
        self.filepath = filepath
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
    
    def _load(self) -> List[Dict[str, Any]]:
        if self.filepath.exists():
            try:
                return json.loads(self.filepath.read_text())
            except Exception:
                return []
        return []
    
    def _save(self, messages: List[Dict[str, Any]]) -> None:
        try:
            self.filepath.write_text(json.dumps(messages, indent=2))
        except Exception as e:
            log.warning(f"Failed to save pending queue: {e}")
    
    def add(self, text: str, parse_mode: str = None) -> None:
        with self._lock:
            msgs = self._load()
            msgs.append({
                'text': text,
                'parse_mode': parse_mode,
                'added': datetime.now(timezone.utc).isoformat(),
                'retries': 0
            })
            self._save(msgs)
            log.debug(f"Queued pending message (total: {len(msgs)})")
    
    def retry_all(self, bot) -> int:
        """Retry all pending messages. Returns count of successful sends."""
        with self._lock:
            msgs = self._load()
            if not msgs:
                return 0
            remaining = []
            sent = 0
            for msg in msgs:
                msg['retries'] = msg.get('retries', 0) + 1
                if bot.send_message(msg['text'], msg.get('parse_mode')):
                    sent += 1
                else:
                    remaining.append(msg)
            self._save(remaining)
            if sent:
                log.info(f"Retry: sent {sent}/{len(msgs)} pending messages ({len(remaining)} remaining)")
            return sent
    
    @property
    def count(self) -> int:
        return len(self._load())
    
    def start_background(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
    
    def stop(self) -> None:
        self._running = False
    
    def _run_loop(self) -> None:
        while self._running:
            try:
                if self.count > 0:
                    from telegram_signals import get_telegram_service  # avoid circular
                    svc = get_telegram_service()
                    self.retry_all(svc.bot)
            except Exception:
                pass
            for _ in range(60):
                if not self._running:
                    break
                time.sleep(1)


# Global pending queue
_pending_queue: Optional[PendingMessageQueue] = None


def get_pending_queue() -> PendingMessageQueue:
    global _pending_queue
    if _pending_queue is None:
        _pending_queue = PendingMessageQueue()
    return _pending_queue


# ══════════════════════════════════════════════════════════════════════════════
# A: ANTI-SPAM RATE LIMITER
# ══════════════════════════════════════════════════════════════════════════════

class AlertRateLimiter:
    """
    Anti-spam rules for Telegram alerts.
    
    Rules:
      - Max 4 EXECUTE alerts per hour (total)
      - Same symbol: min 30min between alerts
      - WAIT alerts: max 2 per hour
      - Quiet hours: 22:00-06:00 UTC (NO alerts)
      - Only /status commands work during quiet hours
    """
    
    MAX_EXECUTE_PER_HOUR = 4
    MAX_WAIT_PER_HOUR = 2
    SAME_SYMBOL_COOLDOWN_SECONDS = 1800  # 30 minutes
    QUIET_HOUR_START = 22
    QUIET_HOUR_END = 6
    
    def __init__(self):
        self.alert_times: Dict[str, List[float]] = {}
        self._lock = threading.Lock()
        self._quiet_start = int(os.environ.get('TELEGRAM_QUIET_START', str(self.QUIET_HOUR_START)))
        self._quiet_end = int(os.environ.get('TELEGRAM_QUIET_END', str(self.QUIET_HOUR_END)))
        self._load_state()
    
    def _load_state(self) -> None:
        filepath = LOG_DIR / 'alert_times.json'
        if filepath.exists():
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                self.alert_times = data.get('alert_times', {})
            except Exception:
                self.alert_times = {}
    
    def _save_state(self) -> None:
        filepath = LOG_DIR / 'alert_times.json'
        try:
            data = {
                'alert_times': self.alert_times,
                'last_updated': datetime.now(timezone.utc).isoformat()
            }
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            log.debug(f"Failed to save alert times: {e}")
    
    def is_quiet_hours(self) -> bool:
        hour = datetime.now(timezone.utc).hour
        if self._quiet_start > self._quiet_end:
            return hour >= self._quiet_start or hour < self._quiet_end
        return self._quiet_start <= hour < self._quiet_end
    
    def _get_hour_key(self, alert_type: str) -> str:
        now = datetime.now(timezone.utc)
        return f"{alert_type}_{now.strftime('%Y%m%d_%H')}"
    
    def _count_recent(self, alert_type: str, seconds: int = 3600) -> int:
        cutoff = time.time() - seconds
        key = self._get_hour_key(alert_type)
        timestamps = self.alert_times.get(key, [])
        return sum(1 for t in timestamps if t > cutoff)
    
    def _last_alert_for_symbol(self, symbol: str) -> Optional[float]:
        key = f"symbol_{symbol}"
        timestamps = self.alert_times.get(key, [])
        return timestamps[-1] if timestamps else None
    
    def can_send(self, alert_type: str, symbol: str) -> tuple:
        with self._lock:
            if self.is_quiet_hours():
                return False, "Quiet hours active (22:00-06:00 UTC)"
            
            if alert_type == 'EXECUTE':
                count = self._count_recent('EXECUTE')
                if count >= self.MAX_EXECUTE_PER_HOUR:
                    return False, f"Max {self.MAX_EXECUTE_PER_HOUR} EXECUTE/hr reached ({count} sent)"
            
            elif alert_type == 'WAIT':
                count = self._count_recent('WAIT')
                if count >= self.MAX_WAIT_PER_HOUR:
                    return False, f"Max {self.MAX_WAIT_PER_HOUR} WAIT/hr reached ({count} sent)"
            
            last_time = self._last_alert_for_symbol(symbol)
            if last_time:
                elapsed = time.time() - last_time
                if elapsed < self.SAME_SYMBOL_COOLDOWN_SECONDS:
                    remaining = int(self.SAME_SYMBOL_COOLDOWN_SECONDS - elapsed)
                    return False, f"Cooldown: {remaining}s remaining for {symbol}"
            
            return True, "OK"
    
    def record_alert(self, alert_type: str, symbol: str) -> None:
        with self._lock:
            now = time.time()
            
            hour_key = self._get_hour_key(alert_type)
            if hour_key not in self.alert_times:
                self.alert_times[hour_key] = []
            self.alert_times[hour_key].append(now)
            
            symbol_key = f"symbol_{symbol}"
            if symbol_key not in self.alert_times:
                self.alert_times[symbol_key] = []
            self.alert_times[symbol_key].append(now)
            
            cutoff = now - 7200
            for key in list(self.alert_times.keys()):
                self.alert_times[key] = [t for t in self.alert_times[key] if t > cutoff]
                if not self.alert_times[key]:
                    del self.alert_times[key]
            
            self._save_state()


# ══════════════════════════════════════════════════════════════════════════════
# B: TELEGRAM BOT (urllib-based)
# ══════════════════════════════════════════════════════════════════════════════

class TelegramBot:
    """Send and receive messages via Telegram Bot API using urllib."""
    
    API_BASE = "https://api.telegram.org/bot"
    
    def __init__(self, auto_discover: bool = False):
        self.bot_token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
        self.chat_id = os.environ.get('TELEGRAM_CHAT_ID', '')
        self._offset = 0
        self._last_update_id = 0
        # Ensure chat_id is integer for Telegram API
        if self.chat_id:
            try:
                self.chat_id = int(self.chat_id)
            except (ValueError, TypeError):
                pass
        if auto_discover and not self.chat_id:
            self.auto_discover_chat()
    
    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)
    
    def send_message(self, text: str, parse_mode: str = None) -> bool:
        if not self.is_configured:
            log.debug("Telegram not configured, skipping send")
            return False
        
        try:
            import urllib.request
            import urllib.parse
            import urllib.error
            
            # Ensure chat_id is int for Telegram API
            chat_id = self.chat_id
            if isinstance(chat_id, str):
                try:
                    chat_id = int(chat_id)
                except ValueError:
                    log.error(f"Invalid chat_id format: {chat_id}")
                    return False
            
            payload = {'chat_id': chat_id, 'text': text}
            if parse_mode:
                payload['parse_mode'] = parse_mode
            
            url = f"{self.API_BASE}{self.bot_token}/sendMessage"
            data = json.dumps(payload).encode('utf-8')
            
            req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
            resp = urllib.request.urlopen(req, timeout=10)
            result = json.loads(resp.read().decode())
            
            if result.get('ok'):
                log.debug("Telegram message sent")
                return True
            else:
                log.warning(f"Telegram API error: {result.get('description', result)}")
                return False
        except urllib.error.HTTPError as e:
            body = e.read().decode() if hasattr(e, 'read') else ''
            if e.code == 400:
                log.warning(f"Chat not found (400) — user must send /start to @{BOT_USERNAME} first")
                log.warning(f"Response: {body[:200]}")
                # Queue for retry
                try:
                    get_pending_queue().add(text, parse_mode)
                except Exception:
                    pass
            elif e.code == 401:
                log.error(f"Unauthorized (401) — invalid bot token")
            elif e.code == 403:
                log.error(f"Forbidden (403) — bot blocked by user or chat_id invalid")
            else:
                log.warning(f"Telegram HTTP {e.code}: {body[:200]}")
            return False
        except Exception as e:
            log.warning(f"Telegram send failed: {e}")
            return False
    
    def verify_chat(self) -> bool:
        """Check if the configured chat_id is valid via getChat API."""
        if not self.bot_token or not self.chat_id:
            return False
        try:
            import urllib.request
            url = f"{self.API_BASE}{self.bot_token}/getChat?chat_id={self.chat_id}"
            resp = urllib.request.urlopen(url, timeout=10)
            result = json.loads(resp.read().decode())
            ok = result.get('ok', False)
            if ok:
                chat_type = result.get('result', {}).get('type', 'unknown')
                log.info(f"Chat verified: {self.chat_id} (type: {chat_type})")
            else:
                log.warning(f"Chat {self.chat_id} invalid: {result.get('description', 'unknown')}")
            return ok
        except urllib.error.HTTPError as e:
            if e.code == 400:
                log.warning(f"Chat {self.chat_id} not found — send /start to @{BOT_USERNAME} first")
            else:
                log.warning(f"Chat verify HTTP {e.code}: {e}")
            return False
        except Exception as e:
            log.debug(f"Chat verify failed: {e}")
            return False
    
    def auto_discover_chat(self) -> Optional[str]:
        """Auto-discover chat_id from getUpdates if not configured."""
        cid = get_chat_id(self.bot_token)
        if cid:
            self.chat_id = cid
            os.environ['TELEGRAM_CHAT_ID'] = cid
            log.info(f"Auto-discovered chat_id: {cid}")
        return cid
    
    def get_updates(self) -> List[Dict[str, Any]]:
        if not self.is_configured:
            return []
        
        try:
            import urllib.request
            import urllib.parse
            
            params = urllib.parse.urlencode({
                'offset': self._offset,
                'timeout': 5,
                'allowed_updates': '["message", "callback_query"]'
            })
            
            url = f"{self.API_BASE}{self.bot_token}/getUpdates?{params}"
            req = urllib.request.Request(url)
            resp = urllib.request.urlopen(req, timeout=15)
            result = json.loads(resp.read().decode())
            
            if result.get('ok'):
                updates = result.get('result', [])
                if updates:
                    self._offset = updates[-1].get('update_id', 0) + 1
                return updates
            return []
        except Exception as e:
            log.debug(f"Telegram getUpdates failed: {e}")
            return []
    
    def send_document(self, file_path: str, caption: str = '') -> bool:
        if not self.is_configured:
            return False
        
        try:
            import urllib.request
            import urllib.parse
            
            boundary = '----OmniBrainBoundary'
            
            body = b''
            body += f'--{boundary}\r\n'.encode()
            body += f'Content-Disposition: form-data; name="chat_id"\r\n\r\n'.encode()
            body += f'{self.chat_id}\r\n'.encode()
            
            if caption:
                body += f'--{boundary}\r\n'.encode()
                body += f'Content-Disposition: form-data; name="caption"\r\n\r\n'.encode()
                body += f'{caption}\r\n'.encode()
            
            body += f'--{boundary}\r\n'.encode()
            body += f'Content-Disposition: form-data; name="document"; filename="{os.path.basename(file_path)}"\r\n'.encode()
            body += b'Content-Type: text/plain\r\n\r\n'
            
            with open(file_path, 'rb') as f:
                body += f.read()
            body += b'\r\n'
            body += f'--{boundary}--\r\n'.encode()
            
            url = f"{self.API_BASE}{self.bot_token}/sendDocument"
            req = urllib.request.Request(url, data=body)
            req.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')
            resp = urllib.request.urlopen(req, timeout=15)
            result = json.loads(resp.read().decode())
            return result.get('ok', False)
        except Exception as e:
            log.debug(f"Telegram sendDocument failed: {e}")
            return False

    def send_photo(self, photo_bytes: bytes, caption: str = '') -> bool:
        """Send a photo via sendPhoto API using multipart upload."""
        if not self.is_configured:
            return False
        try:
            import urllib.request
            boundary = '----OmniBrainPhotoBoundary'
            body = b''
            body += f'--{boundary}\r\n'.encode()
            body += f'Content-Disposition: form-data; name="chat_id"\r\n\r\n'.encode()
            body += f'{self.chat_id}\r\n'.encode()
            if caption:
                body += f'--{boundary}\r\n'.encode()
                body += f'Content-Disposition: form-data; name="caption"\r\n\r\n'.encode()
                body += f'{caption}\r\n'.encode()
            body += f'--{boundary}\r\n'.encode()
            body += b'Content-Disposition: form-data; name="photo"; filename="chart.png"\r\n'
            body += b'Content-Type: image/png\r\n\r\n'
            body += photo_bytes
            body += b'\r\n'
            body += f'--{boundary}--\r\n'.encode()
            url = f"{self.API_BASE}{self.bot_token}/sendPhoto"
            req = urllib.request.Request(url, data=body)
            req.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')
            resp = urllib.request.urlopen(req, timeout=30)
            result = json.loads(resp.read().decode())
            return result.get('ok', False)
        except Exception as e:
            log.debug(f"Telegram sendPhoto failed: {e}")
            return False

    def send_inline_keyboard(self, chat_id: str, text: str,
                              keyboard: List[List[Dict[str, str]]],
                              parse_mode: str = None) -> bool:
        if not self.is_configured:
            return False
        try:
            import urllib.request
            payload = {
                'chat_id': chat_id,
                'text': text,
                'reply_markup': {'inline_keyboard': keyboard},
            }
            if parse_mode:
                payload['parse_mode'] = parse_mode
            url = f"{self.API_BASE}{self.bot_token}/sendMessage"
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
            resp = urllib.request.urlopen(req, timeout=10)
            result = json.loads(resp.read().decode())
            return result.get('ok', False)
        except Exception as e:
            log.error(f"Inline keyboard send failed: {e}")
            return False

    def answer_callback_query(self, callback_query_id: str, text: str = '') -> bool:
        if not self.is_configured:
            return False
        try:
            import urllib.request
            payload = {'callback_query_id': callback_query_id}
            if text:
                payload['text'] = text
            url = f"{self.API_BASE}{self.bot_token}/answerCallbackQuery"
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
            resp = urllib.request.urlopen(req, timeout=10)
            result = json.loads(resp.read().decode())
            return result.get('ok', False)
        except Exception as e:
            log.error(f"Answer callback query failed: {e}")
            return False


# ══════════════════════════════════════════════════════════════════════════════
# C: SIGNAL ALERT SENDER
# ══════════════════════════════════════════════════════════════════════════════

class SignalAlertSender:
    """Format and send EXECUTE / WAIT / BLOCK alerts."""
    
    def __init__(self, bot: TelegramBot, rate_limiter: AlertRateLimiter):
        self.bot = bot
        self.rate_limiter = rate_limiter
        self.last_decision: Dict[str, str] = {}
    
    @staticmethod
    def _format_score_bar(score: int) -> str:
        filled = score // 10
        empty = 10 - filled
        return '\u2588' * filled + '\u2591' * empty
    
    @staticmethod
    def _format_mtf(mtf_data: Dict[str, str]) -> str:
        parts = []
        for tf in ['M15', 'H1', 'H4', 'D1']:
            bias = mtf_data.get(tf, 'NEUTRAL')
            if bias == 'BULLISH':
                parts.append(f"{tf}\u2191")
            elif bias == 'BEARISH':
                parts.append(f"{tf}\u2193")
            else:
                parts.append(f"{tf}\u2192")
        return ' '.join(parts)
    
    def _get_position_sizing(self, symbol: str, price: float, atr: float) -> Optional[Dict]:
        """Calculate position sizing via RiskManager."""
        try:
            sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
            sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'production'))
            from risk_manager import get_risk_manager
            rm = get_risk_manager()
            direction = 'BULLISH'
            sl = round(price - 1.5 * atr, 2) if direction == 'BULLISH' else round(price + 1.5 * atr, 2)
            ps = rm.calculate_position_size(symbol, price, sl, win_rate=0.55, rr=2.0)
            return ps
        except Exception:
            return None

    def _render_and_attach_chart(self, symbol: str, tf: str, direction: str, score: int,
                                   price: float, sl: float, tp1: float,
                                   fvg_zone: Optional[tuple] = None,
                                   ob_zone: Optional[tuple] = None) -> Optional[bytes]:
        """Attempt to render a chart and return PNG bytes."""
        try:
            sys.path.insert(0, str(Path(__file__).parent))
            from chart_renderer import render_signal_chart
            candles = getattr(self, '_last_candles', None)
            return render_signal_chart(
                symbol=symbol, tf=tf, direction=direction, score=score,
                candles=candles or [],
                fvg_zone=fvg_zone,
                ob_zone=ob_zone,
                entry_price=price,
                stop_loss=sl,
                take_profit=tp1,
            )
        except Exception as e:
            log.debug(f"Chart render skipped: {e}")
            return None

    def send_execute_alert(
        self, symbol: str, tf: str, score: int,
        components: Dict[str, int], mtf_data: Dict[str, str],
        threshold: int, cb_state: str,
        price: float, atr: float = 5.0,
        candles: List[Dict] = None,
        fvg_zone: Optional[tuple] = None,
        ob_zone: Optional[tuple] = None,
    ) -> bool:
        can_send, reason = self.rate_limiter.can_send('EXECUTE', symbol)
        if not can_send:
            log.info(f"EXECUTE alert blocked for {symbol}: {reason}")
            return False
        
        direction = 'BULLISH' if score >= 75 else 'BEARISH'
        
        entry = price
        sl = round(entry - 1.5 * atr, 2) if direction == 'BULLISH' else round(entry + 1.5 * atr, 2)
        tp1 = round(entry + 1.0 * atr, 2) if direction == 'BULLISH' else round(entry - 1.0 * atr, 2)
        tp2 = round(entry + 2.0 * atr, 2) if direction == 'BULLISH' else round(entry - 2.0 * atr, 2)
        tp3 = round(entry + 3.0 * atr, 2) if direction == 'BULLISH' else round(entry - 3.0 * atr, 2)
        
        bar = self._format_score_bar(score)
        mtf_str = self._format_mtf(mtf_data)
        
        ob_check = '\u2705' if components.get('OB', 0) > 0 else '\u274c'
        fvg_check = '\u2705' if components.get('FVG', 0) > 0 else '\u274c'
        sweep_check = '\u2705' if components.get('SWEEP', 0) > 0 else '\u274c'
        vwap_check = '\u2705' if components.get('VWAP', 0) > 0 else '\u274c'
        session_check = '\u2705' if components.get('SESSION', 0) > 0 else '\u274c'
        correlation_val = components.get('CORRELATION', 0)
        news_val = components.get('NEWS', 0)
        yield_val = components.get('YIELD', 0)
        sentiment_val = components.get('SENTIMENT', 0)
        pattern_val = components.get('PATTERN', 0)
        divergence_val = components.get('DIVERGENCE', 0)
        
        cb_emoji = '\U0001f7e2' if cb_state == 'ACTIVE' else '\U0001f7e1' if cb_state == 'THROTTLED' else '\U0001f534'
        
        now_utc = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
        
        extra_line = ''
        if pattern_val or divergence_val:
            extra_line = f"Pattern  : +{pattern_val} | Divergence: +{divergence_val}\n"
        if yield_val or sentiment_val or correlation_val or news_val:
            extra_line += f"Yield    : +{yield_val} | Sentiment: +{sentiment_val} | Corr: +{correlation_val} | News: {news_val}\n"
        
        # Risk position sizing
        pos_size = self._get_position_sizing(symbol, entry, atr)
        pos_line = ''
        if pos_size:
            pos_line = (
                f"\U0001f4b0 POSITION SIZE\n"
                f"Lots: {pos_size['recommended_lots']:.2f} ({pos_size['risk_percent']:.0f}% risk)\n"
                f"SL pips: {pos_size['sl_pips']:.1f}\n"
                f"Dollar risk: ${pos_size['dollar_risk']:.0f}\n"
                f"Kelly: {pos_size['kelly_lots']:.2f} lots\n"
                f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            )
        
        message = (
            f"\U0001f680 TRADE SIGNAL \u2014 EXECUTE\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"Asset    : {symbol}\n"
            f"TF       : {tf}\n"
            f"Signal   : {direction}\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"Score    : {score}/100 {bar}\n"
            f"OB       : {ob_check} +{components.get('OB', 0)}\n"
            f"FVG      : {fvg_check} +{components.get('FVG', 0)}\n"
            f"Sweep    : {sweep_check} +{components.get('SWEEP', 0)}\n"
            f"VWAP     : {vwap_check} +{components.get('VWAP', 0)}\n"
            f"Session  : {session_check} +{components.get('SESSION', 0)}\n"
            f"{extra_line}"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"MTF      : {mtf_str}\n"
            f"Threshold: {threshold} (adaptive)\n"
            f"CB State : {cb_emoji} {cb_state}\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"Entry    : {entry}\n"
            f"SL       : {sl}\n"
            f"TP1      : {tp1}\n"
            f"TP2      : {tp2}\n"
            f"TP3      : {tp3}\n"
            f"RR       : 1:2\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"{pos_line}"
            f"Time     : {now_utc}\n"
            f"Provider : Twelve Data\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"\u26a0\ufe0f Not financial advice. DYOR."
        )
        
        sent = self.bot.send_message(message)
        if sent:
            self.rate_limiter.record_alert('EXECUTE', symbol)
            self.last_decision[symbol] = 'EXECUTE'

        chart_bytes = self._render_and_attach_chart(
            symbol, tf, direction, score, price, sl, tp1,
            fvg_zone=fvg_zone, ob_zone=ob_zone,
        )
        if chart_bytes:
            chart_caption = f"{symbol} {tf} | {direction} | Score: {score}/100"
            self.bot.send_photo(chart_bytes, chart_caption)

        return sent
    
    def send_wait_alert(
        self, symbol: str, tf: str, score: int,
        block_reason: str = ''
    ) -> bool:
        can_send, reason = self.rate_limiter.can_send('WAIT', symbol)
        if not can_send:
            log.info(f"WAIT alert blocked for {symbol}: {reason}")
            return False
        
        now_utc = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
        missing = block_reason if block_reason else 'Threshold not met'
        
        message = (
            f"\u23f3 SIGNAL WATCH \u2014 WAIT\n"
            f"Asset: {symbol} | TF: {tf}\n"
            f"Score: {score}/100 | Missing: {missing}\n"
            f"Time: {now_utc}"
        )
        
        sent = self.bot.send_message(message)
        if sent:
            self.rate_limiter.record_alert('WAIT', symbol)
            self.last_decision[symbol] = 'WAIT'
        return sent
    
    def send_block_alert(
        self, symbol: str, tf: str, reason: str, resume_time: str = ''
    ) -> bool:
        prev = self.last_decision.get(symbol)
        if prev != 'EXECUTE':
            log.debug(f"BLOCK alert skipped for {symbol} (prev was {prev}, not EXECUTE)")
            return False
        
        now_utc = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
        resume_str = f"Resume: {resume_time}" if resume_time else "Resume: N/A"
        
        message = (
            f"\U0001f6ab SIGNAL BLOCKED\n"
            f"Asset: {symbol} | TF: {tf}\n"
            f"Reason: {reason}\n"
            f"{resume_str}"
        )
        
        sent = self.bot.send_message(message)
        if sent:
            self.last_decision[symbol] = 'BLOCK'
        return sent


# ══════════════════════════════════════════════════════════════════════════════
# D: SIGNAL OUTCOME TRACKER
# ══════════════════════════════════════════════════════════════════════════════

class SignalOutcomeTracker:
    """
    After each EXECUTE signal, track outcome at 1H, 4H, 24H.
    Uses live_feed_scanner Twelve Data API for price checks.
    """
    
    CHECK_INTERVALS = [
        (1, '1H'),
        (4, '4H'),
        (24, '24H')
    ]
    
    def __init__(self, bot: TelegramBot):
        self.bot = bot
        self.pending: List[Dict[str, Any]] = []
        self.outcomes: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._load_state()
    
    def _load_state(self) -> None:
        filepath = LOG_DIR / 'pending_outcomes.json'
        if filepath.exists():
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                self.pending = data.get('pending', [])
                self.outcomes = data.get('outcomes', [])
            except Exception:
                pass
    
    def _save_state(self) -> None:
        filepath = LOG_DIR / 'pending_outcomes.json'
        try:
            with open(filepath, 'w') as f:
                json.dump({
                    'pending': self.pending,
                    'outcomes': self.outcomes,
                    'last_updated': datetime.now(timezone.utc).isoformat()
                }, f, indent=2, default=str)
        except Exception as e:
            log.debug(f"Failed to save outcomes: {e}")
    
    def add_signal(
        self, symbol: str, tf: str, direction: str,
        entry_price: float, sl: float, tp1: float, score: int
    ) -> None:
        with self._lock:
            signal = {
                'symbol': symbol,
                'tf': tf,
                'direction': direction,
                'entry_price': entry_price,
                'sl': sl,
                'tp1': tp1,
                'score': score,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'signal_time': time.time(),
                'checks': {},
                'status': 'pending'
            }
            self.pending.append(signal)
            self._save_state()
            log.info(f"Outcome tracker: added {symbol}/{tf} signal at {entry_price}")
    
    def _fetch_current_price(self, symbol: str) -> Optional[float]:
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
            from live_feed_scanner import LiveFeedScanner
            scanner = LiveFeedScanner()
            symbol_map = {'XAUUSD': 'XAU/USD', 'EURUSD': 'EUR/USD', 'GBPUSD': 'GBP/USD', 'SP500': 'SPX'}
            td_symbol = symbol_map.get(symbol, symbol)
            
            import urllib.request
            api_key = os.environ.get('LIVE_DATA_API_KEY', '')
            if not api_key:
                return None
            
            url = f"https://api.twelvedata.com/price?symbol={td_symbol}&apikey={api_key}"
            req = urllib.request.Request(url)
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read().decode())
            return float(data.get('price', 0))
        except Exception as e:
            log.debug(f"Price fetch failed for {symbol}: {e}")
            return None
    
    def check_pending(self) -> None:
        with self._lock:
            now = time.time()
            still_pending = []
            
            for signal in self.pending:
                elapsed_hours = (now - signal['signal_time']) / 3600
                
                for interval_hours, interval_label in self.CHECK_INTERVALS:
                    if interval_label not in signal['checks'] and elapsed_hours >= interval_hours:
                        price = self._fetch_current_price(signal['symbol'])
                        if price is not None:
                            entry = signal['entry_price']
                            direction = signal['direction']
                            sl = signal['sl']
                            tp1 = signal['tp1']
                            
                            if direction in ('BULLISH', 'LONG', 'BUY'):
                                tp1_hit = price >= tp1
                                sl_hit = price <= sl
                            else:
                                tp1_hit = price <= tp1
                                sl_hit = price >= sl
                            
                            signal['checks'][interval_label] = {
                                'price': price,
                                'tp1_hit': tp1_hit,
                                'sl_hit': sl_hit,
                                'checked_at': datetime.now(timezone.utc).isoformat()
                            }
                
                all_checked = all(
                    label in signal['checks']
                    for _, label in self.CHECK_INTERVALS
                )
                
                if all_checked:
                    self._send_outcome(signal)
                    signal['status'] = 'completed'
                    self.outcomes.append(signal)
                else:
                    if elapsed_hours < 25:
                        still_pending.append(signal)
                    else:
                        signal['status'] = 'expired'
                        self.outcomes.append(signal)
            
            self.pending = still_pending
            self._save_state()
    
    def _send_outcome(self, signal: Dict[str, Any]) -> None:
        symbol = signal['symbol']
        tf = signal['tf']
        entry = signal['entry_price']
        score = signal['score']
        
        h1_check = signal['checks'].get('1H', {})
        h4_check = signal['checks'].get('4H', {})
        d1_check = signal['checks'].get('24H', {})
        
        if h1_check.get('tp1_hit'):
            result_emoji = '\u2705 TP1 HIT (+1R)'
        elif h1_check.get('sl_hit'):
            result_emoji = '\u274c SL HIT (-1R)'
        elif h4_check.get('tp1_hit'):
            result_emoji = '\u2705 TP1 HIT (+1R)'
        elif h4_check.get('sl_hit'):
            result_emoji = '\u274c SL HIT (-1R)'
        elif d1_check.get('tp1_hit'):
            result_emoji = '\u2705 TP1 HIT (+1R)'
        elif d1_check.get('sl_hit'):
            result_emoji = '\u274c SL HIT (-1R)'
        else:
            result_emoji = '\u2753 INDECISIVE'
        
        recent_outcomes = self.outcomes[-30:]
        wins = sum(1 for o in recent_outcomes if any(
            c.get('tp1_hit') for c in o.get('checks', {}).values()
        ))
        total = len(recent_outcomes) if recent_outcomes else 1
        accuracy = int(wins / total * 100) if total > 0 else 0
        
        h1_str = f"1H: {h1_check.get('price', '?')}"
        if h1_check.get('tp1_hit'):
            h1_str += " \u2705 Hit"
        elif h1_check.get('sl_hit'):
            h1_str += " \u274c Hit"
        
        h4_str = f"4H: {h4_check.get('price', '?')}"
        if h4_check.get('tp1_hit'):
            h4_str += " \u2705 Hit"
        elif h4_check.get('sl_hit'):
            h4_str += " \u274c Hit"
        
        d1_str = f"24H: {d1_check.get('price', '?')}"
        if d1_check.get('tp1_hit'):
            d1_str += " \u2705 Hit"
        elif d1_check.get('sl_hit'):
            d1_str += " \u274c Hit"
        
        message = (
            f"\U0001f4ca SIGNAL OUTCOME \u2014 {symbol} {tf}\n"
            f"Result  : {result_emoji}\n"
            f"Entry   : {entry}\n"
            f"{h1_str}\n"
            f"{h4_str}\n"
            f"{d1_str}\n"
            f"SL      : {signal['sl']} \u274c {'Hit' if h1_check.get('sl_hit') or h4_check.get('sl_hit') else 'Not hit'}\n"
            f"Score was: {score}/100\n"
            f"Accuracy: {accuracy}% (last {total} signals)"
        )
        
        self.bot.send_message(message)
    
    def get_accuracy(self, limit: int = 30) -> int:
        recent = self.outcomes[-limit:]
        if not recent:
            return 0
        wins = sum(1 for o in recent if any(
            c.get('tp1_hit') for c in o.get('checks', {}).values()
        ))
        return int(wins / len(recent) * 100)
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            'pending_count': len(self.pending),
            'completed_count': len(self.outcomes),
            'accuracy_30d': self.get_accuracy(30),
            'accuracy_7d': self.get_accuracy(7)
        }


# ══════════════════════════════════════════════════════════════════════════════
# F: TELEGRAM COMMAND HANDLER
# ══════════════════════════════════════════════════════════════════════════════

class CommandHandler:
    """Handle Telegram bot commands."""
    
    COMMANDS = ['/status', '/score', '/cb', '/pause', '/resume', '/report', '/backtest', '/help',
                '/dna', '/dna_history', '/rollback', '/evolution', '/fitness',
                '/apply_evolution', '/reject_evolution',
                '/levels', '/metrics', '/insight', '/ai',
                '/replay', '/calibrate', '/execution']
    
    def __init__(self, bot: TelegramBot):
        self.bot = bot
        self._callbacks: Dict[str, callable] = {}
        self._paused = False
        self._pause_until: Optional[float] = None
    
    def register_callback(self, command: str, callback: callable) -> None:
        self._callbacks[command] = callback
    
    def is_paused(self) -> bool:
        if self._paused and self._pause_until:
            if time.time() >= self._pause_until:
                self._paused = False
                self._pause_until = None
                return False
            return True
        return False
    
    def handle_update(self, update: Dict[str, Any]) -> None:
        message = update.get('message', {})
        text = message.get('text', '').strip()
        chat_id = str(message.get('chat', {}).get('id', ''))
        
        if not text or not text.startswith('/'):
            return
        
        parts = text.split()
        command = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []
        
        if command == '/start':
            self.bot.send_message(
                "\U0001f9e0 OMNI BRAIN V2 Bot\n\n"
                "Commands:\n"
                "/status \u2014 All asset scores\n"
                "/score XAUUSD \u2014 Detailed breakdown\n"
                "/levels \u2014 Institutional structure map\n"
                "/metrics \u2014 System performance stats\n"
                "/cb \u2014 Circuit breaker states\n"
                "/pause \u2014 Pause alerts 1 hour\n"
                "/resume \u2014 Resume alerts\n"
                "/report \u2014 Trigger daily report\n"
                "/backtest \u2014 Trigger backtest\n"
                "/dna \u2014 DNA evolution status\n"
                "/dna_history \u2014 All generations\n"
                "/rollback {N} \u2014 Rollback to gen N\n"
                "/evolution \u2014 Trigger evolution now\n"
                "/fitness \u2014 Current fitness score\n"
                "/apply_evolution \u2014 Apply AI suggestion\n"
                "/reject_evolution \u2014 Reject AI suggestion\n"
                "/insight \u2014 AI market insight & regime analysis\n"
                "/ai \u2014 AI Decision Engine current analysis\n"
                "/replay {id} \u2014 Replay a trade decision\n"
                "/calibrate \u2014 Confidence calibration stats\n"
                "/execution \u2014 Execution quality report\n"
                "/help \u2014 List all commands"
            )
            return
        
        if command == '/help':
            self.bot.send_message(
                "\U0001f4cb OMNI BRAIN V2 Commands\n\n"
                "/status \u2014 Show scores for all 4 assets\n"
                "/score XAUUSD \u2014 Detailed score breakdown\n"
                "/levels \u2014 Institutional structure map\n"
                "/metrics \u2014 System performance stats\n"
                "/insight \u2014 AI market insight & regime analysis\n"
                "/ai \u2014 AI Decision Engine analysis\n"
                "/replay {id} \u2014 Replay a trade decision\n"
                "/calibrate \u2014 Confidence calibration stats\n"
                "/execution \u2014 Execution quality report\n"
                "/cb \u2014 Circuit breaker states\n"
                "/pause \u2014 Pause all alerts 1 hour\n"
                "/resume \u2014 Resume alerts now\n"
                "/report \u2014 Trigger daily report now\n"
                "/backtest \u2014 Trigger backtest now\n"
                "/dna \u2014 DNA evolution summary\n"
                "/dna_history \u2014 Evolution history\n"
                "/rollback {N} \u2014 Rollback to gen N\n"
                "/evolution \u2014 Trigger evolution cycle\n"
                "/fitness \u2014 Current fitness score\n"
                "/apply_evolution \u2014 Apply AI suggestion\n"
                "/reject_evolution \u2014 Reject AI suggestion\n"
                "/help \u2014 Show this message"
            )
            return
        
        if command == '/pause':
            self._paused = True
            self._pause_until = time.time() + 3600
            self.bot.send_message("\u23f8\ufe0f Alerts paused for 1 hour.\n/use /resume to resume early.")
            return
        
        if command == '/resume':
            self._paused = False
            self._pause_until = None
            self.bot.send_message("\u25b6\ufe0f Alerts resumed.")
            return
        
        if command == '/status':
            callback = self._callbacks.get('/status')
            if callback:
                result = callback()
                self.bot.send_message(result)
            return
        
        if command == '/score' and args:
            symbol = args[0].upper()
            callback = self._callbacks.get('/score')
            if callback:
                result = callback(symbol)
                self.bot.send_message(result)
            return
        
        if command == '/cb':
            callback = self._callbacks.get('/cb')
            if callback:
                result = callback()
                self.bot.send_message(result)
            return
        
        if command == '/report':
            callback = self._callbacks.get('/report')
            if callback:
                result = callback()
                self.bot.send_message(result)
            return
        
        if command == '/backtest':
            callback = self._callbacks.get('/backtest')
            if callback:
                result = callback()
                self.bot.send_message(result)
            return

        if command == '/levels':
            callback = self._callbacks.get('/levels')
            if callback:
                result = callback()
                if isinstance(result, tuple) and len(result) == 2:
                    text, photo = result
                    if photo:
                        self.bot.send_photo(photo, text)
                    else:
                        self.bot.send_message(text)
                else:
                    self.bot.send_message(str(result))
            else:
                self.bot.send_message("Levels system not initialized. Use /status for asset scores.")
            return

        if command == '/metrics':
            callback = self._callbacks.get('/metrics')
            if callback:
                result = callback()
                self.bot.send_message(result)
            return

        if command == '/insight':
            callback = self._callbacks.get('/insight')
            if callback:
                result = callback()
                self.bot.send_message(result)
            return

        if command == '/ai':
            callback = self._callbacks.get('/ai')
            if callback:
                result = callback()
                self.bot.send_message(result)
            return

        if command == '/calibrate':
            callback = self._callbacks.get('/calibrate')
            if callback:
                result = callback()
                self.bot.send_message(result)
            return

        if command == '/execution':
            callback = self._callbacks.get('/execution')
            if callback:
                result = callback()
                self.bot.send_message(result)
            return

        if command == '/replay' and args:
            callback = self._callbacks.get('/replay')
            if callback:
                try:
                    trade_id = args[0]
                    result = callback(trade_id)
                    self.bot.send_message(result)
                except Exception as e:
                    self.bot.send_message(f"Replay error: {e}")
            return

        if command in ('/dna', '/dna_status'):
            callback = self._callbacks.get('/dna')
            if callback:
                result = callback()
                self.bot.send_message(result)
            return
        
        if command == '/dna_history':
            callback = self._callbacks.get('/dna_history')
            if callback:
                result = callback()
                self.bot.send_message(result)
            return
        
        if command == '/rollback' and args:
            try:
                gen = int(args[0])
                callback = self._callbacks.get('/rollback')
                if callback:
                    result = callback(gen)
                    self.bot.send_message(result)
            except ValueError:
                self.bot.send_message("Usage: /rollback {generation_number}")
            return
        
        if command == '/evolution':
            callback = self._callbacks.get('/evolution')
            if callback:
                result = callback()
                self.bot.send_message(result)
            return
        
        if command == '/fitness':
            callback = self._callbacks.get('/fitness')
            if callback:
                result = callback()
                self.bot.send_message(result)
            return
        
        if command == '/apply_evolution':
            callback = self._callbacks.get('/apply_evolution')
            if callback:
                result = callback()
                self.bot.send_message(result)
            return
        
        if command == '/reject_evolution':
            callback = self._callbacks.get('/reject_evolution')
            if callback:
                result = callback()
                self.bot.send_message(result)
            return
        
        self.bot.send_message(f"Unknown command: {command}\nUse /help for commands.")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN SERVICE
# ══════════════════════════════════════════════════════════════════════════════

class TelegramSignalService:
    """Main Telegram signal service orchestrator."""
    
    def __init__(self):
        self.bot = TelegramBot()
        self.rate_limiter = AlertRateLimiter()
        self.alert_sender = SignalAlertSender(self.bot, self.rate_limiter)
        self.outcome_tracker = SignalOutcomeTracker(self.bot)
        self.command_handler = CommandHandler(self.bot)
        
        self._running = False
        self._poll_thread: Optional[threading.Thread] = None
        self._outcome_thread: Optional[threading.Thread] = None
        self._command_thread: Optional[threading.Thread] = None
        
        self._register_commands()
    
    def _register_commands(self) -> None:
        self.command_handler.register_callback('/status', self._cmd_status)
        self.command_handler.register_callback('/score', self._cmd_score)
        self.command_handler.register_callback('/cb', self._cmd_cb)
        self.command_handler.register_callback('/report', self._cmd_report)
        self.command_handler.register_callback('/backtest', self._cmd_backtest)
        self.command_handler.register_callback('/dna', self._cmd_dna)
        self.command_handler.register_callback('/dna_history', self._cmd_dna_history)
        self.command_handler.register_callback('/rollback', self._cmd_rollback)
        self.command_handler.register_callback('/evolution', self._cmd_evolution)
        self.command_handler.register_callback('/fitness', self._cmd_fitness)
        self.command_handler.register_callback('/apply_evolution', self._cmd_apply_evolution)
        self.command_handler.register_callback('/reject_evolution', self._cmd_reject_evolution)
        self.command_handler.register_callback('/insight', self._cmd_insight)
        self.command_handler.register_callback('/ai', self._cmd_ai)
        self.command_handler.register_callback('/calibrate', self._cmd_calibrate)
        self.command_handler.register_callback('/execution', self._cmd_execution)
        self.command_handler.register_callback('/replay', self._cmd_replay)
    
    def _cmd_status(self) -> str:
        try:
            sys.path.insert(0, os.path.dirname(__file__))
            from confidence_scorer import get_scorer
            from adaptive_threshold import get_threshold_engine
            
            scorer = get_scorer()
            threshold_engine = get_threshold_engine()
            lines = ["\U0001f4ca OMNI BRAIN V2 \u2014 LIVE SCORES\n"]
            
            for asset in ASSETS:
                result = scorer.score(symbol=asset, tf='H1')
                threshold = threshold_engine.get_threshold(asset)
                emoji = '\U0001f7e2' if result.decision == 'EXECUTE' else '\U0001f7e1' if result.decision == 'WAIT' else '\U0001f534'
                bar = '\u2588' * (result.score // 10) + '\u2591' * (10 - result.score // 10)
                lines.append(f"{asset:<8} {bar} {result.score}/100 {emoji} {result.decision} (th:{threshold})")
            
            lines.append(f"\nOutcome accuracy: {self.outcome_tracker.get_accuracy()}%")
            return '\n'.join(lines)
        except Exception as e:
            return f"Error: {e}"
    
    def _cmd_score(self, symbol: str) -> str:
        try:
            sys.path.insert(0, os.path.dirname(__file__))
            from confidence_scorer import get_scorer
            from adaptive_threshold import get_threshold_engine
            from circuit_breaker import get_circuit_breaker
            
            scorer = get_scorer()
            threshold_engine = get_threshold_engine()
            cb = get_circuit_breaker()
            
            result = scorer.score(symbol=symbol, tf='H1')
            threshold = threshold_engine.get_threshold(symbol)
            cb_state = cb.get_state(symbol).value
            stats = threshold_engine.get_stats(symbol)
            
            lines = [
                f"\U0001f50d {symbol} SCORE BREAKDOWN\n",
                f"Score   : {result.score}/100",
                f"Decision: {result.decision}",
                f"Thresh. : {threshold}",
                f"CB State: {cb_state}",
                f"\nComponents:"
            ]
            
            max_pts_map = {'OB': 20, 'FVG': 20, 'SWEEP': 30, 'VWAP': 15, 'SESSION': 15,
                           'CORRELATION': 15, 'NEWS': 0, 'YIELD': 10, 'SENTIMENT': 10,
                           'PATTERN': 20, 'DIVERGENCE': 20}
            for comp, pts in result.components.items():
                max_pts = max_pts_map.get(comp, 0)
                filled = pts // (max_pts // 5) if max_pts > 0 else 0
                bar = '\u2588' * filled + '\u2591' * (5 - filled)
                lines.append(f"  {comp:<12} {bar} {pts}/{max_pts}")
            
            lines.extend([
                f"\nHistory:",
                f"  Trades : {stats['total_trades']}",
                f"  Wins   : {stats['wins']}",
                f"  Losses : {stats['losses']}",
                f"  Win%   : {stats['win_rate']:.0f}%"
            ])
            
            return '\n'.join(lines)
        except Exception as e:
            return f"Error: {e}"
    
    def _cmd_cb(self) -> str:
        try:
            sys.path.insert(0, os.path.dirname(__file__))
            from circuit_breaker import get_circuit_breaker
            
            cb = get_circuit_breaker()
            states = cb.get_all_states()
            lines = ["\u26a1 CIRCUIT BREAKER STATES\n"]
            
            for asset in ASSETS:
                state = states.get(asset, {})
                status = state.get('state', 'ACTIVE')
                emoji = '\U0001f7e2' if status == 'ACTIVE' else '\U0001f7e1' if status == 'THROTTLED' else '\U0001f534'
                remaining = state.get('remaining_pause', 0)
                extra = f" ({remaining//60}min left)" if remaining and remaining > 0 else ""
                reason = f" [{state.get('reason', '')}]" if state.get('reason') else ""
                lines.append(f"{asset:<8} {emoji} {status}{reason}{extra}")
            
            return '\n'.join(lines)
        except Exception as e:
            return f"Error: {e}"
    
    def _cmd_report(self) -> str:
        try:
            sys.path.insert(0, os.path.dirname(__file__))
            from daily_report import DailyReport
            report = DailyReport()
            report_text = report.generate()
            report.send_telegram(report_text)
            return "\u2705 Daily report generated and sent."
        except Exception as e:
            return f"Report generation failed: {e}"
    
    def _cmd_backtest(self) -> str:
        try:
            sys.path.insert(0, os.path.dirname(__file__))
            from auto_backtester import AutoBacktester
            bt = AutoBacktester()
            bt.run()
            return "\u2705 Backtest completed and report sent."
        except Exception as e:
            return f"Backtest failed: {e}"
    
    def _cmd_dna(self) -> str:
        try:
            from prompt_evolution import get_dna
            dna = get_dna()
            return dna.get_summary()
        except Exception as e:
            return f"DNA error: {e}"

    def _cmd_dna_history(self) -> str:
        try:
            from prompt_evolution import get_dna
            dna = get_dna()
            history = dna.get_history()
            lines = ["🧬 DNA EVOLUTION HISTORY", "────────────────────"]
            for h in history[-15:]:
                gen = h.get('generation', '?')
                fit = h.get('fitness_score', '?')
                comp = h.get('component', '?')
                muts = len(h.get('mutations', []))
                lines.append(f"Gen {gen} | {comp} | fitness={fit} | {muts} mutations")
            return '\n'.join(lines)
        except Exception as e:
            return f"History error: {e}"

    def _cmd_rollback(self, generation: int) -> str:
        try:
            from prompt_evolution import get_dna
            dna = get_dna()
            results = dna.rollback_all(generation)
            ok = sum(1 for v in results.values() if v)
            fail = sum(1 for v in results.values() if not v)
            return f"Rollback to gen {generation}: {ok} OK, {fail} FAILED"
        except Exception as e:
            return f"Rollback error: {e}"

    def _cmd_evolution(self) -> str:
        try:
            from prompt_evolution import get_evolution_scheduler
            scheduler = get_evolution_scheduler()
            report = scheduler.run_micro_evolution(force=True)
            return scheduler.format_evolution_report(report)
        except Exception as e:
            return f"Evolution error: {e}"

    def _cmd_fitness(self) -> str:
        try:
            from fitness_evaluator import get_fitness_evaluator
            evaluator = get_fitness_evaluator()
            detail = evaluator.get_detailed()
            lines = [
                "📊 FITNESS SCORE",
                f"Overall: {detail['fitness']} ({detail['classification']})",
                f"Signals: {detail['signal_count']} | Execute: {detail['execute_count']}",
                "────────────────────",
            ]
            for k, v in detail['components'].items():
                lines.append(f"{k}: {v['value']} × {v['weight']} = {v['contribution']}")
            return '\n'.join(lines)
        except Exception as e:
            return f"Fitness error: {e}"

    def _cmd_apply_evolution(self) -> str:
        try:
            from ai_evolution_engine import get_ai_evolution_engine
            engine = get_ai_evolution_engine()
            results = engine.apply_suggestion()
            if results.get('success'):
                return "✅ AI evolution applied successfully"
            return f"❌ Apply failed: {results.get('error', 'unknown')}"
        except Exception as e:
            return f"Apply error: {e}"

    def _cmd_reject_evolution(self) -> str:
        try:
            from ai_evolution_engine import get_ai_evolution_engine
            engine = get_ai_evolution_engine()
            engine.reject_suggestion()
            return "❌ AI evolution rejected"
        except Exception as e:
            return f"Reject error: {e}"

    def _cmd_insight(self) -> str:
        try:
            sys.path.insert(0, str(Path(__file__).parent))
            from regime_detector import get_regime_detector
            from dashboard_bridge import get_bridge
            from confidence_scorer import get_scorer

            rd = get_regime_detector()
            bridge = get_bridge()
            scorer = get_scorer()

            metrics = rd.get_metrics()
            regime = metrics.get('regime', 'UNKNOWN')
            risk_mult = metrics.get('risk_multiplier', 0.5)
            half_life = metrics.get('half_life_mins', 30)

            asset_states = {}
            for asset in ASSETS:
                r = scorer.score(symbol=asset, tf='H1')
                asset_states[asset] = {
                    'score': r.score, 'decision': r.decision,
                    'regime': regime, 'signal_strength': f'{r.score}%',
                    'liquidity_tier': 'LOW', 'execution_grade': 'N/A',
                    'direction': 'NEUTRAL',
                }

            state = bridge.build_state(asset_states)
            insight_prompt = bridge.get_insight_prompt()

            lines = [
                "\U0001f9e0 OMNI BRAIN V2 \u2014 MARKET INSIGHT",
                "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501",
                f"Regime: {regime}",
                f"Risk Mult: {risk_mult:.1f}x",
                f"Signal HL: {half_life}min",
                "",
                "Assets:",
            ]

            for sym, info in asset_states.items():
                emoji = '\U0001f7e2' if info['decision'] == 'EXECUTE' else '\U0001f7e1' if info['decision'] == 'WAIT' else '\U0001f534'
                lines.append(f"  {sym:<8} {emoji} {info['score']}/100 {info['decision']}")

            lines.extend([
                "",
                "\U0001f4a1 Insight Prompt (for AI analysis):",
                insight_prompt[:1024],
            ])

            return '\n'.join(lines)
        except Exception as e:
            return f"Insight unavailable: {e}"

    def _cmd_ai(self) -> str:
        try:
            sys.path.insert(0, str(Path(__file__).parent))
            from ai_decision_engine import get_decision_engine
            de = get_decision_engine()
            result = de.get_latest_analysis()
            if not result:
                return "No AI analysis yet. Run a pipeline scan first."
            lines = [
                "\U0001f916 OMNI AI DECISION ENGINE",
                "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501",
                f"Action: {result.get('action', 'N/A')}",
                f"Confidence: {result.get('confidence', 0):.1f}%",
                f"Buy Prob: {result.get('buy_probability', 0):.1f}%",
                f"Sell Prob: {result.get('sell_probability', 0):.1f}%",
                f"Expected RR: {result.get('expected_rr', 0):.2f}",
                f"Invalidity: {result.get('invalidity_level', 0):.1f}%",
            ]
            traps = result.get('trap_analysis')
            if traps:
                lines.append(f"Trap Prob: {traps.get('trap_probability', 0):.1f}%")
            risk = result.get('risk')
            if risk:
                tier = risk.get('tier', risk.get('position_tier', 'N/A'))
                units = risk.get('suggested_units', risk.get('units', 0))
                lines.append(f"Risk Tier: {tier}")
                lines.append(f"Size: {units} units")
            flow = result.get('orderflow_analysis')
            if flow:
                pressure = flow.get('institutional_pressure', flow.get('score', 0))
                lines.append(f"Order Flow Pressure: {pressure:.1f}")
            return '\n'.join(lines)
        except Exception as e:
            return f"AI analysis unavailable: {e}"

    def _cmd_calibrate(self) -> str:
        try:
            sys.path.insert(0, str(Path(__file__).parent))
            from adaptive_confidence import get_calibrator
            c = get_calibrator()
            last = c.get_last_calibration()
            trades = c.get_trade_count()
            if not last:
                return f"No calibration data yet ({trades} trades recorded)."
            lines = [
                "\U0001f4ca CONFIDENCE CALIBRATION",
                "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501",
                f"Raw Confidence: {last.get('raw', 0)}%",
                f"Calibrated: {last.get('calibrated', 0)}%",
                f"Adjustment: {last.get('adjustment', 0):+.1f}%",
                f"Reason: {last.get('reason', '')}",
                f"Trade Count: {trades}",
            ]
            comps = last.get('components', {})
            if comps:
                lines.append("")
                lines.append("Components:")
                for k, v in comps.items():
                    if isinstance(v, dict):
                        lines.append(f"  {k}: {v.get('count', 0)} trades, "
                                     f"WR={v.get('win_rate', 0)*100:.0f}%")
                    elif abs(v) >= 0.5:
                        lines.append(f"  {k}: {v:+.1f}")
            return '\n'.join(lines)
        except Exception as e:
            return f"Calibration unavailable: {e}"

    def _cmd_execution(self) -> str:
        try:
            sys.path.insert(0, str(Path(__file__).parent))
            from execution_quality import get_execution_analyzer
            ea = get_execution_analyzer()
            result = ea.analyze('XAUUSD')
            lines = [
                "\U0001f4f6 EXECUTION QUALITY",
                "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501",
                f"Score: {result.get('score', 0)}/100",
                f"Samples: {result.get('samples', 0)}",
                f"Status: {'GOOD' if not result.get('warn') else 'WARN' if not result.get('block') else 'BLOCKED'}",
                f"Trend: {result.get('trend', 'stable')}",
            ]
            comps = result.get('components', {})
            if comps:
                lines.append("")
                lines.append("Components:")
                for k, v in comps.items():
                    lines.append(f"  {k}: {v}/100")
            if result.get('reason'):
                lines.append(f"\nNote: {result.get('reason')}")
            return '\n'.join(lines)
        except Exception as e:
            return f"Execution quality unavailable: {e}"

    def _cmd_replay(self, trade_id: str = '') -> str:
        try:
            sys.path.insert(0, str(Path(__file__).parent))
            from trade_replay import get_trade_replay
            tr = get_trade_replay()
            if not trade_id:
                recent = tr.get_recent(5)
                if not recent:
                    return "No recorded trades."
                lines = ["\U0001f4cb RECENT TRADES", "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"]
                for r in recent:
                    lines.append(f"  {r.get('trade_id', 'N/A')}: {r.get('action')} "
                                 f"@ {r.get('price', 0)} ({r.get('confidence', 0)}%)")
                lines.append("\nUse /replay {id} to replay a trade")
                return '\n'.join(lines)
            replay = tr.replay(trade_id)
            if not replay:
                expl = tr.explain(trade_id)
                if expl:
                    return expl.get('explanation', 'Trade found but replay unavailable.')
                return f"Trade {trade_id} not found."
            lines = [
                f"\U0001f4cb TRADE REPLAY: {trade_id}",
                "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501",
            ]
            for step in replay.get('steps', []):
                lines.append(f"[{step['step']}] {step['name']}")
                lines.append(f"    {step['data']}")
            return '\n'.join(lines)
        except Exception as e:
            return f"Replay unavailable: {e}"

    def send_signal(
        self, symbol: str, tf: str, decision: str, score: int,
        components: Dict[str, int], mtf_data: Dict[str, str],
        threshold: int, cb_state: str,
        price: float, atr: float = 5.0,
        candles: List[Dict] = None,
    ) -> bool:
        if self.command_handler.is_paused():
            log.info(f"Alert paused, skipping {symbol} {decision}")
            return False
        
        if decision == 'EXECUTE':
            self.alert_sender._last_candles = candles
            sent = self.alert_sender.send_execute_alert(
                symbol, tf, score, components, mtf_data,
                threshold, cb_state, price, atr, candles=candles,
            )
            if sent:
                direction = 'BULLISH' if score >= 75 else 'BEARISH'
                sl = round(price - 1.5 * atr, 2) if direction == 'BULLISH' else round(price + 1.5 * atr, 2)
                tp1 = round(price + 1.0 * atr, 2) if direction == 'BULLISH' else round(price - 1.0 * atr, 2)
                self.outcome_tracker.add_signal(symbol, tf, direction, price, sl, tp1, score)
            return sent
        elif decision == 'WAIT' and score >= 65:
            return self.alert_sender.send_wait_alert(symbol, tf, score)
        elif decision in ('BLOCK', 'BLOCKED_CB'):
            return self.alert_sender.send_block_alert(symbol, tf, cb_state)
        return False
    
    def _poll_commands(self) -> None:
        while self._running:
            try:
                updates = self.bot.get_updates()
                for update in updates:
                    self.command_handler.handle_update(update)
            except Exception as e:
                log.debug(f"Command poll error: {e}")
            time.sleep(5)
    
    def _check_outcomes(self) -> None:
        while self._running:
            try:
                self.outcome_tracker.check_pending()
            except Exception as e:
                log.debug(f"Outcome check error: {e}")
            time.sleep(300)
    
    def start(self) -> None:
        if not self.bot.is_configured:
            log.warning("Telegram not configured (missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID)")
            return
        
        self._running = True
        self._command_thread = threading.Thread(target=self._poll_commands, daemon=True)
        self._command_thread.start()
        
        self._outcome_thread = threading.Thread(target=self._check_outcomes, daemon=True)
        self._outcome_thread.start()

        self._weekly_thread = threading.Thread(target=self._weekly_summary_loop, daemon=True)
        self._weekly_thread.start()

        self._register_upgrade_callbacks()
        
        log.info("Telegram signal service started")
    
    def stop(self) -> None:
        self._running = False
        log.info("Telegram signal service stopped")
    
    def _weekly_summary_loop(self) -> None:
        """Check every 60 minutes if it's Sunday evening to send weekly summary."""
        while self._running:
            try:
                now = datetime.now(timezone.utc)
                # Sunday evening (UTC 18:00-20:00)
                if now.weekday() == 6 and 18 <= now.hour <= 20:
                    sys.path.insert(0, str(Path(__file__).parent))
                    from content_logger import get_content_logger
                    logger = get_content_logger()
                    summary = logger.build_weekly_summary()
                    self.bot.send_message(summary)
                    log.info("Weekly summary sent")
                    # Sleep 24h to avoid re-sending on same Sunday
                    time.sleep(86400)
                else:
                    time.sleep(3600)
            except Exception as e:
                log.debug(f"Weekly summary check failed: {e}")
                time.sleep(3600)
    
    def _register_upgrade_callbacks(self) -> None:
        """Register callbacks for /levels and /metrics commands."""
        try:
            sys.path.insert(0, str(Path(__file__).parent))
            from smc_analyzer import get_analyzer
            from content_logger import get_content_logger
            from paper_trader import get_paper_trader

            def levels_callback():
                analyzer = get_analyzer()
                current_price = 0.0
                try:
                    import urllib.request, json as j
                    api_key = os.environ.get('LIVE_DATA_API_KEY', '')
                    if api_key:
                        url = f"https://api.twelvedata.com/price?symbol=XAU/USD&apikey={api_key}"
                        resp = urllib.request.urlopen(url, timeout=5)
                        data = j.loads(resp.read().decode())
                        current_price = float(data.get('price', 0))
                except Exception:
                    pass

                text = analyzer.get_levels_table(current_price)

                chart_bytes = None
                try:
                    if current_price:
                        from chart_renderer import render_structure_chart
                        chart_bytes = render_structure_chart('XAUUSD', 'H1', analyzer._levels, current_price)
                except Exception:
                    pass

                return (text, chart_bytes) if chart_bytes else (text, None)

            def metrics_callback():
                try:
                    from smc_analyzer import get_analyzer
                    from content_logger import get_content_logger
                    analyzer = get_analyzer()
                    content = get_content_logger()
                    pt = get_paper_trader()
                    
                    smc_metrics = analyzer.get_metrics()
                    outcome_stats = self.outcome_tracker.get_stats() if self.outcome_tracker else {}
                    paper_balance = 10000.0
                    paper_trades = 0
                    try:
                        paper_trades = len(pt.trades) if hasattr(pt, 'trades') else 0
                        if hasattr(pt, 'balance'):
                            paper_balance = pt.balance
                    except Exception:
                        pass
                    wins = content.get_recent_wins(7) if content else []
                    
                    return (
                        "\U0001f4ca SYSTEM METRICS\n"
                        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
                        f"SMC:\n"
                        f"  FVGs tracked: {smc_metrics.get('fvgs_tracked', 0)}\n"
                        f"  FVGs filled: {smc_metrics.get('fvgs_filled', 0)}\n"
                        f"  OBs active: {smc_metrics.get('obs_tracked', 0)}\n"
                        f"  OBs mitigated: {smc_metrics.get('obs_mitigated', 0)}\n"
                        f"  Swings mapped: {smc_metrics.get('swings_mapped', 0)}\n"
                        f"  Chaser: {smc_metrics.get('chaser_active', 'NONE')}\n"
                        f"\nOutcomes:\n"
                        f"  Pending: {outcome_stats.get('pending_count', 0)}\n"
                        f"  Completed: {outcome_stats.get('completed_count', 0)}\n"
                        f"  Accuracy (30d): {outcome_stats.get('accuracy_30d', 0)}%\n"
                        f"\nPaper Trader:\n"
                        f"  Balance: ${paper_balance:.2f}\n"
                        f"  Trades: {paper_trades}\n"
                        f"\nContent:\n"
                        f"  Wins this week: {len(wins)}\n"
                        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
                    )
                except Exception as e:
                    return f"Metrics unavailable: {e}"

            self.command_handler.register_callback('/levels', levels_callback)
            self.command_handler.register_callback('/metrics', metrics_callback)
            log.info("Upgrade callbacks registered: /levels, /metrics")
        except Exception as e:
            log.debug(f"Upgrade callback registration failed: {e}")

    def send_startup_message(self) -> None:
        now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
        self.bot.send_message(
            f"\U0001f7e2 OMNI BRAIN V2 STARTED\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"Time: {now}\n"
            f"Processes: 5 online\n"
            f"Assets: {', '.join(ASSETS)}\n"
            f"Status: All systems operational\n"
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
            f"Commands: /help /status /dna"
        )
    
    def send_shutdown_message(self) -> None:
        now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
        self.bot.send_message(
            f"\U0001f6ab OMNI BRAIN V2 \u2014 OFFLINE\n"
            f"Time: {now}\n"
            f"System shutting down."
        )


# ══════════════════════════════════════════════════════════════════════════════
# GLOBAL INSTANCE
# ══════════════════════════════════════════════════════════════════════════════

_service: Optional[TelegramSignalService] = None


def get_telegram_service() -> TelegramSignalService:
    global _service
    if _service is None:
        _service = TelegramSignalService()
    return _service


def send_signal_alert(
    symbol: str, tf: str, decision: str, score: int,
    components: Dict[str, int] = None, mtf_data: Dict[str, str] = None,
    threshold: int = 75, cb_state: str = 'ACTIVE',
    price: float = 0.0, atr: float = 5.0
) -> bool:
    service = get_telegram_service()
    return service.send_signal(
        symbol, tf, decision, score,
        components or {}, mtf_data or {},
        threshold, cb_state, price, atr
    )


# ══════════════════════════════════════════════════════════════════════════════
# G: TELEGRAM SIGNAL BOT (LANGUAGE SUPPORT)
# ══════════════════════════════════════════════════════════════════════════════

class TelegramSignalBot:
    """Handle Telegram /language, /setlang, /help with 32-language support."""

    LANG_ROWS = [
        ['hi', 'te', 'ta', 'kn'],
        ['ml', 'mr', 'gu', 'pa'],
        ['bn', 'or', 'as', 'ur'],
        ['en', 'ar', 'id', 'ms'],
        ['tr', 'ru', 'pt', 'es'],
        ['fr', 'de', 'zh', 'ja'],
        ['ko', 'th', 'vi', 'sw'],
        ['fa', 'nl', 'pl', 'it'],
    ]

    def __init__(self, bot: TelegramBot):
        self.bot = bot
        self.subs_mgr = None
        self.engine = None

    def _get_subs_mgr(self):
        if self.subs_mgr is None:
            from subscription_manager import get_subscription_manager
            self.subs_mgr = get_subscription_manager()
        return self.subs_mgr

    def _get_engine(self):
        if self.engine is None:
            sys.path.insert(0, str(Path(__file__).parent.parent))
            from content.multilingual_engine import get_engine
            self.engine = get_engine()
        return self.engine

    def _build_language_keyboard(self) -> List[List[Dict[str, str]]]:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from content.multilingual_engine import LANGUAGES
        keyboard = []
        for row in self.LANG_ROWS:
            buttons = []
            for code in row:
                meta = LANGUAGES.get(code, {})
                label = f"{meta.get('flag', '')} {meta.get('name', code)}"
                buttons.append({'text': label, 'callback_data': f'lang_{code}'})
            keyboard.append(buttons)
        return keyboard

    def handle_language_command(self, chat_id: str) -> bool:
        keyboard = self._build_language_keyboard()
        return self.bot.send_inline_keyboard(
            chat_id,
            "\U0001f310 Select your language / अपनी भाषा चुनें",
            keyboard
        )

    def handle_setlang_command(self, chat_id: str, lang_code: str) -> bool:
        engine = self._get_engine()
        mgr = self._get_subs_mgr()
        mgr.set_language(chat_id, lang_code)
        confirmation = engine.get_confirmation(lang_code)
        return self.bot.send_message(confirmation)

    def handle_help_command(self, chat_id: str) -> bool:
        mgr = self._get_subs_mgr()
        lang = mgr.get_language(chat_id)
        engine = self._get_engine()
        help_text = engine.get_bot_help(lang)
        return self.bot.send_message(help_text)

    def handle_status_command(self, chat_id: str) -> bool:
        mgr = self._get_subs_mgr()
        lang = mgr.get_language(chat_id)
        engine = self._get_engine()
        dir_bull = engine.translate_direction('BULLISH', lang)
        dir_bear = engine.translate_direction('BEARISH', lang)
        status_text = (
            f"\U0001f4ca OMNI BRAIN V2 \u2014 LIVE\n"
            f"Status: All systems operational\n"
            f"BULLISH: {dir_bull}\n"
            f"BEARISH: {dir_bear}\n"
            f"Language: {lang}\n"
            f"Use /language to change language"
        )
        return self.bot.send_message(status_text)

    def handle_unknown_command(self, chat_id: str) -> bool:
        mgr = self._get_subs_mgr()
        lang = mgr.get_language(chat_id)
        engine = self._get_engine()
        error_text = engine.get_error_message(lang)
        return self.bot.send_message(error_text)

    def handle_callback_query(self, callback_data: str, chat_id: str,
                               callback_query_id: str) -> bool:
        if callback_data.startswith('lang_'):
            lang_code = callback_data.split('_', 1)[1]
            self.handle_setlang_command(chat_id, lang_code)
            self.bot.answer_callback_query(callback_query_id,
                                            f"Language set to {lang_code}")
            return True
        return False

    def process_update(self, update: Dict[str, Any]) -> None:
        if 'callback_query' in update:
            cq = update['callback_query']
            chat_id = str(cq.get('message', {}).get('chat', {}).get('id', ''))
            callback_data = cq.get('data', '')
            cq_id = cq.get('id', '')
            self.handle_callback_query(callback_data, chat_id, cq_id)
            return

        message = update.get('message', {})
        text = message.get('text', '').strip()
        chat_id = str(message.get('chat', {}).get('id', ''))

        if not text or not text.startswith('/'):
            return

        parts = text.split()
        command = parts[0].lower()

        if command == '/language':
            self.handle_language_command(chat_id)
        elif command == '/setlang' and len(parts) >= 2:
            self.handle_setlang_command(chat_id, parts[1])
        elif command == '/help':
            self.handle_help_command(chat_id)
        elif command == '/status':
            self.handle_status_command(chat_id)
        elif command in ('/start',):
            self.handle_help_command(chat_id)
        elif command.startswith('/'):
            self.handle_unknown_command(chat_id)


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import sys
    
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    
    if '--test' in sys.argv:
        print("=" * 60)
        print("  TELEGRAM SIGNALS - TEST")
        print("=" * 60)
        
        bot = TelegramBot()
        print(f"\n  Telegram configured: {bot.is_configured}")
        
        rl = AlertRateLimiter()
        can, reason = rl.can_send('EXECUTE', 'XAUUSD')
        print(f"  Can send EXECUTE: {can} ({reason})")
        
        rl.record_alert('EXECUTE', 'XAUUSD')
        can, reason = rl.can_send('EXECUTE', 'XAUUSD')
        print(f"  After record: can_send={can} ({reason})")
        
        quiet = rl.is_quiet_hours()
        print(f"  Quiet hours: {quiet}")
        
        sender = SignalAlertSender(bot, rl)
        print(f"  Score bar: {sender._format_score_bar(85)}")
        print(f"  MTF format: {sender._format_mtf({'M15': 'BULLISH', 'H1': 'BULLISH', 'H4': 'NEUTRAL', 'D1': 'BULLISH'})}")
        
        tracker = SignalOutcomeTracker(bot)
        stats = tracker.get_stats()
        print(f"  Outcome tracker: {stats}")
        
        if bot.is_configured:
            print("\n  Sending test messages...")
            sender.send_execute_alert(
                'XAUUSD', 'H1', 85,
                {'OB': 20, 'FVG': 20, 'SWEEP': 30, 'VWAP': 10, 'SESSION': 5},
                {'M15': 'BULLISH', 'H1': 'BULLISH', 'H4': 'NEUTRAL', 'D1': 'BULLISH'},
                75, 'ACTIVE', 2350.50, 5.0
            )
            print("  Test EXECUTE sent")
            
            time.sleep(1)
            sender.send_wait_alert('EURUSD', 'M15', 62, 'MTF H4 conflict')
            print("  Test WAIT sent")
            
            time.sleep(1)
            sender.last_decision['GBPUSD'] = 'EXECUTE'
            sender.send_block_alert('GBPUSD', 'H1', 'Circuit Breaker PAUSED', '2026-06-11 06:00 UTC')
            print("  Test BLOCK sent")
        else:
            print("\n  Telegram not configured, skipping network tests")
        
        print("\n" + "=" * 60)
    
    elif '--background' in sys.argv:
        service = get_telegram_service()
        
        # Robust startup with error recovery
        while True:
            try:
                service.start()
                service.send_startup_message()
                log.info("Telegram service started successfully")
                break
            except Exception as e:
                log.error(f"Telegram startup failed: {e}, retrying in 10s...")
                time.sleep(10)
        
        # Main loop — never crash
        while True:
            try:
                time.sleep(60)
            except KeyboardInterrupt:
                service.send_shutdown_message()
                service.stop()
                break
            except Exception as e:
                log.error(f"Telegram loop error: {e}")
                time.sleep(5)
                continue
    
    else:
        print("Usage:")
        print("  python telegram_signals.py --test          # Run tests")
        print("  python telegram_signals.py --background    # Start service")
