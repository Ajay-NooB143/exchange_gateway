"""
Memory Usage Monitor
====================
Polls memory usage every 30 seconds and alerts via Telegram when threshold crossed.

Features:
- Polls memory every 30 seconds using psutil
- Alert threshold: 80MB
- When threshold crossed: log warning + send Telegram message
- Output format: [MEMORY] 45.2MB / 80MB limit

Usage:
    python memory_monitor.py           # Run continuous monitoring
    python memory_monitor.py --test    # Test Telegram alert
    python memory_monitor.py --once    # Single check
"""

import os
import sys
import time
import logging
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    print("Warning: psutil not installed. Using fallback memory measurement.")

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

# Memory threshold in MB
MEMORY_THRESHOLD_MB = 80

# Poll interval in seconds
POLL_INTERVAL = 30

# Telegram configuration from .env
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')

# Log file
LOG_DIR = Path(__file__).parent / 'logs'
LOG_DIR.mkdir(exist_ok=True)
MEMORY_LOG_FILE = LOG_DIR / 'memory_usage.csv'

# CSV Headers
CSV_HEADERS = 'timestamp,process_mb,threshold_mb,alert_sent\n'

# Initialize log file
if not MEMORY_LOG_FILE.exists():
    MEMORY_LOG_FILE.write_text(CSV_HEADERS)

# ══════════════════════════════════════════════════════════════════════════════
# LOGGING
# ══════════════════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / 'memory_monitor.log')
    ]
)
log = logging.getLogger('MemoryMonitor')


# ══════════════════════════════════════════════════════════════════════════════
# MEMORY MEASUREMENT
# ══════════════════════════════════════════════════════════════════════════════

class MemoryMeter:
    """Measure current process memory usage."""
    
    @staticmethod
    def get_process_memory_mb() -> float:
        """
        Get current process memory usage in MB.
        
        Returns:
            Memory usage in MB
        """
        if PSUTIL_AVAILABLE:
            process = psutil.Process(os.getpid())
            # Get RSS (Resident Set Size) in bytes, convert to MB
            memory_bytes = process.memory_info().rss
            return memory_bytes / (1024 * 1024)
        else:
            # Fallback: Read from /proc/self/status
            try:
                with open('/proc/self/status', 'r') as f:
                    for line in f:
                        if line.startswith('VmRSS:'):
                            # VmRSS is in kB
                            memory_kb = int(line.split()[1])
                            return memory_kb / 1024
            except Exception:
                pass
            return 0.0
    
    @staticmethod
    def get_system_memory_mb() -> dict:
        """
        Get system memory statistics.
        
        Returns:
            Dict with total, available, used, percent
        """
        if PSUTIL_AVAILABLE:
            mem = psutil.virtual_memory()
            return {
                'total': mem.total / (1024 * 1024),
                'available': mem.available / (1024 * 1024),
                'used': mem.used / (1024 * 1024),
                'percent': mem.percent
            }
        return {'total': 0, 'available': 0, 'used': 0, 'percent': 0}


# ══════════════════════════════════════════════════════════════════════════════
# TELEGRAM ALERTS
# ══════════════════════════════════════════════════════════════════════════════

class TelegramAlerter:
    """Send alerts via Telegram."""
    
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.enabled = bool(bot_token and chat_id)
        
        if not self.enabled:
            log.warning("Telegram alerts DISABLED - no token/chat_id configured")
    
    def send_alert(self, message: str) -> bool:
        """
        Send alert via Telegram.
        
        Args:
            message: Alert message text
            
        Returns:
            True if sent successfully
        """
        if not self.enabled:
            return False
        
        try:
            import urllib.request
            import urllib.parse
            
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            
            data = json.dumps({
                'chat_id': self.chat_id,
                'text': message,
                'parse_mode': 'HTML'
            }).encode('utf-8')
            
            req = urllib.request.Request(
                url,
                data=data,
                headers={'Content-Type': 'application/json'}
            )
            
            with urllib.request.urlopen(req, timeout=10) as response:
                result = json.loads(response.read().decode('utf-8'))
                return result.get('ok', False)
                
        except Exception as e:
            log.error(f"Failed to send Telegram alert: {e}")
            return False


# ══════════════════════════════════════════════════════════════════════════════
# MEMORY MONITOR
# ══════════════════════════════════════════════════════════════════════════════

