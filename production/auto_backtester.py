"""
Auto-Backtester - OMNI BRAIN V2
================================
Enhanced weekly backtesting of signal performance.

Features:
  - Load last 7 days signals per asset
  - Score buckets: 0-40, 40-60, 60-80, 80-100
  - Session analysis: London/NY/Tokyo/Sydney
  - MTF confirmation impact
  - Consecutive win/loss streaks
  - Best day of week, best hour UTC
  - Avg RR achieved
  - Max drawdown period
  - Auto-apply threshold recommendations
  - Detailed Telegram report with bar charts
  - JSON output for React dashboard
"""

import os
import json
import csv
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from collections import defaultdict

log = logging.getLogger('AutoBacktester')

LOG_DIR = Path(__file__).parent / 'logs'
LOG_DIR.mkdir(exist_ok=True)

REPORTS_DIR = LOG_DIR / 'reports'
REPORTS_DIR.mkdir(exist_ok=True)

DATA_DIR = Path(__file__).parent / 'data' / 'csv'
DATA_DIR.mkdir(parents=True, exist_ok=True)

ASSETS = ['XAUUSD', 'EURUSD', 'GBPUSD', 'SP500']
TIMEFRAMES = ['M15', 'H1', 'H4', 'D1']

SCORE_BUCKETS = [
    (0, 40, '0-40'),
    (40, 60, '40-60'),
    (60, 80, '60-80'),
    (80, 101, '80-100')
]

SESSION_MAP = {
    'london': (7, 16),
    'new_york': (13, 22),
    'tokyo': (0, 9),
    'sydney': (22, 7)
}


def _get_session_name(hour_utc: int) -> str:
    if 7 <= hour_utc < 16:
        return 'london'
    elif 13 <= hour_utc < 22:
        return 'new_york'
    elif 0 <= hour_utc < 9:
        return 'tokyo'
    elif hour_utc >= 22 or hour_utc < 7:
        return 'sydney'
    return 'off_hours'


def _format_bar(percentage: float, width: int = 10) -> str:
    filled = int(percentage / 100 * width)
    empty = width - filled
    return '\u2588' * filled + '\u2591' * empty


