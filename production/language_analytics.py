"""
Language Analytics Module
=========================
Tracks language preferences, generates daily reports, and provides dashboard API.

Integration with telegram_signals.py:
  from language_analytics import track_language_change
  track_language_change(chat_id, old_lang, new_lang)
"""

import json
import logging
import sys
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Any, Optional

_CONTENT_DIR = Path(__file__).parent.parent / 'content'
if str(_CONTENT_DIR) not in sys.path:
    sys.path.insert(0, str(_CONTENT_DIR))

from multilingual_engine import LANGUAGES

log = logging.getLogger('LanguageAnalytics')

LANGUAGE_ANALYTICS_FILE = Path(__file__).parent / 'logs' / 'language_analytics.json'
SUBSCRIBERS_FILE = Path(__file__).parent / 'logs' / 'subscribers.json'
REVENUE_FILE = Path(__file__).parent / 'logs' / 'revenue.json'
REPORTS_DIR = Path(__file__).parent / 'logs' / 'reports'


def load_subscribers() -> Dict[str, Any]:
    if not SUBSCRIBERS_FILE.exists():
        log.warning('subscribers.json not found')
        return {}
    with open(SUBSCRIBERS_FILE) as f:
        return json.load(f)


def load_revenue() -> List[Dict[str, Any]]:
    if not REVENUE_FILE.exists():
        log.warning('revenue.json not found')
        return []
    with open(REVENUE_FILE) as f:
        data = json.load(f)
    if isinstance(data, dict):
        return data.get('transactions', [])
    if isinstance(data, list):
        return data
    return []


def _load_analytics() -> Dict[str, Any]:
    if LANGUAGE_ANALYTICS_FILE.exists():
        with open(LANGUAGE_ANALYTICS_FILE) as f:
            return json.load(f)
    return {}


def _save_analytics(data: Dict[str, Any]):
    LANGUAGE_ANALYTICS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LANGUAGE_ANALYTICS_FILE, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_language_stats() -> Dict[str, Any]:
    subscribers = load_subscribers()
    transactions = load_revenue()

    total_users = len(subscribers)
    users_with_language = {}
    users_without_language = 0
    subscribed_users = set()

    for chat_id, info in subscribers.items():
        lang = info.get('language') if isinstance(info, dict) else None
        if lang:
            users_with_language[chat_id] = {'language': lang, 'info': info}
        else:
            users_without_language += 1

        expires = info.get('expires') or info.get('expires_at') if isinstance(info, dict) else None
        if expires:
            try:
                exp_date = datetime.fromisoformat(expires.replace('Z', '+00:00'))
                if exp_date > datetime.now(exp_date.tzinfo):
                    subscribed_users.add(chat_id)
            except (ValueError, TypeError):
                pass

    lang_breakdown: Dict[str, Dict[str, Any]] = {}
    for chat_id, entry in users_with_language.items():
        lang = entry['language']
        if lang not in lang_breakdown:
            lang_breakdown[lang] = {'count': 0, 'subscribed': 0, 'revenue': 0.0}
        lang_breakdown[lang]['count'] += 1
        if chat_id in subscribed_users:
            lang_breakdown[lang]['subscribed'] += 1

    revenue_by_lang: Dict[str, float] = {}
    for txn in transactions:
        txn_chat_id = str(txn.get('chat_id', ''))
        amount = float(txn.get('amount', 0))
        txn_lang = None
        if txn_chat_id in users_with_language:
            txn_lang = users_with_language[txn_chat_id]['language']
        else:
            entry = subscribers.get(txn_chat_id, {})
            if isinstance(entry, dict):
                txn_lang = entry.get('language')

        if txn_lang:
            revenue_by_lang[txn_lang] = revenue_by_lang.get(txn_lang, 0.0) + amount
            if txn_lang in lang_breakdown:
                lang_breakdown[txn_lang]['revenue'] += amount

    num_with_lang = len(users_with_language)
    subscribed_with_lang = subscribed_users & set(users_with_language.keys())
    subscribed_count = len(subscribed_with_lang)
    total_revenue = sum(txn.get('amount', 0) for txn in transactions)

    for lang_data in lang_breakdown.values():
        lang_data['pct'] = round(lang_data['count'] / num_with_lang * 100, 1) if num_with_lang else 0.0

    subscribed_pct = round(subscribed_count / num_with_lang * 100, 1) if num_with_lang else 0.0

    return {
        'total_users': total_users,
        'users_with_language': num_with_lang,
        'users_without_language': users_without_language,
        'language_breakdown': lang_breakdown,
        'subscription_stats': {
            'subscribed': subscribed_count,
            'subscribed_pct': subscribed_pct,
            'total_revenue': total_revenue,
            'revenue_by_language': revenue_by_lang,
        },
    }


def _bar(value: int, max_value: int, width: int = 10) -> str:
    if max_value == 0:
        return '░' * width
    filled = int(value / max_value * width)
    return '█' * filled + '░' * (width - filled)