class MemoryMonitor:
    """
    Monitor memory usage and alert when threshold crossed.
    
    Features:
    - Polls memory every 30 seconds
    - Logs to CSV file
    - Sends Telegram alert when threshold exceeded
    """
    
    def __init__(
        self,
        threshold_mb: float = MEMORY_THRESHOLD_MB,
        poll_interval: int = POLL_INTERVAL
    ):
        self.threshold_mb = threshold_mb
        self.poll_interval = poll_interval
        self.meter = MemoryMeter()
        self.alerter = TelegramAlerter(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
        self.last_alert_time = 0
        self.alert_cooldown = 300  # 5 minutes between alerts
        
    def check_memory(self) -> dict:
        """
        Check current memory usage.
        
        Returns:
            Dict with memory stats and alert status
        """
        process_mb = self.meter.get_process_memory_mb()
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Check threshold
        alert_sent = False
        if process_mb >= self.threshold_mb:
            # Check cooldown
            now = time.time()
            if now - self.last_alert_time >= self.alert_cooldown:
                # Send alert
                message = (
                    f"⚠️ <b>MEMORY WARNING</b>\n\n"
                    f"Process: {process_mb:.1f}MB / {self.threshold_mb:.0f}MB limit\n"
                    f"Time: {timestamp}\n"
                    f"PID: {os.getpid()}"
                )
                
                if self.alerter.send_alert(message):
                    alert_sent = True
                    self.last_alert_time = now
                    log.warning(f"MEMORY ALERT SENT: {process_mb:.1f}MB / {self.threshold_mb:.0f}MB")
                else:
                    log.warning(f"MEMORY THRESHOLD EXCEEDED: {process_mb:.1f}MB / {self.threshold_mb:.0f}MB")
            else:
                log.debug(f"Memory alert on cooldown ({self.alert_cooldown - (now - self.last_alert_time):.0f}s remaining)")
        
        # Log to CSV
        self._log_usage(process_mb, alert_sent)
        
        return {
            'process_mb': process_mb,
            'threshold_mb': self.threshold_mb,
            'alert_sent': alert_sent,
            'timestamp': timestamp
        }
    
    def _log_usage(self, process_mb: float, alert_sent: bool):
        """Log memory usage to CSV."""
        timestamp = datetime.now(timezone.utc).isoformat()
        row = f'{timestamp},{process_mb:.2f},{self.threshold_mb},{alert_sent}\n'
        
        with open(MEMORY_LOG_FILE, 'a') as f:
            f.write(row)
    
    def run_continuous(self):
        """Run continuous memory monitoring."""
        log.info(f"Starting memory monitor (threshold: {self.threshold_mb}MB, interval: {self.poll_interval}s)")
        
        try:
            while True:
                result = self.check_memory()
                log.info(f"[MEMORY] {result['process_mb']:.1f}MB / {self.threshold_mb:.0f}MB limit")
                time.sleep(self.poll_interval)
        except KeyboardInterrupt:
            log.info("Memory monitor stopped")
    
    def run_once(self):
        """Run single memory check."""
        result = self.check_memory()
        print(f"[MEMORY] {result['process_mb']:.1f}MB / {self.threshold_mb:.0f}MB limit")
        return result
    
    def test_alert(self):
        """Test Telegram alert functionality."""
        log.info("Testing Telegram alert...")
        
        message = (
            f"✅ <b>MEMORY MONITOR TEST</b>\n\n"
            f"Process: 0.0MB / {self.threshold_mb:.0f}MB limit\n"
            f"Time: {datetime.now(timezone.utc).isoformat()}\n"
            f"PID: {os.getpid()}\n\n"
            f"Alert system is working correctly."
        )
        
        if self.alerter.send_alert(message):
            log.info("Test alert sent successfully")
            return True
        else:
            log.error("Failed to send test alert")
            return False


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Memory Usage Monitor')
    parser.add_argument('--test', action='store_true', help='Test Telegram alert')
    parser.add_argument('--once', action='store_true', help='Run single check')
    parser.add_argument('--threshold', type=float, default=MEMORY_THRESHOLD_MB, help='Memory threshold in MB')
    parser.add_argument('--interval', type=int, default=POLL_INTERVAL, help='Poll interval in seconds')
    
    args = parser.parse_args()
    
    monitor = MemoryMonitor(
        threshold_mb=args.threshold,
        poll_interval=args.interval
    )
    
    if args.test:
        monitor.test_alert()
    elif args.once:
        monitor.run_once()
    else:
        monitor.run_continuous()


if __name__ == '__main__':
    main()