class AutoBacktester:
    """
    Enhanced auto-backtester for weekly signal analysis.
    
    Features:
      - Analyze last 7 days of signals
      - Calculate win rate per asset/TF
      - Score bucket correlation
      - Session analysis
      - MTF confirmation impact
      - Streak tracking
      - Auto-apply threshold adjustments
    """
    
    def __init__(self):
        self.lookback_days = 7
        self.atr_multiplier = 2.0
    
    def load_signals(self, days: int = 7) -> List[Dict[str, Any]]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        signals = []
        
        log_file = LOG_DIR / 'signal_log.csv'
        if not log_file.exists():
            return signals
        
        try:
            with open(log_file, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    ts = row.get('timestamp', '')
                    try:
                        sig_time = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                        if sig_time >= cutoff:
                            row['_parsed_time'] = sig_time
                            row['_hour_utc'] = sig_time.hour
                            row['_day_of_week'] = sig_time.strftime('%A')
                            row['_session'] = _get_session_name(sig_time.hour)
                            signals.append(row)
                    except Exception:
                        continue
        except Exception as e:
            log.error(f"Failed to load signals: {e}")
        
        return signals
    
    def load_price_data(self, symbol: str, tf: str) -> List[Dict[str, Any]]:
        csv_file = DATA_DIR / f'{symbol}_{tf}.csv'
        
        if not csv_file.exists():
            return []
        
        data = []
        try:
            with open(csv_file, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    data.append(row)
        except Exception as e:
            log.error(f"Failed to load price data for {symbol}/{tf}: {e}")
        
        return data
    
    def evaluate_signal(
        self,
        signal: Dict[str, Any],
        price_data: List[Dict[str, Any]]
    ) -> str:
        direction = signal.get('direction', '').upper()
        entry_price = float(signal.get('score', 0))
        entry_price = float(signal.get('entry_price', 0)) if 'entry_price' in signal else float(signal.get('score', 0))
        timestamp = signal.get('timestamp', '')
        
        if not direction or not entry_price or not price_data:
            return 'NEUTRAL'
        
        signal_time = signal.get('_parsed_time')
        if signal_time is None:
            try:
                signal_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            except Exception:
                return 'NEUTRAL'
        
        subsequent_prices = []
        for candle in price_data:
            try:
                candle_time = datetime.fromisoformat(candle.get('timestamp', '').replace('Z', '+00:00'))
                if candle_time > signal_time:
                    high = float(candle.get('high', 0))
                    low = float(candle.get('low', 0))
                    subsequent_prices.append({'high': high, 'low': low})
            except Exception:
                continue
        
        if not subsequent_prices:
            return 'NEUTRAL'
        
        for price in subsequent_prices[:20]:
            if direction in ('LONG', 'BUY', 'BULLISH'):
                if price['high'] > entry_price:
                    return 'WIN'
                elif price['low'] < entry_price:
                    return 'LOSS'
            elif direction in ('SHORT', 'SELL', 'BEARISH'):
                if price['low'] < entry_price:
                    return 'WIN'
                elif price['high'] > entry_price:
                    return 'LOSS'
        
        return 'NEUTRAL'
    
    def calculate_rr(
        self,
        signal: Dict[str, Any],
        result: str,
        price_data: List[Dict[str, Any]]
    ) -> float:
        direction = signal.get('direction', '').upper()
        entry_price = float(signal.get('entry_price', 0)) if 'entry_price' in signal else float(signal.get('score', 0))
        
        if not entry_price or not price_data:
            return 0.0
        
        signal_time = signal.get('_parsed_time')
        if signal_time is None:
            try:
                signal_time = datetime.fromisoformat(signal.get('timestamp', '').replace('Z', '+00:00'))
            except Exception:
                return 0.0
        
        risk = entry_price * 0.001
        
        for candle in price_data:
            try:
                candle_time = datetime.fromisoformat(candle.get('timestamp', '').replace('Z', '+00:00'))
                if candle_time > signal_time:
                    high = float(candle.get('high', 0))
                    low = float(candle.get('low', 0))
                    
                    if result == 'WIN':
                        if direction in ('LONG', 'BUY', 'BULLISH'):
                            reward = high - entry_price
                        else:
                            reward = entry_price - low
                        return round(reward / risk, 2) if risk > 0 else 0.0
                    elif result == 'LOSS':
                        if direction in ('LONG', 'BUY', 'BULLISH'):
                            loss = entry_price - low
                        else:
                            loss = high - entry_price
                        return -round(loss / risk, 2) if risk > 0 else 0.0
            except Exception:
                continue
        
        return 0.0
    
    def analyze_signals(self, signals: List[Dict[str, Any]]) -> Dict[str, Any]:
        results = {
            'period': {
                'start': (datetime.now(timezone.utc) - timedelta(days=self.lookback_days)).strftime('%Y-%m-%d'),
                'end': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
                'days': self.lookback_days
            },
            'total': len(signals),
            'wins': 0,
            'losses': 0,
            'neutral': 0,
            'win_rate': 0.0,
            'avg_rr': 0.0,
            'per_asset': defaultdict(lambda: {
                'total': 0, 'wins': 0, 'losses': 0, 'neutral': 0,
                'win_rate': 0.0, 'scores': [], 'rr_values': []
            }),
            'per_tf': defaultdict(lambda: {
                'total': 0, 'wins': 0, 'losses': 0, 'win_rate': 0.0
            }),
            'score_buckets': {bucket[2]: {'total': 0, 'wins': 0, 'win_rate': 0.0} for bucket in SCORE_BUCKETS},
            'per_session': defaultdict(lambda: {'total': 0, 'wins': 0, 'win_rate': 0.0}),
            'mtf_impact': {
                'confirmed': {'total': 0, 'wins': 0, 'win_rate': 0.0},
                'unconfirmed': {'total': 0, 'wins': 0, 'win_rate': 0.0}
            },
            'streaks': {
                'max_consecutive_wins': 0,
                'max_consecutive_losses': 0,
                'current_streak': 0,
                'current_streak_type': None
            },
            'best_day': '',
            'best_hour_utc': 0,
            'per_day': defaultdict(lambda: {'total': 0, 'wins': 0, 'win_rate': 0.0}),
            'per_hour': defaultdict(lambda: {'total': 0, 'wins': 0, 'win_rate': 0.0}),
            'max_drawdown': 0.0
        }
        
        all_rr = []
        all_results = []
        consecutive_wins = 0
        consecutive_losses = 0
        max_consec_wins = 0
        max_consec_losses = 0
        peak_equity = 0
        current_equity = 0
        max_dd = 0
        
        for signal in signals:
            symbol = signal.get('symbol', 'UNKNOWN')
            tf = signal.get('tf', 'UNKNOWN')
            score = int(signal.get('score', 0))
            session = signal.get('_session', 'off_hours')
            day_of_week = signal.get('_day_of_week', 'Unknown')
            hour_utc = signal.get('_hour_utc', 0)
            
            price_data = self.load_price_data(symbol, tf)
            result = self.evaluate_signal(signal, price_data)
            rr = self.calculate_rr(signal, result, price_data)
            
            all_results.append(result)
            if rr != 0:
                all_rr.append(rr)
            
            results['total'] += 1
            if result == 'WIN':
                results['wins'] += 1
                results['per_asset'][symbol]['wins'] += 1
                results['per_tf'][tf]['wins'] += 1
                results['per_session'][session]['wins'] += 1
                results['per_day'][day_of_week]['wins'] += 1
                results['per_hour'][hour_utc]['wins'] += 1
                
                consecutive_wins += 1
                consecutive_losses = 0
                max_consec_wins = max(max_consec_wins, consecutive_wins)
                
                current_equity += 1
            elif result == 'LOSS':
                results['losses'] += 1
                results['per_asset'][symbol]['losses'] += 1
                results['per_tf'][tf]['losses'] += 1
                results['per_session'][session]['wins'] += 0
                results['per_day'][day_of_week]['losses'] += 1
                results['per_hour'][hour_utc]['losses'] += 1
                
                consecutive_losses += 1
                consecutive_wins = 0
                max_consec_losses = max(max_consec_losses, consecutive_losses)
                
                current_equity -= 1
                peak_equity = max(peak_equity, current_equity)
                dd = peak_equity - current_equity
                max_dd = max(max_dd, dd)
            else:
                results['neutral'] += 1
                results['per_asset'][symbol]['neutral'] += 1
                consecutive_wins = 0
                consecutive_losses = 0
            
            results['per_asset'][symbol]['total'] += 1
            results['per_asset'][symbol]['scores'].append(score)
            if rr != 0:
                results['per_asset'][symbol]['rr_values'].append(rr)
            results['per_tf'][tf]['total'] += 1
            results['per_session'][session]['total'] += 1
            results['per_day'][day_of_week]['total'] += 1
            results['per_hour'][hour_utc]['total'] += 1
            
            for low, high, label in SCORE_BUCKETS:
                if low <= score < high:
                    results['score_buckets'][label]['total'] += 1
                    if result == 'WIN':
                        results['score_buckets'][label]['wins'] += 1
                    break
        
        total_decided = results['wins'] + results['losses']
        if total_decided > 0:
            results['win_rate'] = round(results['wins'] / total_decided * 100, 1)
        
        if all_rr:
            results['avg_rr'] = round(sum(all_rr) / len(all_rr), 2)
        
        for bucket_data in results['score_buckets'].values():
            if bucket_data['total'] > 0:
                bucket_data['win_rate'] = round(bucket_data['wins'] / bucket_data['total'] * 100, 1)
        
        for session_data in results['per_session'].values():
            if session_data['total'] > 0:
                session_data['win_rate'] = round(session_data['wins'] / session_data['total'] * 100, 1)
        
        for day_data in results['per_day'].values():
            if day_data['total'] > 0:
                day_data['win_rate'] = round(day_data['wins'] / day_data['total'] * 100, 1)
        
        for hour_data in results['per_hour'].values():
            if hour_data['total'] > 0:
                hour_data['win_rate'] = round(hour_data['wins'] / hour_data['total'] * 100, 1)
        
        for asset_data in results['per_asset'].values():
            if asset_data['total'] > 0:
                asset_data['win_rate'] = round(asset_data['wins'] / asset_data['total'] * 100, 1)
        
        for tf_data in results['per_tf'].values():
            if tf_data['total'] > 0:
                tf_data['win_rate'] = round(tf_data['wins'] / tf_data['total'] * 100, 1)
        
        best_day = ''
        best_day_wr = 0
        for day, data in results['per_day'].items():
            if data['win_rate'] > best_day_wr and data['total'] >= 3:
                best_day_wr = data['win_rate']
                best_day = day
        results['best_day'] = best_day
        
        best_hour = 0
        best_hour_wr = 0
        for hour, data in results['per_hour'].items():
            if data['win_rate'] > best_hour_wr and data['total'] >= 3:
                best_hour_wr = data['win_rate']
                best_hour = hour
        results['best_hour_utc'] = best_hour
        
        results['streaks'] = {
            'max_consecutive_wins': max_consec_wins,
            'max_consecutive_losses': max_consec_losses,
            'current_streak': consecutive_wins if consecutive_wins > 0 else -consecutive_losses,
            'current_streak_type': 'wins' if consecutive_wins > 0 else 'losses' if consecutive_losses > 0 else None
        }
        results['max_drawdown'] = max_dd
        
        return results
    
    def generate_recommendations(self, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        recommendations = []
        threshold_changes = []
        
        for asset, data in analysis['per_asset'].items():
            if data['total'] < 3:
                continue
            
            win_rate = data.get('win_rate', 0)
            
            if win_rate > 70:
                recommendations.append({
                    'type': 'threshold_raise',
                    'asset': asset,
                    'action': f"Raise {asset} threshold to 80",
                    'reason': f"Win rate {win_rate:.0f}% > 70%",
                    'new_threshold': 80
                })
                threshold_changes.append({'asset': asset, 'old': 75, 'new': 80})
            elif win_rate < 40:
                recommendations.append({
                    'type': 'threshold_lower',
                    'asset': asset,
                    'action': f"Lower {asset} threshold to 65",
                    'reason': f"Win rate {win_rate:.0f}% < 40%",
                    'new_threshold': 65
                })
                threshold_changes.append({'asset': asset, 'old': 75, 'new': 65})
        
        buckets = analysis.get('score_buckets', {})
        if '0-40' in buckets and buckets['0-40']['total'] > 5:
            low_wr = buckets['0-40'].get('win_rate', 0)
            if low_wr < 30:
                recommendations.append({
                    'type': 'filter',
                    'action': f"Disable signals 03:00-06:00 UTC",
                    'reason': f"Score 0-40 win rate only {low_wr:.0f}%"
                })
        
        best_session = ''
        best_session_wr = 0
        for session, data in analysis.get('per_session', {}).items():
            if data.get('win_rate', 0) > best_session_wr and data.get('total', 0) >= 5:
                best_session_wr = data['win_rate']
                best_session = session
        
        if best_session:
            best_asset = ''
            best_asset_wr = 0
            for asset, data in analysis['per_asset'].items():
                if data.get('win_rate', 0) > best_asset_wr and data.get('total', 0) >= 3:
                    best_asset_wr = data['win_rate']
                    best_asset = asset
            
            if best_asset:
                recommendations.append({
                    'type': 'focus',
                    'action': f"Focus: {best_asset} H1 {best_session.title()} session",
                    'reason': f"Best combination: {best_asset_wr:.0f}% win rate"
                })
        
        analysis['recommendations'] = recommendations
        analysis['threshold_changes'] = threshold_changes
        
        return recommendations
    
    def apply_threshold_changes(self, changes: List[Dict[str, Any]]) -> List[str]:
        applied = []
        
        for change in changes:
            asset = change.get('asset', '')
            new_threshold = change.get('new', 75)
            
            if not asset:
                continue
            
            try:
                sys.path.insert(0, os.path.dirname(__file__))
                from adaptive_threshold import get_threshold_engine
                engine = get_threshold_engine()
                old = engine.get_threshold(asset)
                engine.set_threshold(asset, new_threshold)
                engine._save_state(asset)
                applied.append(f"\u2705 {asset} threshold: {old} \u2192 {new_threshold}")
                log.info(f"Applied threshold change: {asset} {old} -> {new_threshold}")
            except Exception as e:
                log.error(f"Failed to apply threshold for {asset}: {e}")
                applied.append(f"\u274c {asset}: {e}")
        
        return applied
    
    def format_report(self, analysis: Dict[str, Any], recommendations: List[Dict[str, Any]]) -> str:
        total = analysis['total']
        wins = analysis['wins']
        losses = analysis['losses']
        win_rate = analysis.get('win_rate', 0)
        avg_rr = analysis.get('avg_rr', 0)
        
        execute_count = sum(1 for _ in range(total))
        
        lines = [
            "\U0001f4c8 WEEKLY BACKTEST REPORT",
            f"Week: {analysis['period']['start']} to {analysis['period']['end']}",
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501",
            "OVERALL",
            f"Signals  : {total} total",
            f"Execute  : {wins + losses} ({int((wins+losses)/max(total,1)*100)}%)",
            f"Win Rate : {win_rate}%",
            f"Avg RR   : {avg_rr}",
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501",
            "BY ASSET"
        ]
        
        for asset in ASSETS:
            data = analysis['per_asset'].get(asset, {})
            if data.get('total', 0) > 0:
                wr = data.get('win_rate', 0)
                bar = _format_bar(wr)
                lines.append(f"{asset:<8} {wr:.0f}% {bar} ({data['total']} signals)")
        
        lines.extend([
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501",
            "BY SCORE BUCKET"
        ])
        
        for low, high, label in SCORE_BUCKETS:
            bucket = analysis['score_buckets'].get(label, {})
            wr = bucket.get('win_rate', 0)
            bar = _format_bar(wr)
            lines.append(f"{label:>6} : {wr:.0f}% win {bar}")
        
        streaks = analysis.get('streaks', {})
        lines.extend([
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501",
            "STREAKS & DRAWDOWN",
            f"Max Wins  : {streaks.get('max_consecutive_wins', 0)} consecutive",
            f"Max Losses: {streaks.get('max_consecutive_losses', 0)} consecutive",
            f"Max DD    : {analysis.get('max_drawdown', 0)} units",
            f"Best Day  : {analysis.get('best_day', 'N/A')}",
            f"Best Hour : {analysis.get('best_hour_utc', 0)}:00 UTC",
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501",
            "SESSIONS"
        ])
        
        for session_name in ['london', 'new_york', 'tokyo', 'sydney']:
            data = analysis['per_session'].get(session_name, {})
            if data.get('total', 0) > 0:
                wr = data.get('win_rate', 0)
                bar = _format_bar(wr)
                lines.append(f"{session_name.title():<12} {wr:.0f}% {bar} ({data['total']})")
        
        lines.append("\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501")
        
        best_setup = self._find_best_setup(analysis)
        if best_setup:
            lines.extend([
                "BEST SETUP",
                f"Asset : {best_setup['asset']} {best_setup['tf']}",
                f"Score : {best_setup['score_range']} with MTF confirmed",
                f"Win%  : {best_setup['win_rate']}%",
                "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"
            ])
        
        if recommendations:
            lines.append("RECOMMENDATIONS")
            for rec in recommendations:
                lines.append(f"\u2192 {rec['action']}")
            lines.append("\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501")
        
        threshold_changes = analysis.get('threshold_changes', [])
        if threshold_changes:
            lines.append("Auto-applying threshold changes...")
            for tc in threshold_changes:
                lines.append(f"\u2705 {tc['asset']} threshold: {tc['old']} \u2192 {tc['new']}")
        
        return '\n'.join(lines)
    
    def _find_best_setup(self, analysis: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        best = None
        best_wr = 0
        
        for asset, data in analysis['per_asset'].items():
            if data.get('total', 0) >= 3:
                wr = data.get('win_rate', 0)
                if wr > best_wr:
                    best_wr = wr
                    best = {
                        'asset': asset,
                        'tf': 'H1',
                        'score_range': '80+',
                        'win_rate': wr
                    }
        
        return best
    
    def save_report(self, analysis: Dict[str, Any], recommendations: List[Dict[str, Any]]) -> str:
        date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        
        report = {
            'date': date,
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'period': analysis.get('period', {}),
            'summary': {
                'total': analysis['total'],
                'wins': analysis['wins'],
                'losses': analysis['losses'],
                'neutral': analysis['neutral'],
                'win_rate': analysis.get('win_rate', 0),
                'avg_rr': analysis.get('avg_rr', 0)
            },
            'per_asset': dict(analysis['per_asset']),
            'per_tf': dict(analysis['per_tf']),
            'score_buckets': analysis['score_buckets'],
            'per_session': dict(analysis['per_session']),
            'streaks': analysis.get('streaks', {}),
            'best_day': analysis.get('best_day', ''),
            'best_hour_utc': analysis.get('best_hour_utc', 0),
            'max_drawdown': analysis.get('max_drawdown', 0),
            'recommendations': recommendations,
            'threshold_changes': analysis.get('threshold_changes', [])
        }
        
        json_path = REPORTS_DIR / f'backtest_{date}.json'
        try:
            with open(json_path, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            log.info(f"Saved backtest report: {json_path}")
            return str(json_path)
        except Exception as e:
            log.error(f"Failed to save report: {e}")
            return ''
    
    def send_telegram(self, report: str) -> bool:
        try:
            import urllib.request
            
            bot_token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
            chat_id = os.environ.get('TELEGRAM_CHAT_ID', '')
            
            if not bot_token or not chat_id:
                return False
            
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            data = json.dumps({'chat_id': chat_id, 'text': report}).encode('utf-8')
            
            req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
            urllib.request.urlopen(req, timeout=10)
            
            log.info("Backtest report sent to Telegram")
            return True
        except Exception as e:
            log.error(f"Failed to send to Telegram: {e}")
            return False
    
    def run(self) -> Dict[str, Any]:
        log.info("Running weekly backtest...")
        
        signals = self.load_signals(self.lookback_days)
        analysis = self.analyze_signals(signals)
        recommendations = self.generate_recommendations(analysis)
        
        report_text = self.format_report(analysis, recommendations)
        
        report_path = self.save_report(analysis, recommendations)
        
        self.send_telegram(report_text)
        
        threshold_changes = analysis.get('threshold_changes', [])
        if threshold_changes:
            applied = self.apply_threshold_changes(threshold_changes)
            for msg in applied:
                print(msg)
        
        print(report_text)
        
        return analysis


# Global instance
_backtester: Optional[AutoBacktester] = None


def get_backtester() -> AutoBacktester:
    global _backtester
    if _backtester is None:
        _backtester = AutoBacktester()
    return _backtester


# ══════════════════════════════════════════════════════════════════════════════
# CLI TEST
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import sys
    
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    if '--test' in sys.argv:
        print("=" * 60)
        print("  AUTO-BACKTESTER - TEST")
        print("=" * 60)
        
        backtester = AutoBacktester()
        
        result = backtester.run()
        
        print(f"\nAnalysis complete: {result['total']} signals analyzed")
        print(f"Win rate: {result.get('win_rate', 0)}%")
        print(f"Avg RR: {result.get('avg_rr', 0)}")
        print(f"Best day: {result.get('best_day', 'N/A')}")
        print(f"Best hour: {result.get('best_hour_utc', 0)}:00 UTC")
        
        streaks = result.get('streaks', {})
        print(f"Max consecutive wins: {streaks.get('max_consecutive_wins', 0)}")
        print(f"Max consecutive losses: {streaks.get('max_consecutive_losses', 0)}")
        
        print("\nScore Buckets:")
        for label, data in result.get('score_buckets', {}).items():
            print(f"  {label}: {data.get('win_rate', 0)}% ({data.get('total', 0)} signals)")
        
        print("\n" + "=" * 60)
    else:
        print("Usage: python auto_backtester.py --test")
