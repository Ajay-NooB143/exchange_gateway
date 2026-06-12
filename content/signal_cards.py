"""
Signal Cards - OMNI BRAIN V2
==============================
Multilingual styled text-based signal cards for Telegram and Instagram.
Generates cards in all 32 languages using the Multilingual Engine.
"""

import os
import sys
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from content.multilingual_engine import get_engine, LANGUAGES

log = logging.getLogger('SignalCards')

STANDARD_WIDTH = 36
JUMBO_WIDTH = 50

DIR_EMOJI = {'BUY': '🟢', 'SELL': '🔴'}
DIR_MAP = {'BUY': 'BULLISH', 'SELL': 'BEARISH'}


def _inner(w):
    return w - 2


def _top(width):
    return '╔' + '═' * _inner(width) + '╗'


def _bottom(width):
    return '╚' + '═' * _inner(width) + '╝'


def _hline(width):
    return '╠' + '═' * _inner(width) + '╣'


def _center(text, width):
    return '║' + text.center(_inner(width)) + '║'


def _row(label, value, width):
    content = f"  {label}: {value}"
    return '║' + content.ljust(_inner(width)) + '║'


def _row_simple(content, width):
    return '║' + content.ljust(_inner(width)) + '║'


def _confidence_bar(value, length=10):
    filled = max(0, min(length, round(value / 100 * length)))
    return '═' * filled + '░' * (length - filled)


def _win_bar(value, length=10):
    filled = max(0, min(length, round(value / 100 * length)))
    return '█' * filled + '░' * (length - filled)


def _wrap_text(text, max_width):
    words = text.split()
    lines = []
    current = ''
    for word in words:
        test = f"{current} {word}".strip()
        if len(test) <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _translate_direction(direction, lang, engine):
    mapped = DIR_MAP.get(direction, direction)
    return engine.translate_direction(mapped, lang)


def generate_signal_card(signal, lang='en', jumbo=False):
    eng = get_engine()
    width = JUMBO_WIDTH if jumbo else STANDARD_WIDTH
    inner = _inner(width)

    dir_emoji = DIR_EMOJI.get(signal['direction'], '')
    trans_dir = _translate_direction(signal['direction'], lang, eng)
    dir_display = f"{dir_emoji} {trans_dir}".strip()

    def t(text):
        return eng.translate(text, lang)

    lines = []
    lines.append(_top(width))
    lines.append(_center('O M N I   B R A I N', width))
    lines.append(_center(f'───  {t("SIGNAL")}  ───', width))
    lines.append(_hline(width))

    lines.append(_row(t('PAIR'), signal['pair'], width))
    lines.append(_row(t('DIRECTION'), dir_display, width))
    lines.append(_row(t('ENTRY'), signal['entry'], width))
    lines.append(_row('SL', signal['sl'], width))

    for key, label in [('tp1', 'TP1'), ('tp2', 'TP2'), ('tp3', 'TP3')]:
        val = signal.get(key)
        if val:
            lines.append(_row(t(label), val, width))

    conf = signal.get('confidence', 0)
    conf_bar = _confidence_bar(conf)
    lines.append(_row(t('CONFIDENCE'), f"{conf_bar}  {conf}%", width))
    lines.append(_row(t('TYPE'), signal.get('signal_type', 'FREE'), width))

    lines.append(_hline(width))

    rationale = signal.get('rationale', '')
    if rationale:
        lines.append(_row_simple(f"  📊 {t('RATIONALE')}:", width))
        max_w = inner - 4
        for line in _wrap_text(rationale, max_w):
            lines.append(_row_simple(f"  {line}", width))

    lines.append(_hline(width))

    wr = signal.get('win_rate', 0)
    lines.append(_row_simple(f"  🎯 {t('WIN RATE')}: {wr}% (last 30)", width))
    time_str = datetime.utcnow().strftime('%H:%M UTC')
    lines.append(_row_simple(f"  ⏰ {time_str}", width))

    lines.append(_hline(width))
    lines.append(_row(t('Join FREE'), '@omnibrainsignals', width))
    lines.append(_row(t('Join VIP'), '@omnibrainsignals', width))
    lines.append(_bottom(width))

    return '\n'.join(lines)


def generate_signal_card_jumbo(signal, lang='en'):
    return generate_signal_card(signal, lang, jumbo=True)


def generate_performance_card(stats, lang='en', jumbo=False):
    eng = get_engine()
    width = JUMBO_WIDTH if jumbo else STANDARD_WIDTH

    is_weekly = 'week' in stats
    period_label_key = 'WEEKLY PERFORMANCE' if is_weekly else 'MONTHLY PERFORMANCE'
    period_label = eng.translate(period_label_key, lang)
    period_val = stats.get('week') if is_weekly else stats.get('month', '')

    def t(text):
        return eng.translate(text, lang)

    wins = stats.get('wins', 0)
    losses = stats.get('losses', 0)
    wr = stats.get('win_rate', 0.0)

    lines = []
    lines.append(_top(width))
    lines.append(_center(f"{period_label}: {period_val}", width))
    lines.append(_hline(width))

    lines.append(_row(t('Total Trades'), str(stats.get('total_trades', 0)), width))

    wins_bar = _win_bar(wr)
    lines.append(_row(t('Wins'), f"{wins}  {wins_bar}", width))

    lr = 100 - wr if wins + losses > 0 else 0
    losses_bar = _win_bar(lr)
    lines.append(_row(t('Losses'), f"{losses}  {losses_bar}", width))

    lines.append(_row(t('Win Rate'), f"{wr}%", width))

    pp = stats.get('profit_pips', 0)
    pps = f"+{pp}" if pp >= 0 else str(pp)
    lines.append(_row(t('Profit'), f"{pps} pips", width))

    ppct = stats.get('profit_percent', 0)
    ppcts = f"+{ppct}" if ppct >= 0 else str(ppct)
    lines.append(_row(t('Return'), f"{ppcts}%", width))

    lines.append(_hline(width))
    lines.append(_row(t('Best'), stats.get('best_trade', ''), width))
    lines.append(_row(t('Worst'), stats.get('worst_trade', ''), width))
    lines.append(_row(t('Avg Win'), stats.get('avg_win', ''), width))
    lines.append(_row(t('Avg Loss'), stats.get('avg_loss', ''), width))

    lines.append(_hline(width))
    cons_bar = _confidence_bar(wr)
    lines.append(_row(t('Consistency'), f"{cons_bar}  {wr}%", width))
    lines.append(_bottom(width))

    return '\n'.join(lines)


