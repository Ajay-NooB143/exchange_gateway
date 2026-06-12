"""
Auto Poster - OMNI BRAIN V2
=============================
Generate ready-to-post Instagram content daily.
Morning market outlook, signal posts, evening results, weekly reviews.

Features:
  - Morning post (08:00 UTC)
  - Signal post (on each EXECUTE)
  - Evening post (20:00 UTC)
  - Weekly Sunday post
  - Hinglish captions with hashtags
  - Save to content/daily/{date}/
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from pathlib import Path

log = logging.getLogger('AutoPoster')

CONTENT_DIR = Path(__file__).parent
DAILY_DIR = CONTENT_DIR / 'daily'
WEEKLY_DIR = CONTENT_DIR / 'weekly'
SHOWCASE_DIR = CONTENT_DIR / 'showcase'

DAILY_DIR.mkdir(parents=True, exist_ok=True)
WEEKLY_DIR.mkdir(parents=True, exist_ok=True)
SHOWCASE_DIR.mkdir(parents=True, exist_ok=True)

HASHTAGS = (
    '#forexsignals #XAUUSD #SMC #smartmoney #forexhindi #trading '
    '#liquidity #orderblock #forextrader #passiveincome #tradingsetup '
    '#forexstrategy #priceaction #technicalanalysis #tradingtips '
    '#forexmarket #daytrading #swingtrading #forexlife #tradingpsychology'
)

HASHTAGS_SHORT = '#forex #XAUUSD #SMC #trading #forexhindi #passiveincome'


def generate_morning_post(date: Optional[str] = None, yield_status: str = '',
                          news_today: str = '', session_plan: str = '',
                          threshold: int = 75) -> str:
    """Generate morning market outlook post."""
    if date is None:
        date = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    post = (
        f"\U0001f305 Aaj ke market outlook \U0001f3af\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"{datetime.now(timezone.utc).strftime('%A, %d %B %Y')}\n\n"
        f"\U0001f4c8 Yield Curve: {yield_status if yield_status else 'Checking...'}\n"
        f"\U0001f4f0 News Today: {news_today if news_today else 'No major events'}\n"
        f"\U0001f3e0 Session Plan: {session_plan if session_plan else 'London/NY session focus'}\n\n"
        f"\U0001f3af Score Threshold: {threshold}\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"Follow for live signals \U0001f446\n\n"
        f"{HASHTAGS_SHORT}"
    )

    post_dir = DAILY_DIR / date / 'morning_posts'
    post_dir.mkdir(parents=True, exist_ok=True)
    filepath = post_dir / f'morning_post_{date}.txt'
    with open(filepath, 'w') as f:
        f.write(post)
    log.info(f"Morning post saved: {filepath}")
    return post


def generate_signal_post(symbol: str, direction: str, score: int, pnl: float = 0,
                         win_rate: float = 0, date: Optional[str] = None) -> str:
    """Generate signal post on EXECUTE."""
    if date is None:
        date = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    emoji = '\U0001f534' if direction in ('BULLISH', 'LONG', 'BUY') else '\U0001f7e2'
    pnl_str = f"Paper P&L: ${pnl:+.2f}" if pnl else ''
    wr_str = f"Win rate: {win_rate:.0f}%" if win_rate else ''

    script = (
        f"\U0001f680 SIGNAL DETECTED\n"
        f"{emoji} {symbol} {direction}\n"
        f"Score: {score}/100\n"
        f"{pnl_str}\n"
        f"{wr_str}\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"Bhaari paisa \U0001f4b0\n"
        f"\n"
        f"{HASHTAGS}"
    )

    reel_script = (
        f"[REEL SCRIPT - {symbol} {direction}]\n"
        f"\u23f1\ufe0f 0-3s: Show chart with {direction.lower()} arrow\n"
        f"\u23f1\ufe0f 3-7s: Score {score}/100 dikh raha hai\n"
        f"\u23f1\ufe0f 7-12s: Entry/SL/TP levels\n"
        f"\u23f1\ufe0f 12-15s: CTA - Link in bio\n"
        f"\nCaption:\n{script}"
    )

    post_dir = DAILY_DIR / date / 'signal_posts'
    post_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime('%H%M%S')
    filepath = post_dir / f'signal_{date}_{timestamp}_{symbol}.txt'
    with open(filepath, 'w') as f:
        f.write(reel_script)
    log.info(f"Signal post saved: {filepath}")
    return reel_script


def generate_evening_post(signals_today: int = 0, winners: int = 0,
                          win_pct: float = 0, pnl: float = 0,
                          date: Optional[str] = None) -> str:
    """Generate evening results post."""
    if date is None:
        date = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    pnl_emoji = '\U0001f7e2' if pnl >= 0 else '\U0001f534'

    post = (
        f"\U0001f4ca Aaj ke results \U0001f4ca\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"{signals_today} signals today\n"
        f"{winners} winners ({win_pct:.0f}%)\n"
        f"Paper P&L: {pnl_emoji} ${pnl:+.2f}\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"Kal milte hain! \U0001f680\n\n"
        f"{HASHTAGS_SHORT}"
    )

    post_dir = DAILY_DIR / date / 'evening_posts'
    post_dir.mkdir(parents=True, exist_ok=True)
    filepath = post_dir / f'evening_post_{date}.txt'
    with open(filepath, 'w') as f:
        f.write(post)
    log.info(f"Evening post saved: {filepath}")
    return post


def generate_weekly_post(week_data: Dict[str, Any]) -> str:
    """Generate weekly Sunday post."""
    week_num = week_data.get('week', 0)
    date_range = week_data.get('date_range', '')
    signals = week_data.get('signals_executed', 0)
    winners = week_data.get('winners', 0)
    win_rate = week_data.get('win_rate', 0)
    pnl = week_data.get('total_pnl', 0)
    roi = week_data.get('roi', 0)
    best = week_data.get('best_trade', 'N/A')

    pnl_emoji = '\U0001f7e2' if pnl >= 0 else '\U0001f534'

    post = (
        f"\U0001f4af WEEKLY PERFORMANCE\n"
        f"Week {week_num} \u2014 {date_range}\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"\U0001f4ca {signals} signals executed\n"
        f"\u2705 {winners} winners ({win_rate:.0f}%)\n"
        f"\u274c {signals - winners} losers\n\n"
        f"P&L: {pnl_emoji} ${pnl:+.2f}\n"
        f"ROI: {roi:+.2f}%\n"
        f"Best: {best}\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"System built on Android \U0001f4f1\n"
        f"100% free to run \u2013 zero cost\n\n"
        f"Agli week aur bhi kamaenge! \U0001f680\U0001f4b0\n\n"
        f"{HASHTAGS}"
    )

    post_dir = DAILY_DIR / 'weekly'
    post_dir.mkdir(parents=True, exist_ok=True)
    filepath = post_dir / f'week_{week_num}_instagram_post.txt'
    with open(filepath, 'w') as f:
        f.write(post)
    log.info(f"Weekly Instagram post saved: {filepath}")
    return post


# ──────────────────────────────────────────────
# MULTILINGUAL POST GENERATORS (32 languages)
# ──────────────────────────────────────────────


def generate_multilingual_morning_posts(date=None, session_plan='', threshold=75):
    from multilingual_engine import get_engine, LANGUAGES
    engine = get_engine()
    if date is None:
        date = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    base_text = f"Good morning traders! Today's market outlook:\n• Session plan: {session_plan}\n• Threshold: {threshold}/100\n• Daily focus: execute high-conviction setups only."

    results = {}
    for lang_code in LANGUAGES:
        translated = engine.translate(base_text, lang_code)
        hashtags = engine.get_hashtags(lang_code)
        post = f"{translated}\n\n{hashtags}"
        results[lang_code] = post

        lang_dir = CONTENT_DIR / 'daily' / date / 'morning'
        lang_dir.mkdir(parents=True, exist_ok=True)
        with open(lang_dir / f'morning_{lang_code}.txt', 'w') as f:
            f.write(post)

    return results


def generate_multilingual_signal_post(symbol='XAUUSD', direction='BULLISH', decision='EXECUTE', score=85, entry='', sl='', tp='', time=''):
    from multilingual_engine import get_engine, LANGUAGES
    engine = get_engine()
    date = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    base = f"🚀 SIGNAL: {symbol} {direction}\nScore: {score}/100\nEntry: {entry}\nSL: {sl} | TP: {tp}"

    results = {}
    for lang_code in LANGUAGES:
        dir_translated = engine.translate_direction(direction, lang_code)
        text = base.replace(direction, dir_translated)
        translated = engine.translate(text, lang_code)
        hashtags = engine.get_hashtags(lang_code)
        post = f"{translated}\n\n{hashtags}"
        results[lang_code] = post

        lang_dir = CONTENT_DIR / 'daily' / date / 'signals'
        lang_dir.mkdir(parents=True, exist_ok=True)
        with open(lang_dir / f'{symbol}_{decision}_{lang_code}.txt', 'w') as f:
            f.write(post)

    return results


def generate_multilingual_evening_posts(signals_today=0, winners=0, win_pct=0, pnl=0, date=None):
    from multilingual_engine import get_engine, LANGUAGES
    engine = get_engine()
    if date is None:
        date = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    base_text = f"Today's results:\n{signals_today} signals, {winners} winners ({win_pct:.0f}%)\nP&L: ${pnl:+.2f}\nSee you tomorrow!"

    results = {}
    for lang_code in LANGUAGES:
        translated = engine.translate(base_text, lang_code)
        hashtags = engine.get_hashtags(lang_code)
        post = f"{translated}\n\n{hashtags}"
        results[lang_code] = post

        lang_dir = CONTENT_DIR / 'daily' / date / 'evening'
        lang_dir.mkdir(parents=True, exist_ok=True)
        with open(lang_dir / f'evening_{lang_code}.txt', 'w') as f:
            f.write(post)

    return results


def generate_multilingual_weekly_posts(week_data=None, date=None):
    from multilingual_engine import get_engine, LANGUAGES
    engine = get_engine()
    if date is None:
        date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    if week_data is None:
        week_data = {}

    signals = week_data.get('signals_executed', 0)
    winners = week_data.get('winners', 0)
    win_rate = week_data.get('win_rate', 0)
    pnl = week_data.get('total_pnl', 0)

    base_text = f"WEEKLY PERFORMANCE\n{signals} signals, {winners} winners ({win_rate:.0f}%)\nP&L: ${pnl:+.2f}\nNext week will be even better!"

    results = {}
    for lang_code in LANGUAGES:
        translated = engine.translate(base_text, lang_code)
        hashtags = engine.get_hashtags(lang_code)
        post = f"{translated}\n\n{hashtags}"
        results[lang_code] = post

        week_dir = CONTENT_DIR / 'weekly' / date
        week_dir.mkdir(parents=True, exist_ok=True)
        with open(week_dir / f'weekly_{lang_code}.txt', 'w') as f:
            f.write(post)

    return results


# ──────────────────────────────────────────────
# REGIONAL CONTENT CALENDARS
# ──────────────────────────────────────────────

REGION_SCHEDULES = {
    'india': {
        'timezone': 'Asia/Kolkata',
        'offset': '+05:30',
        'morning': '08:30',
        'evening': '20:00',
        'peak_hours': ['19:00', '20:00', '21:00', '22:00'],
        'languages': ['hi', 'te', 'ta', 'kn', 'ml', 'mr', 'gu', 'pa', 'bn', 'or', 'as', 'ur'],
    },
    'middle_east': {
        'timezone': 'Asia/Dubai',
        'offset': '+04:00',
        'morning': '09:00',
        'evening': '20:00',
        'peak_hours': ['20:00', '21:00', '22:00', '23:00'],
        'languages': ['ar', 'ur', 'fa'],
    },
    'indonesia': {
        'timezone': 'Asia/Jakarta',
        'offset': '+07:00',
        'morning': '08:00',
        'evening': '20:00',
        'peak_hours': ['19:00', '20:00', '21:00', '22:00'],
        'languages': ['id', 'ms'],
    },
    'turkey': {
        'timezone': 'Europe/Istanbul',
        'offset': '+03:00',
        'morning': '09:00',
        'evening': '20:00',
        'peak_hours': ['20:00', '21:00', '22:00'],
        'languages': ['tr'],
    },
    'europe': {
        'timezone': 'Europe/London',
        'offset': '+01:00',
        'morning': '09:00',
        'evening': '20:00',
        'peak_hours': ['19:00', '20:00', '21:00'],
        'languages': ['en', 'fr', 'de', 'es', 'pt', 'it', 'nl', 'pl'],
    },
    'international': {
        'timezone': 'UTC',
        'offset': '+00:00',
        'morning': '08:00',
        'evening': '20:00',
        'peak_hours': ['12:00', '13:00', '14:00', '15:00'],
        'languages': ['en', 'ru', 'zh', 'ja', 'ko', 'th', 'vi', 'sw'],
    },
}

REGION_CALENDAR_FILES = {
    'india': 'calendar_india.json',
    'middle_east': 'calendar_middleeast.json',
    'indonesia': 'calendar_indonesia.json',
    'turkey': 'calendar_turkey.json',
    'europe': 'calendar_europe.json',
    'international': 'calendar_international.json',
}


def generate_region_calendars(date=None):
    from multilingual_engine import get_engine, LANGUAGES
    engine = get_engine()
    if date is None:
        date = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    calendars = {}
    for region, schedule in REGION_SCHEDULES.items():
        region_posts = []
        for lang_code in schedule['languages']:
            meta = LANGUAGES.get(lang_code, {})
            hashtags = engine.get_hashtags(lang_code)

            morning_post = {
                'type': 'morning',
                'language': lang_code,
                'name': meta.get('name', lang_code),
                'time': schedule['morning'],
                'timezone': schedule['timezone'],
                'hashtags': hashtags,
            }
            evening_post = {
                'type': 'evening',
                'language': lang_code,
                'name': meta.get('name', lang_code),
                'time': schedule['evening'],
                'timezone': schedule['timezone'],
                'hashtags': hashtags,
            }
            region_posts.append(morning_post)
            region_posts.append(evening_post)

        calendar = {
            'date': date,
            'region': region,
            'timezone': schedule['timezone'],
            'offset': schedule['offset'],
            'peak_hours': schedule['peak_hours'],
            'posts': region_posts,
        }

        filename = REGION_CALENDAR_FILES[region]
        filepath = CONTENT_DIR / filename
        with open(filepath, 'w') as f:
            json.dump(calendar, f, indent=2, ensure_ascii=False)
        calendars[region] = calendar

    return calendars


# ──────────────────────────────────────────────
# FESTIVAL / EVENT AWARENESS
# ──────────────────────────────────────────────


def get_indian_festivals(date):
    """Return festival name if date matches known festival."""
    festivals = {
        '2026-01-14': 'Makar Sankranti',
        '2026-01-26': 'Republic Day',
        '2026-03-25': 'Holi',
        '2026-08-15': 'Independence Day',
        '2026-10-02': 'Gandhi Jayanti',
        '2026-10-31': 'Diwali',
        '2026-12-25': 'Christmas',
    }
    return festivals.get(date)


def get_islamic_adjustments(date):
    """Return dict of adjustments during Ramadan."""
    try:
        d = datetime.strptime(date, '%Y-%m-%d') if isinstance(date, str) else date
        ramadan_start = datetime(2026, 3, 1)
        ramadan_end = datetime(2026, 3, 29)
        if ramadan_start <= d <= ramadan_end:
            return {'post_time_offset_hours': -2, 'greeting': 'Ramadan Mubarak'}
    except Exception:
        pass
    return {}


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

    if '--test' in sys.argv:
        print("=" * 60)
        print("  AUTO POSTER - TEST")
        print("=" * 60)

        morning = generate_morning_post(yield_status='Normal (bullish)',
                                        news_today='No high impact',
                                        session_plan='London open focus',
                                        threshold=75)
        print(f"  Morning post:\n{morning}\n")

        signal = generate_signal_post('XAUUSD', 'BULLISH', 85, 182.50, 72.0)
        print(f"  Signal post:\n{signal}\n")

        evening = generate_evening_post(6, 4, 66.7, 347.50)
        print(f"  Evening post:\n{evening}\n")

        weekly = generate_weekly_post({
            'week': 1, 'date_range': 'Jun 8-14',
            'signals_executed': 36, 'winners': 26,
            'win_rate': 72.2, 'total_pnl': 847.50,
            'roi': 8.47, 'best_trade': 'XAUUSD +$312',
        })
        print(f"  Weekly post:\n{weekly}\n")

        print("\n" + "=" * 60)

    elif '--morning' in sys.argv:
        print(generate_morning_post())

    elif '--evening' in sys.argv:
        print(generate_evening_post())

    elif '--multilingual' in sys.argv:
        print("=" * 60)
        print("  MULTILINGUAL POST GENERATOR (32 languages)")
        print("=" * 60)
        total_files = 0

        morning = generate_multilingual_morning_posts(session_plan='London/NY session focus', threshold=75)
        print(f"  Morning posts: {len(morning)} languages")
        total_files += len(morning)

        signal = generate_multilingual_signal_post('XAUUSD', 'BULLISH', 'EXECUTE', 85, '2345.50', '2325.00', '2380.00', '14:30 UTC')
        print(f"  Signal posts: {len(signal)} languages")
        total_files += len(signal)

        evening = generate_multilingual_evening_posts(6, 4, 66.7, 347.50)
        print(f"  Evening posts: {len(evening)} languages")
        total_files += len(evening)

        weekly = generate_multilingual_weekly_posts({
            'signals_executed': 36, 'winners': 26, 'win_rate': 72.2, 'total_pnl': 847.50,
        })
        print(f"  Weekly posts: {len(weekly)} languages")
        total_files += len(weekly)

        calendars = generate_region_calendars()
        print(f"  Region calendars: {len(calendars)}")
        total_files += len(calendars)

        print(f"\n  Total files created: {total_files}")
        print("=" * 60)

    elif '--calendar' in sys.argv:
        calendars = generate_region_calendars()
        for region, cal in calendars.items():
            print(f"  {region}: {len(cal['posts'])} posts scheduled")

    else:
        print("Usage:")
        print("  python auto_poster.py --test           # Run tests")
        print("  python auto_poster.py --morning        # Generate morning post")
        print("  python auto_poster.py --evening        # Generate evening post")
        print("  python auto_poster.py --multilingual   # Generate posts in 32 languages")
        print("  python auto_poster.py --calendar       # Generate regional calendars")
