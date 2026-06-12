"""
Showcase Generator - OMNI BRAIN V2
===================================
Auto-generate proof-of-performance content for social media.
Signal cards, weekly results, monthly track records.

Features:
  A) Signal Card (ASCII or PIL) - 1080x1080 style
  B) Weekly Results Card (1080x1350 style)
  C) Monthly Track Record with Sharpe ratio
  D) Save to content/showcase/ directory
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from pathlib import Path

log = logging.getLogger('ShowcaseGenerator')

SHOWCASE_DIR = Path(__file__).parent.parent / 'content' / 'showcase'
SHOWCASE_DIR.mkdir(parents=True, exist_ok=True)

WEEKLY_DIR = Path(__file__).parent.parent / 'content' / 'weekly'
WEEKLY_DIR.mkdir(parents=True, exist_ok=True)

MONTHLY_DIR = Path(__file__).parent.parent / 'content' / 'monthly'
MONTHLY_DIR.mkdir(parents=True, exist_ok=True)


def generate_signal_card(symbol: str, direction: str, score: int, entry: float,
                         sl: float, tp1: float, tp2: float, tp3: float,
                         lots: float, components: Optional[Dict[str, int]] = None,
                         is_paper: bool = True) -> str:
    """Generate an ASCII signal card (1080x1080 style)."""
    direction_emoji = '\U0001f7e2' if direction in ('BULLISH', 'LONG', 'BUY') else '\U0001f534'
    bar_filled = score // 10
    bar_empty = 10 - bar_filled
    score_bar = '\u2588' * bar_filled + '\u2591' * bar_empty

    comp_str = ''
    if components:
        comps = ' | '.join(f"{k}:+{v}" for k, v in sorted(components.items(), key=lambda x: -x[1]) if v > 0)
        comp_str = f"  {comps}\n"

    card = (
        f"\u250f\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2513\n"
        f"\u2503  \U0001f9e0 OMNI BRAIN V2 \u2014 SIGNAL CARD             \u2503\n"
        f"\u2503                                                \u2503\n"
        f"\u2503  {direction_emoji} {symbol:<6} {direction:<10} Score: {score}/100 \u2503\n"
        f"\u2503  \u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2503\n"
        f"\u2503  Score: {score_bar}                            \u2503\n"
        f"\u2503                                                \u2503\n"
        f"\u2503  Entry: {entry:<10}  Lots: {lots:<.2f}          \u2503\n"
        f"\u2503  SL:    {sl:<10}  TP1: {tp1:<10}  \u2503\n"
        f"\u2503  TP2:   {tp2:<10}  TP3: {tp3:<10}  \u2503\n"
        f"\u2503                                                \u2503\n"
        f"{comp_str}"
        f"\u2503                                                \u2503\n"
    )
    if is_paper:
        card += (
            f"\u2503  \u26a0\ufe0f PAPER TRADE \u2014 Not Financial Advice        \u2503\n"
        )
    card += (
        f"\u2517\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u251b\n"
    )

    date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')
    filename = f"{date_str}_{symbol}_{direction.lower()}_score{score}.txt"
    filepath = SHOWCASE_DIR / filename
    with open(filepath, 'w') as f:
        f.write(card)
    log.info(f"Signal card saved: {filepath}")
    return card


def generate_weekly_card(week_data: Dict[str, Any]) -> str:
    """Generate weekly results card (1080x1350 style)."""
    win_rate = week_data.get('win_rate', 0)
    pnl = week_data.get('total_pnl', 0)
    roi = week_data.get('roi', 0)
    signals = week_data.get('signals_executed', 0)
    best_trade = week_data.get('best_trade', 'N/A')
    week_num = week_data.get('week', 0)
    date_range = week_data.get('date_range', '')
    winners = week_data.get('winners', 0)
    losers = week_data.get('losers', 0)

    pnl_emoji = '\U0001f7e2' if pnl >= 0 else '\U0001f534'
    accuracy_emoji = '\U0001f7e2' if win_rate >= 60 else '\U0001f7e1' if win_rate >= 40 else '\U0001f534'

    bar_filled = int(win_rate // 10)
    bar_empty = 10 - bar_filled
    bar = '\u2588' * bar_filled + '\u2591' * bar_empty

    card = (
        f"\u250f\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2513\n"
        f"\u2503  \U0001f9e0 OMNI BRAIN V2 RESULTS                      \u2503\n"
        f"\u2503                                                \u2503\n"
        f"\u2503  Week {week_num:<2} \u2014 {date_range:<26} \u2503\n"
        f"\u2503  \u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2503\n"
        f"\u2503  Signals executed : {signals:<4}                       \u2503\n"
        f"\u2503  Winners          : {winners:<4} ({win_rate:.1f}%) {accuracy_emoji}{bar}  \u2503\n"
        f"\u2503  Losers           : {losers:<4} ({100-win_rate:.1f}%)                \u2503\n"
        f"\u2503                                                \u2503\n"
        f"\u2503  P&L              : {'+' if pnl >= 0 else ''}${pnl:<.2f} {pnl_emoji}               \u2503\n"
        f"\u2503  ROI              : {'+' if roi >= 0 else ''}{roi:<.2f}%                    \u2503\n"
        f"\u2503  Best trade       : {best_trade:<20}       \u2503\n"
        f"\u2503                                                \u2503\n"
        f"\u2503  Score accuracy   : {win_rate:.0f}%                      \u2503\n"
        f"\u2503  Built on Android \U0001f4f1                           \u2503\n"
        f"\u2503  @forextrader_9                                     \u2503\n"
        f"\u2517\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u251b\n"
    )

    week_num = week_data.get('week', datetime.now(timezone.utc).isocalendar()[1])
    filename = f"week_{week_num}_results.txt"
    filepath = SHOWCASE_DIR / filename
    with open(filepath, 'w') as f:
        f.write(card)

    weekly_path = WEEKLY_DIR / f'week_{week_num}_card.txt'
    with open(weekly_path, 'w') as f:
        f.write(card)

    log.info(f"Weekly card saved: {filepath}")
    return card


def generate_monthly_track_record(trades: List[Dict[str, Any]], starting_balance: float) -> str:
    """Generate monthly track record with Sharpe ratio and max drawdown."""
    if not trades:
        return "No trades to report."

    total_pnl = sum(t.get('pnl', 0) for t in trades)
    winners = [t for t in trades if t.get('pnl', 0) > 0]
    losers = [t for t in trades if t.get('pnl', 0) <= 0]
    win_rate = len(winners) / len(trades) * 100 if trades else 0

    returns = [t.get('pnl', 0) / starting_balance for t in trades]
    avg_return = sum(returns) / len(returns) if returns else 0
    variance = sum((r - avg_return)**2 for r in returns) / len(returns) if returns else 0
    std_return = variance**0.5
    sharpe = (avg_return / std_return * (252**0.5)) if std_return > 0 else 0

    peak = starting_balance
    max_dd = 0
    running = starting_balance
    for t in trades:
        running += t.get('pnl', 0)
        if running > peak:
            peak = running
        dd = (peak - running) / peak * 100
        max_dd = max(max_dd, dd)

    roi = (total_pnl / starting_balance) * 100

    month_name = datetime.now(timezone.utc).strftime('%B %Y')

    report = (
        f"\u250f\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2513\n"
        f"\u2503  \U0001f4ca MONTHLY TRACK RECORD                        \u2503\n"
        f"\u2503  {month_name:<39} \u2503\n"
        f"\u2503  \u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2503\n"
        f"\u2503  Total Trades    : {len(trades):<4}                    \u2503\n"
        f"\u2503  Winners         : {len(winners):<4} ({win_rate:.1f}%)               \u2503\n"
        f"\u2503  Losers          : {len(losers):<4} ({100-win_rate:.1f}%)               \u2503\n"
        f"\u2503                                                \u2503\n"
        f"\u2503  Total P&L       : {'+' if total_pnl >= 0 else ''}${total_pnl:<.2f}                  \u2503\n"
        f"\u2503  ROI             : {'+' if roi >= 0 else ''}{roi:<.2f}%                    \u2503\n"
        f"\u2503  Sharpe Ratio    : {sharpe:<.2f}                      \u2503\n"
        f"\u2503  Max Drawdown    : {max_dd:<.2f}%                     \u2503\n"
        f"\u2503                                                \u2503\n"
    )

    lines = report.split('\n')
    for t in trades[-10:]:  # last 10 trades
        emoji = '\u2705' if t.get('pnl', 0) > 0 else '\u274c'
        lines.insert(-1, f"\u2503  {emoji} {t.get('symbol', '?'):<7} {t.get('direction', ''):<8} ${t.get('pnl', 0):<+.2f}          \u2503")

    lines.insert(-1, f"\u2503                                                \u2503")
    lines.insert(-1, f"\u2503  \u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2503")
    lines.append(f"\u2517\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u251b\n")

    report = '\n'.join(lines)

    filename = f"monthly_{datetime.now(timezone.utc).strftime('%Y_%m')}_track_record.txt"
    filepath = SHOWCASE_DIR / filename
    with open(filepath, 'w') as f:
        f.write(report)

    monthly_path = MONTHLY_DIR / filename
    with open(monthly_path, 'w') as f:
        f.write(report)

    log.info(f"Monthly track record saved: {filepath}")
    return report


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

    if '--test' in sys.argv:
        print("=" * 60)
        print("  SHOWCASE GENERATOR - TEST")
        print("=" * 60)

        card = generate_signal_card('XAUUSD', 'BULLISH', 85, 2350.50, 2338.10, 2352.30, 2359.10, 2365.90, 0.67,
                                    {'OB': 20, 'FVG': 20, 'SWEEP': 30, 'VWAP': 10, 'SESSION': 5})
        print(f"  Signal card generated ({len(card)} chars)")
        print(card)

        weekly_data = {
            'week': 1, 'date_range': '2026-06-08 to 2026-06-14',
            'signals_executed': 36, 'winners': 26, 'losers': 10,
            'win_rate': 72.2, 'total_pnl': 847.50, 'roi': 8.47,
            'best_trade': 'XAUUSD +$312',
        }
        weekly_card = generate_weekly_card(weekly_data)
        print(f"  Weekly card:\n{weekly_card}")

        trades = [
            {'symbol': 'XAUUSD', 'direction': 'BULLISH', 'pnl': 182.50},
            {'symbol': 'EURUSD', 'direction': 'BEARISH', 'pnl': -87.00},
            {'symbol': 'GBPUSD', 'direction': 'BULLISH', 'pnl': 145.20},
            {'symbol': 'XAUUSD', 'direction': 'BULLISH', 'pnl': 312.00},
            {'symbol': 'SP500', 'direction': 'BULLISH', 'pnl': -45.00},
        ]
        monthly = generate_monthly_track_record(trades, 10000.0)
        print(f"  Monthly track record:\n{monthly}")

        print("\n" + "=" * 60)

    elif '--weekly' in sys.argv:
        sys.path.insert(0, str(Path(__file__).parent.parent / 'production'))
        from paper_trader import get_paper_trader
        pt = get_paper_trader()
        report = pt.save_weekly_report()
        card = generate_weekly_card(report)
        print(card)

    elif '--card' in sys.argv and len(sys.argv) >= 6:
        symbol = sys.argv[2]
        direction = sys.argv[3]
        score = int(sys.argv[4])
        entry = float(sys.argv[5])
        sl = float(sys.argv[6]) if len(sys.argv) > 6 else entry * 0.99
        tp1 = float(sys.argv[7]) if len(sys.argv) > 7 else entry * 1.005
        tp2 = float(sys.argv[8]) if len(sys.argv) > 8 else entry * 1.01
        tp3 = float(sys.argv[9]) if len(sys.argv) > 9 else entry * 1.015
        lots = float(sys.argv[10]) if len(sys.argv) > 10 else 0.1
        print(generate_signal_card(symbol, direction, score, entry, sl, tp1, tp2, tp3, lots))

    else:
        print("Usage:")
        print("  python showcase_generator.py --test           # Run tests")
        print("  python showcase_generator.py --weekly         # Generate weekly card")
        print("  python showcase_generator.py --card SYM DIR SCORE ENTRY SL TP1 TP2 TP3 LOTS")
