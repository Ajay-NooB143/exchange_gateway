"""
Instagram Reels Content Generator - OMNI BRAIN V2
==================================================
Auto-generate Instagram Reel scripts from trading signals.

Features:
  A) Auto-generate signal recap reel scripts after EXECUTE signals
  B) Weekly performance reel (every Sunday)
  C) Educational reel series (5 scripts)
  D) ASCII visual templates
  E) Dynamic 30-day content calendar

Usage:
  python instagram_reels_generator.py --test
  python instagram_reels_generator.py --signal XAUUSD --score 85
  python instagram_reels_generator.py --weekly
  python instagram_reels_generator.py --educational
  python instagram_reels_generator.py --calendar
"""

import os
import sys
import json
import csv
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from pathlib import Path

log = logging.getLogger('ReelsGenerator')

CONTENT_DIR = Path(__file__).parent
REELS_DIR = CONTENT_DIR / 'reels'
TEMPLATES_DIR = CONTENT_DIR / 'templates'

REELS_DIR.mkdir(exist_ok=True)
TEMPLATES_DIR.mkdir(exist_ok=True)

LOG_DIR = Path(__file__).parent.parent / 'production' / 'logs'

ASSETS = ['XAUUSD', 'EURUSD', 'GBPUSD', 'SP500']

EDUCATIONAL_SCRIPTS = [
    {
        'id': 1,
        'title': 'OrderBlock kya hota hai?',
        'hook': 'OrderBlock kya hota hai jo itna powerful hai? 🤯',
        'visual': 'Show chart with highlighted order block zone',
        'explanation': (
            'OrderBlock wo zone hai jahan institutions ne bada order lagaya. '
            'Jab price us zone pe wapas aata hai, woh react karta hai. '
            'Hamara system automatically detect karta hai:\n'
            '✅ Bullish OB — price ke neeche, support banega\n'
            '✅ Bearish OB — price ke upar, resistance banega\n'
            '✅ OB + FVG + Sweep = High probability setup'
        ),
        'example': 'XAUUSD H1 — Last week ka Bullish OB 2340 pe tha, price wapas aaya aur 2370 tak gaya!',
        'cta': 'Aisa system chahiye? Link in bio! Follow for daily signals!',
        'hashtags': '#orderblock #forextrader #SMC #smartmoney #XAUUSD #forex #trading'
    },
    {
        'id': 2,
        'title': 'FVG — Fair Value Gap explain',
        'hook': 'FVG kya hai jo har trader dekhna chahta hai? 📊',
        'visual': 'Show chart with FVG zone highlighted, price filling the gap',
        'explanation': (
            'Fair Value Gap tab banta hai jab price ek direction mein bahut tez jaata hai. '
            'Beech ka jo gap hota hai — wo FVG hai.\n'
            '✅ Bullish FVG — 3 candles ka gap upar ki taraf\n'
            '✅ Bearish FVG — 3 candles ka gap neeche ki taraf\n'
            '✅ Price aksar gap fill karne wapas aata hai'
        ),
        'example': 'EURUSD M15 — FVG 1.0845 pe tha, price 1.0848 tak aaya aur fill kiya!',
        'cta': 'FVG ka full course chahiye? Link in bio!',
        'hashtags': '#FVG #fairvaluegap #forextrader #forex #SMC #liquidity'
    },
    {
        'id': 3,
        'title': 'Liquidity Sweep kaise pehchane?',
        'hook': 'Liquidity Sweep kaise pehchane jo fakeout nahi hai! 🎯',
        'visual': 'Show chart with sweep event marked, previous high/low taken out',
        'explanation': (
            'Liquidity Sweep tab hota hai jab price previous high ya low todta hai '
            'aur phir turant reverse hota hai.\n'
            '✅ Institutions ne retailers ke stop-loss hunt kiye\n'
            '✅ Sweep ke baad real move aata hai\n'
            '✅ Hamara system sweep detect karta hai aur signal deta hai'
        ),
        'example': 'GBPUSD H4 — Previous low 1.2680 sweep hua, price 1.2720 tak gaya!',
        'cta': 'Sweep detect karna seekho! Link in bio!',
        'hashtags': '#liquiditysweep #forex #trading #SMC #smartmoney #forexsignals'
    },
    {
        'id': 4,
        'title': 'MTF confirmation kyun zaroori?',
        'hook': 'Ek timeframe pe signal mila — kya kaafi hai? NAHI! ⚠️',
        'visual': 'Show multi-timeframe grid with arrows, conflict highlighted',
        'explanation': (
            'Multi-Timeframe Confirmation ka matlab hai:\n'
            '✅ M15 pe signal mila → H1 ka bias dekho\n'
            '✅ H1 pe signal mila → H4 ka structure dekho\n'
            '✅ H4 pe signal mila → D1 ka trend dekho\n'
            'Agar sab timeframes same direction mein ho — CONFIRMED!\n'
            'Agar conflict hai — BLOCKED! Wait karo.'
        ),
        'example': 'XAUUSD — M15 Bullish, H1 Bullish, H4 Bullish, D1 Bullish = CONFIRMED EXECUTE!',
        'cta': 'MTF confirmation seekho! Link in bio!',
        'hashtags': '#MTF #multitimeframe #forextrader #trading #analysis #forex'
    },
    {
        'id': 5,
        'title': 'Confidence scoring — 0 se 100',
        'hook': 'Hamara system har signal ko 0 se 100 deta hai! Kaise? 🔢',
        'visual': 'Show score bar filling up with component breakdown',
        'explanation': (
            'Confidence Score 5 components se banta hai:\n'
            '✅ OrderBlock confirm = 20 points\n'
            '✅ FVG zone mila = 20 points\n'
            '✅ Liquidity Sweep fire = 30 points\n'
            '✅ VWAP ke upar/neeche = 15 points\n'
            '✅ Session active (London/NY) = 15 points\n'
            'Total 100 mein se kitne mile? Wo hai confidence score!'
        ),
        'example': 'XAUUSD score 85/100 — OB ✅ FVG ✅ Sweep ✅ VWAP ✅ Session ✅',
        'cta': 'Score dekhna seekho! Follow for daily signals!',
        'hashtags': '#confidencescore #forex #trading #signal #analysis #forextrader'
    }
]