def get_daily_report() -> str:
    stats = get_language_stats()
    today = date.today().isoformat()
    breakdown = stats['language_breakdown']
    sub_stats = stats['subscription_stats']

    sorted_langs = sorted(breakdown.items(), key=lambda x: -x[1]['count'])
    total_with_lang = stats['users_with_language']
    max_count = sorted_langs[0][1]['count'] if sorted_langs else 1

    lines = []
    lines.append('╔══════════════════════════════════╗')
    lines.append('║     LANGUAGE ANALYTICS REPORT    ║')
    lines.append(f'║        {today}               ║')
    lines.append('╠══════════════════════════════════╣')
    lines.append(f'║  TOTAL USERS:    {stats["total_users"]:<14} ║')
    with_lang_pct = round(total_with_lang / stats['total_users'] * 100, 1) if stats['total_users'] else 0.0
    no_lang_pct = round(stats['users_without_language'] / stats['total_users'] * 100, 1) if stats['total_users'] else 0.0
    lines.append(f'║  WITH LANG:      {total_with_lang:<8} ({with_lang_pct}%)  ║')
    lines.append(f'║  NO LANG:        {stats["users_without_language"]:<8} ({no_lang_pct}%)  ║')
    lines.append('╠══════════════════════════════════╣')
    lines.append('║  TOP 5 LANGUAGES:               ║')

    for lang_code, lang_data in sorted_langs[:5]:
        meta = LANGUAGES.get(lang_code, {})
        flag = meta.get('flag', '  ')
        name = meta.get('name', lang_code)
        count = lang_data['count']
        bar = _bar(count, max_count)
        lines.append(f'║  {flag} {name:<10} {count:<3} {bar} ║')

    lines.append('╠══════════════════════════════════╣')
    lines.append(f'║  SUBSCRIPTIONS: {sub_stats["subscribed"]:<5} ({sub_stats["subscribed_pct"]}%)     ║')
    lines.append(f'║  TOTAL REVENUE: ${sub_stats["total_revenue"]:<7.2f}    ║')

    rev_by_lang = sub_stats['revenue_by_language']
    top_rev_lang = max(rev_by_lang, key=rev_by_lang.get) if rev_by_lang else None
    if top_rev_lang:
        top_meta = LANGUAGES.get(top_rev_lang, {})
        top_flag = top_meta.get('flag', '  ')
        top_amount = rev_by_lang[top_rev_lang]
        lines.append(f'║  TOP REVENUE:    {top_flag} {top_meta.get("name", top_rev_lang):<10} (${top_amount:.0f}) ║')
    else:
        lines.append(f'║  TOP REVENUE LANG: N/A            ║')

    lines.append('╚══════════════════════════════════╝')
    return '\n'.join(lines)


def generate_daily_report() -> str:
    report_text = get_daily_report()
    today_str = date.today().isoformat()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f'language_report_{today_str}.txt'
    with open(report_path, 'w') as f:
        f.write(report_text)

    stats = get_language_stats()
    analytics = _load_analytics()
    analytics['last_updated'] = datetime.now().isoformat()
    analytics['report_date'] = today_str
    analytics['daily_report'] = report_text
    analytics.update(stats)
    _save_analytics(analytics)

    log.info(f'Daily report saved: {report_path}')
    return str(report_path)


def get_report_insights() -> List[str]:
    stats = get_language_stats()
    breakdown = stats['language_breakdown']
    sub_stats = stats['subscription_stats']
    insights = []

    if breakdown:
        top_lang = max(breakdown, key=lambda k: breakdown[k]['count'])
        top_meta = LANGUAGES.get(top_lang, {})
        top_name = top_meta.get('name', top_lang)
        top_pct = breakdown[top_lang]['pct']
        insights.append(f'\U0001f4c9 {top_name} is the most popular language ({top_pct}% of users)')

        rev_by_lang = sub_stats['revenue_by_language']
        if rev_by_lang:
            top_rev = max(rev_by_lang, key=rev_by_lang.get)
            rev_meta = LANGUAGES.get(top_rev, {})
            rev_name = rev_meta.get('name', top_rev)
            rev_amount = rev_by_lang[top_rev]
            insights.append(f'\U0001f4b0 {rev_name} users generate the most revenue (${rev_amount:.0f})')

    if stats['users_without_language'] > 0:
        pct_no_lang = round(stats['users_without_language'] / stats['total_users'] * 100, 1) if stats['total_users'] else 0
        insights.append(f'\u26a0\ufe0f {stats["users_without_language"]} users ({pct_no_lang}%) haven\'t set a language preference yet')

    if not insights:
        insights.append('No language data available yet')

    return insights


def track_language_change(chat_id: str, old_lang: Optional[str], new_lang: str):
    analytics = _load_analytics()
    changes = analytics.setdefault('language_changes', [])
    changes.append({
        'timestamp': datetime.now().isoformat(),
        'chat_id': chat_id,
        'from': old_lang,
        'to': new_lang,
    })
    _save_analytics(analytics)
    log.info(f'Language change logged: {chat_id}: {old_lang} -> {new_lang}')


def update_analytics() -> Dict[str, Any]:
    stats = get_language_stats()
    insights = get_report_insights()
    today_str = date.today().isoformat()

    analytics = _load_analytics()
    analytics['last_updated'] = datetime.now().isoformat()
    analytics['report_date'] = today_str
    analytics['insights'] = insights
    analytics.update(stats)
    _save_analytics(analytics)

    log.info(f'Analytics updated: {stats["total_users"]} users, {len(stats["language_breakdown"])} languages')
    return stats


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    if '--report' in sys.argv:
        report = get_daily_report()
        print(report)

    if '--insights' in sys.argv:
        insights = get_report_insights()
        for insight in insights:
            print(insight)

    if '--update' in sys.argv:
        result = update_analytics()
        print(f"Analytics updated: {result['total_users']} users, {len(result['language_breakdown'])} languages")

    if '--save' in sys.argv:
        path = generate_daily_report()
        print(f"Report saved: {path}")

    if '--revenue' in sys.argv:
        stats = get_language_stats()
        rev = stats['subscription_stats']['revenue_by_language']
        for lang, amount in sorted(rev.items(), key=lambda x: -x[1]):
            flag = LANGUAGES.get(lang, {}).get('flag', '')
            print(f"{flag} {lang}: ${amount}")
