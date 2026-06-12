"""
Multi-Pair Correlation Engine - OMNI BRAIN V2
Tracks Pearson correlations between trading pairs using rolling candle data.
"""
import os, json, math, logging, time, threading
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from pathlib import Path

log = logging.getLogger('CorrelationEngine')
LOG_DIR = Path(__file__).parent / 'logs'

# 12 pairs to track
CORRELATION_PAIRS = [
    'XAUUSD', 'EURUSD', 'GBPUSD', 'SP500',
    'USDJPY', 'USDCHF', 'AUDUSD', 'USDCAD',
    'US30', 'NAS100', 'USOIL'
]

# Expected correlations for divergence detection
EXPECTED_CORRELATIONS = {
    ('XAUUSD', 'USDCHF'): -0.85,
    ('XAUUSD', 'SP500'): -0.60,
    ('EURUSD', 'GBPUSD'): 0.85,
    ('EURUSD', 'USDCHF'): -0.90,
    ('GBPUSD', 'USDCHF'): -0.85,
    ('AUDUSD', 'USDCAD'): 0.75,
    ('US30', 'NAS100'): 0.90,
    ('US30', 'SP500'): 0.95,
    ('USOIL', 'USDCAD'): 0.70,
    ('XAUUSD', 'USOIL'): -0.40,
    ('EURUSD', 'GBPUSD'): 0.85,
    ('USDJPY', 'XAUUSD'): -0.50,
}