def generate_multilingual_signal(signal, languages=None):
    if languages is None:
        languages = list(LANGUAGES.keys())
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    results = {}
    for lang in languages:
        card = generate_signal_card(signal, lang)
        results[lang] = card
        save_dir = Path(__file__).parent / 'signal_cards' / lang / timestamp
        save_dir.mkdir(parents=True, exist_ok=True)
        (save_dir / 'card.txt').write_text(card, encoding='utf-8')
    return results


def generate_multilingual_performance(stats, languages=None):
    if languages is None:
        languages = list(LANGUAGES.keys())
    period_val = stats.get('week', stats.get('month', 'unknown'))
    results = {}
    for lang in languages:
        card = generate_performance_card(stats, lang)
        results[lang] = card
        save_dir = Path(__file__).parent / 'signal_cards' / lang / str(period_val)
        save_dir.mkdir(parents=True, exist_ok=True)
        (save_dir / 'performance.txt').write_text(card, encoding='utf-8')
    return results


def generate_signal_batch(signals, lang='en'):
    eng = get_engine()
    width = JUMBO_WIDTH
    inner = _inner(width)

    def t(text):
        return eng.translate(text, lang)

    lines = []
    lines.append(_top(width))
    lines.append(_center(f"{t('SIGNAL BATCH')} ({len(signals)})", width))
    lines.append(_hline(width))

    pair_h = t('PAIR')
    dir_h = t('DIRECTION')
    entry_h = t('ENTRY')
    sl_h = 'SL'
    tp_h = 'TP'

    header = f"  {pair_h:<8}{dir_h:<10}{entry_h:<10}{sl_h:<10}{tp_h:<10}"
    lines.append(_row_simple(header, width))

    for sig in signals:
        pair = sig['pair']
        direction = sig['direction']
        entry = sig['entry']
        sl = sig['sl']
        tp = sig.get('tp', sig.get('tp1', ''))

        trans_dir = _translate_direction(direction, lang, eng)

        row = f"  {pair:<8}{trans_dir:<10}{entry:<10}{sl:<10}{tp:<10}"
        lines.append(_row_simple(row, width))

    lines.append(_bottom(width))
    return '\n'.join(lines)


if __name__ == '__main__':
    import sys, json
    import logging
    logging.basicConfig(level=logging.INFO)

    if '--test' in sys.argv:
        signal = {
            'pair': 'EURUSD', 'direction': 'SELL',
            'entry': '1.08450', 'sl': '1.08700',
            'tp1': '1.08200', 'tp2': '1.08000', 'tp3': '1.07800',
            'confidence': 72, 'signal_type': 'VIP',
            'rationale': 'Order Block + FVG confluence on 15min timeframe',
            'win_rate': 72
        }
        for lang in ['en', 'hi', 'te', 'ar']:
            card = generate_signal_card(signal, lang)
            print(f"\n=== {lang} ===")
            print(card)

    if '--all' in sys.argv:
        signal = {
            'pair': 'EURUSD', 'direction': 'SELL',
            'entry': '1.08450', 'sl': '1.08700',
            'tp1': '1.08200', 'tp2': '1.08000', 'tp3': '1.07800',
            'confidence': 72, 'signal_type': 'VIP',
            'rationale': 'Order Block + FVG confluence on 15min timeframe',
            'win_rate': 72
        }
        result = generate_multilingual_signal(signal)
        print(f"Generated {len(result)} language versions")

    if '--batch' in sys.argv:
        signals = [
            {'pair': 'EURUSD', 'direction': 'BUY', 'entry': '1.08450', 'sl': '1.08150', 'tp': '1.08900', 'confidence': 78},
            {'pair': 'GBPUSD', 'direction': 'SELL', 'entry': '1.26500', 'sl': '1.26800', 'tp': '1.26000', 'confidence': 65},
            {'pair': 'USDJPY', 'direction': 'BUY', 'entry': '149.500', 'sl': '149.000', 'tp': '150.200', 'confidence': 70},
        ]
        for lang in ['en', 'hi']:
            card = generate_signal_batch(signals, lang)
            print(f"\n=== {lang} ===")
            print(card)

    if '--perf' in sys.argv:
        stats = {
            'week': '2026-W24',
            'total_trades': 15,
            'wins': 11,
            'losses': 4,
            'win_rate': 73.3,
            'profit_pips': 85.4,
            'profit_percent': 12.5,
            'best_trade': '+32.5 pips',
            'worst_trade': '-15.2 pips',
            'avg_win': '+18.3 pips',
            'avg_loss': '-12.1 pips',
        }
        for lang in ['en', 'hi', 'te', 'ar']:
            card = generate_performance_card(stats, lang)
            print(f"\n=== {lang} ===")
            print(card)
