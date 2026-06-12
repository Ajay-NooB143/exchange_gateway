"""
Sentiment Heatmap Engine - OMNI BRAIN V2
Aggregates sentiment from Fear & Greed Index, currency strength meter, and COT proxy.
"""
import os, json, logging, urllib.request, math, threading
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple
from pathlib import Path

log = logging.getLogger('SentimentEngine')
LOG_DIR = Path(__file__).parent / 'logs'

CURRENCIES = ['USD', 'EUR', 'GBP', 'JPY', 'CHF', 'AUD', 'CAD', 'NZD']

class SentimentEngine:
    def __init__(self):
        self.fear_greed: int = 50
        self.currency_strength: Dict[str, int] = {c: 50 for c in CURRENCIES}
        self.cot_proxy: Dict[str, str] = {}
        self.cache_duration = 3600
        self._last_fetch = 0.0
        self._load_state()
    
    def _load_state(self):
        path = LOG_DIR / 'sentiment_cache.json'
        if path.exists():
            try:
                with open(path) as f: data = json.load(f)
                self.fear_greed = data.get('fear_greed', 50)
                self.currency_strength = data.get('currency_strength', {c: 50 for c in CURRENCIES})
            except Exception as e:
                log.debug(f"Failed to load sentiment cache: {e}")

    def _save_state(self):
        try:
            with open(LOG_DIR / 'sentiment_cache.json', 'w') as f:
                json.dump({'fear_greed': self.fear_greed, 'currency_strength': self.currency_strength, 'updated': datetime.now(timezone.utc).isoformat()}, f, indent=2)
        except Exception as e:
            log.debug(f"Failed to save sentiment cache: {e}")
    
    def fetch_fear_greed(self) -> int:
        """Fetch Fear & Greed Index from alternative.me."""
        try:
            url = 'https://api.alternative.me/fng/?limit=1'
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read())
            value = int(data['data'][0]['value'])
            self.fear_greed = max(0, min(100, value))
        except Exception as e:
            log.debug(f"Fear & Greed fetch failed: {e}")
        return self.fear_greed
    
    def _calculate_currency_strength(self, prices: Dict[str, float]) -> Dict[str, int]:
        """Calculate currency strength from 8 major pair prices.
        
        Uses relative performance of each currency across pairs.
        USD strength derived from inverse pairs (EURUSD, GBPUSD, AUDUSD, NZDUSD).
        """
        strengths = {}
        if prices:
            baseline = {'EURUSD': 1.08, 'GBPUSD': 1.27, 'USDJPY': 150.0,
                        'USDCHF': 0.88, 'AUDUSD': 0.65, 'USDCAD': 1.36,
                        'NZDUSD': 0.60, 'EURJPY': 162.0, 'GBPJPY': 190.0,
                        'EURGBP': 0.85}
            # USD: inverse of EURUSD, GBPUSD, AUDUSD, NZDUSD + direct USDJPY, USDCHF, USDCAD
            usd_score = 50
            eurusd = prices.get('EURUSD', baseline['EURUSD'])
            gbpusd = prices.get('GBPUSD', baseline['GBPUSD'])
            usdjpy = prices.get('USDJPY', baseline['USDJPY'])
            usdchf = prices.get('USDCHF', baseline['USDCHF'])
            audusd = prices.get('AUDUSD', baseline['AUDUSD'])
            usdcad = prices.get('USDCAD', baseline['USDCAD'])
            nzdusd = prices.get('NZDUSD', baseline['NZDUSD'])
            usd_dev = (
                (baseline['EURUSD'] - eurusd) / baseline['EURUSD'] * 100
                + (baseline['GBPUSD'] - gbpusd) / baseline['GBPUSD'] * 100
                + (usdjpy - baseline['USDJPY']) / baseline['USDJPY'] * 100
                + (usdchf - baseline['USDCHF']) / baseline['USDCHF'] * 100
                + (baseline['AUDUSD'] - audusd) / baseline['AUDUSD'] * 100
                + (usdcad - baseline['USDCAD']) / baseline['USDCAD'] * 100
                + (baseline['NZDUSD'] - nzdusd) / baseline['NZDUSD'] * 100
            ) / 7
            strengths['USD'] = max(0, min(100, int(50 - usd_dev * 10)))
            # EUR: via EURUSD and EURJPY
            eur_dev = ((eurusd - baseline['EURUSD']) / baseline['EURUSD'] * 100
                       + (prices.get('EURJPY', baseline['EURJPY']) - baseline['EURJPY']) / baseline['EURJPY'] * 100
                       + (prices.get('EURGBP', baseline['EURGBP']) - baseline['EURGBP']) / baseline['EURGBP'] * 100) / 3
            strengths['EUR'] = max(0, min(100, int(50 + eur_dev * 10)))
            # GBP
            gbp_dev = ((gbpusd - baseline['GBPUSD']) / baseline['GBPUSD'] * 100
                       + (prices.get('GBPJPY', baseline['GBPJPY']) - baseline['GBPJPY']) / baseline['GBPJPY'] * 100
                       + (baseline['EURGBP'] - prices.get('EURGBP', baseline['EURGBP'])) / baseline['EURGBP'] * 100) / 3
            strengths['GBP'] = max(0, min(100, int(50 + gbp_dev * 10)))
            # JPY
            jpy_dev = ((baseline['USDJPY'] - usdjpy) / baseline['USDJPY'] * 100
                       + (baseline['EURJPY'] - prices.get('EURJPY', baseline['EURJPY'])) / baseline['EURJPY'] * 100
                       + (baseline['GBPJPY'] - prices.get('GBPJPY', baseline['GBPJPY'])) / baseline['GBPJPY'] * 100) / 3
            strengths['JPY'] = max(0, min(100, int(50 + jpy_dev * 10)))
            # CHF
            chf_dev = ((baseline['USDCHF'] - usdchf) / baseline['USDCHF'] * 100) 
            strengths['CHF'] = max(0, min(100, int(50 + chf_dev * 10)))
            # AUD
            aud_dev = ((audusd - baseline['AUDUSD']) / baseline['AUDUSD'] * 100)
            strengths['AUD'] = max(0, min(100, int(50 + aud_dev * 10)))
            # CAD
            cad_dev = ((baseline['USDCAD'] - usdcad) / baseline['USDCAD'] * 100)
            strengths['CAD'] = max(0, min(100, int(50 + cad_dev * 10)))
            # NZD
            nzd_dev = ((nzdusd - baseline['NZDUSD']) / baseline['NZDUSD'] * 100)
            strengths['NZD'] = max(0, min(100, int(50 + nzd_dev * 10)))
        else:
            for currency in CURRENCIES:
                strengths[currency] = 50
        self.currency_strength = strengths
        return strengths
    
    def refresh(self, prices: Dict[str, float] = None):
        """Refresh all sentiment data."""
        self.fetch_fear_greed()
        if prices:
            self._calculate_currency_strength(prices)
        self._save_state()
    
    def get_score_adjustment(self, symbol: str) -> Tuple[int, str]:
        """Get score adjustment based on sentiment."""
        fng = self.fear_greed
        if symbol == 'XAUUSD':
            if fng < 20:
                return 15, f"extreme fear {fng} → safe haven +15"
            elif fng > 80:
                return -10, f"extreme greed {fng} → risk on -10"
            return 5, f"F&G {fng} neutral"
        
        elif symbol in ('SP500', 'US30', 'NAS100'):
            if fng > 80:
                return 10, f"extreme greed {fng} → momentum +10"
            elif fng < 20:
                return -15, f"extreme fear {fng} → risk off -15"
        
        usd = self.currency_strength.get('USD', 50)
        if symbol in ('EURUSD', 'GBPUSD'):
            if usd > 70:
                return -10, f"USD strong ({usd}) → bearish -10"
            elif usd < 30:
                return 10, f"USD weak ({usd}) → bullish +10"
        
        if symbol == 'GBPUSD':
            gbp = self.currency_strength.get('GBP', 50)
            if gbp > 70:
                return 10, f"GBP strong ({gbp}) → bullish +10"
        
        return 5, 'neutral'
    
    def format_terminal(self) -> str:
        lines = []
        fng_label = 'GREED' if self.fear_greed > 60 else 'FEAR' if self.fear_greed < 40 else 'NEUTRAL'
        lines.append(f"[SENT] F&G: {self.fear_greed} {'😨' if self.fear_greed < 40 else '🤑' if self.fear_greed > 60 else '😐'} {fng_label}")
        for ccy in ['USD', 'EUR', 'GBP', 'JPY', 'CHF', 'AUD']:
            strength = self.currency_strength.get(ccy, 50)
            icon = '💪' if strength > 60 else '📉' if strength < 40 else '➡️'
            label = 'STRONG' if strength > 60 else 'WEAK' if strength < 40 else 'NEUTRAL'
            lines.append(f"[SENT] {ccy}: {strength} {icon} {label}")
        return "\n".join(lines)

# Global instance
_engine_sent: Optional[SentimentEngine] = None
_lock = threading.Lock()
def get_sentiment_engine() -> SentimentEngine:
    global _engine_sent
    if _engine_sent is None:
        with _lock:
            if _engine_sent is None:
                _engine_sent = SentimentEngine()
    return _engine_sent
