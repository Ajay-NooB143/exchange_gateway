"""
Forex Factory News Integration - OMNI BRAIN V2
Scrapes Forex Factory calendar for economic events and blocks signals around high-impact news.
"""
import os, json, logging, re, time, urllib.request
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from pathlib import Path

log = logging.getLogger('ForexFactoryNews')
LOG_DIR = Path(__file__).parent / 'logs'

CURRENCY_TO_PAIRS = {
    'USD': ['XAUUSD', 'EURUSD', 'GBPUSD', 'SP500', 'US30', 'NAS100', 'USDJPY', 'USDCHF', 'USDCAD'],
    'EUR': ['EURUSD', 'EURJPY', 'EURCHF', 'EURGBP'],
    'GBP': ['GBPUSD', 'EURGBP', 'GBPJPY', 'GBPCHF'],
    'JPY': ['USDJPY', 'EURJPY', 'GBPJPY'],
    'CHF': ['USDCHF', 'EURCHF', 'GBPCHF'],
    'CAD': ['USDCAD', 'EURCAD', 'GBPCAD'],
    'AUD': ['AUDUSD', 'EURAUD', 'GBPAUD'],
    'NZD': ['NZDUSD', 'EURNZD', 'GBPNZD'],
    'XAU': ['XAUUSD'],
    'BTC': ['BTCUSD'],
}

NEWS_BLOCK_MINUTES = int(os.environ.get('NEWS_BLOCK_MINUTES', '30'))

