"""
Multi-Timeframe Divergence Scanner - OMNI BRAIN V2
Detects RSI/MACD/Stochastic divergences across timeframes.
"""
import logging, math
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

log = logging.getLogger('DivergenceScanner')

@dataclass
class DivergenceResult:
    symbol: str
    divergences: List[Dict] = field(default_factory=list)
    total_score: int = 0
    timestamp: str = ''
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

class DivergenceScanner:
    TF_WEIGHTS = {'M15': 5, 'H1': 10, 'H4': 15}
    MULTI_TF_BONUS = 20
    
    def scan(self, symbol: str, candles: Dict[str, List[Dict]]) -> DivergenceResult:
        """
        Scan multiple timeframes for divergences.
        candles: {tf: [{open, high, low, close, volume}, ...]}
        """
        divergences = []
        total = 0
        detected_tfs = []
        
        for tf, tf_candles in candles.items():
            if tf not in self.TF_WEIGHTS:
                continue
            if len(tf_candles) < 20:
                continue
            
            closes = [c['close'] for c in tf_candles]
            highs = [c['high'] for c in tf_candles]
            lows = [c['low'] for c in tf_candles]
            
            rsi = self._calc_rsi(closes, 14)
            macd, macd_signal = self._calc_macd(closes)
            stoch_k, stoch_d = self._calc_stochastic(highs, lows, closes)
            
            # RSI divergence
            rsi_div = self._detect_rsi_divergence(closes, rsi)
            if rsi_div:
                score = self.TF_WEIGHTS[tf]
                divergences.append({'type': 'RSI', 'tf': tf, 'direction': rsi_div['direction'], 'score': score, 'detail': rsi_div['detail']})
                total += score
                detected_tfs.append(tf)
            
            # MACD divergence
            macd_div = self._detect_macd_divergence(closes, macd, macd_signal)
            if macd_div:
                score = self.TF_WEIGHTS[tf]
                divergences.append({'type': 'MACD', 'tf': tf, 'direction': macd_div['direction'], 'score': score, 'detail': macd_div['detail']})
                total += score
                detected_tfs.append(tf)
        
        # Multi-TF bonus: same divergence on 2+ TFs
        unique_dirs = set(d['direction'] for d in divergences)
        if len(detected_tfs) >= 2 and unique_dirs:
            total += self.MULTI_TF_BONUS
            divergences.append({'type': 'MULTI_TF', 'tf': '/'.join(set(detected_tfs)), 'direction': list(unique_dirs)[0], 'score': self.MULTI_TF_BONUS, 'detail': 'Confirmed across timeframes'})
        
        return DivergenceResult(symbol=symbol, divergences=divergences, total_score=total)
    
    def _calc_rsi(self, closes: List[float], period: int = 14) -> List[float]:
        if len(closes) < period + 1:
            return [50.0] * len(closes)
        deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        rsi = [50.0] * period
        for i in range(period, len(deltas)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
            if avg_loss == 0:
                rsi.append(100.0)
            else:
                rs = avg_gain / avg_loss
                rsi.append(100.0 - (100.0 / (1.0 + rs)))
        # Pad to match closes length
        while len(rsi) < len(closes):
            rsi.insert(0, 50.0)
        return rsi[:len(closes)]
    
    def _calc_macd(self, closes: List[float]) -> Tuple[List[float], List[float]]:
        ema12 = self._ema(closes, 12)
        ema26 = self._ema(closes, 26)
        macd = [ema12[i] - ema26[i] for i in range(len(closes))]
        signal = self._ema(macd, 9)
        return macd, signal
    
    def _ema(self, data: List[float], period: int) -> List[float]:
        if len(data) < period:
            return data[:]
        multiplier = 2.0 / (period + 1)
        ema = [sum(data[:period]) / period]
        for i in range(period, len(data)):
            ema.append((data[i] - ema[-1]) * multiplier + ema[-1])
        while len(ema) < len(data):
            ema.insert(0, ema[0])
        return ema[:len(data)]
    
    def _calc_stochastic(self, highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> Tuple[List[float], List[float]]:
        k = []
        for i in range(len(closes)):
            if i < period:
                k.append(50.0)
            else:
                hh = max(highs[i-period:i+1])
                ll = min(lows[i-period:i+1])
                if hh == ll:
                    k.append(50.0)
                else:
                    k.append((closes[i] - ll) / (hh - ll) * 100)
        d = self._ema(k, 3)
        return k, d
    
    def _detect_rsi_divergence(self, closes: List[float], rsi: List[float]) -> Optional[Dict]:
        if len(closes) < 10 or len(rsi) < 10:
            return None
        # Look at last 5 bars for divergence
        recent_c = closes[-5:]
        recent_r = rsi[-5:]
        if len(recent_c) < 5 or len(recent_r) < 5:
            return None
        
        # Regular bullish: price lower low, RSI higher low
        if recent_c[-1] < min(recent_c[:-1]) and recent_r[-1] > min(recent_r[:-2]):
            return {'direction': 'BULLISH', 'detail': f"price {recent_c[-1]:.2f} < prior low, RSI {recent_r[-1]:.1f} > prior low"}
        
        # Regular bearish: price higher high, RSI lower high
        if recent_c[-1] > max(recent_c[:-1]) and recent_r[-1] < max(recent_r[:-2]):
            return {'direction': 'BEARISH', 'detail': f"price {recent_c[-1]:.2f} > prior high, RSI {recent_r[-1]:.1f} < prior high"}
        
        return None
    
    def _detect_macd_divergence(self, closes: List[float], macd: List[float], signal: List[float]) -> Optional[Dict]:
        if len(closes) < 5 or len(macd) < 5:
            return None
        recent_c = closes[-5:]
        recent_m = macd[-5:]
        if recent_c[-1] < min(recent_c[:-1]) and recent_m[-1] > min(recent_m[:-2]):
            return {'direction': 'BULLISH', 'detail': f"MACD bullish divergence on last {len(recent_c)} bars"}
        if recent_c[-1] > max(recent_c[:-1]) and recent_m[-1] < max(recent_m[:-2]):
            return {'direction': 'BEARISH', 'detail': f"MACD bearish divergence on last {len(recent_c)} bars"}
        return None
    
    def format_terminal(self, result: DivergenceResult) -> str:
        if not result.divergences:
            return f"[DIV] {result.symbol}: No divergence 0pts"
        parts = [f"[DIV] {result.symbol}:"]
        for d in result.divergences:
            parts.append(f"{d['tf']} {d['type']} {d['direction']}+{d['score']}")
        parts.append(f"={result.total_score}pts")
        return " ".join(parts)

# Global instance
_scanner: Optional[DivergenceScanner] = None
def get_divergence_scanner() -> DivergenceScanner:
    global _scanner
    if _scanner is None:
        _scanner = DivergenceScanner()
    return _scanner
