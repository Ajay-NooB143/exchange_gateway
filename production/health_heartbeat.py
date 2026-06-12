"""
Health Heartbeat - OMNI BRAIN V2
================================
Periodic health status via Telegram.

Features:
  - Every 5 minutes send Telegram heartbeat
  - If silent > 10 minutes → self-alert
  - Store last heartbeat: logs/heartbeat.json

Heartbeat Format:
  💚 OMNI BRAIN HEARTBEAT
  Time: {UTC}
  ─────────────────────
  XAUUSD  Score:82 🟢 EXECUTE
  EURUSD  Score:61 🟡 WAIT
  GBPUSD  Score:38 🔴 BLOCK
  SP500   Score:75 🟢 EXECUTE
  ─────────────────────
  Memory: 45MB / 80MB
  MT5: 🟢 Connected
  CB: 🟢 All Active
  Uptime: 2h 34m
"""

import os
import json
import logging
import time
import threading
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Callable
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

log = logging.getLogger('HealthHeartbeat')

LOG_DIR = Path(__file__).parent / 'logs'
LOG_DIR.mkdir(exist_ok=True)

API_KEY = os.environ.get('API_KEY', 'omni-bridge-key-2026')


class HealthHeartbeat:
    """
    Health heartbeat system.
    
    Sends periodic status updates via Telegram.
    Self-alerts if silent for > 10 minutes.
    """
    
    HEARTBEAT_INTERVAL = 300  # 5 minutes
    SILENCE_THRESHOLD = 600   # 10 minutes
    
    ASSETS = ['XAUUSD', 'EURUSD', 'GBPUSD', 'SP500']
    
    def __init__(self):
        self.start_time = time.time()
        self.last_heartbeat: Optional[float] = None
        self.last_alert: Optional[float] = None
        self.running = False
        self._thread: Optional[threading.Thread] = None
        
        # Callbacks for data
        self.score_callback: Optional[Callable] = None
        self.memory_callback: Optional[Callable] = None
        self.mt5_callback: Optional[Callable] = None
        self.cb_callback: Optional[Callable] = None
        
        self._load_state()
    
    def _load_state(self) -> None:
        """Load state from file."""
        filepath = LOG_DIR / 'heartbeat.json'
        
        if filepath.exists():
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                self.last_heartbeat = data.get('last_heartbeat')
            except Exception:
                pass
    
    def _save_state(self) -> None:
        """Save state to file."""
        filepath = LOG_DIR / 'heartbeat.json'
        
        data = {
            'last_heartbeat': self.last_heartbeat,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        try:
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            log.error(f"Failed to save heartbeat state: {e}")
    
    def _format_uptime(self) -> str:
        """Format uptime as human readable."""
        elapsed = time.time() - self.start_time
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        return f"{hours}h {minutes}m"
    
    def _get_live_scores(self) -> Dict[str, Dict[str, Any]]:
        """Get current scores for all assets.

        Tries last_scan.json first (if < 5 min old), then force-scans
        via localhost:3000 API, then falls back to mock scores.
        """
        last_scan_path = LOG_DIR / 'last_scan.json'
        try:
            if last_scan_path.exists():
                with open(last_scan_path) as f:
                    last = json.load(f)
                age = time.time() - last.get('timestamp', 0)
                if age < 300:
                    scans = last.get('scans', [])
                    scores = {}
                    for s in scans:
                        sym = s.get('symbol', '')
                        scores[sym] = {
                            'score': s.get('score', 0),
                            'decision': s.get('decision', 'WAIT')
                        }
                    if scores:
                        return scores
        except Exception as e:
            log.debug(f"Failed to load last_scan.json: {e}")

        # Force fresh scan via localhost API
        try:
            import urllib.request
            import urllib.error
            url = 'http://localhost:3000/api/test-full-scan'
            data = json.dumps({}).encode('utf-8')
            req = urllib.request.Request(url, data=data,
                headers={'X-API-Key': API_KEY, 'Content-Type': 'application/json'})
            resp = urllib.request.urlopen(req, timeout=30)
            result = json.loads(resp.read().decode())
            scans = result.get('scans', [])
            scores = {}
            for s in scans:
                scores[s['symbol']] = {'score': s.get('score', 0), 'decision': s.get('decision', 'WAIT')}
            if scores:
                return scores
        except Exception as e:
            log.debug(f"Force scan failed: {e}")

        # Fallback
        return {asset: {'score': 0, 'decision': 'N/A'} for asset in self.ASSETS}

    def _get_subscriber_counts(self) -> tuple:
        """Get subscriber counts from subscribers.json.
        Returns (free_count, vip_count).
        """
        subs_path = Path(__file__).parent / 'logs' / 'subscribers.json'
        try:
            if subs_path.exists():
                with open(subs_path) as f:
                    subs = json.load(f)
                free = sum(1 for s in subs.values() if s.get('tier', '').lower() == 'free')
                vip = sum(1 for s in subs.values() if s.get('tier', '').upper() == 'VIP')
                return free, vip
        except Exception:
            pass
        return 0, 0

    def _get_signals_today(self) -> tuple:
        """Get signals today count and winners.
        Returns (total, winners).
        """
        last_scan_path = LOG_DIR / 'last_scan.json'
        try:
            if last_scan_path.exists():
                with open(last_scan_path) as f:
                    data = json.load(f)
                scans = data.get('scans', [])
                total = len(scans)
                winners = sum(1 for s in scans if s.get('decision') == 'EXECUTE')
                return total, winners
        except Exception:
            pass
        return 0, 0
    
    def _get_memory(self) -> Dict[str, Any]:
        """Get memory status (system-wide)."""
        if self.memory_callback:
            try:
                return self.memory_callback()
            except Exception as e:
                log.debug(f"Memory callback error: {e}")
        
        try:
            import psutil
            mem = psutil.virtual_memory()
            used_mb = mem.used / (1024 * 1024)
            total_mb = mem.total / (1024 * 1024)
            return {
                'used_mb': used_mb,
                'limit_mb': total_mb,
                'total': total_mb,
                'percent': mem.percent
            }
        except Exception:
            try:
                with open('/proc/meminfo') as f:
                    for line in f:
                        if 'MemAvailable' in line:
                            kb = int(line.split()[1])
                            return {'used_mb': kb / 1024, 'limit_mb': 800, 'percent': 0}
                        if 'MemTotal' in line:
                            total_kb = int(line.split()[1])
                            return {'used_mb': total_kb / 1024 * 0.3, 'limit_mb': total_kb / 1024, 'percent': 30}
            except Exception:
                pass
            return {'used_mb': 0, 'limit_mb': 800, 'percent': 0}
    
    def _get_mt5_status(self) -> bool:
        """Get MT5 connection status."""
        if self.mt5_callback:
            try:
                return self.mt5_callback()
            except Exception:
                pass
        return True
    
    def _get_cb_status(self) -> str:
        """Get circuit breaker status."""
        if self.cb_callback:
            try:
                return self.cb_callback()
            except Exception:
                pass
        return "All Active"
    
    def _build_message(self) -> str:
        """Build heartbeat message."""
        now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')

        # Header
        lines = [
            "\U0001f49a OMNI BRAIN V2 \u2014 LIVE",
            now,
            "\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500"
        ]

        # Asset scores
        scores = self._get_live_scores()
        for asset in self.ASSETS:
            data = scores.get(asset, {})
            score = data.get('score', 0)
            decision = data.get('decision', 'N/A')

            if score >= 75:
                emoji = '\U0001f7e2'
            elif score >= 50:
                emoji = '\U0001f7e1'
            elif score == 0:
                emoji = '\u26ab'
            else:
                emoji = '\U0001f534'

            display_decision = decision if decision in ('EXECUTE', 'WAIT', 'BLOCK') else 'NO DATA' if score == 0 else decision
            lines.append(f"{asset:<8} {score:>2} {emoji} {display_decision}")

        lines.append("\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500")

        # Memory
        memory = self._get_memory()
        used_mb = memory.get('used_mb', 0)
        pct = memory.get('percent', 0)
        if pct == 0 and used_mb > 0:
            pct = (used_mb / memory.get('limit_mb', 80)) * 100
        lines.append(f"Memory : {used_mb:.0f}MB ({int(pct)}%)")

        # Uptime
        lines.append(f"Uptime : {self._format_uptime()}")

        # Signals today
        signals_total, signals_winners = self._get_signals_today()
        lines.append(f"Signals: {signals_total} today")
        if signals_total > 0 and signals_winners > 0:
            wr = signals_winners / signals_total * 100
            lines.append(f"Winners: {signals_winners} ({wr:.0f}%)")

        # Subscribers
        free_subs, vip_subs = self._get_subscriber_counts()
        lines.append(f"VIP subs: {vip_subs}")
        lines.append(f"Free subs: {free_subs}")

        # Calibration day
        lines.append(f"Cal day : 1/7")

        # DNA generation
        lines.append(f"DNA gen : 1")

        return '\n'.join(lines)
    
    def _verify_chat(self, bot_token: str, chat_id: str) -> bool:
        """Check if chat exists before sending."""
        try:
            import urllib.request
            import urllib.error
            url = f"https://api.telegram.org/bot{bot_token}/getChat?chat_id={chat_id}"
            resp = urllib.request.urlopen(url, timeout=10)
            result = json.loads(resp.read().decode())
            return result.get('ok', False)
        except urllib.error.HTTPError as e:
            if e.code == 400:
                log.warning("Chat not found — send /start to @omnibrainsignals_free first")
            return False
        except Exception:
            return False
    
    def _send_telegram(self, message: str) -> bool:
        """Send message via Telegram."""
        try:
            import urllib.request
            import urllib.error
            
            bot_token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
            chat_id = os.environ.get('TELEGRAM_CHAT_ID', '')
            
            if not bot_token or not chat_id:
                log.debug("Telegram not configured")
                return False
            
            if not self._verify_chat(bot_token, chat_id):
                log.warning("Skipping heartbeat — chat not authorized. Send /start to @omnibrainsignals_free")
                return False
            
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            data = json.dumps({'chat_id': chat_id, 'text': message}).encode('utf-8')
            
            req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
            urllib.request.urlopen(req, timeout=10)
            
            return True
        except urllib.error.HTTPError as e:
            if e.code == 400:
                log.warning("Chat not found — user must send /start to bot first")
            else:
                log.warning(f"Telegram HTTP {e.code}: {e}")
            return False
        except Exception as e:
            log.warning(f"Failed to send Telegram: {e}")
            return False
    
    def send_heartbeat(self) -> bool:
        """Send heartbeat message."""
        message = self._build_message()
        success = self._send_telegram(message)
        
        if success:
            self.last_heartbeat = time.time()
            self._save_state()
            log.info("[HEARTBEAT] Sent successfully")
        else:
            log.warning("[HEARTBEAT] Failed to send")
        
        return success
    
    def check_silence(self) -> bool:
        """Check if heartbeat has been silent too long."""
        if self.last_heartbeat is None:
            return False
        
        elapsed = time.time() - self.last_heartbeat
        
        if elapsed > self.SILENCE_THRESHOLD:
            # Send self-alert
            alert_msg = (
                f"⚠️ HEARTBEAT MISSED — check system\n"
                f"Last heartbeat: {int(elapsed)}s ago\n"
                f"Threshold: {self.SILENCE_THRESHOLD}s"
            )
            
            now = time.time()
            if self.last_alert is None or (now - self.last_alert) > self.SILENCE_THRESHOLD:
                self._send_telegram(alert_msg)
                self.last_alert = now
                log.warning("[HEARTBEAT] Silence alert sent")
            
            return True
        
        return False
    
    def _run_loop(self) -> None:
        """Background heartbeat loop."""
        while self.running:
            try:
                self.send_heartbeat()
                self.check_silence()
            except Exception as e:
                log.error(f"Heartbeat error: {e}")
            
            # Sleep in small increments for quick shutdown
            for _ in range(self.HEARTBEAT_INTERVAL):
                if not self.running:
                    break
                time.sleep(1)
    
    def start(self) -> None:
        """Start background heartbeat."""
        if self.running:
            return
        
        self.running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        log.info("[HEARTBEAT] Background started")
    
    def stop(self) -> None:
        """Stop background heartbeat."""
        self.running = False
        if self._thread:
            self._thread.join(timeout=5)
        log.info("[HEARTBEAT] Stopped")
    
    def get_status(self) -> Dict[str, Any]:
        """Get heartbeat status."""
        return {
            'running': self.running,
            'last_heartbeat': self.last_heartbeat,
            'uptime': self._format_uptime(),
            'uptime_seconds': time.time() - self.start_time
        }


# Global instance
_heartbeat: Optional[HealthHeartbeat] = None


def get_heartbeat() -> HealthHeartbeat:
    """Get or create global heartbeat instance."""
    global _heartbeat
    if _heartbeat is None:
        _heartbeat = HealthHeartbeat()
    return _heartbeat


# ══════════════════════════════════════════════════════════════════════════════
# CLI TEST
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import sys

    logging.basicConfig(level=logging.INFO, format='%(message)s')

    if '--once' in sys.argv:
        print("=" * 60)
        print("  HEALTH HEARTBEAT - TEST")
        print("=" * 60)

        hb = HealthHeartbeat()

        # Print message
        print("\n" + hb._build_message())
        print("\n" + "=" * 60)
    else:
        print("Usage: python health_heartbeat.py --once")