class ForexFactoryNews:
    def __init__(self):
        self.calendar: List[Dict] = []
        self.history: List[Dict] = []
        self.last_full_fetch = 0.0
        self.last_today_fetch = 0.0
        self._load_state()
    
    def _load_state(self):
        for name in ('news_calendar.json', 'news_history.json'):
            path = LOG_DIR / name
            if path.exists():
                try:
                    with open(path) as f: data = json.load(f)
                    if name == 'news_calendar.json': self.calendar = data
                    else: self.history = data
                except Exception as e:
                    log.debug(f"Failed to load news state: {e}")

    def _save_calendar(self):
        try:
            with open(LOG_DIR / 'news_calendar.json', 'w') as f:
                json.dump(self.calendar, f, indent=2)
        except Exception as e:
            log.debug(f"Failed to save news calendar: {e}")

    def _save_history(self):
        try:
            with open(LOG_DIR / 'news_history.json', 'w') as f:
                json.dump(self.history[-200:], f, indent=2)
        except Exception as e:
            log.debug(f"Failed to save news history: {e}")
    
    def fetch_calendar(self, force: bool = False):
        """Fetch Forex Factory calendar HTML and parse events."""
        now = time.time()
        if not force and now - self.last_full_fetch < 21600:  # 6 hours
            return
        self.last_full_fetch = now
        
        url = 'https://www.forexfactory.com/calendar'
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml',
            'Accept-Language': 'en-US,en;q=0.9',
            'Cache-Control': 'no-cache',
        }
        try:
            req = urllib.request.Request(url, headers=headers)
            resp = urllib.request.urlopen(req, timeout=15)
            html = resp.read().decode('utf-8', errors='ignore')
            self.calendar = self._parse_html(html)
            log.info(f"Forex Factory: fetched {len(self.calendar)} events")
            self._save_calendar()
        except Exception as e:
            log.warning(f"Forex Factory fetch failed: {e}")
            if not self.calendar:
                self.calendar = self._fallback_calendar()
    
    def fetch_today(self):
        """Refresh today's events more frequently."""
        now = time.time()
        if now - self.last_today_fetch < 1800:  # 30 min
            return
        self.last_today_fetch = now
        self.fetch_calendar(force=True)
    
    def _parse_html(self, html: str) -> List[Dict]:
        """Parse Forex Factory HTML to extract events."""
        events = []
        rows = re.findall(r'<tr[^>]*class="calendar__row[^"]*"[^>]*>(.*?)</tr>', html, re.DOTALL)
        if not rows:
            rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)
        
        current_date = None
        for row in rows:
            date_match = re.search(r'class="calendar__date"[^>]*>\s*([^<]+)\s*<', row)
            if date_match:
                current_date = date_match.group(1).strip()
            
            time_match = re.search(r'class="calendar__time"[^>]*>\s*([^<]+)\s*<', row)
            currency_match = re.search(r'class="calendar__currency"[^>]*>\s*([^<]+)\s*<', row)
            event_match = re.search(r'class="calendar__event"[^>]*>\s*(?:<[^>]*>)*([^<]+(?:<[^>]*>[^<]*)*)\s*<', row)
            impact_match = re.search(r'class="calendar__impact"[^>]*>\s*(?:<[^>]*>)*\s*([^<]+)', row)
            
            if not (time_match and currency_match and event_match):
                continue
            
            event_time_str = time_match.group(1).strip()
            currency = currency_match.group(1).strip()
            event_name = re.sub(r'<[^>]+>', '', event_match.group(1)).strip()
            impact_text = impact_match.group(1).strip().upper() if impact_match else 'LOW'
            
            impact = 'LOW'
            if 'HIGH' in impact_text or impact_text == '3':
                impact = 'HIGH'
            elif 'MEDIUM' in impact_text or impact_text == '2':
                impact = 'MEDIUM'
            
            try:
                event_time = self._parse_time(current_date or '', event_time_str)
            except Exception as e:
                log.debug(f"Failed to parse event time '{event_time_str}': {e}")
                event_time = datetime.now(timezone.utc) + timedelta(days=1)
            
            events.append({
                'date': current_date or '',
                'time_str': event_time_str,
                'timestamp': event_time.isoformat(),
                'ts_unix': event_time.timestamp(),
                'currency': currency,
                'event': event_name,
                'impact': impact,
                'scraped_at': datetime.now(timezone.utc).isoformat()
            })
        
        if not events:
            return self._fallback_calendar()
        return events
    
    def _parse_time(self, date_str: str, time_str: str) -> datetime:
        now = datetime.now(timezone.utc)
        months = {'Jan':1,'Feb':2,'Mar':3,'Apr':4,'May':5,'Jun':6,'Jul':7,'Aug':8,'Sep':9,'Oct':10,'Nov':11,'Dec':12}
        try:
            for mname, mnum in months.items():
                if mname in date_str:
                    day = int(re.search(r'(\d+)', date_str).group(1))
                    year = now.year
                    if now.month == 12 and mnum == 1:
                        year += 1
                    return datetime(year, mnum, day, 0, 0, tzinfo=timezone.utc)
        except Exception as e:
            log.debug(f"Failed to parse date '{date_str}': {e}")
        return now
    
    def _fallback_calendar(self) -> List[Dict]:
        """Return fallback calendar entries."""
        now = datetime.now(timezone.utc)
        return [
            {'event': 'Fed Interest Rate Decision', 'currency': 'USD', 'impact': 'HIGH',
             'timestamp': (now + timedelta(days=1)).isoformat(), 'ts_unix': (now + timedelta(days=1)).timestamp()},
            {'event': 'US CPI Inflation Data', 'currency': 'USD', 'impact': 'HIGH',
             'timestamp': (now + timedelta(days=2)).isoformat(), 'ts_unix': (now + timedelta(days=2)).timestamp()},
            {'event': 'Non-Farm Payrolls', 'currency': 'USD', 'impact': 'HIGH',
             'timestamp': (now + timedelta(days=5)).isoformat(), 'ts_unix': (now + timedelta(days=5)).timestamp()},
        ]
    
    def check_signal_block(self, symbol: str) -> Tuple[bool, str]:
        """
        Check if signal should be blocked due to upcoming news.
        Returns (blocked, reason).
        """
        self.fetch_today()
        now = datetime.now(timezone.utc)
        now_ts = now.timestamp()
        
        for event in self.calendar:
            event_ts = event.get('ts_unix', 0)
            currency = event.get('currency', '')
            impact = event.get('impact', 'LOW')
            
            affected = CURRENCY_TO_PAIRS.get(currency, [])
            if symbol not in affected:
                continue
            
            mins_until = (event_ts - now_ts) / 60
            
            if impact == 'HIGH':
                if 0 < mins_until < NEWS_BLOCK_MINUTES:
                    return True, f"HIGH impact {event['event']} in {int(mins_until)}min ({currency}) - BLOCKED"
                if -15 < mins_until <= 0:
                    return True, f"HIGH impact {event['event']} released {int(abs(mins_until))}min ago - BLOCKED"
            
            elif impact == 'MEDIUM':
                if 0 < mins_until < 15:
                    return False, f"MEDIUM impact {event['event']} in {int(mins_until)}min - reduce score"
                if -10 < mins_until <= 0:
                    return False, f"MEDIUM impact {event['event']} released - reduce score"
        
        return False, 'clear'
    
    def get_upcoming_high_impact(self, max_items: int = 5, minutes: Optional[int] = None) -> List[Dict]:
        """Get upcoming high-impact events."""
        now_ts = datetime.now(timezone.utc).timestamp()
        upcoming = []
        for event in self.calendar:
            event_ts = event.get('ts_unix', 0)
            if event_ts > now_ts and event['impact'] in ('HIGH', 'MEDIUM'):
                mins_until = int((event_ts - now_ts) / 60)
                if minutes is not None and mins_until > minutes:
                    continue
                event['minutes_until'] = mins_until
                upcoming.append(event)
        upcoming.sort(key=lambda x: x.get('minutes_until', 999))
        return upcoming[:max_items]
    
    def get_pre_high_impact_alerts(self) -> List[Dict]:
        """Get HIGH impact events within 30 min that need Telegram pre-alert."""
        now_ts = datetime.now(timezone.utc).timestamp()
        alerts = []
        for event in self.calendar:
            event_ts = event.get('ts_unix', 0)
            if event['impact'] == 'HIGH' and event_ts > now_ts:
                mins_until = int((event_ts - now_ts) / 60)
                if 25 <= mins_until <= 30:
                    affected_pairs = CURRENCY_TO_PAIRS.get(event['currency'], [])
                    alerts.append({
                        'event': event['event'],
                        'currency': event['currency'],
                        'timestamp': event['timestamp'],
                        'minutes_until': mins_until,
                        'affected_pairs': affected_pairs,
                        'block_until': (datetime.fromtimestamp(event_ts) + timedelta(minutes=15)).strftime('%H:%M UTC')
                    })
        return alerts
    
    def check_released_events(self) -> List[Dict]:
        """Check for recently released HIGH impact events (actual vs forecast)."""
        now_ts = datetime.now(timezone.utc).timestamp()
        released = []
        for event in self.calendar:
            event_ts = event.get('ts_unix', 0)
            if event['impact'] == 'HIGH' and -60 < (now_ts - event_ts) < 0:
                forecast = event.get('forecast', 'N/A')
                actual = event.get('actual', 'N/A')
                currency = event.get('currency', '')
                affected_pairs = CURRENCY_TO_PAIRS.get(currency, [])
                result = ''
                direction = ''
                if actual != 'N/A' and forecast != 'N/A':
                    try:
                        act_f = float(actual)
                        fct_f = float(forecast)
                        diff = act_f - fct_f
                        if diff > 0:
                            result = '🟢 BEAT'
                            direction = f'BULLISH'
                        elif diff < 0:
                            result = '🔴 MISS'
                            direction = f'BEARISH'
                        else:
                            result = '🟡 INLINE'
                    except Exception as e:
                        log.debug(f"Failed to parse forecast result: {e}")
                        result = f'Actual: {actual}'
                released.append({
                    'event': event['event'],
                    'currency': currency,
                    'forecast': forecast,
                    'actual': actual,
                    'result': result,
                    'direction': direction,
                    'affected_pairs': affected_pairs,
                })
        return released
    
    def format_telegram_pre_alert(self, alert: Dict) -> str:
        """Format pre-high-impact news alert for Telegram."""
        pairs_str = ', '.join(alert['affected_pairs'][:6])
        return (
            f"📰 HIGH IMPACT NEWS INCOMING\n"
            f"Event: {alert['event']}\n"
            f"Currency: {alert['currency']}\n"
            f"Time: {alert['timestamp']} ({alert['minutes_until']} min away)\n"
            f"Affects: {pairs_str}\n"
            f"⛔ Signals BLOCKED until {alert['block_until']}"
        )
    
    def format_telegram_release(self, event: Dict) -> str:
        """Format post-release news alert for Telegram."""
        pairs_str = ', '.join(event['affected_pairs'][:6])
        bias = ''
        if event['direction'] == 'BULLISH':
            bias = f"\nSignal bias shift: {event['affected_pairs'][0]} BEARISH pressure" if event['currency'] == 'USD' else ''
        elif event['direction'] == 'BEARISH':
            bias = f"\nSignal bias shift: {event['affected_pairs'][0]} BULLISH pressure" if event['currency'] == 'USD' else ''
        return (
            f"📊 NEWS RELEASED\n"
            f"Event: {event['event']}\n"
            f"Forecast: {event['forecast']} | Actual: {event['actual']}\n"
            f"Result: {event['result']}\n"
            f"Impact: {event['currency']} {event['direction']}{bias}"
        )
    
    def format_terminal(self) -> str:
        upcoming = self.get_upcoming_high_impact(3)
        if not upcoming:
            return "[NEWS] All clear for next 2h ✅"
        lines = []
        for ev in upcoming:
            mins = ev.get('minutes_until', 0)
            icon = '⛔' if ev['impact'] == 'HIGH' else '⚠️'
            if mins < NEWS_BLOCK_MINUTES and ev['impact'] == 'HIGH':
                lines.append(f"[NEWS] {ev['event']} in {mins}min {icon} BLOCKING")
            else:
                lines.append(f"[NEWS] {ev['event']} in {mins//60}h {mins%60}m {icon}")
        return "\n".join(lines)

    @classmethod
    def get_instance(cls) -> 'ForexFactoryNews':
        global _news
        if _news is None:
            _news = cls()
        return _news

# Global instance
_news: Optional[ForexFactoryNews] = None

def get_forex_factory_news() -> ForexFactoryNews:
    global _news
    if _news is None:
        _news = ForexFactoryNews()
    return _news
