"""
Content Logger - Short-Form Content Export
===========================================
Automatically exports high-performance trading days into organized
text folders for Instagram Reels / YouTube Shorts script hooks.
"""

import json
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

log = logging.getLogger('ContentLogger')

CONTENT_DIR = Path(__file__).parent.parent / 'content' / 'trade_logs'
CONTENT_DIR.mkdir(parents=True, exist_ok=True)


class ContentLogger:
    """Logs standout trading days for social media content creation."""

    def __init__(self):
        self._paper_trader = None
        self._daily_dir = CONTENT_DIR / datetime.now(timezone.utc).strftime('%Y-%m-%d')
        self._daily_dir.mkdir(parents=True, exist_ok=True)

    def _get_paper_trader(self):
        if self._paper_trader is None:
            sys.path.insert(0, str(Path(__file__).parent))
            from paper_trader import get_paper_trader
            self._paper_trader = get_paper_trader()
        return self._paper_trader

    def log_trade_day(self, symbol: str, direction: str, score: int,
                       entry: float, exit_: float, pnl: float,
                       strategy_notes: str = '') -> Optional[Path]:
        """Log a completed trade to the daily content folder."""
        try:
            date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
            day_dir = CONTENT_DIR / date_str
            day_dir.mkdir(parents=True, exist_ok=True)

            # Daily summary
            summary_file = day_dir / 'trades.json'
            trades = []
            if summary_file.exists():
                with open(summary_file) as f:
                    trades = json.load(f)

            trade = {
                'symbol': symbol,
                'direction': direction,
                'score': score,
                'entry': entry,
                'exit': exit_,
                'pnl': pnl,
                'strategy_notes': strategy_notes,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'is_high_performance': score >= 85,
            }
            trades.append(trade)
            with open(summary_file, 'w') as f:
                json.dump(trades, f, indent=2)

            # If high performance, also write a content hook
            if score >= 85:
                hook = self._generate_content_hook(symbol, direction, score, entry, exit_, pnl)
                hook_file = day_dir / f'{symbol}_{direction}_WIN.md'
                with open(hook_file, 'w') as f:
                    f.write(hook)
                log.info(f"Content hook saved: {hook_file}")
                return hook_file

            return summary_file

        except Exception as e:
            log.debug(f"Trade log failed: {e}")
            return None

    def _generate_content_hook(self, symbol: str, direction: str, score: int,
                                entry: float, exit_: float, pnl: float) -> str:
        """Generate a ready-to-use Instagram Reel / YouTube Shorts script hook."""
        direction_emoji = '\U0001f4c8' if direction.upper() == 'LONG' else '\U0001f4c9'
        pnl_str = f'+${pnl:.2f}' if pnl >= 0 else f'-${abs(pnl):.2f}'

        lines = [
            f"# {symbol} \u2014 {direction} \u2014 Score: {score}/100",
            f"# PnL: {pnl_str}",
            f"# Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            '',
            '--- HOOK (Instagram Reel / YouTube Shorts) ---',
            '',
            f'{direction_emoji} INCREDIBLE {symbol} TRADE',
            '',
            'The setup:',
            f'- SMC confluence at H1 premium/discount zone',
            f'- FVG + Order Block alignment (score {score}/100)',
            f'- Entry: {entry}',
            f'- Exit: {exit_}',
            f'- PnL: {pnl_str}',
            '',
            'Why it worked:',
            '- Institutional structure was respected',
            '- Smart Money Concepts identified the liquidity grab',
            '- Price reacted exactly at the OB/FVG zone',
            '',
            'Key lesson for your trading:',
            'Wait for premium-to-discount or discount-to-premium sweeps.',
            'Let the market show its hand before entering.',
            '',
            '--- END ---',
            '',
            '#OMNIBRAIN #forex #XAUUSD #goldtrading #smc #smartmoney',
            '#trading #forextrader #daytrading #gold',
        ]
        return '\n'.join(lines)

    def get_recent_wins(self, days: int = 7) -> List[Dict]:
        """Get recent high-performance trades for weekly summary."""
        wins = []
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        for day_dir in sorted(CONTENT_DIR.iterdir()):
            if not day_dir.is_dir():
                continue
            summary_file = day_dir / 'trades.json'
            if not summary_file.exists():
                continue
            try:
                with open(summary_file) as f:
                    trades = json.load(f)
                for t in trades:
                    ts = t.get('timestamp', '')
                    if ts:
                        try:
                            t_time = datetime.fromisoformat(ts)
                            if t_time >= cutoff:
                                wins.append(t)
                        except Exception:
                            wins.append(t)
            except Exception:
                continue

        return sorted(wins, key=lambda x: x.get('timestamp', ''), reverse=True)

    def build_weekly_summary(self) -> str:
        """Build a professional weekly performance summary text."""
        wins = self.get_recent_wins(7)
        total_trades = len(wins)
        if total_trades == 0:
            return "No trades recorded this week."

        winning = [w for w in wins if w.get('pnl', 0) > 0]
        win_rate = (len(winning) / total_trades * 100) if total_trades > 0 else 0
        total_pnl = sum(w.get('pnl', 0) for w in wins)
        max_drawdown = min(w.get('pnl', 0) for w in wins)
        avg_score = sum(w.get('score', 0) for w in wins) / max(total_trades, 1)

        best_trade = max(wins, key=lambda x: x.get('pnl', 0)) if wins else {}
        worst_trade = min(wins, key=lambda x: x.get('pnl', 0)) if wins else {}

        lines = [
            "\U0001f4ca WEEKLY PERFORMANCE SUMMARY",
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501",
            f"Period  : Last 7 days",
            f"Trades  : {total_trades}",
            f"Win Rate: {win_rate:.0f}%",
            f"Total PnL: {'+' if total_pnl >= 0 else ''}${total_pnl:.2f}",
            f"Avg Score: {avg_score:.0f}/100",
            f"Max DD  : ${max_drawdown:.2f}",
            "",
            f"Best Trade : {best_trade.get('symbol', 'N/A')} {best_trade.get('direction', '')}",
            f"  Entry: {best_trade.get('entry', 'N/A')}  Exit: {best_trade.get('exit', 'N/A')}",
            f"  PnL: ${best_trade.get('pnl', 0):.2f}" if best_trade else "",
            "",
            f"Worst Trade: {worst_trade.get('symbol', 'N/A')} {worst_trade.get('direction', '')}",
            f"  Entry: {worst_trade.get('entry', 'N/A')}  Exit: {worst_trade.get('exit', 'N/A')}",
            f"  PnL: ${worst_trade.get('pnl', 0):.2f}" if worst_trade else "",
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501",
            "Trading powered by OMNI BRAIN V2",
            "Smart Money Concepts | AI-Enhanced | 24/7",
            "#OMNIBRAIN #forex #trading #weeklyrecap",
        ]
        return '\n'.join([l for l in lines if l])


# ══════════════════════════════════════════════════════════════════════════════
# GLOBAL INSTANCE
# ══════════════════════════════════════════════════════════════════════════════

_logger: Optional[ContentLogger] = None


def get_content_logger() -> ContentLogger:
    global _logger
    if _logger is None:
        _logger = ContentLogger()
    return _logger


if __name__ == '__main__':
    # Demo
    logger = get_content_logger()
    logger.log_trade_day('XAUUSD', 'LONG', 88, 2350.50, 2365.80, 153.00,
                          'H1 FVG + OB confluence, Asian session sweep')
    print(logger.build_weekly_summary())