class CorrelationEngine:
    """Track rolling Pearson correlations between all pairs."""
    
    WINDOW = 50  # rolling window for correlation
    
    def __init__(self):
        self.price_history: Dict[str, List[float]] = {p: [] for p in CORRELATION_PAIRS}
        self.correlation_matrix: Dict[str, Dict[str, float]] = {}
        self.divergence_alerts: List[Dict] = []
        self._load_state()
    
    def _load_state(self):
        path = LOG_DIR / 'correlation_matrix.json'
        if path.exists():
            try:
                with open(path) as f: data = json.load(f)
                self.correlation_matrix = data.get('matrix', {})
                self.divergence_alerts = data.get('alerts', [])
            except Exception as e:
                log.debug(f"Failed to load correlation state: {e}")

    def _save_state(self):
        path = LOG_DIR / 'correlation_matrix.json'
        try:
            with open(path, 'w') as f:
                json.dump({'matrix': self.correlation_matrix, 'alerts': self.divergence_alerts[-50:], 'updated': datetime.now(timezone.utc).isoformat()}, f, indent=2)
        except Exception as e:
            log.debug(f"Failed to save correlation state: {e}")
    
    def update_price(self, symbol: str, price: float):
        """Update price for a symbol and maintain rolling window."""
        if symbol not in self.price_history:
            return
        self.price_history[symbol].append(price)
        if len(self.price_history[symbol]) > self.WINDOW + 1:
            self.price_history[symbol] = self.price_history[symbol][-(self.WINDOW + 1):]
    
    def _pearson(self, a: List[float], b: List[float]) -> float:
        """Calculate Pearson correlation coefficient between two lists."""
        n = min(len(a), len(b))
        if n < 10:
            return 0.0
        a, b = a[-n:], b[-n:]
        # Use returns, not prices
        ra = [a[i+1] - a[i] for i in range(n-1)]
        rb = [b[i+1] - b[i] for i in range(n-1)]
        if not ra or not rb:
            return 0.0
        n2 = len(ra)
        sum_a = sum(ra); sum_b = sum(rb)
        sum_ab = sum(x*y for x,y in zip(ra,rb))
        sum_a2 = sum(x*x for x in ra)
        sum_b2 = sum(y*y for y in rb)
        num = n2 * sum_ab - sum_a * sum_b
        den = math.sqrt((n2 * sum_a2 - sum_a**2) * (n2 * sum_b2 - sum_b**2))
        if den == 0:
            return 0.0
        corr = num / den
        return max(-1.0, min(1.0, corr))
    
    def update_correlation_matrix(self) -> Dict[str, Dict[str, float]]:
        """Recalculate all pairwise correlations."""
        symbols = [s for s in CORRELATION_PAIRS if len(self.price_history.get(s, [])) >= 10]
        matrix = {}
        for s1 in symbols:
            matrix[s1] = {}
            for s2 in symbols:
                if s1 == s2:
                    matrix[s1][s2] = 1.0
                else:
                    corr = self._pearson(self.price_history[s1], self.price_history[s2])
                    matrix[s1][s2] = round(corr, 4)
        self.correlation_matrix = matrix
        self._save_state()
        return matrix
    
    def get_correlation(self, pair1: str, pair2: str) -> float:
        """Get current correlation between two pairs."""
        return self.correlation_matrix.get(pair1, {}).get(pair2, 0.0)
    
    def check_divergence(self) -> List[Dict]:
        """Check for divergences (current corr differs from expected by > 2 sigma)."""
        alerts = []
        for (p1, p2), expected in EXPECTED_CORRELATIONS.items():
            current = self.get_correlation(p1, p2)
            if current == 0.0:
                continue
            sigma = 0.15  # approx std dev of correlation estimates
            diff = abs(current - expected)
            if diff > 2 * sigma:
                divergence_type = "POSITIVE" if current > expected else "NEGATIVE"
                alert = {
                    'pair1': p1, 'pair2': p2,
                    'expected': expected, 'current': current,
                    'diff': round(diff, 2),
                    'type': divergence_type,
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }
                alerts.append(alert)
                # Only add new alerts (avoid duplicates within 1 hour)
                if not any(a['pair1']==p1 and a['pair2']==p2 
                          for a in self.divergence_alerts 
                          if abs((datetime.fromisoformat(a['timestamp']) - datetime.now(timezone.utc)).total_seconds()) < 3600):
                    self.divergence_alerts.append(alert)
        self.divergence_alerts = self.divergence_alerts[-50:]
        return alerts
    
    def get_score_adjustment(self, symbol: str, direction: str, dxy_falling: bool = False) -> Tuple[int, str]:
        """
        Get score adjustment based on correlation rules.
        Returns (adjustment, reason).
        """
        if symbol == 'XAUUSD':
            usdchf_corr = self.get_correlation('XAUUSD', 'USDCHF')
            sp500_corr = self.get_correlation('XAUUSD', 'SP500')
            adjustments = 0
            reasons = []
            if direction == 'BULLISH':
                if usdchf_corr < -0.3:
                    adjustments += 10
                    reasons.append(f"USDCHF inverse {usdchf_corr:.2f} ✅ +10")
                elif usdchf_corr > 0.3:
                    adjustments -= 15
                    reasons.append(f"USDCHF not inverse {usdchf_corr:.2f} ❌ -15")
                if sp500_corr < -0.3:
                    adjustments += 10
                    reasons.append(f"SP500 inverse {sp500_corr:.2f} ✅ +10")
                # DXY falling bonus
                if dxy_falling:
                    adjustments += 10
                    reasons.append(f"DXY falling +10 bonus")
            return adjustments, ' | '.join(reasons) if reasons else 'neutral'
        
        elif symbol == 'EURUSD':
            gbpusd_corr = self.get_correlation('EURUSD', 'GBPUSD')
            if direction == 'BULLISH':
                if gbpusd_corr > 0.5:
                    return 10, f"GBPUSD confirms {gbpusd_corr:.2f} ✅ +10"
                elif gbpusd_corr < 0:
                    return -10, f"GBPUSD diverges {gbpusd_corr:.2f} ❌ -10"
        return 0, 'neutral'
    
    def format_telegram_divergence(self, alert: Dict) -> str:
        """Format a divergence alert for Telegram."""
        now_utc = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
        return (
            f"⚡ CORRELATION DIVERGENCE\n"
            f"Pair: {alert['pair1']} vs {alert['pair2']}\n"
            f"Normal correlation: {alert['expected']:+.2f}\n"
            f"Current: {alert['current']:+.2f} ({alert['type']})\n"
            f"Opportunity: Mean reversion likely\n"
            f"Time: {now_utc}"
        )

    def format_terminal(self) -> List[str]:
        """Format correlation status for terminal display."""
        lines = []
        for (p1, p2), expected in EXPECTED_CORRELATIONS.items():
            current = self.get_correlation(p1, p2)
            if current == 0:
                continue
            diff = abs(current - expected)
            icon = '✅' if diff < 0.2 else ('⚠️' if diff < 0.4 else '🚨')
            if expected < 0:
                status = "INVERSE" if current < -0.3 else "DIVERGING"
            else:
                status = "CONFIRMS" if current > 0.5 else "DIVERGING"
            lines.append(f"[CORR] {p1} ←→ {p2}: {current:+.2f} {icon} {status}")
        return lines

# Global instance
_engine: Optional[CorrelationEngine] = None
_lock = threading.Lock()
def get_correlation_engine() -> CorrelationEngine:
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                _engine = CorrelationEngine()
    return _engine
