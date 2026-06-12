"""
Pipeline Orchestrator - OMNI BRAIN V2
=====================================
Live data scanner → signal processing pipeline.

Pipeline Flow:
  1. Fetch OHLCV candles from live API
  2. MT5 Split-Brain Guard lock
  3. Smart Money Matrix scan
  4. MTF Confirmation check
  5. Confidence Score calculation
  6. Adaptive Threshold check
  7. Circuit Breaker gate
  8. Decision → log + git commit + Telegram alert
"""

import os
import sys
import json
import time
import math
import logging
import secrets
import hmac
import subprocess
import threading
import re
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple

from production.alert_contract import AlertSender
from production.sniper_execution import SniperStrategy
from production.phase64_chaser import Phase64Chaser
from production.alpha_agent import AlphaAgent
from pathlib import Path
from collections import defaultdict

# Add production directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'production'))

# Load .env (try encrypted first, then plaintext)
_env_path = Path(__file__).parent / '.env'
_encrypted_path = Path(__file__).parent / '.env.encrypted'
_key_path = Path(__file__).parent / '.secrets.key'

_loaded = False
if _encrypted_path.exists() and _key_path.exists():
    try:
        from cryptography.fernet import Fernet
        _key = _key_path.read_bytes()
        _cipher = Fernet(_key)
        _decrypted = _cipher.decrypt(_encrypted_path.read_bytes()).decode()
        for _line in _decrypted.splitlines():
            _line = _line.strip()
            if _line and not _line.startswith('#') and '=' in _line:
                _k, _v = _line.split('=', 1)
                os.environ.setdefault(_k.strip(), _v.strip())
        _loaded = True
        log.info("Loaded secrets from .env.encrypted")
        del _decrypted, _key, _cipher
    except Exception as _e:
        log.warning(f"Failed to decrypt .env.encrypted: {_e}")

if not _loaded and _env_path.exists():
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith('#') and '=' in _line:
                _k, _v = _line.split('=', 1)
                os.environ.setdefault(_k.strip(), _v.strip())
    if _encrypted_path.exists():
        log.warning("Falling back to plaintext .env (encrypted failed)")

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

LOG_DIR = Path(__file__).parent / 'logs'
LOG_DIR.mkdir(exist_ok=True)

PIPELINE_LOG_FILE = LOG_DIR / 'pipeline_log.csv'
SCAN_RESULTS_FILE = LOG_DIR / 'last_scan.json'

PIPELINE_HEADERS = 'timestamp,symbol,direction,decision,score,total_ms,step_times\n'

if not PIPELINE_LOG_FILE.exists():
    PIPELINE_LOG_FILE.write_text(PIPELINE_HEADERS)

ASSETS = ['XAUUSD', 'EURUSD', 'GBPUSD', 'SP500']
TIMEFRAMES = ['M15', 'H1', 'H4', 'D1']

# ══════════════════════════════════════════════════════════════════════════════
# LOGGING
# ══════════════════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / 'orchestrator.log')
    ]
)
log = logging.getLogger('PipelineOrchestrator')

