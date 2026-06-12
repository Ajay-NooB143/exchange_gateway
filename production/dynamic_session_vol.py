"""Dynamic Session Volatility Model

Automatically adapts risk to trading sessions (Asian, London, NY,
Overlap, Dead Zone). Measures ATR, volume, spread, volatility,
range expansion, momentum. Adjusts lot size, SL, TP, confidence
threshold, risk multiplier, position scaling, and partial TP logic.
"""

import logging
import math
import statistics
from typing import List, Dict, Optional, Any
from datetime import datetime, timezone

log = logging.getLogger(__name__)

SESSION_HOURS = {
    'ASIAN': (0, 6),
    'LONDON_OPEN': (7, 10),
    'LONDON_CLOSE': (10, 12),
    'NY_OPEN': (13, 16),
    'NY_CLOSE': (16, 18),
    'OVERLAP': (13, 16),
    'DEAD_ZONE': (19, 23),
}

RISK_BY_SESSION = {
    'ASIAN': 0.40,
    'LONDON_OPEN': 1.0,
    'LONDON_CLOSE': 0.80,
    'NY_OPEN': 0.90,
    'NY_CLOSE': 0.70,
    'OVERLAP': 1.10,
    'DEAD_ZONE': 0.0,
}

SESSION_NAMES = {
    'ASIAN': 'Asian Session',
    'LONDON_OPEN': 'London Open',
    'LONDON_CLOSE': 'London Close',
    'NY_OPEN': 'New York Open',
    'NY_CLOSE': 'New York Close',
    'OVERLAP': 'London-NY Overlap',
    'DEAD_ZONE': 'Dead Zone',
}


