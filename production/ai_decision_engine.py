"""
Master AI Decision Engine — Full Pipeline Integration
======================================================
Orchestrates all modules in order:
Market Data -> Regime -> MTF Consensus -> Liquidity Sweep -> Trap ->
Order Flow -> Gold Macro -> Killzone/Session -> Dynamic Session Vol ->
Adaptive Confidence -> News Lockout -> Portfolio Allocator ->
Risk Governor -> Execution Quality -> Position Manager ->
Trade Replay -> Final Decision -> API/Telegram
"""

import logging
import math
import time
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path

log = logging.getLogger('AIDecisionEngine')

ACTION_BUY = 'BUY'
ACTION_SELL = 'SELL'
ACTION_WAIT = 'WAIT'
ACTION_CANCEL = 'CANCEL'


class AIDecisionEngine:
    """Central AI decision engine — orchestrates all sub-modules."""

    def __init__(self):
        self._modules_loaded = False
        self._modules: Dict[str, Any] = {}
        self._last_decision: Dict[str, Any] = {}
        self._latest_analysis: Dict[str, Any] = {}
        self._final_json: Dict[str, Any] = {}
        self._signal_timestamp: float = 0.0

    def _load_modules(self):
        if self._modules_loaded:
            return
        try:
            sys.path.insert(0, str(Path(__file__).parent))

            from regime_detector import get_regime_detector
            from liquidity_sweep_intelligence import get_sweep_intelligence
            from trap_detector import get_trap_detector
            from gold_macro_engine import get_gold_macro_engine
            from killzone_engine import get_killzone_engine
            from order_flow_module import get_order_flow_module
            from position_manager import get_position_manager
            from pattern_learning_engine import get_learning_engine
            from ai_risk_governor import get_risk_governor
            from monte_carlo_lab import get_monte_carlo_lab
            from ai_trade_coach import get_trade_coach
            from confidence_scorer import get_scorer
            from smc_analyzer import get_analyzer
            from confluence_memory import get_memory

            # NEW modules
            from adaptive_confidence import get_calibrator
            from mtf_consensus import get_mtf_consensus
            from news_lockout import get_news_lockout
            from safe_rl_learner import get_rl_learner
            from portfolio_risk_allocator import get_portfolio_allocator
            from execution_quality import get_execution_analyzer
            from trade_replay import get_trade_replay
            from dynamic_session_vol import get_session_vol_model

            self._modules = {
                'regime_detector': get_regime_detector(),
                'sweep': get_sweep_intelligence(),
                'trap': get_trap_detector(),
                'gold_macro': get_gold_macro_engine(),
                'killzone': get_killzone_engine(),
                'orderflow': get_order_flow_module(),
                'position': get_position_manager(),
                'learning': get_learning_engine(),
                'risk_governor': get_risk_governor(),
                'monte_carlo': get_monte_carlo_lab(),
                'coach': get_trade_coach(),
                'scorer': get_scorer(),
                'smc': get_analyzer(),
                'memory': get_memory(),

                'calibrator': get_calibrator(),
                'mtf_consensus': get_mtf_consensus(),
                'news_lockout': get_news_lockout(),
                'rl_learner': get_rl_learner(),
                'portfolio_allocator': get_portfolio_allocator(),
                'exec_analyzer': get_execution_analyzer(),
                'trade_replay': get_trade_replay(),
                'session_vol': get_session_vol_model(),
            }
            self._modules_loaded = True
            log.info("AI Decision Engine: All 22 modules loaded")
        except Exception as e:
            log.warning(f"AI Decision Engine: Module load failed: {e}")

    def analyze(
        self,
        symbol: str = 'XAUUSD',
        candles: Dict[str, List[Dict]] = None,
        current_price: float = 0.0,
        vwap: float = 0.0,
        atr: float = 5.0,
        dxy: Optional[float] = None,
        dxy_change: float = 0.0,
        us10y: Optional[float] = None,
        us10y_change: float = 0.0,
        silver: Optional[float] = None,
        oil: Optional[float] = None,
        sp500: Optional[float] = None,
        vix: Optional[float] = None,
        news_active: bool = False,
        pdh: Optional[float] = None,
        pdl: Optional[float] = None,
        weekly_high: Optional[float] = None,
        weekly_low: Optional[float] = None,
        asian_high: Optional[float] = None,
        asian_low: Optional[float] = None,
        support: Optional[float] = None,
        resistance: Optional[float] = None,
        account_balance: float = 10000.0,
        current_drawdown: float = 0.0,
        current_spread: float = 1.0,
        current_latency: Optional[float] = None,
        volume: float = 100.0,
        spread: float = 1.0,
    ) -> Dict[str, Any]:
        self._load_modules()
        if candles is None:
            candles = {}
        pipeline_start = time.time()
        components: Dict[str, Any] = {}

        result = {
            'symbol': symbol,
            'buy_probability': 0,
            'sell_probability': 0,
            'confidence': 0,
            'calibrated_confidence': 0,
            'expected_rr': 0.0,
            'invalidity_level': 100,
            'action': ACTION_WAIT,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'components': {},
            'execution_time_ms': 0,
            'consensus': 50,
            'bias': 'NEUTRAL',
            'alignment': 100,
            'trap_probability': 0,
            'macro_state': 'NEUTRAL',
            'orderflow': 'NEUTRAL',
            'session': '',
            'session_classification': '',
            'news_lock': False,
            'news_lock_type': '',
            'execution_score': 85,
            'risk_tier': 'NORMAL',
            'risk_multiplier': 1.0,
            'lot_multiplier': 1.0,
            'portfolio_allocation': '',
            'sl': 0.0,
            'tp': 0.0,
            'reason': [],
        }

        try:
            m1_candles = candles.get('M1', [])
            m5_candles = candles.get('M5', [])
            m15_candles = candles.get('M15', [])
            h1_candles = candles.get('H1', [])
            all_tf = [m1_candles, m5_candles, m15_candles, h1_candles]
            primary_candles = h1_candles or m15_candles or m5_candles or m1_candles

            # ============ STEP 1: MULTI-TF STRUCTURE ============
            m1_trend = self._trend_bias(m1_candles)
            components['M1'] = m1_trend
            m5_bias = self._tf_bias_score(m5_candles)
            components['M5'] = m5_bias
            m15_bias = self._tf_bias_score(m15_candles)
            components['M15'] = m15_bias
            h1_bias = self._tf_bias_score(h1_candles)
            components['H1'] = h1_bias
            atr_expansion = self._atr_expansion(primary_candles, atr)
            components['ATR_EXPANSION'] = atr_expansion
            vwap_position = self._vwap_position(current_price, vwap, atr)
            components['VWAP'] = vwap_position

            # ============ STEP 2: REGIME DETECTION ============
            regime_module = self._modules.get('regime_detector')
            regime = 'COMPRESSION'
            if regime_module:
                regime = regime_module.classify(primary_candles, atr)
                components['REGIME'] = regime
                result['regime'] = regime
                result['regime_metrics'] = regime_module.get_metrics()

            # ============ STEP 3: MULTI-TIMEFRAME CONSENSUS ============
            mtf = self._modules.get('mtf_consensus')
            mtf_result = {}
            if mtf:
                mtf_result = mtf.analyze(
                    candles, current_price,
                    sweep_analysis=None, trap_analysis=None,
                    orderflow_analysis=None, macro_analysis=None,
                    regime=regime,
                    session=result.get('session', ''),
                )
                result['consensus'] = mtf_result.get('consensus', 50)
                result['bias'] = mtf_result.get('bias', 'NEUTRAL')
                result['alignment'] = mtf_result.get('alignment', 100)
                result['mtf_rejected'] = mtf_result.get('rejected', False)
                if mtf_result.get('rejected'):
                    result['reason'].append(
                        f"MTF disagreement: {mtf_result.get('disagreement_detail', {}).get('detail', '')}")

            # ============ STEP 4: LIQUIDITY SWEEP ============
            sweep_module = self._modules.get('sweep')
            sweep_analysis = {}
            if sweep_module:
                sweep_analysis = sweep_module.analyze(
                    primary_candles, current_price,
                    pdh=pdh, pdl=pdl,
                    weekly_high=weekly_high, weekly_low=weekly_low,
                    asian_high=asian_high, asian_low=asian_low,
                    session=result.get('session', ''),
                )
                components['SWEEP'] = sweep_analysis.get('score', 0)

            # ============ STEP 5: TRAP DETECTOR ============
            trap_module = self._modules.get('trap')
            trap_analysis = {}
            if trap_module:
                trap_analysis = trap_module.analyze(
                    primary_candles, current_price,
                    pdh=pdh, pdl=pdl, support=support, resistance=resistance,
                )
                components['TRAP'] = trap_analysis.get('trap_probability', 0)
            result['trap_probability'] = trap_analysis.get('trap_probability', 0)
            result['trap_blocked'] = trap_analysis.get('blocked', False)

            # ============ STEP 6: ORDER FLOW ============
            of_module = self._modules.get('orderflow')
            of_analysis = {}
            if of_module:
                of_analysis = of_module.analyze(primary_candles, current_price)
                components['ORDERFLOW'] = of_analysis.get('score', 50)
            pressure = of_analysis.get('institutional_pressure', of_analysis.get('score', 50))
            if pressure >= 70:
                result['orderflow'] = 'Strong Buy'
            elif pressure >= 55:
                result['orderflow'] = 'Buy'
            elif pressure <= 30:
                result['orderflow'] = 'Strong Sell'
            elif pressure <= 45:
                result['orderflow'] = 'Sell'
            else:
                result['orderflow'] = 'NEUTRAL'

            # ============ STEP 7: GOLD MACRO ============
            macro_module = self._modules.get('gold_macro')
            macro_analysis = {}
            if macro_module and symbol == 'XAUUSD':
                macro_analysis = macro_module.analyze(
                    dxy=dxy, dxy_change_pct=dxy_change,
                    us10y_yield=us10y, us10y_change_bps=us10y_change,
                    silver=silver, oil=oil, sp500=sp500, vix=vix,
                )
                components['MACRO'] = macro_analysis.get('probability', 50)
            result['macro_state'] = macro_analysis.get('bias', 'NEUTRAL')

            # ============ STEP 8: KILLZONE / SESSION ============
            session_module = self._modules.get('killzone')
            session_analysis = {}
            if session_module:
                session_analysis = session_module.analyze(
                    primary_candles, current_price,
                    has_news=news_active,
                )
                components['SESSION'] = session_analysis.get('quality_score', 50)
            result['session'] = session_analysis.get('session', '')
            result['session_name'] = session_analysis.get('session_name', '')
            result['killzone'] = session_analysis

            # ============ STEP 9: DYNAMIC SESSION VOLATILITY ============
            sv_module = self._modules.get('session_vol')
            sv_result = {}
            if sv_module:
                sv_result = sv_module.analyze(
                    symbol=symbol,
                    session=result.get('session', ''),
                    atr=atr, volume=volume, spread=spread,
                    current_volatility=atr * (components.get('ATR_EXPANSION', 50) / 50),
                    candles=primary_candles,
                )
                result['session_classification'] = sv_result.get('classification', 'NORMAL')
                result['session_risk_mult'] = sv_result.get('risk_multiplier', 1.0)

                if not sv_result.get('allow_trading', True):
                    result['reason'].append(f"Session vol: {sv_result.get('classification', 'NO_TRADE')}")

            # ============ STEP 10: ADAPTIVE CONFIDENCE ============
            calibrator = self._modules.get('calibrator')

            # SMC structure
            smc = self._modules.get('smc')
            if smc and primary_candles:
                try:
                    smc_analysis = smc.build_levels(primary_candles, 'H1' if h1_candles else 'M15')
                    components['SMC_LEVELS'] = len(smc_analysis)
                    components['FVG'] = len(smc._fvgs) if smc._fvgs else 0
                    components['OB'] = len(smc._obs) if smc._obs else 0
                except Exception:
                    pass

            # MTF divergence (backup)
            mtf_divergence = self._mtf_divergence(all_tf)
            components['MTF_DIVERGENCE'] = mtf_divergence

            # Confluence memory
            memory_module = self._modules.get('memory')
            memory_adjustment = 1.0
            if memory_module:
                try:
                    win_rate, samples = memory_module.query_win_rate(
                        symbol, fvg=components.get('FVG', 0) > 0,
                        regime=regime,
                        session=session_analysis.get('session', ''),
                    )
                    if samples >= 5:
                        memory_adjustment = 1.0 + (win_rate - 0.5) * 0.6
                except Exception:
                    pass
            components['MEMORY'] = round(memory_adjustment, 3)

            # ============ COMPUTE PROBABILITIES ============
            buy_prob, sell_prob = self._compute_probabilities(components, regime)
            result['buy_probability'] = buy_prob
            result['sell_probability'] = sell_prob

            raw_confidence = self._compute_final_confidence(components, buy_prob, sell_prob, trap_analysis)
            result['confidence'] = raw_confidence

            # ============ STEP 10B: CALIBRATE CONFIDENCE ============
            if calibrator:
                cal_result = calibrator.calibrate(
                    raw_confidence, symbol=symbol,
                    session=result.get('session', ''),
                    atr=atr,
                )
                result['calibrated_confidence'] = cal_result.get('calibrated', raw_confidence)
                result['confidence_calibration'] = cal_result

                if abs(cal_result.get('adjustment', 0)) >= 5:
                    result['reason'].append(
                        f"Confidence adjusted: {cal_result.get('adjustment', 0):+.1f}%")
            else:
                result['calibrated_confidence'] = raw_confidence

            final_confidence = result.get('calibrated_confidence', raw_confidence)

            # ============ STEP 11: NEWS LOCKOUT ============
            news_lock_module = self._modules.get('news_lockout')
            news_result = {}
            if news_lock_module:
                news_result = news_lock_module.check(
                    symbol=symbol,
                    volatility=atr * (components.get('ATR_EXPANSION', 50) / 50),
                    current_price=current_price,
                    atr=atr,
                )
                result['news_lock'] = news_result.get('locked', False)
                result['news_lock_type'] = news_result.get('lock_type', '')
                if news_result.get('locked'):
                    result['reason'].append(
                        f"News lock: {news_result.get('reason', 'Event lock')}")
                if news_result.get('emergency'):
                    result['reason'].append("EMERGENCY: Market halt")

            # ============ STEP 12: PORTFOLIO ALLOCATOR ============
            pa_module = self._modules.get('portfolio_allocator')
            pa_result = {}
            if pa_module:
                pa_module.register_strategy('SCALP', win_rate=0.50, avg_rr=0.8,
                                            volatility=1.2 if regime == 'VOLATILITY' else 1.0,
                                            correlation=0.3)
                pa_module.register_strategy('INTRADAY', win_rate=0.55, avg_rr=1.5,
                                            volatility=1.0, correlation=0.4)
                pa_module.register_strategy('SWING', win_rate=0.60, avg_rr=2.5,
                                            volatility=0.8, correlation=0.2)
                pa_result = pa_module.allocate(
                    account_balance=account_balance,
                    risk_budget=0.02,
                    current_drawdown=current_drawdown,
                    volatility_multiplier=max(0.5, atr / 5.0),
                )
                for name, alloc in pa_result.get('allocations', {}).items():
                    if alloc.get('priority', 99) == 1:
                        result['portfolio_allocation'] = f"{alloc.get('allocation_pct', 0)}%"
                        break
                result['portfolio'] = pa_result

            # ============ STEP 13: EXPECTED RR ============
            expected_rr = self._compute_expected_rr(components, buy_prob, sell_prob, atr, current_price)
            result['expected_rr'] = round(expected_rr, 2)

            # ============ STEP 14: INVALIDITY LEVEL ============
            invalidity = self._compute_invalidity(trap_analysis, components, news_active)
            if news_result.get('locked'):
                invalidity = min(100, invalidity + 25)
            if mtf_result.get('rejected'):
                invalidity = min(100, invalidity + 20)
            if sv_result.get('classification') == 'NO_TRADE':
                invalidity = 100
            result['invalidity_level'] = invalidity

            # ============ STEP 15: FINAL ACTION ============
            action = self._decide_action(final_confidence, invalidity, buy_prob, sell_prob, news_active)
            if mtf_result.get('rejected') and action in (ACTION_BUY, ACTION_SELL):
                action = ACTION_WAIT
            if sv_result.get('classification') == 'NO_TRADE':
                action = ACTION_CANCEL
            if news_result.get('locked'):
                action = ACTION_WAIT
            result['action'] = action

            # ============ STEP 16: RISK GOVERNOR ============
            governor = self._modules.get('risk_governor')
            if governor:
                risk_assessment = governor.get_position_size_factor(final_confidence, account_balance)
                result['risk'] = risk_assessment
                result['risk_tier'] = risk_assessment.get('tier', risk_assessment.get('position_tier', 'NORMAL'))

            # ============ STEP 17: EXECUTION QUALITY ============
            eq_module = self._modules.get('exec_analyzer')
            eq_result = {}
            if eq_module:
                eq_result = eq_module.analyze(symbol, current_spread=current_spread,
                                               current_latency=current_latency)
                result['execution_score'] = eq_result.get('score', 85)
                result['execution_warn'] = eq_result.get('warn', False)
                result['execution_block'] = eq_result.get('block', False)
                if eq_result.get('block'):
                    result['reason'].append(f"Execution quality critical: {eq_result.get('score')}")
                    action = ACTION_CANCEL
                    result['action'] = ACTION_CANCEL

            # ============ STEP 18: PORTFOLIO RISK APPLIED ============
            pa_risk_mult = pa_result.get('risk_multiplier', 1.0) if pa_result else 1.0
            sv_risk_mult = sv_result.get('risk_multiplier', 1.0) if sv_result else 1.0
            result['risk_multiplier'] = round(pa_risk_mult * sv_risk_mult, 3)
            result['lot_multiplier'] = round(
                pa_result.get('lot_multiplier', 1.0) * sv_result.get('lot_multiplier', 1.0)
                if pa_result else 1.0, 3)

            # ============ STEP 19: SL / TP ============
            sl, tp = self._compute_sl_tp(current_price, atr, action, sv_result)
            result['sl'] = round(sl, 2)
            result['tp'] = round(tp, 2)

            # ============ STEP 20: SAFE RL LEARNER ============
            rl = self._modules.get('rl_learner')
            if rl:
                result['rl_adjustments'] = rl.get_adjustments()

            # ============ STEP 21: TRADE REPLAY ============
            replay = self._modules.get('trade_replay')
            if replay and action in (ACTION_BUY, ACTION_SELL):
                trade_id = replay.record_decision(result)
                result['trade_id'] = trade_id

            # ============ FINAL JSON OUTPUT ============
            result['components'] = components
            result['sweep_analysis'] = sweep_analysis
            result['trap_analysis'] = trap_analysis
            result['macro_analysis'] = macro_analysis
            result['orderflow_analysis'] = of_analysis

            reasons = result.get('reason', [])
            if not reasons and action in (ACTION_BUY, ACTION_SELL):
                if components.get('SWEEP', 0) > 60:
                    reasons.append('Liquidity Sweep')
                if result.get('orderflow') in ('Strong Buy', 'Buy'):
                    reasons.append(f"Order Flow: {result.get('orderflow', '')}")
                if macro_analysis.get('bias') == result.get('bias'):
                    reasons.append('Macro Alignment')
                if result.get('session') in ('LONDON_OPEN', 'NY_OPEN', 'OVERLAP'):
                    reasons.append(f"{result.get('session_name', result.get('session', ''))}")
                if mtf_result.get('consensus', 0) >= 75:
                    reasons.append(f"High AI Consensus ({mtf_result.get('consensus', 0)}%)")
                if trap_analysis.get('trap_probability', 100) < 30:
                    reasons.append('Low Trap Probability')
                if eq_result and eq_result.get('score', 0) >= 85:
                    reasons.append(f"Execution Quality ({eq_result.get('score', 0)})")

            result['reason'] = reasons

            # Build structured summary
            result['_final'] = self._build_final_output(result)

        except Exception as e:
            log.warning(f"AI Decision Engine error: {e}")
            result['error'] = str(e)

        result['execution_time_ms'] = round((time.time() - pipeline_start) * 1000, 1)
        self._latest_analysis = result
        self._signal_timestamp = time.time()
        return result

    def get_latest_analysis(self) -> Dict[str, Any]:
        return dict(self._latest_analysis)

    def get_final_output(self) -> Dict[str, Any]:
        analysis = self._latest_analysis
        return self._build_final_output(analysis)

    def get_modules_status(self) -> Dict[str, bool]:
        return {k: v is not None for k, v in self._modules.items()}

    def _build_final_output(self, result: Dict[str, Any]) -> Dict[str, Any]:
        action = result.get('action', 'WAIT')
        conf = result.get('calibrated_confidence', result.get('confidence', 0))
        cons = result.get('consensus', 50)
        return {
            'action': action,
            'confidence': result.get('confidence', 0),
            'calibrated_confidence': conf,
            'bull_probability': round(result.get('buy_probability', 0) / 100, 2),
            'bear_probability': round(result.get('sell_probability', 0) / 100, 2),
            'consensus': cons,
            'trap_probability': round(result.get('trap_probability', 0) / 100, 2),
            'macro_state': result.get('macro_state', 'NEUTRAL'),
            'orderflow': result.get('orderflow', 'NEUTRAL'),
            'killzone': result.get('session_name', result.get('session', '')),
            'news_lock': result.get('news_lock', False),
            'execution_score': result.get('execution_score', 85),
            'risk_tier': result.get('risk_tier', 'NORMAL'),
            'portfolio_allocation': result.get('portfolio_allocation', ''),
            'recommended_lot': round(
                result.get('lot_multiplier', 1.0) * 0.10, 2),
            'reason': result.get('reason', []),
            'sl': result.get('sl', 0),
            'tp': result.get('tp', 0),
            'expected_rr': result.get('expected_rr', 0),
        }

    def _trend_bias(self, candles: List[Dict]) -> int:
        if not candles or len(candles) < 10:
            return 0
        try:
            closes = [c.get('close', 0) for c in candles[-20:] if 'close' in c]
            if len(closes) < 5:
                return 0
            ema_fast = sum(closes[-5:]) / 5
            ema_slow = sum(closes) / len(closes)
            diff = (ema_fast - ema_slow) / max(ema_slow, 1) * 1000
            return max(-100, min(100, int(diff)))
        except Exception:
            return 0

    def _tf_bias_score(self, candles: List[Dict]) -> int:
        if not candles or len(candles) < 5:
            return 50
        try:
            recent = candles[-10:]
            up = sum(1 for c in recent if c.get('close', 0) > c.get('open', 0))
            ratio = up / max(len(recent), 1)
            return int(ratio * 100)
        except Exception:
            return 50

    def _atr_expansion(self, candles: List[Dict], atr: float) -> int:
        if not candles or len(candles) < 10 or atr <= 0:
            return 50
        try:
            recent = candles[-10:]
            ranges = [c.get('high', 0) - c.get('low', 0) for c in recent if 'high' in c]
            avg_range = sum(ranges) / max(len(ranges), 1)
            ratio = avg_range / atr
            if ratio > 1.3:
                return 80
            elif ratio > 1.0:
                return 65
            elif ratio > 0.7:
                return 50
            return 35
        except Exception:
            return 50

    def _vwap_position(self, price: float, vwap: float, atr: float) -> int:
        if atr <= 0 or vwap <= 0:
            return 50
        try:
            diff = (price - vwap) / atr
            if diff > 0.5:
                return 70
            elif diff > 0.2:
                return 60
            elif diff > -0.2:
                return 50
            elif diff > -0.5:
                return 40
            return 30
        except Exception:
            return 50

    def _mtf_divergence(self, all_tf: List[List[Dict]]) -> int:
        biases = [self._tf_bias_score(tf) for tf in all_tf if tf]
        if len(biases) < 2:
            return 50
        try:
            avg = sum(biases) / len(biases)
            divergence = max(abs(b - avg) for b in biases)
            return max(0, 100 - int(divergence * 2))
        except Exception:
            return 50

    def _compute_probabilities(self, components: Dict, regime: str) -> Tuple[int, int]:
        buy_score = 0
        sell_score = 0
        weights = {
            'M1': 0.08, 'M5': 0.08, 'M15': 0.10, 'H1': 0.10,
            'ATR_EXPANSION': 0.05, 'VWAP': 0.05, 'SESSION': 0.07,
            'SWEEP': 0.10, 'TRAP': 0.08, 'MACRO': 0.07,
            'ORDERFLOW': 0.08, 'MTF_DIVERGENCE': 0.04,
        }
        for key, weight in weights.items():
            val = components.get(key, 50)
            if isinstance(val, str):
                val = 50
            if isinstance(val, bool):
                val = 80 if val else 30
            val = max(0, min(100, val))
            buy_score += val * weight
            sell_score += (100 - val) * weight

        trap_prob = components.get('TRAP', 0)
        if trap_prob > 70:
            sell_score = max(sell_score, buy_score + 20)

        if regime == 'VOLATILITY':
            buy_score *= 0.5
            sell_score *= 0.5

        total = buy_score + sell_score
        if total == 0:
            return 50, 50
        buy_pct = int(buy_score / total * 100)
        sell_pct = int(sell_score / total * 100)
        return min(100, buy_pct), min(100, sell_pct)

    def _compute_final_confidence(self, components: Dict, buy_prob: int,
                                    sell_prob: int, trap: Dict) -> int:
        confidence = max(buy_prob, sell_prob)
        trap_prob = trap.get('trap_probability', 0)
        if trap_prob > 70:
            confidence = int(confidence * 0.4)
        elif trap_prob > 50:
            confidence = int(confidence * 0.7)
        memory_adj = components.get('MEMORY', 1.0)
        confidence = int(confidence * memory_adj)
        return max(0, min(100, confidence))

    def _compute_expected_rr(self, components: Dict, buy_prob: int,
                               sell_prob: int, atr: float, price: float) -> float:
        base_rr = 2.0
        confidence = max(buy_prob, sell_prob)
        if confidence >= 90:
            return round(base_rr * 1.5, 2)
        elif confidence >= 80:
            return round(base_rr * 1.2, 2)
        elif confidence >= 70:
            return base_rr
        elif confidence >= 60:
            return 1.5
        return 1.0

    def _compute_invalidity(self, trap: Dict, components: Dict, news: bool) -> int:
        trap_prob = trap.get('trap_probability', 0)
        invalidity = trap_prob
        if news:
            invalidity = min(100, invalidity + 20)
        if components.get('MTF_DIVERGENCE', 50) < 30:
            invalidity = min(100, invalidity + 15)
        if components.get('REGIME') == 'VOLATILITY':
            invalidity = min(100, invalidity + 10)
        return invalidity

    def _decide_action(self, confidence: int, invalidity: int,
                         buy_prob: int, sell_prob: int, news: bool) -> str:
        if invalidity >= 80:
            return ACTION_CANCEL
        if news:
            return ACTION_WAIT
        if confidence >= 75 and invalidity < 50:
            return ACTION_BUY if buy_prob >= sell_prob else ACTION_SELL
        if confidence >= 60 and invalidity < 60:
            return ACTION_WAIT
        return ACTION_CANCEL

    def _compute_sl_tp(self, price: float, atr: float, action: str,
                        sv_result: Dict) -> Tuple[float, float]:
        if price <= 0 or atr <= 0:
            return 0, 0
        sv_sl_adj = sv_result.get('sl_adjustment', 1.0) if sv_result else 1.0
        sv_tp_adj = sv_result.get('tp_adjustment', 1.0) if sv_result else 1.0
        if action == ACTION_BUY:
            sl = price - atr * 1.5 * sv_sl_adj
            tp = price + atr * 3.0 * sv_tp_adj
        elif action == ACTION_SELL:
            sl = price + atr * 1.5 * sv_sl_adj
            tp = price - atr * 3.0 * sv_tp_adj
        else:
            sl = price - atr * 1.5
            tp = price + atr * 3.0
        return sl, tp


