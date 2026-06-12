"""
Daily Performance Report - OMNI BRAIN V2
=========================================
Generate daily performance reports at 23:59 UTC.

Collects from logs/:
  - All signals fired today per asset
  - Confidence scores distribution
  - EXECUTE/WAIT/BLOCK counts
  - Circuit breaker triggers
  - MTF confirmation rate
  - Threshold adaptations
"""

import os
import json
import csv
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from pathlib import Path
from collections import defaultdict

log = logging.getLogger('DailyReport')

LOG_DIR = Path(__file__).parent / 'logs'
LOG_DIR.mkdir(exist_ok=True)

REPORTS_DIR = LOG_DIR / 'reports'
REPORTS_DIR.mkdir(exist_ok=True)

ASSETS = ['XAUUSD', 'EURUSD', 'GBPUSD', 'SP500']


class DailyReport:
    """
    Daily performance report generator.
    
    Collects and aggregates daily trading data.
    """
    
    def __init__(self):
        self.start_time = time.time()
    
    def collect_signals(self, date: Optional[str] = None) -> List[Dict[str, Any]]:
        """Collect all signals from today's log."""
        if date is None:
            date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        
        signals = []
        log_file = LOG_DIR / 'signal_log.csv'
        
        if not log_file.exists():
            return signals
        
        try:
            with open(log_file, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    ts = row.get('timestamp', '')
                    if ts.startswith(date):
                        signals.append(row)
        except Exception as e:
            log.error(f"Failed to collect signals: {e}")
        
        return signals
    
    def collect_circuit_breaker_events(self, date: Optional[str] = None) -> List[Dict[str, Any]]:
        """Collect circuit breaker events from today."""
        if date is None:
            date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        
        events = []
        cb_file = LOG_DIR / 'circuit_state.json'
        
        if cb_file.exists():
            try:
                with open(cb_file, 'r') as f:
                    data = json.load(f)
                
                for symbol, state in data.get('assets', {}).items():
                    triggered = state.get('triggered_at', '')
                    if triggered and triggered.startswith(date):
                        events.append({
                            'symbol': symbol,
                            'reason': state.get('reason', 'Unknown'),
                            'state': state.get('state', 'Unknown'),
                            'triggered_at': triggered
                        })
            except Exception as e:
                log.debug(f"Failed to collect CB events: {e}")
        
        return events
    
    def calculate_stats(self, signals: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate statistics from signals."""
        if not signals:
            return {
                'total': 0,
                'execute': 0,
                'wait': 0,
                'block': 0,
                'execute_pct': 0,
                'wait_pct': 0,
                'block_pct': 0,
                'avg_score': 0,
                'best_asset': 'N/A',
                'best_asset_avg': 0,
                'worst_asset': 'N/A',
                'worst_asset_avg': 0,
                'per_asset': {},
                'per_tf': {}
            }
        
        total = len(signals)
        execute = 0
        wait = 0
        block = 0
        scores = []
        per_asset = defaultdict(lambda: {'count': 0, 'scores': []})
        per_tf = defaultdict(lambda: {'count': 0, 'scores': []})
        
        for sig in signals:
            score = int(sig.get('score', 0))
            scores.append(score)
            
            # Determine decision from score
            if score >= 75:
                execute += 1
                decision = 'EXECUTE'
            elif score >= 50:
                wait += 1
                decision = 'WAIT'
            else:
                block += 1
                decision = 'BLOCK'
            
            symbol = sig.get('symbol', 'UNKNOWN')
            per_asset[symbol]['count'] += 1
            per_asset[symbol]['scores'].append(score)
            
            tf = sig.get('tf', 'UNKNOWN')
            per_tf[tf]['count'] += 1
            per_tf[tf]['scores'].append(score)
        
        # Calculate averages
        for asset in per_asset:
            asset_scores = per_asset[asset]['scores']
            per_asset[asset]['avg_score'] = sum(asset_scores) / len(asset_scores) if asset_scores else 0
        
        for tf in per_tf:
            tf_scores = per_tf[tf]['scores']
            per_tf[tf]['avg_score'] = sum(tf_scores) / len(tf_scores) if tf_scores else 0
        
        # Find best/worst
        best_asset = max(per_asset.items(), key=lambda x: x[1]['avg_score']) if per_asset else ('N/A', {'avg_score': 0})
        worst_asset = min(per_asset.items(), key=lambda x: x[1]['avg_score']) if per_asset else ('N/A', {'avg_score': 0})
        
        return {
            'total': total,
            'execute': execute,
            'wait': wait,
            'block': block,
            'execute_pct': (execute / total * 100) if total > 0 else 0,
            'wait_pct': (wait / total * 100) if total > 0 else 0,
            'block_pct': (block / total * 100) if total > 0 else 0,
            'avg_score': sum(scores) / len(scores) if scores else 0,
            'best_asset': best_asset[0],
            'best_asset_avg': best_asset[1]['avg_score'],
            'worst_asset': worst_asset[0],
            'worst_asset_avg': worst_asset[1]['avg_score'],
            'per_asset': dict(per_asset),
            'per_tf': dict(per_tf)
        }
    
    def generate_report(self, date: Optional[str] = None) -> Dict[str, Any]:
        """Generate complete daily report."""
        if date is None:
            date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        
        log.info(f"Generating report for {date}...")
        
        signals = self.collect_signals(date)
        cb_events = self.collect_circuit_breaker_events(date)
        stats = self.calculate_stats(signals)
        
        report = {
            'date': date,
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'signals': stats,
            'circuit_breaker': {
                'triggers': len(cb_events),
                'events': cb_events
            },
            'mtf_conflicts': 0,  # Would need MTF log
            'threshold_adaptations': 0,  # Would need threshold log
            'memory_peak_mb': self._get_memory_peak(),
            'uptime_hours': (time.time() - self.start_time) / 3600
        }
        
        return report
    
    def _get_memory_peak(self) -> float:
        """Get peak memory usage."""
        try:
            import psutil
            process = psutil.Process(os.getpid())
            return process.memory_info().rss / (1024 * 1024)
        except Exception:
            return 0
    
    def format_report(self, report: Dict[str, Any]) -> str:
        """Format report for terminal/Telegram display."""
        date = report['date']
        sigs = report['signals']
        cb = report['circuit_breaker']
        
        lines = [
            "📊 DAILY PERFORMANCE REPORT",
            f"Date: {date}",
            "─────────────────────────────",
            f"Total Signals : {sigs['total']}",
            f"EXECUTE       : {sigs['execute']} ({sigs['execute_pct']:.0f}%)",
            f"WAIT          : {sigs['wait']} ({sigs['wait_pct']:.0f}%)",
            f"BLOCK         : {sigs['block']} ({sigs['block_pct']:.0f}%)",
            "─────────────────────────────",
            f"Avg Score     : {sigs['avg_score']:.1f}",
            f"Best Asset    : {sigs['best_asset']} ({sigs['best_asset_avg']:.1f} avg)",
            f"Worst Asset   : {sigs['worst_asset']} ({sigs['worst_asset_avg']:.1f} avg)",
            "─────────────────────────────",
            f"CB Triggers   : {cb['triggers']}",
            f"Memory Peak   : {report['memory_peak_mb']:.1f}MB",
            f"Uptime        : {report['uptime_hours']:.1f}h"
        ]
        
        return '\n'.join(lines)
    
    def save_report(self, report: Dict[str, Any]) -> None:
        """Save report to files."""
        date = report['date']
        
        # Save JSON
        json_path = REPORTS_DIR / f'daily_{date}.json'
        try:
            with open(json_path, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            log.info(f"Saved JSON report: {json_path}")
        except Exception as e:
            log.error(f"Failed to save JSON: {e}")
        
        # Save human-readable
        txt_path = REPORTS_DIR / f'daily_{date}.txt'
        try:
            with open(txt_path, 'w') as f:
                f.write(self.format_report(report))
            log.info(f"Saved TXT report: {txt_path}")
        except Exception as e:
            log.error(f"Failed to save TXT: {e}")
    
    def send_telegram(self, report: Dict[str, Any]) -> bool:
        """Send report to Telegram."""
        try:
            import urllib.request
            
            bot_token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
            chat_id = os.environ.get('TELEGRAM_CHAT_ID', '')
            
            if not bot_token or not chat_id:
                return False
            
            message = self.format_report(report)
            
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            data = json.dumps({'chat_id': chat_id, 'text': message}).encode('utf-8')
            
            req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
            urllib.request.urlopen(req, timeout=10)
            
            log.info("Report sent to Telegram")
            return True
        except Exception as e:
            log.error(f"Failed to send to Telegram: {e}")
            return False
    
    def run_weekly_proof(self, bot_send_fn=None):
        """Generate weekly proof post if it's Sunday."""
        now = datetime.now(timezone.utc)
        if now.weekday() != 6:  # Sunday
            return None
        try:
            import sys
            from pathlib import Path as PPath
            content_dir = PPath(__file__).parent.parent / 'content'
            sys.path.insert(0, str(content_dir))
            from proof_post_generator import ProofPostGenerator
            gen = ProofPostGenerator()
            result = gen.load_weekly_stats()
            if result:
                gen.run_weekly_generation(bot_send_fn=bot_send_fn)
                log.info("Weekly proof post generated")
            return result
        except Exception as e:
            log.warning(f"Weekly proof post skipped: {e}")
            return None

    def run_calibration_check(self):
        """Run daily calibration engine check."""
        try:
            sys.path.insert(0, str(PPath(__file__).parent))
            from calibration_engine import get_calibration_engine
            ce = get_calibration_engine()
            result = ce.get_daily_calibration()
            if result.get('calibration'):
                log.info(f"Calibration weights tuned: {result['calibration']['adjustments']}")
            return result
        except Exception as e:
            log.debug(f"Calibration check skipped: {e}")
            return None

    def run_onboarding_schedule(self, bot_send_fn=None):
        """Run daily onboarding message scheduler."""
        try:
            from subscription_manager import get_subscription_manager
            sm = get_subscription_manager()
            sm.schedule_onboarding(bot_send_fn)
        except Exception as e:
            log.debug(f"Onboarding scheduler skipped: {e}")

    def run_inactive_check(self, bot_send_fn=None):
        """Check for inactive users and send re-engagement."""
        try:
            from subscription_manager import get_subscription_manager
            sm = get_subscription_manager()
            inactive = sm.check_inactive_users(7)
            for chat_id in inactive:
                msg = sm.get_re_engagement_message(1)
                if bot_send_fn and msg:
                    try:
                        bot_send_fn(chat_id, msg)
                    except Exception:
                        pass
            inactive_30 = sm.check_inactive_users(30)
            for chat_id in inactive_30:
                msg = sm.get_re_engagement_message(2)
                if bot_send_fn and msg:
                    try:
                        bot_send_fn(chat_id, msg)
                    except Exception:
                        pass
        except Exception as e:
            log.debug(f"Inactive check skipped: {e}")

    def run(self, date: Optional[str] = None) -> Dict[str, Any]:
        """Run complete report generation."""
        report = self.generate_report(date)
        self.save_report(report)
        self.send_telegram(report)
        return report


# Global instance
_daily_report: Optional[DailyReport] = None


def get_daily_report() -> DailyReport:
    """Get or create global daily report instance."""
    global _daily_report
    if _daily_report is None:
        _daily_report = DailyReport()
    return _daily_report


# ══════════════════════════════════════════════════════════════════════════════
# CLI TEST
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import sys
    
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    if '--test' in sys.argv:
        print("=" * 60)
        print("  DAILY PERFORMANCE REPORT - TEST")
        print("=" * 60)
        
        report = DailyReport()
        
        # Generate report
        result = report.generate_report()
        
        # Print formatted
        print("\n" + report.format_report(result))
        
        # Save
        report.save_report(result)
        
        print("\n" + "=" * 60)
    else:
        print("Usage: python daily_report.py --test")
