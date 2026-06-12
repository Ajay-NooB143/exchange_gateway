"""
System Heartbeat - Decoupled Diagnostic Monitor
================================================
Runs a diagnostic check every 6 hours (configurable) on PM2 process
resource utilization (CPU/Memory). Transmits structured status updates
to a private Telegram admin group chat.

On unhandled exceptions or critical alerts, fires an immediate override.
"""

import json
import logging
import os
import sys
import threading
import time
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any

# Load .env at module level so PM2 processes pick it up
_env_path = Path(__file__).parent.parent / '.env'
if _env_path.exists():
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith('#') and '=' in _line:
                _k, _v = _line.split('=', 1)
                os.environ.setdefault(_k.strip(), _v.strip())

log = logging.getLogger('SystemHeartbeat')

HEARTBEAT_DIR = Path(__file__).parent / 'logs'
HEARTBEAT_DIR.mkdir(exist_ok=True)

HEARTBEAT_STATE_FILE = HEARTBEAT_DIR / 'system_heartbeat.json'
INTERVAL_SECONDS = 21600  # 6 hours
CRITICAL_INTERVAL_SECONDS = 60  # Check critical health every 60s


class SystemHeartbeat:
    """Decoupled heartbeat with PM2 diagnostics and critical alerting."""

    def __init__(self):
        self._admin_chat_id = os.environ.get('ADMIN_CHAT_ID') or os.environ.get('TELEGRAM_CHAT_ID', '')
        self._bot_token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._critical_thread: Optional[threading.Thread] = None
        self._last_ok = None

    # ── PM2 Diagnostics ───────────────────────────────────────────────────

    def _get_pm2_status(self) -> List[Dict]:
        """Query pm2 jlist for process resource data."""
        try:
            result = subprocess.run(
                ['pm2', 'jlist'],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode != 0:
                return []
            procs = json.loads(result.stdout) if result.stdout else []
            statuses = []
            for p in procs:
                monit = p.get('monit', {})
                pm2_env = p.get('pm2_env', {})
                statuses.append({
                    'name': p.get('name', 'unknown'),
                    'status': pm2_env.get('status', 'unknown'),
                    'pid': pm2_env.get('pid', 0),
                    'cpu': monit.get('cpu', 0),
                    'memory_mb': round(monit.get('memory', 0) / (1024 * 1024), 1),
                    'uptime_sec': pm2_env.get('pm_uptime', 0) and int(time.time() - pm2_env['pm_uptime'] / 1000) or 0,
                    'restarts': pm2_env.get('restart_time', 0),
                })
            return statuses
        except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError) as e:
            log.debug(f"PM2 jlist failed: {e}")
            return []
        except Exception as e:
            log.debug(f"PM2 status error: {e}")
            return []

    def _get_disk_usage(self) -> dict:
        """Get disk usage info."""
        try:
            result = subprocess.run(
                ['df', '-h', '/'],
                capture_output=True, text=True, timeout=5
            )
            lines = result.stdout.strip().split('\n')
            if len(lines) >= 2:
                parts = lines[-1].split()
                return {
                    'total': parts[1] if len(parts) > 1 else '?',
                    'used': parts[2] if len(parts) > 2 else '?',
                    'avail': parts[3] if len(parts) > 3 else '?',
                    'use_pct': parts[4] if len(parts) > 4 else '?',
                }
        except Exception:
            pass
        return {}

    def _get_memory_usage(self) -> dict:
        """Get system memory usage."""
        try:
            result = subprocess.run(
                ['free', '-m'],
                capture_output=True, text=True, timeout=5
            )
            lines = result.stdout.strip().split('\n')
            if len(lines) >= 2:
                parts = lines[1].split()
                return {
                    'total_mb': parts[1] if len(parts) > 1 else '?',
                    'used_mb': parts[2] if len(parts) > 2 else '?',
                    'free_mb': parts[3] if len(parts) > 3 else '?',
                }
        except Exception:
            pass
        return {}

    def _get_uptime(self) -> str:
        """Get system uptime."""
        try:
            result = subprocess.run(
                ['uptime', '-p'],
                capture_output=True, text=True, timeout=5
            )
            return result.stdout.strip() if result.stdout else '?'
        except Exception:
            return '?'

    # ── Diagnostics ───────────────────────────────────────────────────────

    def run_diagnostics(self) -> Dict[str, Any]:
        """Run full diagnostic check."""
        pm2_procs = self._get_pm2_status()
        disk = self._get_disk_usage()
        mem = self._get_memory_usage()

        total_cpu = sum(p.get('cpu', 0) for p in pm2_procs)
        total_mem = sum(p.get('memory_mb', 0) for p in pm2_procs)
        errored = [p for p in pm2_procs if p.get('status') == 'errored']
        stopped = [p for p in pm2_procs if p.get('status') == 'stopped']

        critical = bool(errored) or bool(disk.get('use_pct', '0%').rstrip('%') and int(disk['use_pct'].rstrip('%')) > 90)

        return {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'uptime': self._get_uptime(),
            'pm2': {
                'total_processes': len(pm2_procs),
                'cpu_pct': round(total_cpu, 1),
                'memory_mb': round(total_mem, 1),
                'errored': [p['name'] for p in errored],
                'stopped': [p['name'] for p in stopped],
                'processes': pm2_procs,
            },
            'disk': disk,
            'memory': mem,
            'critical': critical,
        }

    def _format_status_message(self, diag: Dict[str, Any]) -> str:
        """Format diagnostics into a structured Telegram message."""
        emoji = '\U0001f534 CRITICAL' if diag.get('critical') else '\U0001f7e2 SYSTEM HEARTBEAT'

        lines = [
            f"{emoji}",
            f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501",
            f"Time: {diag.get('timestamp', '?')[:19]} UTC",
            f"Uptime: {diag.get('uptime', '?')}",
            "",
        ]

        pm2 = diag.get('pm2', {})
        lines.append(f"\U0001f4ca PM2 Processes: {pm2.get('total_processes', 0)}")
        lines.append(f"  CPU: {pm2.get('cpu_pct', 0)}%  |  RAM: {pm2.get('memory_mb', 0)} MB")

        errored = pm2.get('errored', [])
        if errored:
            lines.append(f"  \u26a0\ufe0f Errored: {', '.join(errored)}")

        stopped = pm2.get('stopped', [])
        if stopped:
            lines.append(f"  \u23f8\ufe0f Stopped: {', '.join(stopped)}")

        lines.append("")
        lines.append(f"\U0001f4be Processes:")
        for proc in pm2.get('processes', []):
            s = proc.get('status', '?')
            icon = '\U0001f7e2' if s == 'online' else '\U0001f534' if s == 'errored' else '\u26aa'
            mem = proc.get('memory_mb', 0)
            cpu = proc.get('cpu', 0)
            lines.append(f"  {icon} {proc.get('name', '?'):20s} CPU:{cpu:>5.1f}% RAM:{mem:>5.1f}MB")

        disk_d = diag.get('disk', {})
        if disk_d:
            lines.append(f"\n\U0001f4bd Disk: {disk_d.get('used', '?')} / {disk_d.get('total', '?')} ({disk_d.get('use_pct', '?')})")

        mem_d = diag.get('memory', {})
        if mem_d:
            lines.append(f"\U0001f4a1 RAM: {mem_d.get('used_mb', '?')}MB / {mem_d.get('total_mb', '?')}MB")

        if diag.get('critical'):
            lines.append(f"\n\u26a0\ufe0f CRITICAL ALERT \u2014 Action required!")

        return '\n'.join(lines)

    def _send_telegram(self, message: str) -> bool:
        """Send a Telegram message via Bot API."""
        if not self._bot_token or not self._admin_chat_id:
            log.debug("Admin chat not configured, skipping heartbeat send")
            return False

        try:
            import urllib.request
            import json as j

            url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
            payload = j.dumps({
                'chat_id': self._admin_chat_id,
                'text': message,
                'parse_mode': 'HTML',
            }).encode('utf-8')

            req = urllib.request.Request(url, data=payload,
                                          headers={'Content-Type': 'application/json'})
            resp = urllib.request.urlopen(req, timeout=15)
            result = j.loads(resp.read().decode())
            return result.get('ok', False)
        except Exception as e:
            log.debug(f"Heartbeat send failed: {e}")
            return False

    # ── Heartbeat Loop ────────────────────────────────────────────────────

    def _heartbeat_loop(self):
        """Main 6-hour heartbeat loop."""
        while self._running:
            try:
                diag = self.run_diagnostics()
                msg = self._format_status_message(diag)
                sent = self._send_telegram(msg)
                if sent:
                    log.info("System heartbeat sent")
                    self._last_ok = time.time()
                else:
                    log.warning("System heartbeat failed to send")

                # Save state
                try:
                    with open(HEARTBEAT_STATE_FILE, 'w') as f:
                        json.dump({'last_heartbeat': diag['timestamp'],
                                    'critical': diag.get('critical')}, f)
                except Exception:
                    pass

            except Exception as e:
                log.error(f"Heartbeat loop error: {e}")
                try:
                    self._send_telegram(f"\u26a0\ufe0f HEARTBEAT EXCEPTION: {e}")
                except Exception:
                    pass

            # Sleep interval, checking running flag every 60s
            for _ in range(INTERVAL_SECONDS // 60):
                if not self._running:
                    return
                time.sleep(60)

    def _critical_check_loop(self):
        """Quick check every 60s for critical issues."""
        while self._running:
            time.sleep(CRITICAL_INTERVAL_SECONDS)
            if not self._running:
                return

            try:
                diag = self.run_diagnostics()
                if diag.get('critical') or diag.get('pm2', {}).get('errored'):
                    msg = self._format_status_message(diag)
                    sent = self._send_telegram(msg)
                    if sent:
                        log.info("Critical alert sent")
                        self._last_ok = time.time()

                    # Avoid spam — only re-alert if state changes
                    prev_state = getattr(self, '_prev_critical_state', None)
                    current_state = (diag.get('critical'), tuple(diag.get('pm2', {}).get('errored', [])))
                    if current_state != prev_state:
                        self._send_telegram(msg)
                        self._prev_critical_state = current_state

            except Exception:
                pass

    def start(self):
        """Start heartbeat threads."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._thread.start()

        self._critical_thread = threading.Thread(target=self._critical_check_loop, daemon=True)
        self._critical_thread.start()

        log.info("System heartbeat started (6h interval, 60s critical check)")

    def stop(self):
        """Stop heartbeat threads."""
        self._running = False
        log.info("System heartbeat stopped")

    def send_immediate(self) -> bool:
        """Send an immediate diagnostic status."""
        diag = self.run_diagnostics()
        msg = self._format_status_message(diag)
        return self._send_telegram(msg)


# ══════════════════════════════════════════════════════════════════════════════
# GLOBAL INSTANCE
# ══════════════════════════════════════════════════════════════════════════════

_heartbeat: Optional[SystemHeartbeat] = None


def get_system_heartbeat() -> SystemHeartbeat:
    global _heartbeat
    if _heartbeat is None:
        _heartbeat = SystemHeartbeat()
    return _heartbeat


if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

    hb = get_system_heartbeat()

    if '--once' in sys.argv:
        diag = hb.run_diagnostics()
        print(json.dumps(diag, indent=2))
        print('---')
        print(hb._format_status_message(diag))
    elif '--daemon' in sys.argv:
        hb.start()
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            hb.stop()
    else:
        print("Usage:")
        print("  python system_heartbeat.py --once      # Single diagnostic")
        print("  python system_heartbeat.py --daemon    # Background daemon")
