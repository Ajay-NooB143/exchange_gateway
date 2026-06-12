"""
Self-Healing Cron - OMNI BRAIN V2
==================================
Automated system health checks and repairs.

Runs every 15 minutes via APScheduler.

Checks:
  1. All PM2 processes alive
  2. Stale lock files in /tmp/mt5_sync_*.lock
  3. Log directory not filling disk
  4. .env file present and readable
  5. Telegram connection alive
  6. Memory monitor process alive
"""

import os
import sys
import json
import time
import glob
import logging
import subprocess
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Tuple
from pathlib import Path

log = logging.getLogger('SelfHealingCron')

LOG_DIR = Path(__file__).parent / 'logs'
LOG_DIR.mkdir(exist_ok=True)

SELF_HEAL_LOG = LOG_DIR / 'self_heal.log'

# Thresholds
LOCK_STALE_SECONDS = 60
LOG_DIR_MAX_SIZE_MB = 500
PM2_PROCESSES = [
    'omni-xauusd', 'omni-eurusd', 'omni-gbpusd', 'omni-sp500',
    'omni-pipeline', 'omni-heartbeat', 'omni-report', 'omni-monitor'
]


class SelfHealingCron:
    """
    Self-healing system that runs periodic checks and fixes issues.
    
    Checks:
      1. PM2 processes alive
      2. Stale lock files
      3. Log directory size
      4. .env file present
      5. Telegram connection
      6. Memory monitor alive
    """
    
    def __init__(self):
        self.fixes_applied = []
    
    def log_check(self, check_name: str, status: str, details: str = ''):
        """Log a check result."""
        timestamp = datetime.now(timezone.utc).isoformat()
        log_entry = f"[{timestamp}] {check_name}: {status} {details}\n"
        
        with open(SELF_HEAL_LOG, 'a') as f:
            f.write(log_entry)
        
        if status == 'FIXED':
            log.info(f"[SELF-HEAL] {check_name}: {details}")
            self.fixes_applied.append({'check': check_name, 'details': details, 'time': timestamp})
    
    # ════════════════════════════════════════════════════════════════════════════
    # CHECK 1: PM2 PROCESSES
    # ════════════════════════════════════════════════════════════════════════════
    
    def check_pm2_processes(self) -> List[str]:
        """Check if all PM2 processes are alive."""
        dead_processes = []
        
        try:
            result = subprocess.run(
                ['pm2', 'jlist'],
                capture_output=True, text=True, timeout=10
            )
            
            if result.returncode != 0:
                self.log_check('PM2', 'ERROR', 'Failed to get PM2 status')
                return PM2_PROCESSES
            
            processes = json.loads(result.stdout)
            running_names = {p.get('name') for p in processes if p.get('pm2_env', {}).get('status') == 'online'}
            
            for name in PM2_PROCESSES:
                if name not in running_names:
                    dead_processes.append(name)
                    
                    # Try to restart
                    try:
                        subprocess.run(
                            ['pm2', 'restart', name],
                            capture_output=True, timeout=10
                        )
                        self.log_check('PM2', 'FIXED', f'Restarted {name}')
                    except Exception as e:
                        self.log_check('PM2', 'ERROR', f'Failed to restart {name}: {e}')
            
            if not dead_processes:
                self.log_check('PM2', 'OK', f'All {len(PM2_PROCESSES)} processes running')
            
        except Exception as e:
            self.log_check('PM2', 'ERROR', str(e))
        
        return dead_processes
    
    # ════════════════════════════════════════════════════════════════════════════
    # CHECK 2: STALE LOCK FILES
    # ════════════════════════════════════════════════════════════════════════════
    
    def check_stale_locks(self) -> List[str]:
        """Check for stale lock files."""
        stale_locks = []
        
        lock_pattern = '/tmp/mt5_sync_*.lock'
        lock_files = glob.glob(lock_pattern)
        
        now = time.time()
        
        for lock_file in lock_files:
            try:
                file_age = now - os.path.getmtime(lock_file)
                
                if file_age > LOCK_STALE_SECONDS:
                    os.remove(lock_file)
                    stale_locks.append(lock_file)
                    self.log_check('LOCK', 'FIXED', f'Deleted stale lock: {lock_file} (age: {file_age:.0f}s)')
            except Exception as e:
                self.log_check('LOCK', 'ERROR', f'Failed to check {lock_file}: {e}')
        
        if not stale_locks and lock_files:
            self.log_check('LOCK', 'OK', f'All {len(lock_files)} lock files fresh')
        elif not lock_files:
            self.log_check('LOCK', 'OK', 'No lock files found')
        
        return stale_locks
    
    # ════════════════════════════════════════════════════════════════════════════
    # CHECK 3: LOG DIRECTORY SIZE
    # ════════════════════════════════════════════════════════════════════════════
    
    def check_log_directory(self) -> float:
        """Check log directory size."""
        try:
            total_size = 0
            for dirpath, dirnames, filenames in os.walk(LOG_DIR):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    total_size += os.path.getsize(fp)
            
            size_mb = total_size / (1024 * 1024)
            
            if size_mb > LOG_DIR_MAX_SIZE_MB:
                # Archive old logs
                self._archive_old_logs()
                self.log_check('LOGS', 'FIXED', f'Archived logs (was {size_mb:.1f}MB)')
                return size_mb
            
            self.log_check('LOGS', 'OK', f'{size_mb:.1f}MB / {LOG_DIR_MAX_SIZE_MB}MB')
            return size_mb
            
        except Exception as e:
            self.log_check('LOGS', 'ERROR', str(e))
            return 0
    
    def _archive_old_logs(self):
        """Archive old log files."""
        archive_dir = LOG_DIR / 'archive'
        archive_dir.mkdir(exist_ok=True)
        
        cutoff = datetime.now() - timedelta(days=7)
        
        for log_file in LOG_DIR.glob('*.log'):
            try:
                if datetime.fromtimestamp(log_file.stat().st_mtime) < cutoff:
                    archive_path = archive_dir / log_file.name
                    log_file.rename(archive_path)
            except Exception:
                continue
    
    # ════════════════════════════════════════════════════════════════════════════
    # CHECK 4: .ENV FILE
    # ════════════════════════════════════════════════════════════════════════════
    
    def check_env_file(self) -> bool:
        """Check if .env file exists and is readable."""
        env_file = Path(__file__).parent / '.env'
        
        if not env_file.exists():
            self.log_check('ENV', 'CRITICAL', '.env file missing!')
            self._send_critical_alert('.env file missing!')
            return False
        
        try:
            with open(env_file, 'r') as f:
                content = f.read()
            
            if len(content) < 10:
                self.log_check('ENV', 'WARNING', '.env file appears empty')
                return False
            
            self.log_check('ENV', 'OK', '.env file present and readable')
            return True
            
        except Exception as e:
            self.log_check('ENV', 'ERROR', f'Cannot read .env: {e}')
            return False
    
    # ════════════════════════════════════════════════════════════════════════════
    # CHECK 5: TELEGRAM CONNECTION
    # ════════════════════════════════════════════════════════════════════════════
    
    def check_telegram(self) -> bool:
        """Check Telegram connection."""
        try:
            import urllib.request
            
            bot_token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
            chat_id = os.environ.get('TELEGRAM_CHAT_ID', '')
            
            if not bot_token or not chat_id:
                self.log_check('TELEGRAM', 'SKIP', 'Not configured')
                return True
            
            url = f"https://api.telegram.org/bot{bot_token}/getMe"
            response = urllib.request.urlopen(url, timeout=10)
            
            if response.status == 200:
                self.log_check('TELEGRAM', 'OK', 'Connected')
                return True
            else:
                self.log_check('TELEGRAM', 'ERROR', f'Status {response.status}')
                return False
                
        except Exception as e:
            self.log_check('TELEGRAM', 'ERROR', str(e))
            return False
    
    # ════════════════════════════════════════════════════════════════════════════
    # CHECK 6: MEMORY MONITOR
    # ════════════════════════════════════════════════════════════════════════════
    
    def check_memory_monitor(self) -> bool:
        """Check if memory monitor is alive."""
        try:
            result = subprocess.run(
                ['pm2', 'jlist'],
                capture_output=True, text=True, timeout=10
            )
            
            if result.returncode != 0:
                return False
            
            processes = json.loads(result.stdout)
            for p in processes:
                if p.get('name') == 'omni-monitor':
                    status = p.get('pm2_env', {}).get('status')
                    if status == 'online':
                        self.log_check('MEMORY', 'OK', 'Monitor running')
                        return True
                    else:
                        # Restart it
                        subprocess.run(['pm2', 'restart', 'omni-monitor'], capture_output=True, timeout=10)
                        self.log_check('MEMORY', 'FIXED', 'Restarted memory monitor')
                        return True
            
            self.log_check('MEMORY', 'ERROR', 'Monitor not found')
            return False
            
        except Exception as e:
            self.log_check('MEMORY', 'ERROR', str(e))
            return False
    
    # ════════════════════════════════════════════════════════════════════════════
    # CRITICAL ALERTS
    # ════════════════════════════════════════════════════════════════════════════
    
    def _send_critical_alert(self, message: str):
        """Send critical alert via Telegram."""
        try:
            import urllib.request
            
            bot_token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
            chat_id = os.environ.get('TELEGRAM_CHAT_ID', '')
            
            if not bot_token or not chat_id:
                return
            
            alert_msg = f"🚨 CRITICAL: {message}\nTime: {datetime.now(timezone.utc).isoformat()}"
            
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            data = json.dumps({'chat_id': chat_id, 'text': alert_msg}).encode('utf-8')
            
            req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
            urllib.request.urlopen(req, timeout=10)
        except Exception:
            pass
    
    def _send_fix_alert(self, fixes: List[Dict[str, str]]):
        """Send fix notification via Telegram."""
        if not fixes:
            return
        
        try:
            import urllib.request
            
            bot_token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
            chat_id = os.environ.get('TELEGRAM_CHAT_ID', '')
            
            if not bot_token or not chat_id:
                return
            
            lines = ["🔧 SELF-HEAL APPLIED"]
            for fix in fixes:
                lines.append(f"Issue: {fix['check']}")
                lines.append(f"Action: {fix['details']}")
                lines.append(f"Time: {fix['time']}")
                lines.append("")
            
            message = '\n'.join(lines)
            
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            data = json.dumps({'chat_id': chat_id, 'text': message}).encode('utf-8')
            
            req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
            urllib.request.urlopen(req, timeout=10)
        except Exception:
            pass
    
    # ════════════════════════════════════════════════════════════════════════════
    # RUN ALL CHECKS
    # ════════════════════════════════════════════════════════════════════════════
    
    def run_checks(self) -> Dict[str, Any]:
        """Run all health checks."""
        self.fixes_applied = []
        
        start_time = time.time()
        
        results = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'pm2': self.check_pm2_processes(),
            'locks': self.check_stale_locks(),
            'log_size_mb': self.check_log_directory(),
            'env_ok': self.check_env_file(),
            'telegram_ok': self.check_telegram(),
            'memory_monitor_ok': self.check_memory_monitor()
        }
        
        duration = time.time() - start_time
        
        # Send fix alerts
        if self.fixes_applied:
            self._send_fix_alert(self.fixes_applied)
        
        results['fixes'] = self.fixes_applied
        results['duration_ms'] = duration * 1000
        
        return results