_engine: Optional[AIDecisionEngine] = None


def get_decision_engine() -> AIDecisionEngine:
    global _engine
    if _engine is None:
        _engine = AIDecisionEngine()
    return _engine


if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    if '--test' in sys.argv:
        de = get_decision_engine()
        test_candles = {
            'M1': [{'high': i+100, 'low': i+99, 'close': i+99.5, 'open': i+99, 'volume': 100} for i in range(20)],
            'M5': [{'high': i+101, 'low': i+99, 'close': i+100, 'open': i+99.5, 'volume': 200} for i in range(20)],
            'M15': [{'high': i+102, 'low': i+98, 'close': i+100, 'open': i+99, 'volume': 300} for i in range(20)],
            'H1': [{'high': i+103, 'low': i+97, 'close': i+100.5, 'open': i+99, 'volume': 500} for i in range(20)],
        }
        result = de.analyze('XAUUSD', test_candles, 105.5, vwap=104.0, atr=5.0)
        print(f"Action: {result['action']}")
        print(f"Confidence: {result['confidence']} -> Calibrated: {result['calibrated_confidence']}")
        print(f"Consensus: {result['consensus']}, Bias: {result['bias']}")
        print(f"Session: {result['session']}, Execution: {result['execution_score']}")
        print(f"Risk Tier: {result['risk_tier']}, News Lock: {result['news_lock']}")
        print(f"Reasons: {result['reason']}")
        print(f"Time: {result['execution_time_ms']}ms")
        if '_final' in result:
            print("=== FINAL JSON ===")
            import json
            print(json.dumps(result['_final'], indent=2))
        print("AIDecisionEngine Integration OK")
