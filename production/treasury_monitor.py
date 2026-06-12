"""
US Treasury Yield Monitor - OMNI BRAIN V2
Tracks 2Y/10Y/30Y yields and calculates curve inversion/impact.
"""
import os, json, logging, time, urllib.request, threading
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple
from pathlib import Path

log = logging.getLogger('TreasuryMonitor')
LOG_DIR = Path(__file__).parent / 'logs'

YIELD_SYMBOLS = {'US02Y': '2Y', 'US10Y': '10Y', 'US30Y': '30Y'}
INFLATION_PROXY = 2.5

class TreasuryMonitor:
    def __init__(self):
        self.api_key = os.environ.get('LIVE_DATA_API_KEY', '')
        self.yields: Dict[str, float] = {}
        self.prev_yields: Dict[str, float] = {}
        self.history: Dict[str, list] = {'US02Y': [], 'US10Y': [], 'US30Y': []}
        self.last_fetch = 0.0
        self.fetch_interval = 900  # 15 min
    
    @property
    def is_configured(self):
        return bool(self.api_key)
    
    def fetch_yields(self) -> Dict[str, float]:
        """Fetch current yields from Twelve Data."""
        if not self.is_configured:
            return self.yields
        now = time.time()
        if now - self.last_fetch < self.fetch_interval:
            return self.yields
        self.last_fetch = now
        self.prev_yields = self.yields.copy()
        for symbol, label in YIELD_SYMBOLS.items():
            try:
                url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval=15min&outputsize=2&apikey={self.api_key}"
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                resp = urllib.request.urlopen(req, timeout=10)
                data = json.loads(resp.read())
                if data.get('status') == 'ok':
                    values = data.get('values', [])
                    if values:
                        close = float(values[0]['close'])
                        self.yields[label] = close
                        self.history[symbol].append({'price': close, 'timestamp': datetime.now(timezone.utc).isoformat()})
                        if len(self.history[symbol]) > 100:
                            self.history[symbol] = self.history[symbol][-100:]
            except Exception as e:
                log.debug(f"Failed to fetch {symbol}: {e}")
        self._save_state()
        return self.yields
    
    def _save_state(self):
        try:
            with open(LOG_DIR / 'yield_history.json', 'w') as f:
                json.dump({'yields': self.yields, 'history': self.history, 'updated': datetime.now(timezone.utc).isoformat()}, f, indent=2)
        except Exception as e:
            log.debug(f"Failed to save yield history: {e}")

    def get_yield_curve(self) -> float:
        """10Y - 2Y spread. Negative = inverted."""
        if '10Y' in self.yields and '2Y' in self.yields:
            return round(self.yields['10Y'] - self.yields['2Y'], 2)
        return 0.0
    
    def get_real_yield(self) -> float:
        """10Y yield minus inflation proxy."""
        if '10Y' in self.yields:
            return round(self.yields['10Y'] - INFLATION_PROXY, 2)
        return 0.0
    
    def get_score_adjustment(self, symbol: str) -> Tuple[int, str]:
        """Get score adjustment based on yield dynamics."""
        yields = self.yields
        if not yields:
            return 0, 'no yield data'
        curve = self.get_yield_curve()
        real_yield = self.get_real_yield()
        ten_y = yields.get('10Y', 0)
        
        if symbol == 'XAUUSD':
            if real_yield < 0:
                return 10, f"real yield {real_yield:.1f}% → gold BULLISH +10"
            elif real_yield > 3:
                return -10, f"real yield {real_yield:.1f}% → gold BEARISH -10"
            if curve < 0:
                return 15, f"curve {curve:.1f}% INVERTED → safe haven +15"
            return 5, f"curve {curve:.1f}% normal +5"
        
        elif symbol in ('SP500', 'US30', 'NAS100'):
            if curve < 0:
                return -15, f"curve INVERTED → equities BEARISH -15"
            if ten_y > 5:
                return -15, f"10Y {ten_y:.1f}% > 5% → all equities BEARISH -15"
            if curve > 0.5:
                return 10, f"curve normal → equities BULLISH +10"
            return 0, 'neutral'
        
        elif symbol in ('EURUSD', 'GBPUSD'):
            if '10Y' in self.prev_yields and '10Y' in self.yields:
                change = self.yields['10Y'] - self.prev_yields.get('10Y', self.yields['10Y'])
                if change > 0.05:
                    return -10, f"US10Y rising +{change:.1f}% → USD strong"
                elif change < -0.05:
                    return 10, f"US10Y falling {change:.1f}% → USD weak"
        return 0, 'neutral'
    
    def get_significant_moves(self) -> Optional[str]:
        """Check for significant yield moves and return Telegram-formatted alert."""
        if not self.prev_yields or not self.yields:
            return None
        alerts = []
        for label in ('2Y', '10Y', '30Y'):
            curr = self.yields.get(label, 0)
            prev = self.prev_yields.get(label, curr)
            change = (curr - prev) * 100  # in bps
            if abs(change) > 5:
                direction = "RISE" if change > 0 else "DROP"
                alerts.append(f"{label}: {prev:.2f}% → {curr:.2f}% ({(direction)} {abs(change):.0f}bps)")
        if not alerts:
            return None
        curve = self.get_yield_curve()
        curve_desc = "NORMAL" if curve > 0.5 else ("FLATTENING" if curve > 0 else "INVERTED")
        ten_y = self.yields.get('10Y', 0)
        now_utc = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
        impact_lines = []
        if curve < 0:
            impact_lines.append("XAUUSD: 🟢 safe haven +15")
            impact_lines.append("SP500:  🔴 BEARISH pressure -15")
        elif ten_y > 5:
            impact_lines.append("XAUUSD: 🟡 mixed")
            impact_lines.append("SP500:  🔴 BEARISH all equities")
        real = self.get_real_yield()
        if real < 0:
            impact_lines.append("XAUUSD: 🟢 BULLISH (real yield negative)")
        elif real > 3:
            impact_lines.append("XAUUSD: 🔴 BEARISH (real yield high)")
        if '10Y' in self.prev_yields and '10Y' in self.yields:
            change_10y = self.yields['10Y'] - self.prev_yields.get('10Y', self.yields['10Y'])
            if abs(change_10y) > 0.05:
                if change_10y > 0:
                    impact_lines.append("EURUSD: 🔴 USD strengthening")
                else:
                    impact_lines.append("EURUSD: 🟢 USD weakening")
        impact_str = "\n".join(impact_lines) if impact_lines else "Impact: Checking..."
        msg = (
            f"📈 TREASURY YIELD ALERT\n"
            f"{' | '.join(alerts)}\n"
            f"Yield Curve: {curve:+.2f}% ({curve_desc})\n"
            f"Impact:\n{impact_str}\n"
            f"Time: {now_utc}"
        )
        return msg
    
    def format_terminal(self) -> str:
        yields = self.yields
        if not yields:
            return "[YIELD] No data"
        curve = self.get_yield_curve()
        real = self.get_real_yield()
        parts = [f"[YIELD] 2Y:{yields.get('2Y', 'N/A'):.2f}% 10Y:{yields.get('10Y', 'N/A'):.2f}% 30Y:{yields.get('30Y', 'N/A'):.2f}%"]
        if curve < 0:
            parts.append(f"[YIELD] Curve: {curve:.1f}% ⚠️ INVERTED")
        else:
            parts.append(f"[YIELD] Curve: {curve:.1f}% ✅ NORMAL")
        parts.append(f"[YIELD] Real: {real:.1f}% → Gold {'BULLISH' if real < 0 else 'BEARISH' if real > 3 else 'NEUTRAL'}")
        return "\n".join(parts)

# Global instance
_monitor: Optional[TreasuryMonitor] = None
_lock = threading.Lock()
def get_treasury_monitor() -> TreasuryMonitor:
    global _monitor
    if _monitor is None:
        with _lock:
            if _monitor is None:
                _monitor = TreasuryMonitor()
    return _monitor