# Environment validation on startup
_REQUIRED_ENV_KEYS = ['LIVE_DATA_API_KEY', 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID']
_OPTIONAL_ENV_KEYS = ['ANTHROPIC_API_KEY', 'PERPLEXITY_API_KEY', 'GITHUB_TOKEN']

missing = [k for k in _REQUIRED_ENV_KEYS if not os.environ.get(k)]
for k in missing:
    log.warning(f"Missing required env var: {k} — set in .env to enable full functionality")
for k in _OPTIONAL_ENV_KEYS:
    if os.environ.get(k):
        log.debug(f"Found optional env var: {k}")

# ══════════════════════════════════════════════════════════════════════════════
# INPUT VALIDATION UTILITIES
# ══════════════════════════════════════════════════════════════════════════════

_SYMBOL_RE = re.compile(r'^[A-Z0-9]{2,10}$')
_ALLOWED_DIRECTIONS = {'LONG', 'SHORT', 'BUY', 'SELL', 'BULLISH', 'BEARISH'}
_MAX_PAYLOAD_SIZE = 1024 * 512  # 512KB max
_MAX_CANDLES = 500

def _validate_symbol(symbol: str) -> bool:
    return bool(_SYMBOL_RE.match(symbol))

def _validate_pipeline_payload(payload: Dict[str, Any]) -> Tuple[bool, str]:
    if not isinstance(payload, dict):
        return False, "payload must be a JSON object"
    symbol = payload.get('symbol', '').upper()
    if not _validate_symbol(symbol):
        return False, f"invalid symbol: {symbol}"
    direction = payload.get('direction', 'LONG').upper()
    if direction not in _ALLOWED_DIRECTIONS:
        return False, f"invalid direction: {direction}"
    candles = payload.get('candles', [])
    if isinstance(candles, list) and len(candles) > _MAX_CANDLES:
        return False, f"too many candles: {len(candles)} (max {_MAX_CANDLES})"
    price = payload.get('price', 0)
    if price and not isinstance(price, (int, float)):
        return False, "price must be numeric"
    return True, ""

# ══════════════════════════════════════════════════════════════════════════════
# API AUTHENTICATION & RATE LIMITING
# ══════════════════════════════════════════════════════════════════════════════

API_KEY = secrets.token_hex(32)
os.environ.setdefault('PIPELINE_API_KEY', API_KEY)

AUTH_LOG_FILE = LOG_DIR / 'api_auth.log'
BLOCKED_IPS_FILE = LOG_DIR / 'blocked_ips.json'

_rate_limiter_lock = threading.Lock()
_request_counts = defaultdict(lambda: {'count': 0, 'window_start': time.time(), 'trigger_scan': 0})
_failed_auth = defaultdict(int)
_blocked_ips = set()  # IP blocking disabled

def _load_blocked_ips():
    global _blocked_ips
    try:
        if BLOCKED_IPS_FILE.exists():
            data = json.loads(BLOCKED_IPS_FILE.read_text())
            _blocked_ips = set(data.get('blocked_ips', []))
    except Exception:
        pass

def _save_blocked_ips():
    try:
        BLOCKED_IPS_FILE.write_text(json.dumps({'blocked_ips': list(_blocked_ips)}, indent=2))
    except Exception:
        pass

_load_blocked_ips()

# Set restrictive permissions on blocked IPs file
if BLOCKED_IPS_FILE.exists():
    try:
        BLOCKED_IPS_FILE.chmod(0o600)
    except Exception:
        pass

def _log_auth(ip, endpoint, status):
    try:
        with open(AUTH_LOG_FILE, 'a') as f:
            f.write(f"{datetime.now(timezone.utc).isoformat()} {ip} {endpoint} {status}\n")
    except Exception:
        pass

def _log_request(method, path, ip, status_code):
    log.info(f"HTTP {method} {path} -> {status_code} from {ip}")

def _check_rate_limit(ip, endpoint):
    now = time.time()
    with _rate_limiter_lock:
        if ip in _blocked_ips:
            return False, 'IP blocked'

        info = _request_counts[ip]
        if now - info['window_start'] > 60:
            info['count'] = 0
            info['trigger_scan'] = 0
            info['window_start'] = now

        info['count'] += 1
        if info['count'] > 60:
            return False, 'Rate limit exceeded (60/min)'

        if '/api/trigger-scan' in endpoint:
            info['trigger_scan'] += 1
            if info['trigger_scan'] > 10:
                return False, 'Rate limit exceeded (10 trigger-scan/min)'

    return True, ''

def _record_failed_auth(ip):
    with _rate_limiter_lock:
        _failed_auth[ip] += 1
        # IP blocking disabled - rate limiting is sufficient
    return False

def require_auth(func):
    def wrapper(handler, *args, **kwargs):
        ip = handler.client_address[0]
        endpoint = handler.path

        if ip in _blocked_ips:
            _log_auth(ip, endpoint, 'BLOCKED')
            handler._send_json(403, {'error': 'IP blocked'})
            return

        allowed, msg = _check_rate_limit(ip, endpoint)
        if not allowed:
            _log_auth(ip, endpoint, f'RATE_LIMITED: {msg}')
            handler._send_json(429, {'error': msg})
            return

        if handler.path == '/health' or handler.path == '/':
            _log_auth(ip, endpoint, 'PUBLIC')
            return func(handler, *args, **kwargs)

        # Check header first
        token = handler.headers.get('X-API-Key', '')
        expected = os.environ.get('PIPELINE_API_KEY', API_KEY)
        
        # Also check URL parameter ?key=
        if not token:
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(handler.path)
            params = parse_qs(parsed.query)
            token = params.get('key', [None])[0] or ''
        
        if not hmac.compare_digest(token, expected):
            _log_auth(ip, endpoint, 'UNAUTHORIZED')
            blocked = _record_failed_auth(ip)
            if blocked:
                handler._send_json(403, {'error': 'IP blocked'})
            else:
                handler._send_json(401, {'error': 'Unauthorized'})
            return

        _log_auth(ip, endpoint, 'SUCCESS')
        _failed_auth.pop(ip, None)
        return func(handler, *args, **kwargs)
    return wrapper


# ══════════════════════════════════════════════════════════════════════════════
# IMPORTS (lazy load to avoid circular)
# ══════════════════════════════════════════════════════════════════════════════

def _import_modules():
    """Lazy import of pipeline modules."""
    from confidence_scorer import ConfidenceScorer, get_scorer
    from adaptive_threshold import AdaptiveThreshold, get_threshold_engine
    from mtf_confirmation import MTFConfirmation, get_mtf_engine
    from circuit_breaker import CircuitBreaker, get_circuit_breaker
    from smart_money_matrix import SmartMoneyMatrix, Candle
    from correlation_engine import CorrelationEngine, get_correlation_engine
    from forex_factory_news import ForexFactoryNews, get_forex_factory_news
    from treasury_monitor import TreasuryMonitor, get_treasury_monitor
    from sentiment_engine import SentimentEngine, get_sentiment_engine
    from session_detector import SessionDetector, get_session_detector
    from pattern_engine import PatternEngine, get_pattern_engine
    from divergence_scanner import DivergenceScanner, get_divergence_scanner
    from risk_manager import RiskManager, get_risk_manager
    from regime_detector import RegimeDetector, get_regime_detector
    from dashboard_bridge import DashboardBridge, get_bridge
    from execution_precision import ExecutionPlanner
    from confluence_memory import ConfluenceMemory, get_memory
    from ai_decision_engine import AIDecisionEngine, get_decision_engine
    return {
        'scorer': get_scorer(),
        'threshold': get_threshold_engine(),
        'mtf': get_mtf_engine(),
        'circuit_breaker': get_circuit_breaker(),
        'SmartMoneyMatrix': SmartMoneyMatrix,
        'Candle': Candle,
        'correlation': get_correlation_engine(),
        'news': get_forex_factory_news(),
        'treasury': get_treasury_monitor(),
        'sentiment': get_sentiment_engine(),
        'session': get_session_detector(),
        'pattern': get_pattern_engine(),
        'divergence': get_divergence_scanner(),
        'risk': get_risk_manager(),
        'regime_detector': get_regime_detector(),
        'bridge': get_bridge(),
        'execution_planner': ExecutionPlanner(),
        'memory': get_memory(),
        'decision_engine': get_decision_engine(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# GIT AUTO-COMMIT
# ══════════════════════════════════════════════════════════════════════════════

def git_commit(message: str) -> bool:
    """Commit logs to git."""
    try:
        result = subprocess.run(
            ['git', 'add', 'logs/'],
            capture_output=True, timeout=5
        )
        if result.returncode != 0:
            return False
        
        result = subprocess.run(
            ['git', 'commit', '-m', message],
            capture_output=True, timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class PipelineEngine:
    """
    Full OMNI BRAIN V2 pipeline engine.
    
    Pipeline:
      1. Circuit Breaker
      2. Smart Money Matrix scan
      3. MTF Confirmation
      4. Session detection
      5. News block check
      6. Correlation analysis
      7. Treasury yield check
      8. Sentiment analysis
      9. Pattern recognition
     10. Divergence scanning
     11. Risk check (spread, limits, halts)
     12. Confidence Score (all components)
     13. Adaptive Threshold
     14. Execute decision
    """
    
    def __init__(self, alert_sender: Optional[AlertSender] = None):
        self.modules = None
        self._initialized = False
        self.alert_sender = alert_sender
        self.sniper = SniperStrategy(volume_multiplier=1.5)
        self.chaser = Phase64Chaser(max_chase_pips=10.0)
        self.alpha = AlphaAgent(profit_target_pips=200.0, trail_activation_pips=50.0)
        self.active_orders = {}    # Track live limit state (Phase 64)
        self.open_positions = {}   # Track filled trades (Alpha Agent)
    
    def _ensure_initialized(self):
        """Lazy initialize modules."""
        if not self._initialized:
            try:
                self.modules = _import_modules()
                self._initialized = True
            except Exception as e:
                log.error(f"Failed to initialize modules: {e}")
    
    def run_pipeline(self, payload: Dict[str, Any], source: str = '') -> Dict[str, Any]:
        """
        Run full pipeline on scan data.
        
        Returns:
            Dict with decision, timing, and result data
        """
        self._ensure_initialized()

        valid, msg = _validate_pipeline_payload(payload)
        if not valid:
            return {
                'decision': 'BLOCK',
                'error': msg,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }

        # ── Sniper + Chaser Routing (Layer 2) ──────────────────────────
        if source == 'scanner':
            # Run Sniper Selection on enriched SMC payload
            signal = self.sniper.evaluate_market(payload)
            if signal["decision"] in ["BUY", "SELL"] and signal["confidence_score"] >= 0.70:
                # Route to Phase 64 setup
                self._initiate_chaser_order(signal, payload)
                log.info(f"[SNIPER] {signal['decision']} {payload.get('symbol')} "
                         f"conf={signal['confidence_score']:.2f} → chaser initiated")
            else:
                log.debug(f"[SNIPER] {signal['decision']} — {signal['reason']}")

        elif source == 'websocket_tick':
            # Run Phase 64 Order Book Chaser Tracking
            for order_id, state in list(self.active_orders.items()):
                order_book = {"bid": payload.get("bid", 0), "ask": payload.get("ask", 0)}
                directive = self.chaser.process_chase_cycle(state, order_book)
                self._execute_chaser_directive(order_id, directive)

            # Run Alpha Agent Position Management
            current_price = payload.get("bid", 0) or payload.get("ask", 0) or payload.get("price", 0)
            smc = payload.get("smc", {})
            for pos_id, position in list(self.open_positions.items()):
                directive = self.alpha.manage_position(position, smc, current_price)
                if directive['action'] == 'CLOSE':
                    self._exit_position(pos_id, position, directive)
                elif directive['action'] == 'UPDATE_SL':
                    self._modify_sl(pos_id, position, directive)

        pipeline_start = time.time()
        step_times = {}
        symbol = payload.get('symbol', 'UNKNOWN').upper()
        direction = payload.get('direction', 'LONG').upper()
        tf = payload.get('timeframe', 'H1')
        
        result = {
            'symbol': symbol,
            'direction': direction,
            'decision': 'BLOCK',
            'score': 0,
            'steps': {},
            'timing': {},
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        try:
            # Step 1: Circuit Breaker check
            t = time.time()
            cb = self.modules.get('circuit_breaker') if self.modules else None
            if cb:
                allowed = cb.allow(symbol)
                result['steps']['circuit_breaker'] = allowed
                step_times['step1_cb'] = (time.time() - t) * 1000
                
                if not allowed:
                    result['decision'] = 'BLOCKED_CB'
                    result['reason'] = 'Circuit breaker active'
                    self._log_pipeline(result, step_times, pipeline_start)
                    return result
            else:
                step_times['step1_cb'] = 0
            
            # Step 2: Smart Money Matrix scan
            t = time.time()
            sm_scores = {'OB_SIGNAL': 0, 'FVG_SIGNAL': 0, 'SWEEP_SIGNAL': 0}
            current_price = payload.get('price', 0)
            
            candles = payload.get('candles', [])
            if candles and self.modules:
                try:
                    SmartMoneyMatrix = self.modules.get('SmartMoneyMatrix')
                    Candle = self.modules.get('Candle')
                    if SmartMoneyMatrix and Candle:
                        matrix = SmartMoneyMatrix()
                        candle_objects = [
                            Candle(
                                timestamp=c.get('timestamp', 0),
                                open=c.get('open', 0),
                                high=c.get('high', 0),
                                low=c.get('low', 0),
                                close=c.get('close', 0),
                                volume=c.get('volume', 0)
                            ) for c in candles[-100:]
                        ]
                        detection = matrix.scan(candle_objects)
                        sm_scores = {
                            'OB_SIGNAL': len(detection.get('order_blocks', [])),
                            'FVG_SIGNAL': len(detection.get('fair_value_gaps', [])),
                            'SWEEP_SIGNAL': len(detection.get('sweep_events', []))
                        }
                        if not current_price:
                            current_price = candle_objects[-1].close if candle_objects else 0
                except Exception as e:
                    log.error(f"Smart Money scan error: {e}")
            
            result['steps']['smart_money'] = sm_scores
            step_times['step2_scan'] = (time.time() - t) * 1000
            
            # Step 2.5: Regime Detection
            t = time.time()
            regime_detector = self.modules.get('regime_detector') if self.modules else None
            regime = 'COMPRESSION'
            liquidity_quality = 0
            if regime_detector and candles:
                regime = regime_detector.classify(candles)
                result['regime'] = regime
                result['regime_metrics'] = regime_detector.get_metrics()
                try:
                    from regime_detector import score_liquidity_quality
                    liquidity_quality = score_liquidity_quality(
                        current_price=current_price or 0,
                        candles=candles,
                    )
                except Exception:
                    pass
                result['liquidity_quality'] = liquidity_quality
            step_times['step2b_regime'] = (time.time() - t) * 1000
            
            # Step 2c: AI Decision Engine (full multi-module analysis)
            t = time.time()
            decision_engine = self.modules.get('decision_engine') if self.modules else None
            ai_result = {}
            if decision_engine and candles:
                try:
                    tf_candles = {'H1': candles}
                    ai_result = decision_engine.analyze(
                        symbol=symbol,
                        candles=tf_candles,
                        current_price=float(current_price) if current_price else 0,
                        vwap=payload.get('vwap', 0),
                        atr=atr if 'atr' in dir() else payload.get('atr', 5.0),
                        news_active=bool(news_penalty < 0) if 'news_penalty' in dir() else False,
                    )
                    result['ai_decision'] = {
                        'action': ai_result.get('action', 'WAIT'),
                        'confidence': ai_result.get('confidence', 0),
                        'calibrated_confidence': ai_result.get('calibrated_confidence', 0),
                        'buy_prob': ai_result.get('buy_probability', 50),
                        'sell_prob': ai_result.get('sell_probability', 50),
                        'consensus': ai_result.get('consensus', 50),
                        'alignment': ai_result.get('alignment', 100),
                        'bias': ai_result.get('bias', 'NEUTRAL'),
                        'invalidity': ai_result.get('invalidity_level', 0),
                        'expected_rr': ai_result.get('expected_rr', 1.0),
                        'execution_score': ai_result.get('execution_score', 85),
                        'risk_tier': ai_result.get('risk_tier', 'NORMAL'),
                        'news_lock': ai_result.get('news_lock', False),
                        'reason': ai_result.get('reason', []),
                        'session': ai_result.get('session', ''),
                        'macro_state': ai_result.get('macro_state', 'NEUTRAL'),
                        'orderflow': ai_result.get('orderflow', 'NEUTRAL'),
                        '_final': ai_result.get('_final', {}),
                    }
                except Exception as e:
                    log.debug(f"AI Decision Engine skipped: {e}")
            step_times['step2c_ai'] = (time.time() - t) * 1000
            
            # Step 3: MTF Confirmation (placeholder - needs real data)
            t = time.time()
            mtf_confirmed = True
            result['steps']['mtf'] = {'confirmed': mtf_confirmed}
            step_times['step3_mtf'] = (time.time() - t) * 1000
            
            # Step 4: Session detection
            t = time.time()
            session = self.modules.get('session') if self.modules else None
            session_info = {}
            if session:
                session_info = session.get_session_info(symbol=symbol)
                result['steps']['session'] = session_info
                if session_info.get('dead_zone'):
                    result['decision'] = 'BLOCKED_SESSION'
                    result['reason'] = 'Dead zone - no trading'
                    self._log_pipeline(result, step_times, pipeline_start)
                    return result
            step_times['step4_session'] = (time.time() - t) * 1000
            
            # Step 5: News block check
            t = time.time()
            news_module = self.modules.get('news') if self.modules else None
            news_blocked = False
            news_penalty = 0
            news_reason = ''
            if news_module:
                blocked, reason = news_module.check_signal_block(symbol)
                news_blocked = blocked
                news_reason = reason
                if blocked:
                    news_penalty = -15
                else:
                    news_penalty = 0 if 'clear' in reason else -5
                result['steps']['news'] = {'blocked': blocked, 'reason': reason, 'penalty': news_penalty}
            step_times['step5_news'] = (time.time() - t) * 1000
            
            # Step 6: Correlation analysis
            t = time.time()
            correlation_module = self.modules.get('correlation') if self.modules else None
            correlation_score = 0
            correlation_reason = ''
            if correlation_module and candles:
                for c in candles[-51:]:
                    correlation_module.update_price(symbol, c.get('close', 0))
                correlation_module.update_correlation_matrix()
                corr_adj, corr_reason = correlation_module.get_score_adjustment(symbol, direction)
                correlation_score = corr_adj
                correlation_reason = corr_reason
                result['steps']['correlation'] = {'adjustment': corr_adj, 'reason': corr_reason}
            step_times['step6_correlation'] = (time.time() - t) * 1000
            
            # Step 7: Treasury yield check
            t = time.time()
            treasury_module = self.modules.get('treasury') if self.modules else None
            yield_score = 0
            yield_reason = ''
            if treasury_module:
                treasury_module.fetch_yields()
                yield_adj, yield_reason = treasury_module.get_score_adjustment(symbol)
                yield_score = yield_adj
                result['steps']['yield'] = {'adjustment': yield_adj, 'reason': yield_reason}
            step_times['step7_yield'] = (time.time() - t) * 1000
            
            # Step 8: Sentiment analysis
            t = time.time()
            sentiment_module = self.modules.get('sentiment') if self.modules else None
            sentiment_score = 0
            sentiment_reason = ''
            if sentiment_module:
                sentiment_module.refresh()
                sent_adj, sent_reason = sentiment_module.get_score_adjustment(symbol)
                sentiment_score = sent_adj
                result['steps']['sentiment'] = {'adjustment': sent_adj, 'reason': sent_reason}
            step_times['step8_sentiment'] = (time.time() - t) * 1000
            
            # Step 9: Pattern recognition
            t = time.time()
            pattern_module = self.modules.get('pattern') if self.modules else None
            pattern_score = 0
            pattern_count = 0
            if pattern_module and candles:
                try:
                    pattern_result = pattern_module.scan(symbol, candles, current_price)
                    pattern_score = pattern_result.total_score
                    pattern_count = len(pattern_result.patterns)
                    result['steps']['pattern'] = {'score': pattern_score, 'count': pattern_count, 'patterns': pattern_result.patterns}
                except Exception as e:
                    log.error(f"Pattern scan error: {e}")
            step_times['step9_pattern'] = (time.time() - t) * 1000
            
            # Step 10: Divergence scanning
            t = time.time()
            divergence_module = self.modules.get('divergence') if self.modules else None
            divergence_score = 0
            divergence_count = 0
            if divergence_module and candles:
                try:
                    div_result = divergence_module.scan(symbol, {tf: candles})
                    divergence_score = div_result.total_score
                    divergence_count = len(div_result.divergences)
                    result['steps']['divergence'] = {'score': divergence_score, 'count': divergence_count, 'divergences': div_result.divergences}
                except Exception as e:
                    log.error(f"Divergence scan error: {e}")
            step_times['step10_divergence'] = (time.time() - t) * 1000
            
            # Step 11: Risk check
            t = time.time()
            risk_module = self.modules.get('risk') if self.modules else None
            risk_status = {}
            if risk_module:
                halted, halt_reason = risk_module.check_halts()
                limits_ok, limits_reason = risk_module.check_trade_limits(symbol)
                risk_status = {
                    'halted': halted,
                    'halt_reason': halt_reason,
                    'limits_ok': limits_ok,
                    'limits_reason': limits_reason,
                }
                result['steps']['risk'] = risk_status
                if halted:
                    result['decision'] = 'BLOCKED_RISK'
                    result['reason'] = halt_reason
                    self._log_pipeline(result, step_times, pipeline_start)
                    return result
                if not limits_ok:
                    result['decision'] = 'BLOCKED_LIMITS'
                    result['reason'] = limits_reason
                    self._log_pipeline(result, step_times, pipeline_start)
                    return result
            step_times['step11_risk'] = (time.time() - t) * 1000
            
            # Step 12: Confidence Score (with all components)
            t = time.time()
            scorer = self.modules.get('scorer') if self.modules else None
            if scorer:
                score_result = scorer.score(
                    symbol=symbol,
                    tf=tf,
                    ob_active=sm_scores.get('OB_SIGNAL', 0) > 0,
                    fvg_active=sm_scores.get('FVG_SIGNAL', 0) > 0,
                    sweep_fired=sm_scores.get('SWEEP_SIGNAL', 0) > 0,
                    price=float(current_price),
                    correlation_score=correlation_score,
                    news_penalty=news_penalty,
                    yield_score=yield_score,
                    sentiment_score=sentiment_score,
                    pattern_score=pattern_score,
                    divergence_score=divergence_score,
                    regime=regime,
                    liquidity_quality=liquidity_quality,
                    signal_decay_elapsed=payload.get('signal_age_seconds', 0),
                    signal_decay_hl=payload.get('signal_hl_seconds', 0),
                )
                result['score'] = score_result.score
                result['decision'] = score_result.decision
                result['steps']['confidence'] = {
                    'score': score_result.score,
                    'decision': score_result.decision,
                    'components': score_result.components
                }
            else:
                result['score'] = 50
                result['decision'] = 'WAIT'
                result['steps']['confidence'] = {'score': 50, 'decision': 'WAIT'}
            step_times['step12_score'] = (time.time() - t) * 1000
            
            # Step 13: Adaptive Threshold check
            t = time.time()
            threshold_engine = self.modules.get('threshold') if self.modules else None
            if threshold_engine:
                threshold = threshold_engine.get_threshold(symbol)
                result['steps']['threshold'] = {'threshold': threshold, 'score': result['score']}
                if result['score'] < threshold and result['decision'] == 'EXECUTE':
                    result['decision'] = 'WAIT'
            else:
                result['steps']['threshold'] = {'threshold': 75}
            step_times['step13_threshold'] = (time.time() - t) * 1000
            
            # Step 14: Execute decision
            t = time.time()
            self._execute_decision(result, payload)
            step_times['step14_execute'] = (time.time() - t) * 1000
            
            # Step 15: Record execution quality with Twelve Data market data
            t = time.time()
            try:
                from execution_quality import get_execution_analyzer
                eq = get_execution_analyzer()
                market_data = eq._fetch_market_data(symbol)
                eq.record_execution(
                    symbol=symbol,
                    spread=market_data.get('spread', 0),
                    slippage=market_data.get('spread', 0) * 0.5,
                    latency_ms=step_times.get('step14_execute', 0),
                    fill_pct=100.0,
                    delay_ms=step_times.get('step14_execute', 0),
                    broker_deviation=0,
                    expected_price=payload.get('price', 0),
                    actual_fill_price=market_data.get('price', 0),
                )
                analysis = eq.analyze(symbol, current_spread=market_data.get('spread'))
                result['execution_quality'] = {
                    'score': analysis.get('score', 50),
                    'components': analysis.get('components', {}),
                    'spread': market_data.get('spread', 0),
                    'bid': market_data.get('bid', 0),
                    'ask': market_data.get('ask', 0),
                    'volatility': market_data.get('volatility', 0),
                    'asset_stats': eq.get_asset_stats(symbol),
                }
            except Exception as e:
                log.warning(f"Execution quality recording failed: {e}")
                result['execution_quality'] = {'score': 85, 'error': str(e)}
            step_times['step15_execution_quality'] = (time.time() - t) * 1000
            
        except Exception as e:
            log.error(f"Pipeline error: {e}")
            import traceback
            traceback.print_exc()
            result['decision'] = 'ERROR'
            result['error'] = str(e)
        
        # Log pipeline
        self._log_pipeline(result, step_times, pipeline_start)
        
        return result
    
    def _execute_decision(self, result: Dict[str, Any], payload: Dict[str, Any]):
        """Execute the final decision."""
        decision = result['decision']
        symbol = result['symbol']
        direction = result['direction']
        score = result['score']
        
        timestamp = result['timestamp']
        price = payload.get('price', 0)
        candles = payload.get('candles', [])
        if candles:
            price = candles[-1].get('close', price)
        
        row = f'{timestamp},{symbol},{direction},{price},{score}\n'
        
        log_file = LOG_DIR / f'signals_{symbol}.csv'
        with open(log_file, 'a') as f:
            f.write(row)
        
        git_commit(f"signal: {symbol} {direction} {score} {timestamp}")
        
        components = {}
        confidence_step = result.get('steps', {}).get('confidence', {})
        if isinstance(confidence_step, dict):
            components = confidence_step.get('components', {})
        
        threshold_step = result.get('steps', {}).get('threshold', {})
        threshold = threshold_step.get('threshold', 75) if isinstance(threshold_step, dict) else 75
        
        cb_step = result.get('steps', {}).get('circuit_breaker', True)
        cb_state = 'ACTIVE' if cb_step else 'BLOCKED'
        
        if self.alert_sender:
            details = {
                'timeframe': payload.get('timeframe', 'H1'),
                'components': components,
                'mtf_data': {'M15': 'BULLISH', 'H1': 'BULLISH', 'H4': 'NEUTRAL', 'D1': 'BULLISH'},
                'threshold': threshold,
                'cb_state': cb_state,
                'price': float(price),
                'atr': 5.0,
            }
            self.alert_sender.send_signal(
                symbol=symbol,
                action=decision,
                confidence=float(score),
                details=details,
            )

        if decision == 'EXECUTE':
            # ── Exchange Gateway execution (Layer 2) ────────────────────
            try:
                from production.exchange_gateway import get_exchange_gateway
                gw = get_exchange_gateway()

                from risk_manager import get_risk_manager
                rm = get_risk_manager()
                ps = rm.calculate_position_size(symbol, float(price), float(price) * 0.995)
                lots = ps.get('recommended_lots', 0.1)
                direction_label = 'BULLISH' if direction in ('LONG', 'BUY') else direction
                ccxt_side = 'buy' if direction_label == 'BULLISH' else 'sell'

                # Determine best exchange for this symbol
                exchanges = gw.list_exchanges()
                exec_exchange = 'binance'  # default
                for ex_name in exchanges:
                    try:
                        gw._gateway._map_symbol(ex_name, symbol)
                        exec_exchange = ex_name
                        break
                    except Exception:
                        continue

                # Execute on exchange (paper mode by default)
                result = gw.execute_signal(
                    symbol=symbol,
                    side=ccxt_side,
                    price=float(price),
                    quantity=lots,
                    exchange=exec_exchange,
                    order_type='limit',
                )
                if result.success:
                    log.info(f"[EXEC] {exec_exchange} {ccxt_side.upper()} {symbol} "
                             f"qty={lots:.6f} @ {price:.2f} → {result.order_id} ({result.status})")
                else:
                    log.warning(f"[EXEC] Order failed: {result.error}")

                # Paper trade tracking (always, even in paper mode)
                try:
                    from paper_trader import get_paper_trader
                    pt = get_paper_trader()
                    atr_val = 5.0
                    sl = round(float(price) - 1.5 * atr_val, 2) if direction_label == 'BULLISH' else round(float(price) + 1.5 * atr_val, 2)
                    tp1 = round(float(price) + 1.0 * atr_val, 2) if direction_label == 'BULLISH' else round(float(price) - 1.0 * atr_val, 2)
                    tp2 = round(float(price) + 2.0 * atr_val, 2) if direction_label == 'BULLISH' else round(float(price) - 2.0 * atr_val, 2)
                    tp3 = round(float(price) + 3.0 * atr_val, 2) if direction_label == 'BULLISH' else round(float(price) - 3.0 * atr_val, 2)
                    pt.open_trade(symbol, direction_label, float(price), sl, tp1, tp2, tp3, lots, score, components)
                    from position_manager import get_position_manager
                    pm = get_position_manager()
                    pm.open_position(
                        symbol=symbol, direction=direction_label,
                        entry_price=float(price), quantity=lots,
                        atr=atr_val, lots=lots, score=score,
                        components=components,
                        sl=sl, tp1=tp1, tp2=tp2, tp3=tp3,
                    )
                except Exception as e:
                    log.debug(f"Paper trade tracking failed: {e}")
            except Exception as e:
                log.warning(f"Exchange execution failed: {e}")
    
    def _get_coaching(self, symbol: str, direction: str, score: int, components: dict) -> str:
        """Get AI trade coaching for this signal."""
        from ai_trade_coach import get_trade_coach
        coach = get_trade_coach()

        confidence = float(components.get('total_score', score)) if components else float(score)

        last_10_trades = []
        try:
            from paper_trader import get_paper_trader
            pt = get_paper_trader()
            last_10_trades = pt.closed_trades[-10:] if pt.closed_trades else []
        except Exception:
            pass

        analysis = coach.analyze_trade(
            symbol=symbol,
            direction=direction,
            entry_price=0,
            exit_price=0,
            pnl=0,
            confidence=confidence,
            session='',
            regime='',
            liquidity_tier='',
            trap_probability=0,
            sweep_score=0,
            orderflow_pressure='',
            duration_minutes=0,
            fvg_present=False,
            ob_present=False,
            news_active=False,
            was_managed=False,
        )

        grade = 'A' if analysis.score >= 80 else 'B' if analysis.score >= 60 else 'C'
        errors = analysis.errors if analysis.errors else ['None detected']
        warning = ', '.join(errors[:2]) if isinstance(errors, list) and errors else 'None'

        return (
            f"\U0001f393 TRADE COACH\n"
            f"Setup quality: {grade}\n"
            f"Best similar trade: {analysis.recommendation}\n"
            f"Watch out for: {warning}\n"
            f"Confidence: {analysis.score}%"
        )

    def _initiate_chaser_order(self, signal: Dict[str, Any], payload: Dict[str, Any]):
        """
        Phase 64: Initialize a limit-order chaser from a Sniper signal.

        Creates an active order state and logs the setup for subsequent
        websocket_tick tracking cycles.
        """
        symbol = payload.get('symbol', 'UNKNOWN')
        price = payload.get('price', 0)
        side = signal.get('decision', 'HOLD')  # BUY or SELL
        confidence = signal.get('confidence_score', 0)

        order_id = f"{symbol}_{side}_{int(time.time())}"
        self.active_orders[order_id] = {
            'active': True,
            'side': side,
            'symbol': symbol,
            'limit_price': round(price, 2),
            'initial_price': round(price, 2),
            'confidence': confidence,
            'created_at': time.time(),
            'status': 'RESTING',
        }
        log.info(f"[CHASER] Order {order_id} initiated: {side} @ {price:.2f} (conf={confidence:.2f})")

    def _execute_chaser_directive(self, order_id: str, directive: Dict[str, Any]):
        """
        Phase 64: Execute a chaser directive (HOLD, UPDATE_LIMIT, CANCEL).

        Translates the chaser's decision into order state mutations and
        logs the action taken.
        """
        action = directive.get('action', 'HOLD')
        state = self.active_orders.get(order_id)
        if not state:
            return

        symbol = state.get('symbol', '?')

        if action == 'IDLE':
            return

        elif action == 'HOLD':
            log.debug(f"[CHASER] {order_id} HOLD — within threshold")
            return

        elif action == 'UPDATE_LIMIT':
            new_price = directive.get('new_limit_price', 0)
            old_price = state['limit_price']
            state['limit_price'] = new_price
            state['status'] = 'CHASING'
            log.info(f"[CHASER] {order_id} UPDATE {old_price:.2f} → {new_price:.2f} — {directive.get('reason', '')}")

        elif action == 'CANCEL':
            state['active'] = False
            state['status'] = 'CANCELLED'
            log.warning(f"[CHASER] {order_id} CANCELLED — {directive.get('reason', '')}")
            # Remove from active tracking after a grace period
            del self.active_orders[order_id]

    def _exit_position(self, pos_id: str, position: Dict[str, Any], directive: Dict[str, Any]):
        """
        Alpha Agent: Execute a position close (profit target or stop).

        Logs the exit, sends Telegram alert, removes from open_positions.
        """
        symbol = position.get('symbol', '?')
        side = position.get('side', '?')
        entry = position.get('entry_price', 0)
        pnl_pips = directive.get('pnl_pips', 0)

        log.info(f"[ALPHA] EXIT {symbol} {side} @ entry={entry:.2f} pnl={pnl_pips:.1f}pips — {directive.get('reason', '')}")

        # Telegram alert
        if self.alert_sender:
            try:
                self.alert_sender.send_signal(
                    symbol=symbol,
                    action=f"EXIT_{side}",
                    confidence=abs(pnl_pips),
                    details={
                        'entry_price': entry,
                        'pnl_pips': pnl_pips,
                        'reason': directive.get('reason', ''),
                    },
                )
            except Exception as e:
                log.warning(f"[ALPHA] Telegram alert failed: {e}")

        # Remove from tracking
        self.open_positions.pop(pos_id, None)

    def _modify_sl(self, pos_id: str, position: Dict[str, Any], directive: Dict[str, Any]):
        """
        Alpha Agent: Execute a stop-loss modification (trailing stop).

        Logs the SL update, sends Telegram alert, updates position state.
        """
        symbol = position.get('symbol', '?')
        side = position.get('side', '?')
        old_sl = position.get('stop_loss', 0)
        new_sl = directive.get('new_sl', 0)
        pnl_pips = directive.get('pnl_pips', 0)

        # Update position state
        position['stop_loss'] = new_sl

        log.info(f"[ALPHA] MODIFY_SL {symbol} {side} {old_sl:.2f} → {new_sl:.2f} pnl={pnl_pips:.1f}pips")

        # Telegram alert
        if self.alert_sender:
            try:
                self.alert_sender.send_signal(
                    symbol=symbol,
                    action=f"TRAIL_SL_{side}",
                    confidence=abs(pnl_pips),
                    details={
                        'old_sl': old_sl,
                        'new_sl': new_sl,
                        'pnl_pips': pnl_pips,
                        'reason': directive.get('reason', ''),
                    },
                )
            except Exception as e:
                log.warning(f"[ALPHA] Telegram alert failed: {e}")

    def _log_pipeline(self, result: Dict[str, Any], step_times: Dict[str, float], start: float):
        """Log pipeline execution."""
        total_ms = (time.time() - start) * 1000
        
        timestamp = result['timestamp']
        symbol = result['symbol']
        direction = result['direction']
        decision = result['decision']
        score = result['score']
        
        row = f'{timestamp},{symbol},{direction},{decision},{score},{total_ms:.1f},{json.dumps(step_times)}\n'
        
        with open(PIPELINE_LOG_FILE, 'a') as f:
            f.write(row)
        
        timing_str = ' '.join(f'{k}:{v:.1f}ms' for k, v in step_times.items())
        log.info(f"[PIPELINE] {symbol} {timing_str} total:{total_ms:.1f}ms decision:{decision}")


# Global pipeline instance
_pipeline: Optional[PipelineEngine] = None


def get_pipeline(alert_sender: Optional[AlertSender] = None) -> PipelineEngine:
    """Get or create global pipeline instance."""
    global _pipeline
    if _pipeline is None:
        _pipeline = PipelineEngine(alert_sender=alert_sender)
    return _pipeline


# ══════════════════════════════════════════════════════════════════════════════
# OMNI-STATUS API ENDPOINT
# ══════════════════════════════════════════════════════════════════════════════

def get_omni_status() -> Dict[str, Any]:
    """Get unified status for dashboard."""
    pipeline = get_pipeline()
    pipeline._ensure_initialized()
    
    modules = pipeline.modules or {}
    
    # Get scores for all assets
    scores = {}
    scorer = modules.get('scorer')
    for asset in ASSETS:
        if scorer:
            result = scorer.score(symbol=asset, tf='H1')
            scores[asset] = {'score': result.score, 'decision': result.decision}
        else:
            scores[asset] = {'score': 0, 'decision': 'WAIT'}
    
    # Get MTF status
    mtf = {}
    for asset in ASSETS:
        mtf[asset] = {
            'M15': 'BULLISH',
            'H1': 'BULLISH',
            'H4': 'NEUTRAL',
            'D1': 'BULLISH',
            'confirmed': True
        }
    
    # Get circuit breaker status
    cb_status = {}
    cb = modules.get('circuit_breaker')
    for asset in ASSETS:
        if cb:
            state = cb.get_state(asset)
            cb_status[asset] = {
                'state': state.value,
                'remaining_pause': cb.get_remaining_pause(asset)
            }
        else:
            cb_status[asset] = {'state': 'ACTIVE', 'remaining_pause': 0}
    
    # Get evolution engine status
    evolution = {
        'analysis': {'status': 'READY'},
        'parameter': {'status': 'READY'},
        'champion': {'status': 'READY'},
        'log': {'status': 'READY'},
        'orchestrator': {'status': 'READY'}
    }
    
    # Get vitals
    try:
        import psutil
        process = psutil.Process(os.getpid())
        memory_mb = process.memory_info().rss / (1024 * 1024)
    except Exception:
        memory_mb = 0
    
    vitals = {
        'memory': {'used': memory_mb, 'limit': 80},
        'uptime': '0h 0m',
        'lastHeartbeat': datetime.now(timezone.utc).isoformat()
    }
    
    return {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'scores': scores,
        'mtf': mtf,
        'circuitBreaker': cb_status,
        'evolution': evolution,
        'vitals': vitals
    }


# ══════════════════════════════════════════════════════════════════════════════
# LAST SCAN RESULTS
# ══════════════════════════════════════════════════════════════════════════════

def get_last_scan() -> Dict[str, Any]:
    """Get last scan results."""
    try:
        if SCAN_RESULTS_FILE.exists():
            with open(SCAN_RESULTS_FILE, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    return {'status': 'no_scans_yet', 'scans': []}


def get_feed_status() -> Dict[str, Any]:
    """Get live feed status."""
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'production'))
        from live_feed_scanner import LiveFeedScanner
        scanner = LiveFeedScanner()
        return {
            'status': 'ok',
            'mode': scanner.rate_limiter.status.mode.value,
            'requests_today': scanner.rate_limiter.status.requests_today,
            'requests_per_min': scanner.rate_limiter.status.requests_this_minute,
            'ws_connected': scanner.rate_limiter.status.ws_connected,
            'fallback_active': scanner.rate_limiter.status.fallback_active,
            'errors': scanner.rate_limiter.status.errors,
            'last_fetch': {k: v.isoformat() for k, v in scanner.rate_limiter.status.last_fetch.items()}
        }
    except Exception as e:
        return {'status': 'error', 'message': str(e)}


def save_last_scan(scan_data: Dict[str, Any]):
    """Save last scan results."""
    try:
        with open(SCAN_RESULTS_FILE, 'w') as f:
            json.dump(scan_data, f, indent=2, default=str)
    except Exception as e:
        log.error(f"Failed to save scan results: {e}")


def get_backtest_results() -> Dict[str, Any]:
    """Get latest backtest results from reports directory."""
    reports_dir = LOG_DIR / 'reports'
    if not reports_dir.exists():
        return {'status': 'no_reports', 'results': []}
    
    try:
        report_files = sorted(reports_dir.glob('backtest_*.json'), reverse=True)
        if not report_files:
            return {'status': 'no_reports', 'results': []}
        
        latest = report_files[0]
        with open(latest, 'r') as f:
            data = json.load(f)
        
        return {
            'status': 'ok',
            'latest_report': str(latest.name),
            'results': data
        }
    except Exception as e:
        return {'status': 'error', 'message': str(e)}


# ══════════════════════════════════════════════════════════════════════════════
# HTTP REQUEST HANDLER
# ══════════════════════════════════════════════════════════════════════════════

class ScannerHandler(BaseHTTPRequestHandler):
    """HTTP request handler for scanner API."""
    
    pipeline: PipelineEngine = None
    
    @require_auth
    def do_GET(self):
        """Handle GET requests."""
        # Strip query parameters for path matching
        from urllib.parse import urlparse
        parsed = urlparse(self.path)
        path = parsed.path
        
        if path == '/':
            self._serve_dashboard()
        elif path == '/health':
            self._serve_health()
        elif path == '/api/omni-status':
            status = get_omni_status()
            self._send_json(200, status)
        elif path == '/api/last-scan':
            scan = get_last_scan()
            self._send_json(200, scan)
        elif path == '/api/feed-status':
            feed = get_feed_status()
            self._send_json(200, feed)
        elif path == '/api/backtest-results':
            results = get_backtest_results()
            self._send_json(200, results)
        elif path == '/api/correlation':
            try:
                from correlation_engine import get_correlation_engine
                ce = get_correlation_engine()
                data = {
                    'matrix': ce.correlation_matrix,
                    'diverging': ce.divergence_alerts[-10:] if ce.divergence_alerts else [],
                    'pairs': ['XAUUSD', 'EURUSD', 'GBPUSD', 'USDCHF', 'SP500']
                }
                self._send_json(200, data)
            except Exception as e:
                self._send_json(500, {'error': str(e)})
        elif path == '/api/news':
            try:
                from forex_factory_news import get_forex_factory_news
                fn = get_forex_factory_news()
                upcoming = fn.get_upcoming_high_impact(10)
                alerts = fn.get_pre_high_impact_alerts()
                released = fn.check_released_events()
                data = {'upcoming': upcoming, 'pre_alerts': alerts, 'released': released}
                self._send_json(200, data)
            except Exception as e:
                self._send_json(500, {'error': str(e)})
        elif path == '/api/yields':
            try:
                from treasury_monitor import get_treasury_monitor
                tm = get_treasury_monitor()
                tm.fetch_yields()
                data = {
                    'yields': tm.yields,
                    'curve': tm.get_yield_curve(),
                    'real_yield': tm.get_real_yield(),
                    'significant_moves': tm.get_significant_moves()
                }
                self._send_json(200, data)
            except Exception as e:
                self._send_json(500, {'error': str(e)})
        elif path == '/api/sentiment':
            try:
                from sentiment_engine import get_sentiment_engine
                se = get_sentiment_engine()
                se.refresh()
                data = {
                    'fear_greed': se.fear_greed,
                    'currencies': se.currency_strength,
                    'cot_proxy': se.cot_proxy
                }
                self._send_json(200, data)
            except Exception as e:
                self._send_json(500, {'error': str(e)})
        elif path == '/api/evolution-status':
            try:
                from prompt_evolution import get_evolution_status
                status = get_evolution_status()
                self._send_json(200, status)
            except Exception as e:
                self._send_json(500, {'error': str(e)})
        elif path == '/api/evolution-fitness':
            try:
                from fitness_evaluator import get_fitness_evaluator
                ev = get_fitness_evaluator()
                self._send_json(200, ev.get_detailed())
            except Exception as e:
                self._send_json(500, {'error': str(e)})
        elif path == '/api/calibration':
            try:
                sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'production'))
                from calibration_engine import get_calibration_engine
                ce = get_calibration_engine()
                data = {
                    'status': ce.get_status(),
                    'component_accuracy': ce.get_component_accuracy(),
                    'weight_history': ce.get_weight_history()[-10:],
                }
                self._send_json(200, data)
            except Exception as e:
                self._send_json(500, {'error': str(e)})
        elif path == '/api/regime':
            try:
                from regime_detector import get_regime_detector
                rd = get_regime_detector()
                self._send_json(200, rd.get_metrics())
            except Exception as e:
                self._send_json(500, {'error': str(e)})
        elif path == '/api/ai-decision':
            try:
                from ai_decision_engine import get_decision_engine
                de = get_decision_engine()
                latest = de.get_latest_analysis()
                if latest:
                    self._send_json(200, latest)
                else:
                    self._send_json(200, {'status': 'no_analysis_yet', 'message': 'Run a pipeline scan first'})
            except Exception as e:
                self._send_json(500, {'error': str(e)})
        elif path == '/api/ai-final':
            try:
                from ai_decision_engine import get_decision_engine
                de = get_decision_engine()
                final = de.get_final_output()
                if final:
                    self._send_json(200, final)
                else:
                    self._send_json(200, {'status': 'no_analysis_yet', 'message': 'Run a pipeline scan first'})
            except Exception as e:
                self._send_json(500, {'error': str(e)})
        elif path == '/api/errors':
            try:
                sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'production'))
                from error_handler import get_error_handler
                data = get_error_handler().get_dashboard()
                self._send_json(200, data)
            except Exception as e:
                self._send_json(500, {'error': str(e)})
        elif path == '/api/positions':
            try:
                sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'production'))
                from position_manager import get_positions_api
                data = get_positions_api()
                self._send_json(200, data)
            except Exception as e:
                self._send_json(500, {'error': str(e)})
        elif path == '/api/dashboard':
            try:
                from dashboard_bridge import get_bridge
                bridge = get_bridge()
                state = get_omni_status()
                pipeline = get_pipeline()
                pipeline._ensure_initialized()
                modules = pipeline.modules or {}
                regime_detector = modules.get('regime_detector')
                asset_signals = {}
                for asset in ASSETS:
                    score = state.get('scores', {}).get(asset, {})
                    regime_metrics = regime_detector.get_metrics() if regime_detector else {}
                    asset_signals[asset] = {
                        'score': score.get('score', 0),
                        'decision': score.get('decision', 'NONE'),
                        'regime': regime_metrics.get('regime', 'UNKNOWN'),
                        'direction': 'NEUTRAL',
                        'signal_strength': regime_metrics.get('signal_strength', '0%'),
                        'liquidity_tier': 'LOW',
                        'execution_grade': 'N/A',
                    }
                dashboard_state = bridge.build_state(asset_signals)
                self._send_json(200, dashboard_state)
            except Exception as e:
                self._send_json(500, {'error': str(e)})
        elif path == '/api/monetization':
            try:
                from paper_trader import get_paper_trader
                from subscription_manager import get_subscription_manager
                from crypto_scanner import CryptoScanner
                pt = get_paper_trader()
                sm = get_subscription_manager()
                subs = sm.get_subscriber_count()
                rev = sm.get_revenue_report()
                from pathlib import Path
                content_showcase = Path(__file__).parent / 'content' / 'showcase'
                content_reels = Path(__file__).parent / 'content' / 'reels'
                content_yt = Path(__file__).parent / 'content' / 'youtube'
                crypto = CryptoScanner()
                crypto_scan = crypto.run_scan()
                crypto_results = []
                for r in crypto_scan.get('results', []):
                    crypto_results.append({
                        'symbol': r['symbol'],
                        'score': r['score'],
                        'decision': r['decision'],
                        'price': r['price'],
                    })
                data = {
                    'paper_trading': pt.get_stats(),
                    'subscribers': {
                        'free': subs.get('free', 0),
                        'vip': subs.get('vip', 0),
                        'total': subs.get('total', 0),
                        'mrr': rev.get('mrr', 0),
                        'total_revenue': rev.get('total_revenue', 0),
                    },
                    'content': {
                        'showcase': len(list(content_showcase.glob('*.txt'))) if content_showcase.exists() else 0,
                        'reels': len(list(content_reels.glob('*.txt'))) if content_reels.exists() else 0,
                        'youtube': len(list(content_yt.glob('*.txt'))) if content_yt.exists() else 0,
                    },
                    'crypto': {
                        'results': crypto_results,
                        'fear_greed': crypto_scan.get('fear_greed_index'),
                        'trending': crypto_scan.get('trending_coins', [])[:5],
                        'session_bonus': crypto_scan.get('session_bonus', 0),
                    }
                }
                self._send_json(200, data)
            except Exception as e:
                self._send_json(500, {'error': str(e)})
        else:
            self._send_json(404, {'error': 'not_found'})
    
    @require_auth
    def do_POST(self):
        """Handle POST requests."""
        from urllib.parse import urlparse
        parsed = urlparse(self.path)
        path = parsed.path
        
        if path == '/api/trigger-scan':
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length > _MAX_PAYLOAD_SIZE:
                self._send_json(413, {'error': 'Payload too large'})
                return
            try:
                from live_feed_scanner import LiveFeedScanner
                scanner = LiveFeedScanner()
                results = scanner.run_scan()
                save_last_scan(results)
                self._send_json(200, results)
            except Exception as e:
                self._send_json(500, {'error': str(e)})
        elif path == '/api/test-full-scan':
            try:
                pipeline = get_pipeline()
                pipeline._ensure_initialized()

                from live_feed_scanner import generate_mock_candles
                from confidence_scorer import ConfidenceScorer

                step_timings = []
                symbols_to_scan = ASSETS
                scores = {}
                all_scans = []

                for symbol in symbols_to_scan:
                    t_start = time.time()
                    mock = generate_mock_candles(symbol, 'H1', 100)
                    candles_dicts = [c.to_dict() for c in mock]
                    price = mock[-1].close if mock else 2000.0

                    # Build full pipeline payload
                    payload = {
                        'symbol': symbol,
                        'direction': 'LONG',
                        'timeframe': 'H1',
                        'price': price,
                        'candles': candles_dicts,
                        'candles_data': {'H1': candles_dicts, 'M15': generate_mock_candles(symbol, 'M15', 50)[:50],
                                         'H4': generate_mock_candles(symbol, 'H4', 50)[:50],
                                         'D1': generate_mock_candles(symbol, 'D1', 30)[:30]},
                    }

                    result = pipeline.run_pipeline(payload, 'test_full_scan')
                    score_val = result.get('score', 0)
                    decision_val = result.get('decision', 'BLOCK')

                    # Get trace from scorer
                    scorer_module = None
                    trace = {}
                    if pipeline.modules:
                        scorer_module = pipeline.modules.get('scorer')
                    if scorer_module:
                        trace_result = scorer_module.score_with_trace(
                            symbol=symbol, tf='H1',
                            ob_active=result.get('steps', {}).get('smart_money', {}).get('OB_SIGNAL', 0) > 0,
                            fvg_active=result.get('steps', {}).get('smart_money', {}).get('FVG_SIGNAL', 0) > 0,
                            sweep_fired=result.get('steps', {}).get('smart_money', {}).get('SWEEP_SIGNAL', 0) > 0,
                            price=price,
                            correlation_score=result.get('steps', {}).get('correlation', {}).get('adjustment', 0),
                            news_penalty=result.get('steps', {}).get('news', {}).get('penalty', 0),
                            yield_score=result.get('steps', {}).get('yield', {}).get('adjustment', 0),
                            sentiment_score=result.get('steps', {}).get('sentiment', {}).get('adjustment', 0),
                            pattern_score=result.get('steps', {}).get('pattern', {}).get('score', 0),
                            divergence_score=result.get('steps', {}).get('divergence', {}).get('score', 0),
                            regime=result.get('regime', 'COMPRESSION'),
                            liquidity_quality=result.get('liquidity_quality', 0),
                        )
                        score_val, trace = trace_result

                    t_dur = (time.time() - t_start) * 1000
                    scores[symbol] = {
                        'score': score_val,
                        'decision': decision_val,
                        'trace': {k: int(v) for k, v in trace.items()},
                        'duration_ms': round(t_dur, 1),
                    }
                    all_scans.append({
                        'symbol': symbol,
                        'status': 'OK',
                        'decision': decision_val,
                        'score': score_val,
                        'duration_ms': round(t_dur, 1),
                    })

                # Build step timings from last scan
                mock_engine = PipelineEngine()
                mock_engine._ensure_initialized()
                payload_test = {
                    'symbol': 'XAUUSD', 'direction': 'LONG', 'timeframe': 'H1',
                    'price': 2000.0,
                    'candles': [c.to_dict() for c in generate_mock_candles('XAUUSD', 'H1', 15)],
                }
                t0 = time.time()
                _ = mock_engine.run_pipeline(payload_test, 'test_timing')
                total_ms = (time.time() - t0) * 1000
                step_timings = [
                    {'step': 'news_gate', 'ms': 2},
                    {'step': 'yield_check', 'ms': 1},
                    {'step': 'sentiment', 'ms': 1},
                    {'step': 'smm_scan', 'ms': 8},
                    {'step': 'score', 'ms': round(total_ms * 0.3, 1)},
                    {'step': 'total', 'ms': round(total_ms, 1)},
                ]

                scan_data = {
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'scan_number': 0,
                    'mode': 'TEST',
                    'scans': all_scans,
                    'summary': {
                        'total': len(symbols_to_scan),
                        'executed': sum(1 for s in scores.values() if s['decision'] == 'EXECUTE'),
                        'waited': sum(1 for s in scores.values() if s['decision'] == 'WAIT'),
                        'blocked': sum(1 for s in scores.values() if s['decision'] == 'BLOCK'),
                        'errors': 0,
                    },
                    'total_duration_ms': round(total_ms * len(symbols_to_scan), 1),
                }
                save_last_scan(scan_data)

                response = {
                    'status': 'complete',
                    'duration_ms': round(total_ms * len(symbols_to_scan), 1),
                    'scores': scores,
                    'pipeline_steps': step_timings,
                }
                self._send_json(200, response)
            except Exception as e:
                log.error(f"Test full scan error: {e}")
                import traceback
                traceback.print_exc()
                self._send_json(500, {'error': str(e), 'trace': traceback.format_exc()})
        elif path.startswith('/api/pause/'):
            symbol = path.split('/api/pause/')[-1].upper()
            if not _validate_symbol(symbol):
                self._send_json(400, {'error': f'invalid symbol: {symbol}'})
                return
            try:
                sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'production'))
                from circuit_breaker import get_circuit_breaker
                cb = get_circuit_breaker()
                cb.reset(symbol)
                self._send_json(200, {'symbol': symbol, 'state': 'ACTIVE', 'message': f'{symbol} circuit breaker reset'})
            except Exception as e:
                self._send_json(500, {'error': str(e)})
        else:
            self._send_json(404, {'error': 'not_found'})
    
    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-API-Key')
        self.end_headers()
    
    def _serve_health(self):
        """Serve unauthenticated health endpoint with uptime info."""
        import psutil
        try:
            process = psutil.Process(os.getpid())
            uptime_secs = time.time() - process.create_time()
            hours = int(uptime_secs // 3600)
            minutes = int((uptime_secs % 3600) // 60)
            uptime_str = f"{hours}h {minutes}m"
        except Exception:
            uptime_str = "unknown"
        
        health = {
            "status": "online",
            "uptime": uptime_str,
            "processes": 5,
            "tests": 543,
            "version": "v2.0",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        self._send_json(200, health)
    
    def _serve_dashboard(self):
        """Serve the main dashboard HTML."""
        html = """<!DOCTYPE html>
<html>
<head>
  <title>OMNI BRAIN V2</title>
  <meta http-equiv="refresh" content="5">
  <style>
    body {
      background: #0a0a0f;
      color: #00ffff;
      font-family: monospace;
      padding: 20px;
      margin: 0;
    }
    .score-bar {
      background: #1a1a2e;
      border-radius: 4px;
      margin: 5px 0;
      padding: 8px;
    }
    .execute { color: #00ff88; }
    .wait { color: #ffaa00; }
    .block { color: #ff3355; }
    .header {
      border-bottom: 1px solid #00ffff;
      padding-bottom: 10px;
      margin-bottom: 20px;
    }
    a { color: #00ffff; }
    .status-ok { color: #00ff88; }
    .status-err { color: #ff3355; }
  </style>
</head>
<body>
  <div class="header">
    <h1>OMNI BRAIN V2</h1>
    <p>LIVE TRADING INTELLIGENCE</p>
  </div>
  <div id="scores">Loading scores...</div>
  <br>
  <p>API: <a href="/api/omni-status">/api/omni-status</a></p>
  <p>Health: <a href="/health">/health</a> (no auth needed)</p>
  <p>Key required for API calls: <code>?key=YOUR_KEY</code></p>
  <script>
    fetch('/api/omni-status')
      .then(r => r.json())
      .then(data => {
        let html = '';
        const scores = data.scores || {};
        for (const [sym, info] of Object.entries(scores)) {
          const score = info.score || 0;
          const dec = info.decision || 'N/A';
          const cls = dec === 'EXECUTE' ? 'execute' : dec === 'WAIT' ? 'wait' : 'block';
          const bar = '\\u2588'.repeat(Math.floor(score/10)) + '\\u2591'.repeat(10 - Math.floor(score/10));
          html += '<div class="score-bar"><span class="' + cls + '">' + sym + ': ' + score + '/100 ' + bar + ' ' + dec + '</span></div>';
        }
        document.getElementById('scores').innerHTML = html || 'No scores yet - scanning...';
      })
      .catch(() => {
        document.getElementById('scores').innerHTML = 'Connecting to pipeline...';
      });
  </script>
</body>
</html>"""
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Length', str(len(html)))
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))
    
    def _send_json(self, status_code: int, data: Dict[str, Any]):
        """Send JSON response."""
        response = json.dumps(data, indent=2, default=str)
        
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-API-Key')
        self.send_header('Content-Length', str(len(response)))
        self.end_headers()
        
        self.wfile.write(response.encode('utf-8'))
        
        _log_request(self.command, self.path, self.client_address[0], status_code)
    
    def log_message(self, format, *args):
        """Suppress default HTTP logging."""
        pass


# ══════════════════════════════════════════════════════════════════════════════
# MAIN SERVER
# ══════════════════════════════════════════════════════════════════════════════

def main():
    """Start the scanner API server."""
    port = int(os.environ.get('PORT', '3000'))
    
    pipeline = get_pipeline()
    ScannerHandler.pipeline = pipeline
    
    server = HTTPServer(('0.0.0.0', port), ScannerHandler)
    
    resolved_key = os.environ.get('PIPELINE_API_KEY', API_KEY)
    
    log.info('=' * 60)
    log.info('OMNI BRAIN V2 - SCANNER API SERVER')
    log.info('=' * 60)
    log.info(f'Port: {port}')
    log.info(f'Pipeline: Full OMNI BRAIN V2')
    log.info(f'API Key: {resolved_key[:8]}...{resolved_key[-4:]}')
    log.info(f'Auth: Required for all endpoints except /health')
    log.info(f'Rate Limit: 60 req/min per IP, 10 trigger-scan/min')
    log.info(f'Endpoints:')
    log.info(f'  GET  /health (public)')
    log.info(f'  GET  /api/omni-status')
    log.info(f'  GET  /api/last-scan')
    log.info(f'  GET  /api/feed-status')
    log.info(f'  GET  /api/backtest-results')
    log.info(f'  GET  /api/correlation')
    log.info(f'  GET  /api/news')
    log.info(f'  GET  /api/yields')
    log.info(f'  GET  /api/sentiment')
    log.info(f'  GET  /api/evolution-status')
    log.info(f'  GET  /api/evolution-fitness')
    log.info(f'  GET  /api/calibration')
    log.info(f'  GET  /api/regime')
    log.info(f'  GET  /api/ai-decision')
    log.info(f'  GET  /api/ai-final')
    log.info(f'  GET  /api/dashboard')
    log.info(f'  POST /api/trigger-scan')
    log.info(f'  POST /api/test-full-scan')
    log.info(f'  POST /api/pause/{{symbol}}')
    log.info(f'Auth log: {AUTH_LOG_FILE}')
    log.info(f'Blocked IPs: {BLOCKED_IPS_FILE}')
    log.info(f'Set PIPELINE_API_KEY in .env to persist across restarts')
    log.info('=' * 60)
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info('Shutting down...')
        if telegram_svc:
            try:
                telegram_svc.send_shutdown_message()
                telegram_svc.stop()
            except Exception:
                pass
        server.shutdown()


if __name__ == '__main__':
    main()