class ReelScriptGenerator:
    """Generate Instagram Reel scripts from trading signals."""
    
    def __init__(self):
        self.reels_dir = REELS_DIR
        self.templates_dir = TEMPLATES_DIR
    
    def generate_signal_reel(
        self, symbol: str, direction: str, score: int,
        entry: float = 0.0, sl: float = 0.0, tp1: float = 0.0,
        components: Dict[str, int] = None
    ) -> str:
        """Generate a reel script for an EXECUTE signal."""
        comps = components or {}
        
        ob_check = '\u2705 OrderBlock confirm hua' if comps.get('OB', 0) > 0 else '\u274c OrderBlock nahi mila'
        fvg_check = '\u2705 FVG zone mila' if comps.get('FVG', 0) > 0 else '\u274c FVG nahi mila'
        sweep_check = '\u2705 Liquidity sweep fire hua' if comps.get('SWEEP', 0) > 0 else '\u274c Sweep nahi hua'
        vwap_check = '\u2705 VWAP ke upar price' if comps.get('VWAP', 0) > 0 else '\u274c VWAP ke neeche'
        session_check = '\u2705 London/NY session active' if comps.get('SESSION', 0) > 0 else '\u274c Session nahi hai'
        
        score_bar = '\u2588' * (score // 10) + '\u2591' * (10 - score // 10)
        risk_pct = 1.0
        
        sl_pips = abs(entry - sl) if entry and sl else 0
        if symbol in ('XAUUSD', 'SP500'):
            sl_pips = sl_pips * 10
        
        script = f"""─────────────────────────────────────
REEL SCRIPT: {symbol} {direction} SIGNAL
─────────────────────────────────────
HOOK (0-3 sec):
"{symbol} ne diya EXECUTE signal! 🔥
Score: {score}/100 — kya hoga aage?"

VISUAL (3-8 sec):
Show terminal with signal details
Highlight score bar filling up: {score_bar}
Show MTF grid all green

BREAKDOWN (8-20 sec):
"Dekho kaise bana yeh signal:
{ob_check}
{fvg_check}
{sweep_check}
{vwap_check}
{session_check}
Total score: {score}/100 🎯"

ENTRY SETUP (20-30 sec):
"Entry: {entry}
SL: {sl} ({sl_pips:.0f} pips)
TP1: {tp1} | TP2: {tp1 + 2 * (tp1 - entry) if entry and tp1 else 0}
RR: 1:2 — risk sirf {risk_pct}%"

CTA (30-35 sec):
"Aisa system chahiye?
Link in bio 👆
Follow karo daily signals ke liye!"

HASHTAGS:
#forextrader #{symbol} #SmartMoney
#forexsignals #trading #forex
#liquidity #orderblock #SMC
#forexhindi #tradinghindi
─────────────────────────────────────"""
        
        date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        filename = f"{date_str}_{symbol}_{direction}.txt"
        filepath = self.reels_dir / filename
        
        try:
            with open(filepath, 'w') as f:
                f.write(script)
            log.info(f"Generated signal reel: {filepath}")
        except Exception as e:
            log.error(f"Failed to save reel: {e}")
        
        return script
    
    def generate_weekly_reel(self) -> str:
        """Generate weekly performance reel script."""
        try:
            bt_path = LOG_DIR / 'reports'
            json_files = sorted(bt_path.glob('backtest_*.json'), reverse=True)
            
            if not json_files:
                return self._generate_weekly_reel_from_signals()
            
            with open(json_files[0], 'r') as f:
                bt_data = json.load(f)
            
            summary = bt_data.get('summary', {})
            per_asset = bt_data.get('per_asset', {})
            
            total = summary.get('total', 0)
            win_rate = summary.get('win_rate', 0)
            avg_rr = summary.get('avg_rr', 0)
            
            best_asset = ''
            best_wr = 0
            for asset, data in per_asset.items():
                if data.get('win_rate', 0) > best_wr:
                    best_wr = data['win_rate']
                    best_asset = asset
            
            return self._format_weekly_reel(total, win_rate, avg_rr, best_asset, best_wr, per_asset)
        except Exception as e:
            log.error(f"Failed to load backtest data: {e}")
            return self._generate_weekly_reel_from_signals()
    
    def _generate_weekly_reel_from_signals(self) -> str:
        log_file = LOG_DIR / 'signal_log.csv'
        if not log_file.exists():
            return self._format_weekly_reel(0, 0, 0, 'N/A', 0, {})
        
        signals = []
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        
        try:
            with open(log_file, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        ts = datetime.fromisoformat(row.get('timestamp', '').replace('Z', '+00:00'))
                        if ts >= cutoff:
                            signals.append(row)
                    except Exception:
                        continue
        except Exception:
            pass
        
        total = len(signals)
        return self._format_weekly_reel(total, 0, 0, 'N/A', 0, {})
    
    def _format_weekly_reel(
        self, total: int, win_rate: float, avg_rr: float,
        best_asset: str, best_wr: float, per_asset: Dict
    ) -> str:
        asset_lines = []
        for asset in ASSETS:
            data = per_asset.get(asset, {})
            wr = data.get('win_rate', 0)
            sig_count = data.get('total', 0)
            bar = '\u2588' * int(wr / 10) + '\u2591' * (10 - int(wr / 10))
            asset_lines.append(f"{asset}: {wr:.0f}% {bar} ({sig_count} signals)")
        
        asset_str = '\n'.join(asset_lines) if asset_lines else 'No data yet'
        
        date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        
        script = f"""─────────────────────────────────────
WEEKLY PERFORMANCE REEL — {date_str}
─────────────────────────────────────
HOOK (0-3 sec):
"Is hafte {win_rate}% signals sahi nikle! 🔥
Dekho kya hua iss hafte!"

VISUAL (3-10 sec):
Bar chart of win rates per asset
{asset_str}

BEST SETUP (10-20 sec):
"Best setup tha:
{best_asset} — {best_wr:.0f}% win rate
Score 80+ with MTF confirmed
Avg RR: {avg_rr}"

OVERALL (20-25 sec):
"Total signals: {total}
Win rate: {win_rate}%
Avg RR: {avg_rr}
System consistently profitable! 📈"

CTA (25-30 sec):
"System dekho link in bio
Follow for daily signals! 🎯"

HASHTAGS:
#forextrader #weeklyresults #forex
#trading #profit #signals #forexhindi
─────────────────────────────────────"""
        
        date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        filename = f"{date_str}_weekly.txt"
        filepath = self.reels_dir / filename
        
        try:
            with open(filepath, 'w') as f:
                f.write(script)
            log.info(f"Generated weekly reel: {filepath}")
        except Exception as e:
            log.error(f"Failed to save weekly reel: {e}")
        
        return script
    
    def generate_educational_reel(self, reel_id: int = 0) -> str:
        """Generate educational reel script."""
        if reel_id < 1 or reel_id > len(EDUCATIONAL_SCRIPTS):
            reel_id = 1
        
        edu = EDUCATIONAL_SCRIPTS[reel_id - 1]
        
        script = f"""─────────────────────────────────────
EDUCATIONAL REEL #{edu['id']}: {edu['title']}
─────────────────────────────────────
HOOK (0-3 sec):
"{edu['hook']}"

VISUAL (3-8 sec):
{edu['visual']}

EXPLANATION (8-25 sec):
{edu['explanation']}

EXAMPLE (25-30 sec):
"{edu['example']}"

CTA (30-35 sec):
"{edu['cta']}"

HASHTAGS:
{edu['hashtags']}
─────────────────────────────────────"""
        
        filename = f"edu_{reel_id:02d}_{edu['title'].replace(' ', '_')[:30]}.txt"
        filepath = self.reels_dir / filename
        
        try:
            with open(filepath, 'w') as f:
                f.write(script)
            log.info(f"Generated educational reel: {filepath}")
        except Exception as e:
            log.error(f"Failed to save educational reel: {e}")
        
        return script
    
    def generate_all_educational_reels(self) -> List[str]:
        scripts = []
        for edu in EDUCATIONAL_SCRIPTS:
            script = self.generate_educational_reel(edu['id'])
            scripts.append(script)
        return scripts
    
    def generate_content_calendar(self) -> Dict[str, Any]:
        """Generate 30-day content calendar from today."""
        today = datetime.now(timezone.utc).date()
        calendar = {'generated_at': datetime.now(timezone.utc).isoformat(), 'days': []}
        
        assets_cycle = ['XAUUSD', 'EURUSD', 'GBPUSD', 'SP500']
        edu_topics = [
            'OrderBlock kya hota hai?',
            'FVG — Fair Value Gap explain',
            'Liquidity Sweep kaise pehchane?',
            'MTF confirmation kyun zaroori?',
            'Confidence scoring — 0 se 100'
        ]
        
        for i in range(30):
            day = today + timedelta(days=i)
            day_num = i + 1
            events = []
            
            if day_num in (1, 3, 5, 8, 10, 12, 15, 17, 19, 22, 24, 26):
                asset = assets_cycle[(day_num - 1) % len(assets_cycle)]
                events.append({
                    'type': 'signal_recap',
                    'title': f'{asset} Signal Recap',
                    'asset': asset,
                    'time': '10:00 UTC'
                })
            
            if day_num in (2, 4, 9, 11, 16, 20, 23, 25, 27):
                edu_idx = (day_num - 1) % len(edu_topics)
                events.append({
                    'type': 'educational',
                    'title': edu_topics[edu_idx],
                    'time': '14:00 UTC'
                })
            
            if day_num in (7, 14, 21, 28):
                events.append({
                    'type': 'weekly_results',
                    'title': 'Weekly Performance Results',
                    'time': '18:00 UTC'
                })
            
            events.append({
                'type': 'story',
                'title': 'Daily Live Score Card',
                'time': '09:00 UTC'
            })
            
            day_str = day.strftime('%Y-%m-%d')
            day_name = day.strftime('%A')
            calendar['days'].append({
                'date': day_str,
                'day_name': day_name,
                'day_number': day_num,
                'events': events
            })
        
        calendar_path = CONTENT_DIR / 'calendar.json'
        try:
            with open(calendar_path, 'w') as f:
                json.dump(calendar, f, indent=2)
            log.info(f"Generated content calendar: {calendar_path}")
        except Exception as e:
            log.error(f"Failed to save calendar: {e}")
        
        return calendar
    
    def load_template(self, template_name: str) -> str:
        filepath = self.templates_dir / template_name
        if filepath.exists():
            return filepath.read_text()
        return ''
    
    def render_signal_card(
        self, symbol: str, direction: str, score: int,
        entry: float = 0, tp: float = 0, sl: float = 0
    ) -> str:
        template = self.load_template('signal_card.txt')
        if not template:
            return f"No template: signal_card.txt"
        
        filled = score // 10
        bar = '\u2588' * filled + '\u2591' * (10 - filled)
        decision = 'EXECUTE' if score >= 75 else 'WAIT' if score >= 50 else 'BLOCK'
        
        return template.format(
            symbol=symbol, direction=direction, score=score,
            bar=bar, decision=decision,
            entry=entry, tp=tp, sl=sl
        )
    
    def render_weekly_card(
        self, total: int, win_rate: float,
        best_asset: str, avg_rr: float
    ) -> str:
        template = self.load_template('weekly_card.txt')
        if not template:
            return "No template: weekly_card.txt"
        
        return template.format(
            total=total, win_rate=win_rate,
            best_asset=best_asset, avg_rr=avg_rr
        )


# Global instance
_generator: Optional[ReelScriptGenerator] = None


def get_reels_generator() -> ReelScriptGenerator:
    global _generator
    if _generator is None:
        _generator = ReelScriptGenerator()
    return _generator


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import sys
    
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    if '--test' in sys.argv:
        print("=" * 60)
        print("  INSTAGRAM REELS GENERATOR - TEST")
        print("=" * 60)
        
        gen = ReelScriptGenerator()
        
        print("\n--- Signal Reel (XAUUSD EXECUTE, score 85) ---")
        signal_reel = gen.generate_signal_reel(
            'XAUUSD', 'BULLISH', 85,
            entry=2350.50, sl=2343.20, tp1=2357.80,
            components={'OB': 20, 'FVG': 20, 'SWEEP': 30, 'VWAP': 10, 'SESSION': 5}
        )
        print(signal_reel[:500])
        
        print("\n--- Weekly Reel ---")
        weekly_reel = gen.generate_weekly_reel()
        print(weekly_reel[:500])
        
        print("\n--- Educational Reel #1 ---")
        edu_reel = gen.generate_educational_reel(1)
        print(edu_reel[:500])
        
        print("\n--- All Educational Reels ---")
        all_edu = gen.generate_all_educational_reels()
        print(f"Generated {len(all_edu)} educational reels")
        
        print("\n--- Content Calendar ---")
        calendar = gen.generate_content_calendar()
        print(f"Generated {len(calendar['days'])}-day calendar")
        for day in calendar['days'][:3]:
            events = ', '.join(e['type'] for e in day['events'])
            print(f"  {day['date']} ({day['day_name']}): {events}")
        
        print("\n--- Signal Card Template ---")
        card = gen.render_signal_card('XAUUSD', 'BULLISH', 85, 2350.50, 2357.80, 2343.20)
        print(card)
        
        print("\n" + "=" * 60)
    
    elif '--signal' in sys.argv:
        idx = sys.argv.index('--signal')
        symbol = sys.argv[idx + 1].upper() if idx + 1 < len(sys.argv) else 'XAUUSD'
        score = int(sys.argv[sys.argv.index('--score') + 1]) if '--score' in sys.argv else 80
        
        gen = ReelScriptGenerator()
        reel = gen.generate_signal_reel(symbol, 'BULLISH', score)
        print(reel)
    
    elif '--weekly' in sys.argv:
        gen = ReelScriptGenerator()
        reel = gen.generate_weekly_reel()
        print(reel)
    
    elif '--educational' in sys.argv:
        gen = ReelScriptGenerator()
        reels = gen.generate_all_educational_reels()
        for r in reels:
            print(r)
            print()
    
    elif '--calendar' in sys.argv:
        gen = ReelScriptGenerator()
        cal = gen.generate_content_calendar()
        print(json.dumps(cal, indent=2)[:2000])
    
    else:
        print("Usage:")
        print("  python instagram_reels_generator.py --test")
        print("  python instagram_reels_generator.py --signal XAUUSD --score 85")
        print("  python instagram_reels_generator.py --weekly")
        print("  python instagram_reels_generator.py --educational")
        print("  python instagram_reels_generator.py --calendar")
