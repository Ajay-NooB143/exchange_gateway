"""
Module 6 — Gold Macro Engine
==============================
Analyzes DXY, US10Y yield, Silver, Oil, SP500, VIX, treasury flows,
inflation expectations, central bank events, and risk-on/off sentiment.

Generates Gold Macro Bias (Bullish/Neutral/Bearish) with probability 0-100%.
"""

import logging
import math
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

log = logging.getLogger('GoldMacroEngine')

GOLD_MACRO_BIAS_BULLISH = 'BULLISH'
GOLD_MACRO_BIAS_NEUTRAL = 'NEUTRAL'
GOLD_MACRO_BIAS_BEARISH = 'BEARISH'


class GoldMacroEngine:
    """
    Comprehensive macro analysis for XAUUSD.

    Analyzes:
      - DXY (inverse correlation ~-0.8)
      - US10Y real yield
      - Silver correlation
      - Oil (inflation proxy)
      - SP500 (risk appetite)
      - VIX (fear)
      - Treasury flows
      - Inflation expectations
      - Central bank events
      - Risk-on/off sentiment
    """

    def __init__(self):
        self._bias: str = GOLD_MACRO_BIAS_NEUTRAL
        self._probability: int = 50
        self._components: Dict[str, Any] = {}

    def analyze(
        self,
        dxy: Optional[float] = None,
        dxy_change_pct: float = 0.0,
        us10y_yield: Optional[float] = None,
        us10y_change_bps: float = 0.0,
        silver: Optional[float] = None,
        silver_change_pct: float = 0.0,
        oil: Optional[float] = None,
        oil_change_pct: float = 0.0,
        sp500: Optional[float] = None,
        sp500_change_pct: float = 0.0,
        vix: Optional[float] = None,
        inflation_expectation: Optional[float] = None,
        central_bank_dovish: Optional[bool] = None,
        risk_on: Optional[bool] = None,
        treasury_inflow: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Run gold macro analysis.

        Returns:
            Dict with bias, probability, component scores.
        """
        components = {}
        bullish_signals = 0
        bearish_signals = 0
        total_weight = 0

        # DXY (inverse)
        if dxy is not None:
            score = self._score_dxy(dxy, dxy_change_pct)
            components['DXY'] = score
            if score > 60:
                bullish_signals += score * 0.3
            elif score < 40:
                bearish_signals += (100 - score) * 0.3
            total_weight += 30

        # US10Y real yield (inverse)
        if us10y_yield is not None:
            score = self._score_yield(us10y_yield, us10y_change_bps)
            components['US10Y'] = score
            if score > 60:
                bullish_signals += score * 0.2
            elif score < 40:
                bearish_signals += (100 - score) * 0.2
            total_weight += 20

        # Silver (positive correlation)
        if silver is not None:
            score = self._score_silver(silver, silver_change_pct)
            components['SILVER'] = score
            if score > 55:
                bullish_signals += score * 0.1
            else:
                bearish_signals += (100 - score) * 0.1
            total_weight += 10

        # Oil (inflation proxy)
        if oil is not None:
            score = self._score_oil(oil, oil_change_pct)
            components['OIL'] = score
            if score > 55:
                bullish_signals += score * 0.05
            else:
                bearish_signals += (100 - score) * 0.05
            total_weight += 5

        # SP500 (risk appetite)
        if sp500 is not None:
            score = self._score_sp500(sp500, sp500_change_pct)
            components['SP500'] = score
            if score > 55:
                bullish_signals += score * 0.1
            else:
                bearish_signals += (100 - score) * 0.1
            total_weight += 10

        # VIX (fear)
        if vix is not None:
            score = self._score_vix(vix)
            components['VIX'] = score
            if score > 60:
                bullish_signals += score * 0.05
            else:
                bearish_signals += (100 - score) * 0.05
            total_weight += 5

        # Inflation expectations
        if inflation_expectation is not None:
            score = self._score_inflation(inflation_expectation)
            components['INFLATION'] = score
            if score > 55:
                bullish_signals += score * 0.1
            else:
                bearish_signals += (100 - score) * 0.1
            total_weight += 10

        # Central bank events
        if central_bank_dovish is not None:
            score = 70 if central_bank_dovish else 30
            components['CB_EVENT'] = score
            if central_bank_dovish:
                bullish_signals += score * 0.05
            else:
                bearish_signals += (100 - score) * 0.05
            total_weight += 5

        # Risk sentiment
        if risk_on is not None:
            score = 60 if risk_on else 40
            components['RISK_SENTIMENT'] = score
            if risk_on:
                bullish_signals += score * 0.03
            else:
                bearish_signals += (100 - score) * 0.03
            total_weight += 3

        # Treasury flows
        if treasury_inflow is not None:
            score = 40 if treasury_inflow else 60
            components['TREASURY_FLOW'] = score
            if not treasury_inflow:
                bullish_signals += score * 0.02
            else:
                bearish_signals += (100 - score) * 0.02
            total_weight += 2

        self._components = components

        # Compute final probability
        if total_weight > 0:
            net = (bullish_signals - bearish_signals) / max(total_weight, 1)
            self._probability = int(50 + net * 50)
        else:
            self._probability = 50

        self._probability = max(0, min(100, self._probability))

        # Bias classification
        if self._probability >= 65:
            self._bias = GOLD_MACRO_BIAS_BULLISH
        elif self._probability <= 35:
            self._bias = GOLD_MACRO_BIAS_BEARISH
        else:
            self._bias = GOLD_MACRO_BIAS_NEUTRAL

        return {
            'bias': self._bias,
            'probability': self._probability,
            'components': components,
            'component_count': len(components),
        }

    def _score_dxy(self, dxy: float, change_pct: float) -> int:
        score = 50
        # DXY above 105 = bearish gold, below 100 = bullish gold
        if dxy > 105:
            score = 20
        elif dxy > 103:
            score = 30
        elif dxy > 101:
            score = 40
        elif dxy > 99:
            score = 55
        elif dxy > 97:
            score = 65
        else:
            score = 75

        # Recent change adjustment
        if change_pct < -0.3:
            score = min(100, score + 15)
        elif change_pct > 0.3:
            score = max(0, score - 15)

        return score

    def _score_yield(self, yield_val: float, change_bps: float) -> int:
        # Low yields = bullish gold
        score = 50
        if yield_val < 2.0:
            score = 75
        elif yield_val < 3.0:
            score = 60
        elif yield_val < 4.0:
            score = 45
        elif yield_val < 5.0:
            score = 30
        else:
            score = 20

        if change_bps < -5:
            score = min(100, score + 10)
        elif change_bps > 5:
            score = max(0, score - 10)

        return score

    def _score_silver(self, silver: float, change_pct: float) -> int:
        score = 50
        if change_pct > 1.0:
            score = 65
        elif change_pct > 0.5:
            score = 55
        elif change_pct < -1.0:
            score = 35
        elif change_pct < -0.5:
            score = 45
        return score

    def _score_oil(self, oil: float, change_pct: float) -> int:
        score = 50
        if change_pct > 2.0:
            score = 60
        elif change_pct > 1.0:
            score = 55
        elif change_pct < -2.0:
            score = 40
        elif change_pct < -1.0:
            score = 45
        return score

    def _score_sp500(self, sp500: float, change_pct: float) -> int:
        score = 50
        if change_pct > 1.0:
            score = 60
        elif change_pct > 0.5:
            score = 55
        elif change_pct < -1.0:
            score = 40
        elif change_pct < -0.5:
            score = 45
        return score

    def _score_vix(self, vix: float) -> int:
        if vix > 30:
            return 65
        elif vix > 25:
            return 55
        elif vix > 20:
            return 50
        elif vix > 15:
            return 45
        return 40

    def _score_inflation(self, inflation: float) -> int:
        if inflation > 4.0:
            return 65
        elif inflation > 3.0:
            return 55
        elif inflation > 2.0:
            return 50
        elif inflation > 1.0:
            return 45
        return 40

    def get_bias(self) -> str:
        return self._bias

    def get_probability(self) -> int:
        return self._probability


_gold: Optional[GoldMacroEngine] = None


def get_gold_macro_engine() -> GoldMacroEngine:
    global _gold
    if _gold is None:
        _gold = GoldMacroEngine()
    return _gold


if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    if '--test' in sys.argv:
        ge = get_gold_macro_engine()
        result = ge.analyze(dxy=104.5, dxy_change_pct=-0.5, us10y_yield=4.2, us10y_change_bps=-8, silver=30.5, silver_change_pct=1.2, oil=78.0, oil_change_pct=0.5, sp500=5300, sp500_change_pct=0.8, vix=14, risk_on=True)
        print(f"Bias: {result['bias']}, Probability: {result['probability']}%")
        print(f"Components: {result['components']}")
        print("GoldMacroEngine OK")