# Global instance
_self_heal: Optional[SelfHealingCron] = None


def get_self_heal() -> SelfHealingCron:
    """Get or create global self-heal instance."""
    global _self_heal
    if _self_heal is None:
        _self_heal = SelfHealingCron()
    return _self_heal


# ══════════════════════════════════════════════════════════════════════════════
# CLI TEST
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import sys
    
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    if '--once' in sys.argv:
        print("=" * 60)
        print("  SELF-HEALING CRON - TEST")
        print("=" * 60)
        
        cron = SelfHealingCron()
        
        # Run checks
        results = cron.run_checks()
        
        # Print results
        print(f"\nTimestamp: {results['timestamp']}")
        print(f"Duration: {results['duration_ms']:.1f}ms")
        print(f"\nPM2 Dead: {results['pm2']}")
        print(f"Stale Locks: {results['locks']}")
        print(f"Log Size: {results['log_size_mb']:.1f}MB")
        print(f"ENV OK: {results['env_ok']}")
        print(f"Telegram OK: {results['telegram_ok']}")
        print(f"Memory Monitor OK: {results['memory_monitor_ok']}")
        
        if results['fixes']:
            print(f"\nFixes Applied: {len(results['fixes'])}")
            for fix in results['fixes']:
                print(f"  - {fix['check']}: {fix['details']}")
        
        print("\n" + "=" * 60)
    else:
        print("Usage: python self_healing_cron.py --once")