class DynamicSessionVolModel:
    """Session-aware risk adjustment engine."""

    def __init__(self):
        self._session_history: Dict[str, List[Dict]] = {}
        self._last_result: Dict[str, Any] = {}

    def analyze(self, symbol: str = 'XAUUSD', session: str = '',
                atr: float = 5.0, volume: float = 100.0,
                spread: float = 1.0, current_volatility: Optional[float] = None,
                candles: Optional[List[Dict]] = None) -> Dict[str, Any]:
        result = {
            'session': session,
            'session_name': SESSION_NAMES.get(session, session),
            'risk_multiplier': 1.0,
            'lot_multiplier': 1.0,
            'sl_adjustment': 1.0,
            'tp_adjustment': 1.0,
            'confidence_threshold': 50,
            'allow_trading': True,
            'classification': 'NORMAL',
            'components': {},
        }
        try:
            # -- Base session risk --
            base_risk = RISK_BY_SESSION.get(session, 0.5)
            if base_risk == 0:
                result['allow_trading'] = False
                result['classification'] = 'NO_TRADE'
                result['risk_multiplier'] = 0
                result['reason'] = f"No trading in {SESSION_NAMES.get(session, session)}"
                return result

            # -- Volatility adjustment --
            vol_adj = self._volatility_adjustment(atr, current_volatility)
            result['components']['volatility_adj'] = round(vol_adj, 3)

            # -- Volume adjustment --
            vol_adj_factor = self._volume_adjustment(volume, session)
            result['components']['volume_adj'] = round(vol_adj_factor, 3)

            # -- Spread adjustment --
            spread_adj = self._spread_adjustment(spread, atr)
            result['components']['spread_adj'] = round(spread_adj, 3)

            # -- Range expansion --
            range_exp = self._range_expansion(candles, atr) if candles else 1.0
            result['components']['range_expansion'] = round(range_exp, 3)

            # -- Momentum guard --
            mom_guard = self._momentum_guard(candles) if candles else 1.0
            result['components']['momentum_guard'] = round(mom_guard, 3)

            # -- Composite adjustments --
            risk_mult = base_risk * vol_adj * vol_adj_factor * spread_adj * range_exp * mom_guard
            risk_mult = max(0, min(2.0, risk_mult))
            lot_mult = max(0.1, min(2.0, risk_mult))
            sl_adj = max(0.5, min(2.0, 1.0 + (1.0 - risk_mult) * 0.5))
            tp_adj = max(0.5, min(2.0, 1.0 + (risk_mult - 0.5) * 0.3))

            conf_threshold = max(30, int(60 - (risk_mult - 0.5) * 20))

            classification = self._classify(risk_mult)

            result['risk_multiplier'] = round(risk_mult, 3)
            result['lot_multiplier'] = round(lot_mult, 3)
            result['sl_adjustment'] = round(sl_adj, 3)
            result['tp_adjustment'] = round(tp_adj, 3)
            result['confidence_threshold'] = conf_threshold
            result['classification'] = classification

            # Record history
            if session not in self._session_history:
                self._session_history[session] = []
            self._session_history[session].append({
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'risk_multiplier': risk_mult,
                'atr': atr,
                'volume': volume,
                'spread': spread,
            })
            if len(self._session_history[session]) > 100:
                self._session_history[session] = self._session_history[session][-100:]

            self._last_result = result

        except Exception as e:
            log.warning(f"DynamicSessionVolModel.analyze error: {e}")
            result['error'] = str(e)

        return result

    def get_session_history(self, session: str) -> List[Dict]:
        return list(self._session_history.get(session, []))

    def get_last_result(self) -> Dict[str, Any]:
        return dict(self._last_result) if self._last_result else {}

    def get_suggested_params(self, base_sl: float, base_tp: float,
                             base_lot: float) -> Dict[str, Any]:
        if not self._last_result:
            return {'sl': base_sl, 'tp': base_tp, 'lot': base_lot}
        r = self._last_result
        return {
            'sl': round(base_sl * r.get('sl_adjustment', 1.0), 1),
            'tp': round(base_tp * r.get('tp_adjustment', 1.0), 1),
            'lot': round(base_lot * r.get('lot_multiplier', 1.0), 2),
            'risk_mult': r.get('risk_multiplier', 1.0),
            'classification': r.get('classification', 'NORMAL'),
        }

    # ---- Internal ----

    def _volatility_adjustment(self, atr: float,
                               current_vol: Optional[float]) -> float:
        if current_vol is None or atr <= 0:
            return 1.0
        ratio = current_vol / atr
        if ratio > 2.5:
            return 0.2
        if ratio > 2.0:
            return 0.4
        if ratio > 1.5:
            return 0.7
        if ratio < 0.5:
            return 1.3
        return 1.0

    def _volume_adjustment(self, volume: float, session: str) -> float:
        baselines = {
            'ASIAN': 50,
            'LONDON_OPEN': 200,
            'LONDON_CLOSE': 150,
            'NY_OPEN': 250,
            'NY_CLOSE': 180,
            'OVERLAP': 300,
            'DEAD_ZONE': 30,
        }
        baseline = baselines.get(session, 100)
        if baseline <= 0:
            return 1.0
        ratio = volume / baseline
        if ratio < 0.3:
            return 0.5
        if ratio < 0.5:
            return 0.7
        if ratio > 2.0:
            return 1.2
        return 1.0

    def _spread_adjustment(self, spread: float, atr: float) -> float:
        if spread <= 0 or atr <= 0:
            return 1.0
        pct = spread / atr * 100
        if pct > 5.0:
            return 0.3
        if pct > 3.0:
            return 0.6
        if pct > 2.0:
            return 0.8
        return 1.0

    def _range_expansion(self, candles: Optional[List[Dict]],
                          atr: float) -> float:
        if not candles or len(candles) < 10:
            return 1.0
        try:
            recent = candles[-5:]
            ranges = [c.get('high', 0) - c.get('low', 0) for c in recent]
            avg_range = sum(ranges) / len(ranges)
            if atr > 0:
                ratio = avg_range / atr
                if ratio > 1.5:
                    return 0.6
                if ratio > 1.2:
                    return 0.8
                if ratio < 0.5:
                    return 1.3
            return 1.0
        except Exception:
            return 1.0

    def _momentum_guard(self, candles: Optional[List[Dict]]) -> float:
        if not candles or len(candles) < 5:
            return 1.0
        try:
            closes = [c.get('close', 0) for c in candles[-10:]]
            if len(closes) < 5:
                return 1.0
            recent_vol = statistics.stdev(closes[-5:]) if len(closes) >= 5 else 0
            older_vol = statistics.stdev(closes[:5]) if len(closes) >= 10 else recent_vol
            if older_vol > 0:
                ratio = recent_vol / older_vol
                if ratio > 2.0:
                    return 0.5
                if ratio > 1.5:
                    return 0.8
            return 1.0
        except Exception:
            return 1.0

    def _classify(self, risk_mult: float) -> str:
        if risk_mult <= 0:
            return 'NO_TRADE'
        if risk_mult < 0.3:
            return 'VERY_CONSERVATIVE'
        if risk_mult < 0.6:
            return 'CONSERVATIVE'
        if risk_mult < 0.85:
            return 'MODERATE'
        if risk_mult < 1.15:
            return 'NORMAL'
        return 'AGGRESSIVE'


_vol_model: Optional[DynamicSessionVolModel] = None


def get_session_vol_model() -> DynamicSessionVolModel:
    global _vol_model
    if _vol_model is None:
        _vol_model = DynamicSessionVolModel()
    return _vol_model


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    sv = get_session_vol_model()
    result = sv.analyze('XAUUSD', 'LONDON_OPEN', atr=6.5, volume=220,
                        spread=1.2, current_volatility=8.0)
    print(f"Session: {SESSION_NAMES.get('LONDON_OPEN', '')}")
    print(f"Risk Mult: {result['risk_multiplier']}, Lot Mult: {result['lot_multiplier']}")
    print(f"SL Adj: {result['sl_adjustment']}, TP Adj: {result['tp_adjustment']}")
    print(f"Classification: {result['classification']}")
    print(f"Allow: {result['allow_trading']}")
    res2 = sv.analyze('XAUUSD', 'DEAD_ZONE', atr=5.0, volume=30, spread=3.0)
    print(f"\nSession: DEAD_ZONE")
    print(f"Allow: {res2['allow_trading']}, Class: {res2['classification']}")
