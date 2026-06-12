"""News Lockout Engine

Automatically protects trading during macro events.
Supports pre-news lock, post-news cooldown, dynamic cooldown based on volatility,
and emergency halt mode.
"""

import time
import logging
import math
import json
from typing import List, Dict, Optional, Any, Tuple
from pathlib import Path
from datetime import datetime, timezone, timedelta

from production.forex_factory_news import ForexFactoryNews

log = logging.getLogger(__name__)

HIGH_IMPACT_EVENTS = [
    'CPI', 'PPI', 'NFP', 'FOMC', 'POWELL', 'ECB', 'BOE', 'BOJ',
    'GDP', 'CORE INFLATION', 'PMI', 'ISM', 'RETAIL SALES',
]

PRE_LOCK_MINUTES = 15
POST_LOCK_MINUTES = 10
EMERGENCY_COOLDOWN_MINUTES = 60

NEWS_FILE = Path(__file__).parent.parent / 'data' / 'known_events.json'


class NewsLockoutEngine:
    """Monitors economic events and locks trading during high-impact releases."""

    def __init__(self):
        self._active_lock: Optional[Dict[str, Any]] = None
        self._emergency_mode = False
        self._emergency_until: Optional[float] = None
        self._volatility_spike = False

    def check(self, symbol: str = 'XAUUSD',
              volatility: Optional[float] = None,
              current_price: Optional[float] = None,
              atr: Optional[float] = None) -> Dict[str, Any]:
        result = {
            'locked': False,
            'lock_type': '',
            'reason': '',
            'remaining_seconds': 0,
            'emergency': self._emergency_mode,
            'volatility_spike': False,
            'events': [],
        }
        try:
            now = time.time()

            # -- Emergency mode check --
            if self._emergency_mode:
                if self._emergency_until and now < self._emergency_until:
                    remaining = int(self._emergency_until - now)
                    result['locked'] = True
                    result['lock_type'] = 'EMERGENCY'
                    result['reason'] = 'Emergency halt mode active'
                    result['remaining_seconds'] = remaining
                    return result
                self._emergency_mode = False
                self._emergency_until = None

            # -- Volatility spike check --
            if volatility is not None and atr and atr > 0:
                vol_ratio = volatility / atr
                if vol_ratio > 2.5:
                    self._volatility_spike = True
                    result['volatility_spike'] = True
                    result['locked'] = True
                    result['lock_type'] = 'VOLATILITY'
                    result['reason'] = f'Volatility spike: {vol_ratio:.1f}x ATR'
                    result['remaining_seconds'] = int(POST_LOCK_MINUTES * 60 * (vol_ratio / 2.5))
                    return result

            self._volatility_spike = False

            # -- Load upcoming news events --
            events = self._load_events()
            now_dt = datetime.now(timezone.utc)

            active_events = []
            for ev in events:
                ev_ts = ev.get('timestamp', '')
                ev_title = ev.get('title', '').upper()
                ev_impact = ev.get('impact', '').upper()

                if ev_impact not in ('HIGH', 'MEDIUM'):
                    continue

                try:
                    ev_dt = datetime.fromisoformat(ev_ts)
                except (ValueError, TypeError):
                    continue

                ev_unix = ev_dt.timestamp()
                pre_lock_sec = PRE_LOCK_MINUTES * 60
                post_lock_sec = POST_LOCK_MINUTES * 60

                if volatility is not None and atr and atr > 0:
                    v = volatility / atr
                    if v > 2.0:
                        post_lock_sec = int(post_lock_sec * min(v, 3.0))
                    if v > 1.5 and ev_impact == 'HIGH':
                        pre_lock_sec = int(pre_lock_sec * min(v * 0.8, 2.0))

                lock_start = ev_unix - pre_lock_sec
                lock_end = ev_unix + post_lock_sec

                if lock_start <= now <= lock_end:
                    active_events.append({
                        'title': ev_title,
                        'impact': ev_impact,
                        'timestamp': ev_ts,
                        'remaining': int(lock_end - now),
                        'stage': 'pre' if now < ev_unix else 'post',
                    })

            if active_events:
                active_events.sort(key=lambda x: x['remaining'])
                top = active_events[0]
                result['locked'] = True
                result['lock_type'] = f"PRE_{top['stage'].upper()}"
                result['reason'] = f"{top['title']} ({top['impact']}) - {top['stage']}-event lock"
                result['remaining_seconds'] = top['remaining']
                result['events'] = active_events
                self._active_lock = top
            else:
                self._active_lock = None

        except Exception as e:
            log.warning(f"NewsLockoutEngine.check error: {e}")
            result['error'] = str(e)

        return result

    def trigger_emergency(self, reason: str = 'Geopolitical emergency',
                          duration_minutes: int = 60) -> Dict[str, Any]:
        self._emergency_mode = True
        self._emergency_until = time.time() + (duration_minutes * 60)
        return {
            'locked': True,
            'lock_type': 'EMERGENCY',
            'reason': reason,
            'remaining_seconds': duration_minutes * 60,
            'emergency': True,
        }

    def clear_emergency(self) -> None:
        self._emergency_mode = False
        self._emergency_until = None

    def is_locked(self) -> bool:
        return self._active_lock is not None or self._emergency_mode or self._volatility_spike

    def get_lock_status(self) -> Dict[str, Any]:
        return {
            'locked': self.is_locked(),
            'active_lock': self._active_lock,
            'emergency': self._emergency_mode,
            'volatility_spike': self._volatility_spike,
        }

    def add_event(self, title: str, timestamp: str, impact: str = 'HIGH',
                  currency: str = 'USD') -> None:
        events = self._load_events()
        events.append({
            'title': title,
            'timestamp': timestamp,
            'impact': impact.upper(),
            'currency': currency.upper(),
        })
        try:
            NEWS_FILE.parent.mkdir(parents=True, exist_ok=True)
            NEWS_FILE.write_text(json.dumps(events, indent=2))
        except Exception as e:
            log.warning(f"Could not save event: {e}")

    def _load_events(self) -> List[Dict]:
        # 1) Primary: ForexFactoryNews live data
        try:
            ff = ForexFactoryNews.get_instance()
            ff.fetch_today()
            upcoming = ff.get_upcoming_high_impact(max_items=20, minutes=60)
            if upcoming:
                mapped = []
                for ev in upcoming:
                    mapped.append({
                        'title': ev.get('event', ev.get('title', 'Unknown')),
                        'timestamp': ev.get('timestamp', ''),
                        'impact': ev.get('impact', 'HIGH'),
                        'currency': ev.get('currency', 'USD'),
                    })
                now = time.time()
                cutoff = now - 86400
                fresh = [ev for ev in mapped if self._event_is_fresh(ev, cutoff)]
                if fresh:
                    return fresh
        except Exception as e:
            log.debug(f"ForexFactoryNews unavailable: {e}")

        # 2) Fallback: known_events.json
        try:
            if NEWS_FILE.exists():
                data = json.loads(NEWS_FILE.read_text())
                if isinstance(data, list):
                    now = time.time()
                    cutoff = now - 86400
                    fresh = [ev for ev in data if self._event_is_fresh(ev, cutoff)]
                    if fresh:
                        return fresh
        except Exception as e:
            log.debug(f"Could not load known_events.json: {e}")

        # 3) Last resort: generated defaults
        return self._default_events()

    def _event_is_fresh(self, ev: Dict, cutoff: float) -> bool:
        try:
            ev_ts = ev.get('timestamp', '')
            if not ev_ts:
                return False
            ev_dt = datetime.fromisoformat(ev_ts)
            return ev_dt.timestamp() > cutoff
        except (ValueError, TypeError):
            return False

    def _default_events(self) -> List[Dict]:
        now = datetime.now(timezone.utc)
        week_ahead = now + timedelta(days=7)
        return [
            {
                'title': 'NFP',
                'timestamp': self._next_weekday(now, 5, week_ahead).isoformat(),
                'impact': 'HIGH',
                'currency': 'USD',
            },
            {
                'title': 'CPI',
                'timestamp': self._next_weekday(now, 3, week_ahead).isoformat(),
                'impact': 'HIGH',
                'currency': 'USD',
            },
            {
                'title': 'FOMC',
                'timestamp': self._next_weekday(now, 4, week_ahead).isoformat(),
                'impact': 'HIGH',
                'currency': 'USD',
            },
            {
                'title': 'PPI',
                'timestamp': self._next_weekday(now, 2, week_ahead).isoformat(),
                'impact': 'HIGH',
                'currency': 'USD',
            },
        ]

    @staticmethod
    def _next_weekday(from_dt: datetime, weekday: int,
                      until: datetime) -> datetime:
        days_ahead = weekday - from_dt.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        candidate = from_dt + timedelta(days=days_ahead)
        if candidate > until:
            candidate = from_dt + timedelta(days=days_ahead - 7)
        return candidate.replace(hour=13, minute=30, second=0, microsecond=0)


_lockout: Optional[NewsLockoutEngine] = None


def get_news_lockout() -> NewsLockoutEngine:
    global _lockout
    if _lockout is None:
        _lockout = NewsLockoutEngine()
    return _lockout


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    nl = get_news_lockout()
    result = nl.check('XAUUSD', volatility=8.0, atr=5.0)
    print(f"Locked: {result['locked']}, Type: {result['lock_type']}")
    print(f"Reason: {result['reason']}")
    print(f"Remaining: {result['remaining_seconds']}s")
    em = nl.trigger_emergency('Test emergency')
    print(f"Emergency: {em['locked']}, Reason: {em['reason']}")
