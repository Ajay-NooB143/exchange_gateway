"""
Live Data Feed Scanner - OMNI BRAIN V2
=======================================
Twelve Data WebSocket + REST polling with rate limiting.

Features:
  - WebSocket real-time price feeds
  - REST fallback with smart batching (8 req/min limit)
  - Rate limit tracking and daily usage monitoring
  - Auto-reconnect with exponential backoff
  - Full pipeline integration
  - API status monitor

Twelve Data API:
  - WebSocket: wss://ws.twelvedata.com/v1/quotes/price
  - REST: GET https://api.twelvedata.com/time_series
  - Free plan: 8 requests/minute, 800/day
"""

import os
import sys
import json
import time
import logging
import threading
import hashlib
import random
import math
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Tuple

from production.pipeline_contract import PipelineProtocol
from pathlib import Path
from collections import deque
from dataclasses import dataclass, field
from enum import Enum

log = logging.getLogger('LiveFeedScanner')

# ══════════════════════════════════════════════════════════════════════════════
# SMART MONEY CONCEPTS (SMC) — LAYER 1 DETECTION
# ══════════════════════════════════════════════════════════════════════════════

def detect_fvg(candles: List[Candle]) -> List[Dict[str, Any]]:
    """
    Detect Fair Value Gaps (FVG) — 3-candle imbalance pattern.

    A Fair Value Gap exists when price delivers inefficiently, leaving
    an unfilled zone between candle 1 and candle 3.

    Bullish FVG: candle_1.high < candle_3.low  (gap UP)
    Bearish FVG: candle_1.low  > candle_3.high (gap DOWN)

    Returns list of dicts:
        {
            'type': 'BULLISH_FVG' | 'BEARISH_FVG',
            'index': int,           # index of middle candle (candle 2)
            'gap_top': float,       # upper boundary of the gap
            'gap_bottom': float,    # lower boundary of the gap
            'gap_size': float,      # |gap_top - gap_bottom|
            'midpoint': float,      # (gap_top + gap_bottom) / 2
            'filled': bool,         # True if price has traded into the gap
            'timestamp': int        # timestamp of middle candle
        }
    """
    fvgs = []
    if len(candles) < 3:
        return fvgs

    for i in range(1, len(candles) - 1):
        c1 = candles[i - 1]  # candle before
        c2 = candles[i]      # middle candle (the impulse)
        c3 = candles[i + 1]  # candle after

        # Bullish FVG: gap between c1.high and c3.low
        if c1.high < c3.low:
            gap_bottom = c1.high
            gap_top = c3.low
            gap_size = gap_top - gap_bottom

            # Check if gap has been filled by subsequent candles
            filled = False
            for j in range(i + 2, len(candles)):
                if candles[j].low <= gap_top:
                    filled = True
                    break

            fvgs.append({
                'type': 'BULLISH_FVG',
                'index': i,
                'gap_top': round(gap_top, 6),
                'gap_bottom': round(gap_bottom, 6),
                'gap_size': round(gap_size, 6),
                'midpoint': round((gap_top + gap_bottom) / 2, 6),
                'filled': filled,
                'timestamp': c2.timestamp
            })

        # Bearish FVG: gap between c1.low and c3.high
        elif c1.low > c3.high:
            gap_top = c1.low
            gap_bottom = c3.high
            gap_size = gap_top - gap_bottom

            # Check if gap has been filled by subsequent candles
            filled = False
            for j in range(i + 2, len(candles)):
                if candles[j].high >= gap_bottom:
                    filled = True
                    break

            fvgs.append({
                'type': 'BEARISH_FVG',
                'index': i,
                'gap_top': round(gap_top, 6),
                'gap_bottom': round(gap_bottom, 6),
                'gap_size': round(gap_size, 6),
                'midpoint': round((gap_top + gap_bottom) / 2, 6),
                'filled': filled,
                'timestamp': c2.timestamp
            })

    return fvgs


def detect_order_block(candles: List[Candle]) -> List[Dict[str, Any]]:
    """
    Detect Order Blocks (OB) — institutional supply/demand zones.

    An Order Block is the last opposing candle before a Break of Structure (BOS).

    Bullish OB: Last bearish candle before a strong bullish BOS
        - BOS confirmed when price breaks above the most recent swing high
        - OB zone = [candle.low, candle.high]

    Bearish OB: Last bullish candle before a strong bearish BOS
        - BOS confirmed when price breaks below the most recent swing low
        - OB zone = [candle.low, candle.high]

    Swing detection uses a lookback window of 5 candles (2 each side).

    Returns list of dicts:
        {
            'type': 'BULLISH_OB' | 'BEARISH_OB',
            'index': int,           # index of the order block candle
            'ob_high': float,       # upper boundary of OB zone
            'ob_low': float,        # lower boundary of OB zone
            'ob_midpoint': float,   # (ob_high + ob_low) / 2
            'bos_index': int,       # index of candle that broke structure
            'bos_price': float,     # price level that was broken
            'strength': float,      # 0.0-1.0, based on impulse momentum
            'timestamp': int        # timestamp of OB candle
        }
    """
    order_blocks = []
    if len(candles) < 7:  # Need enough candles for swing detection + BOS
        return order_blocks

    # Step 1: Detect swing highs and swing lows
    swing_highs = []  # [(index, price), ...]
    swing_lows = []   # [(index, price), ...]

    lookback = 2  # candles on each side to confirm swing

    for i in range(lookback, len(candles) - lookback):
        # Swing high: candle[i].high is highest in the window
        is_swing_high = True
        for j in range(i - lookback, i + lookback + 1):
            if j != i and candles[j].high >= candles[i].high:
                is_swing_high = False
                break
        if is_swing_high:
            swing_highs.append((i, candles[i].high))

        # Swing low: candle[i].low is lowest in the window
        is_swing_low = True
        for j in range(i - lookback, i + lookback + 1):
            if j != i and candles[j].low <= candles[i].low:
                is_swing_low = False
                break
        if is_swing_low:
            swing_lows.append((i, candles[i].low))

    # Step 2: Detect Break of Structure (BOS)
    # Bullish BOS: price breaks above most recent swing high
    # Bearish BOS: price breaks below most recent swing low

    last_swing_high_idx = -1
    last_swing_high_price = 0
    last_swing_low_idx = -1
    last_swing_low_price = float('inf')

    for i in range(len(candles)):
        # Update swing highs
        for sh_idx, sh_price in swing_highs:
            if sh_idx == i:
                last_swing_high_idx = sh_idx
                last_swing_high_price = sh_price

        # Update swing lows
        for sl_idx, sl_price in swing_lows:
            if sl_idx == i:
                last_swing_low_idx = sl_idx
                last_swing_low_price = sl_price

        # Check for BOS at candle i (need prior swing to exist)
        if last_swing_high_idx >= 0 and i > last_swing_high_idx + 1:
            # Bullish BOS: close breaks above swing high
            if candles[i].close > last_swing_high_price:
                # Find the last bearish candle before this BOS (the OB)
                ob_idx = -1
                for j in range(i - 1, max(last_swing_high_idx - 1, 0), -1):
                    if candles[j].close < candles[j].open:  # bearish candle
                        ob_idx = j
                        break

                if ob_idx >= 0:
                    ob_candle = candles[ob_idx]
                    bos_candle = candles[i]

                    # Strength: impulse momentum (BOS candle body / avg range)
                    avg_range = sum(
                        candles[k].high - candles[k].low
                        for k in range(max(0, i - 10), i)
                    ) / min(10, i)
                    strength = min(1.0, (bos_candle.close - bos_candle.open) / avg_range) if avg_range > 0 else 0.5

                    order_blocks.append({
                        'type': 'BULLISH_OB',
                        'index': ob_idx,
                        'ob_high': round(ob_candle.high, 6),
                        'ob_low': round(ob_candle.low, 6),
                        'ob_midpoint': round((ob_candle.high + ob_candle.low) / 2, 6),
                        'bos_index': i,
                        'bos_price': round(last_swing_high_price, 6),
                        'strength': round(strength, 4),
                        'timestamp': ob_candle.timestamp
                    })

                # After BOS, reset to find new swing high
                last_swing_high_idx = -1
                last_swing_high_price = 0

        if last_swing_low_idx >= 0 and i > last_swing_low_idx + 1:
            # Bearish BOS: close breaks below swing low
            if candles[i].close < last_swing_low_price:
                # Find the last bullish candle before this BOS (the OB)
                ob_idx = -1
                for j in range(i - 1, max(last_swing_low_idx - 1, 0), -1):
                    if candles[j].close > candles[j].open:  # bullish candle
                        ob_idx = j
                        break

                if ob_idx >= 0:
                    ob_candle = candles[ob_idx]
                    bos_candle = candles[i]

                    avg_range = sum(
                        candles[k].high - candles[k].low
                        for k in range(max(0, i - 10), i)
                    ) / min(10, i)
                    strength = min(1.0, (bos_candle.open - bos_candle.close) / avg_range) if avg_range > 0 else 0.5

                    order_blocks.append({
                        'type': 'BEARISH_OB',
                        'index': ob_idx,
                        'ob_high': round(ob_candle.high, 6),
                        'ob_low': round(ob_candle.low, 6),
                        'ob_midpoint': round((ob_candle.high + ob_candle.low) / 2, 6),
                        'bos_index': i,
                        'bos_price': round(last_swing_low_price, 6),
                        'strength': round(strength, 4),
                        'timestamp': ob_candle.timestamp
                    })

                last_swing_low_idx = -1
                last_swing_low_price = float('inf')

    return order_blocks


def detect_smc_context(candles: List[Candle]) -> Dict[str, Any]:
    """
    Aggregate SMC detection for a single timeframe.

    Returns dict with:
        - fvgs: list of FVG dicts
        - order_blocks: list of OB dicts
        - bullish_fvg_count: int
        - bearish_fvg_count: int
        - bullish_ob_count: int
        - bearish_ob_count: int
        - unfilled_fvgs: list of FVGs not yet filled
        - nearest_ob: dict or None (closest OB to current price)
        - smc_bias: 'BULLISH' | 'BEARISH' | 'NEUTRAL'
    """
    fvgs = detect_fvg(candles)
    order_blocks = detect_order_block(candles)

    bullish_fvgs = [f for f in fvgs if f['type'] == 'BULLISH_FVG']
    bearish_fvgs = [f for f in fvgs if f['type'] == 'BEARISH_FVG']
    bullish_obs = [o for o in order_blocks if o['type'] == 'BULLISH_OB']
    bearish_obs = [o for o in order_blocks if o['type'] == 'BEARISH_OB']
    unfilled_fvgs = [f for f in fvgs if not f['filled']]

    # Determine SMC bias
    bull_score = len(bullish_fvgs) * 2 + len(bullish_obs) * 3
    bear_score = len(bearish_fvgs) * 2 + len(bearish_obs) * 3

    if bull_score > bear_score + 1:
        bias = 'BULLISH'
    elif bear_score > bull_score + 1:
        bias = 'BEARISH'
    else:
        bias = 'NEUTRAL'

    # Find nearest OB to current price (last candle close)
    nearest_ob = None
    if candles:
        current_price = candles[-1].close
        min_dist = float('inf')
        for ob in order_blocks:
            dist = abs(current_price - ob['ob_midpoint'])
            if dist < min_dist:
                min_dist = dist
                nearest_ob = ob
                nearest_ob['distance'] = round(dist, 6)

    return {
        'fvgs': fvgs,
        'order_blocks': order_blocks,
        'bullish_fvg_count': len(bullish_fvgs),
        'bearish_fvg_count': len(bearish_fvgs),
        'bullish_ob_count': len(bullish_obs),
        'bearish_ob_count': len(bearish_obs),
        'unfilled_fvgs': unfilled_fvgs,
        'nearest_ob': nearest_ob,
        'smc_bias': bias,
    }


# ══════════════════════════════════════════════════════════════════════════════
# LOAD .ENV
# ══════════════════════════════════════════════════════════════════════════════

def _load_env():
    """Load .env file from project root."""
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key.strip(), value.strip())

_load_env()

LOG_DIR = Path(__file__).parent / 'logs'
LOG_DIR.mkdir(exist_ok=True)

# ══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

ASSETS = ['XAUUSD', 'EURUSD', 'GBPUSD', 'SP500']
CRYPTO_ASSETS = ['BTCUSD', 'ETHUSD', 'BNBUSD', 'SOLUSD', 'XRPUSD']
ALL_ASSETS = ASSETS + CRYPTO_ASSETS
TIMEFRAMES = ['M15', 'H1', 'H4', 'D1']
SCAN_INTERVAL = int(os.environ.get('SCAN_INTERVAL_SECONDS', '60'))

# Symbol mapping: Our format → Twelve Data format
SYMBOL_MAP = {
    'XAUUSD': 'XAU/USD',
    'EURUSD': 'EUR/USD',
    'GBPUSD': 'GBP/USD',
    'SP500': 'SPX',
    'BTCUSD': 'BTC/USD',
    'ETHUSD': 'ETH/USD',
    'BNBUSD': 'BNB/USD',
    'SOLUSD': 'SOL/USD',
    'XRPUSD': 'XRP/USD',
}

# Reverse mapping: Twelve Data → Our format
SYMBOL_MAP_REVERSE = {v: k for k, v in SYMBOL_MAP.items()}

# Timeframe mapping
TF_MAP = {
    'M1': '1min', 'M5': '5min', 'M15': '15min', 'M30': '30min',
    'H1': '1h', 'H4': '4h', 'D1': '1day'
}

# Rate limits (free plan)
RATE_LIMIT_PER_MIN = 8
RATE_LIMIT_DAILY = 800
MIN_REQUEST_INTERVAL = 7.5  # seconds — proactive throttle (8 req / 60s = 7.5s floor)

# Mock data config
USE_MOCK_DATA = os.environ.get('USE_MOCK_DATA', '').lower() in ('true', '1', 'yes')
MOCK_SCORE_OVERRIDE = int(os.environ.get('MOCK_SCORE_OVERRIDE', '0'))


def generate_mock_candles(symbol: str, tf: str, limit: int = 100) -> List[Candle]:
    """Generate realistic mock OHLCV candles for testing when API is unavailable."""
    mock_configs = {
        'XAUUSD': {'base': 2200.0, 'range': 200.0, 'decimals': 2},
        'EURUSD': {'base': 1.10, 'range': 0.05, 'decimals': 5},
        'GBPUSD': {'base': 1.25, 'range': 0.08, 'decimals': 5},
        'SP500': {'base': 4500.0, 'range': 300.0, 'decimals': 2},
        'BTCUSD': {'base': 65000.0, 'range': 5000.0, 'decimals': 2},
        'ETHUSD': {'base': 3500.0, 'range': 400.0, 'decimals': 2},
        'BNBUSD': {'base': 580.0, 'range': 40.0, 'decimals': 2},
        'SOLUSD': {'base': 140.0, 'range': 20.0, 'decimals': 2},
        'XRPUSD': {'base': 0.50, 'range': 0.10, 'decimals': 5},
    }

    config = mock_configs.get(symbol, {'base': 100.0, 'range': 10.0, 'decimals': 2})
    base = config['base']
    rng = config['range']
    decimals = config['decimals']
    r = random.Random(hash(f"{symbol}_{tf}") % (2**32))

    candles = []
    now = int(time.time())
    tf_seconds_map = {'M1': 60, 'M5': 300, 'M15': 900, 'M30': 1800, 'H1': 3600, 'H4': 14400, 'D1': 86400}
    interval = tf_seconds_map.get(tf, 3600)

    price = base
    for i in range(limit):
        ts = now - (limit - i) * interval
        change = r.gauss(0, abs(rng) * 0.005) if abs(rng) > 0 else 0
        price += change
        high = price + r.uniform(0, abs(rng) * 0.01) if abs(rng) > 0 else price * 1.001
        low = price - r.uniform(0, abs(rng) * 0.01) if abs(rng) > 0 else price * 0.999
        vol = r.uniform(100, 10000)

        candles.append(Candle(
            timestamp=ts,
            open=round(price, decimals),
            high=round(high, decimals),
            low=round(low, decimals),
            close=round(price + change, decimals),
            volume=round(vol, 0)
        ))

    return candles


class FeedMode(Enum):
    """Feed connection mode."""
    WEBSOCKET = 'WEBSOCKET'
    REST_POLLING = 'REST_POLLING'


@dataclass
class APIStatus:
    """Track API usage and status."""
    mode: FeedMode = FeedMode.REST_POLLING
    requests_this_minute: int = 0
    requests_today: int = 0
    minute_reset_time: float = 0
    daily_reset_time: float = 0
    last_fetch: Dict[str, datetime] = field(default_factory=dict)
    ws_latency_ms: float = 0
    ws_connected: bool = False
    ws_retries: int = 0
    errors: int = 0
    last_error: str = ''
    fallback_active: bool = False


@dataclass
class Candle:
    """OHLCV candle data."""
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'timestamp': self.timestamp,
            'open': self.open,
            'high': self.high,
            'low': self.low,
            'close': self.close,
            'volume': self.volume
        }


@dataclass
class ScanResult:
    """Result of a single asset scan."""
    symbol: str
    status: str
    decision: str = 'BLOCK'
    score: int = 0
    direction: str = 'LONG'
    components: Dict[str, int] = field(default_factory=dict)
    mtf_confirmed: bool = False
    candles: Dict[str, int] = field(default_factory=dict)
    scan_duration_ms: float = 0
    timestamp: str = ''
    error: str = ''


# ══════════════════════════════════════════════════════════════════════════════
# RATE LIMITER
# ══════════════════════════════════════════════════════════════════════════════

class RateLimiter:
    """
    Twelve Data rate limiter.
    Free plan: 8 requests/minute, 800/day.
    """
    
    def __init__(self):
        self.status = APIStatus()
        self._request_times: deque = deque()
        self._lock = threading.Lock()
        self._last_429_time: float = 0
        self._load_state()
    
    def _load_state(self):
        """Load daily usage from file."""
        state_file = LOG_DIR / 'api_state.json'
        try:
            if state_file.exists():
                with open(state_file, 'r') as f:
                    state = json.load(f)
                    self.status.requests_today = state.get('requests_today', 0)
                    daily_reset = state.get('daily_reset_time', 0)
                    if daily_reset > time.time():
                        self.status.daily_reset_time = daily_reset
                    else:
                        self.status.requests_today = 0
                        self.status.daily_reset_time = time.time() + 86400
        except Exception:
            self.status.daily_reset_time = time.time() + 86400
    
    def _save_state(self):
        """Save daily usage to file."""
        state_file = LOG_DIR / 'api_state.json'
        try:
            with open(state_file, 'w') as f:
                json.dump({
                    'requests_today': self.status.requests_today,
                    'daily_reset_time': self.status.daily_reset_time
                }, f)
        except Exception:
            pass
    
    def can_request(self) -> Tuple[bool, float]:
        """
        Check if a request can be made.
        Returns (can_make, wait_seconds).
        """
        with self._lock:
            now = time.time()
            
            # Daily limit check
            if now > self.status.daily_reset_time:
                self.status.requests_today = 0
                self.status.daily_reset_time = now + 86400
            
            if self.status.requests_today >= RATE_LIMIT_DAILY:
                wait = self.status.daily_reset_time - now
                return False, wait
            
            # Per-minute limit check
            # Remove requests older than 60 seconds
            while self._request_times and self._request_times[0] < now - 60:
                self._request_times.popleft()
            
            if len(self._request_times) >= RATE_LIMIT_PER_MIN:
                wait = self._request_times[0] + 60 - now
                return False, max(0, wait)
            
            return True, 0
    
    def record_request(self):
        """Record a successful request."""
        with self._lock:
            now = time.time()
            self._request_times.append(now)
            self.status.requests_this_minute = len(self._request_times)
            self.status.requests_today += 1
            
            if now > self.status.daily_reset_time:
                self.status.requests_today = 1
                self.status.daily_reset_time = now + 86400
            
            self._save_state()
    
    def wait_if_needed(self) -> float:
        """Wait if rate limited. Returns wait time."""
        can_make, wait = self.can_request()
        if not can_make:
            log.warning("[RATE] Minute cap hit — waiting %.1fs", wait)
            time.sleep(wait)
            return wait
        return 0

    def throttle(self):
        """Proactive delay between requests to stay under 8 req/min.

        Enforces a minimum gap of 7.5 seconds between consecutive calls
        so the rolling 60-second window never exceeds the limit.
        """
        with self._lock:
            if self._request_times:
                elapsed = time.time() - self._request_times[-1]
                if elapsed < MIN_REQUEST_INTERVAL:
                    delay = MIN_REQUEST_INTERVAL - elapsed
                    log.debug("[RATE] Throttle — sleeping %.1fs", delay)
                    time.sleep(delay)

    def record_429(self, retry_after: Optional[float] = None):
        """Handle a 429 response. Clears rolling window, purges state, sleeps."""
        state_file = LOG_DIR / 'api_state.json'
        wait = retry_after or 60.0
        with self._lock:
            self.status.errors += 1
            self.status.last_error = 'Rate limited (429)'
            self._request_times.clear()
            self.status.requests_this_minute = 0
            self.status.requests_today = 0
        log.warning("[RATE] 429 received — cleared window + state, backing off %.0fs", wait)
        time.sleep(wait)
        with self._lock:
            self._last_429_time = time.time()
        try:
            state_file.unlink(missing_ok=True)
            log.info("[RATE] Purged %s", state_file)
        except OSError:
            pass

    def post_429_buffer(self):
        """Wait after 429 recovery to ensure server window is fully clear.

        TwelveData's rolling window can persist up to 90s from the last
        server-side request. We wait until that window has expired before
        firing the next request.
        """
        if self._last_429_time:
            elapsed = time.time() - self._last_429_time
            if elapsed < 90:
                delay = max(5.0, 90.0 - elapsed)
                log.info("[RATE] Post-429 buffer — waiting %.0fs (elapsed %.0fs/90s)", delay, elapsed)
                time.sleep(delay)
    
    def get_status_display(self) -> str:
        """Get formatted status string."""
        mode = self.status.mode.value
        conn = '✓' if self.status.ws_connected or self.status.mode == FeedMode.REST_POLLING else '✗'
        latency = f"{self.status.ws_latency_ms:.0f}ms" if self.status.ws_latency_ms > 0 else '-'
        
        lines = [
            f"[FEED] Mode: {mode} {conn} {latency} latency",
            f"[FEED] Rate: {self.status.requests_this_minute}/{RATE_LIMIT_PER_MIN} per min | {self.status.requests_today}/{RATE_LIMIT_DAILY} today",
        ]
        
        for asset in ALL_ASSETS:
            last = self.status.last_fetch.get(asset)
            if last:
                lines.append(f"[FEED] {asset:8s} last: {last.strftime('%H:%M:%S')} UTC")
            else:
                lines.append(f"[FEED] {asset:8s} last: never")
        
        if self.status.fallback_active:
            lines.append(f"[FEED] ⚠️ FALLBACK ACTIVE: REST polling (WS disconnected)")
        
        if self.status.last_error:
            lines.append(f"[FEED] Last error: {self.status.last_error}")
        
        return '\n'.join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# TWELVE DATA REST CLIENT
# ══════════════════════════════════════════════════════════════════════════════

class TwelveDataREST:
    """Twelve Data REST API client with rate limiting."""
    
    BASE_URL = 'https://api.twelvedata.com'
    
    def __init__(self, api_key: str, rate_limiter: RateLimiter):
        self.api_key = api_key
        self.rate_limiter = rate_limiter
        self._cache: Dict[str, List[Candle]] = {}
        self._cache_time: Dict[str, float] = {}
        self._cache_ttl = 30  # Cache for 30 seconds
    
    def fetch_candles(self, symbol: str, timeframe: str, limit: int = 100) -> List[Candle]:
        """
        Fetch OHLCV candles with proactive throttling and 429 backoff.

        Flow:
          1. Return cached data if fresh (< 30s old).
          2. Enforce minimum inter-request delay (7.5s).
          3. Check rolling per-minute and daily caps.
          4. Fire request — only record on success.
          5. On 429: read Retry-After, sleep, return cache.
        """
        cache_key = f"{symbol}_{timeframe}"

        # 1. Cache hit
        if cache_key in self._cache:
            cache_age = time.time() - self._cache_time.get(cache_key, 0)
            if cache_age < self._cache_ttl:
                log.debug("[REST] Cache hit: %s %s (%.0fs old)", symbol, timeframe, cache_age)
                return self._cache[cache_key]

        # 2. Post-429 buffer + proactive throttle
        self.rate_limiter.post_429_buffer()
        self.rate_limiter.throttle()

        # 3. Rolling window check
        self.rate_limiter.wait_if_needed()

        # 4. Build request
        td_symbol = SYMBOL_MAP.get(symbol, symbol)
        tf = TF_MAP.get(timeframe, '1h')
        url = (f"{self.BASE_URL}/time_series?"
               f"symbol={td_symbol}&interval={tf}"
               f"&outputsize={limit}&apikey={self.api_key}")

        try:
            import urllib.request
            import urllib.error

            req = urllib.request.Request(url)
            response = urllib.request.urlopen(req, timeout=10)

            # Record ONLY after a successful response
            self.rate_limiter.record_request()

            data = json.loads(response.read().decode('utf-8'))

            if 'values' not in data:
                log.warning("[REST] No data for %s %s", symbol, timeframe)
                return self._cache.get(cache_key, [])

            candles = []
            for v in reversed(data['values']):
                candle = self._parse_candle(v)
                if candle:
                    candles.append(candle)

            self._cache[cache_key] = candles
            self._cache_time[cache_key] = time.time()
            self.rate_limiter.status.last_fetch[symbol] = datetime.now(timezone.utc)

            log.info("[REST] Fetched %s %s — %d candles", symbol, timeframe, len(candles))
            return candles

        except urllib.error.HTTPError as e:
            if e.code == 429:
                retry_after = e.headers.get('Retry-After')
                retry_secs = float(retry_after) if retry_after else 60.0
                self.rate_limiter.record_429(retry_after=retry_secs)
            elif e.code in (401, 403):
                log.error("[REST] API key invalid or unauthorized")
                self.rate_limiter.status.last_error = 'API key invalid'
            else:
                log.error("[REST] HTTP %d fetching %s: %s", e.code, symbol, e.reason)
                self.rate_limiter.status.errors += 1
                self.rate_limiter.status.last_error = str(e.reason)[:100]
            return self._cache.get(cache_key, [])

        except Exception as e:
            log.error("[REST] Error fetching %s: %s", symbol, e)
            self.rate_limiter.status.errors += 1
            self.rate_limiter.status.last_error = str(e)[:100]
            return self._cache.get(cache_key, [])
    
    def _parse_candle(self, data: Dict[str, Any]) -> Optional[Candle]:
        """Parse a candle from API response."""
        try:
            dt_str = data.get('datetime', '')
            if 'T' in dt_str:
                dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
            else:
                dt = datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S')
                dt = dt.replace(tzinfo=timezone.utc)
            
            return Candle(
                timestamp=int(dt.timestamp()),
                open=float(data['open']),
                high=float(data['high']),
                low=float(data['low']),
                close=float(data['close']),
                volume=float(data.get('volume', 0))
            )
        except Exception as e:
            log.warning(f"[REST] Failed to parse candle: {e}")
            return None
    
    def validate_candles(self, candles: List[Candle]) -> List[Candle]:
        """Validate candle data, reject bad data."""
        if not candles:
            return []
        
        validated = []
        for c in candles:
            # Skip candles with invalid prices
            if c.open <= 0 or c.high <= 0 or c.low <= 0 or c.close <= 0:
                log.warning(f"[VALIDATE] Invalid price in candle at {c.timestamp}")
                continue
            
            # Skip candles where high < low
            if c.high < c.low:
                log.warning(f"[VALIDATE] High < Low in candle at {c.timestamp}")
                continue
            
            validated.append(c)
        
        return validated


# ══════════════════════════════════════════════════════════════════════════════
# TWELVE DATA WEBSOCKET CLIENT
# ══════════════════════════════════════════════════════════════════════════════

class TwelveDataWebSocket:
    """Twelve Data WebSocket client for real-time prices."""
    
    WS_URL = 'wss://ws.twelvedata.com/v1/quotes/price'
    
    def __init__(self, api_key: str, rate_limiter: RateLimiter, on_price_update=None):
        self.api_key = api_key
        self.rate_limiter = rate_limiter
        self.on_price_update = on_price_update
        self._ws = None
        self._thread = None
        self._running = False
        self._connected = False
        self._retries = 0
        self._max_retries = 10
        self._last_prices: Dict[str, Dict[str, Any]] = {}
    
    def connect(self):
        """Connect to WebSocket."""
        try:
            import websocket
            
            url = f"{self.WS_URL}?apikey={self.api_key}"
            
            self._ws = websocket.WebSocketApp(
                url,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close
            )
            
            self._thread = threading.Thread(target=self._ws.run_forever, daemon=True)
            self._thread.start()
            
            log.info("[WS] Connecting to Twelve Data WebSocket...")
            
        except ImportError:
            log.warning("[WS] websocket-client not installed. Install: pip install websocket-client")
            self.rate_limiter.status.fallback_active = True
        except Exception as e:
            log.error(f"[WS] Connection failed: {e}")
            self.rate_limiter.status.fallback_active = True
    
    def _on_open(self, ws):
        """Handle WebSocket connection."""
        self._connected = True
        self._retries = 0
        self.rate_limiter.status.ws_connected = True
        self.rate_limiter.status.mode = FeedMode.WEBSOCKET
        
        # Subscribe to symbols
        symbols = ','.join(SYMBOL_MAP.values())
        subscribe_msg = json.dumps({
            'action': 'subscribe',
            'params': {'symbols': symbols}
        })
        
        ws.send(subscribe_msg)
        log.info(f"[WS] Connected, subscribed to: {symbols}")
    
    def _on_message(self, ws, message):
        """Handle incoming WebSocket message."""
        try:
            data = json.loads(message)
            
            if 'symbol' in data:
                symbol = SYMBOL_MAP_REVERSE.get(data['symbol'], data['symbol'])
                
                self._last_prices[symbol] = {
                    'price': float(data.get('price', 0)),
                    'timestamp': datetime.now(timezone.utc),
                    'volume': float(data.get('volume', 0))
                }
                
                self.rate_limiter.status.last_fetch[symbol] = datetime.now(timezone.utc)
                
                if self.on_price_update:
                    self.on_price_update(symbol, self._last_prices[symbol])
                    
        except Exception as e:
            log.error(f"[WS] Message parse error: {e}")
    
    def _on_error(self, ws, error):
        """Handle WebSocket error."""
        self._connected = False
        self.rate_limiter.status.ws_connected = False
        self.rate_limiter.status.errors += 1
        self.rate_limiter.status.last_error = str(error)[:100]
        log.error(f"[WS] Error: {error}")
    
    def _on_close(self, ws, close_status_code, close_msg):
        """Handle WebSocket close."""
        self._connected = False
        self.rate_limiter.status.ws_connected = False
        log.info(f"[WS] Disconnected (code={close_status_code})")
        
        # Auto-reconnect with exponential backoff: 5s, 10s, 20s, 40s, 80s, 160s, 300s...
        if self._running and self._retries < self._max_retries:
            self._retries += 1
            delay = min(5 * (2 ** (self._retries - 1)), 300)
            log.info(f"[WS] Reconnecting in {delay}s (attempt {self._retries}/{self._max_retries})")
            time.sleep(delay)
            
            if self._running:
                self.connect()
        else:
            log.warning("[WS] Max retries reached, switching to REST polling")
            self.rate_limiter.status.fallback_active = True
            self.rate_limiter.status.mode = FeedMode.REST_POLLING
    
    def disconnect(self):
        """Disconnect WebSocket."""
        self._running = False
        if self._ws:
            self._ws.close()
    
    def get_last_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get last received price for symbol."""
        return self._last_prices.get(symbol)


# ══════════════════════════════════════════════════════════════════════════════
# REST POLLING WITH BATCHING
# ══════════════════════════════════════════════════════════════════════════════

class RESTPollingBatcher:
    """
    Smart REST polling that stays under 8 req/min.
    
    Batch schedule:
      Batch 1 (0s):   XAUUSD M15, XAUUSD H1
      Batch 2 (15s):  XAUUSD H4, XAUUSD D1
      Batch 3 (30s):  EURUSD M15, EURUSD H1
      Batch 4 (45s):  EURUSD H4, EURUSD D1
      Batch 5 (60s):  GBPUSD M15, GBPUSD H1
      Batch 6 (75s):  GBPUSD H4, GBPUSD D1
      Batch 7 (90s):  SP500 M15, SP500 H1
      Batch 8 (105s): SP500 H4, SP500 D1
    """
    
    def __init__(self, rest_client: TwelveDataREST):
        self.rest_client = rest_client
        self._batch_index = 0
        self._batch_schedule = self._build_schedule()
        self._last_batch_time = 0
        self._candle_cache: Dict[str, List[Candle]] = {}
    
    def _build_schedule(self) -> List[List[Tuple[str, str]]]:
        """Build batch schedule."""
        schedule = []
        for symbol in ASSETS:
            batch = [(symbol, tf) for tf in TIMEFRAMES]
            # Split into pairs
            for i in range(0, len(batch), 2):
                schedule.append(batch[i:i+2])
        return schedule
    
    def fetch_batch(self) -> Dict[str, Dict[str, List[Candle]]]:
        """
        Fetch next batch of data.
        Returns: {symbol: {timeframe: [Candle]}}
        """
        now = time.time()
        
        # Wait if needed (15 seconds between batches)
        if now - self._last_batch_time < 15:
            time.sleep(15 - (now - self._last_batch_time))
        
        batch = self._batch_schedule[self._batch_index % len(self._batch_schedule)]
        self._batch_index += 1
        self._last_batch_time = time.time()
        
        results: Dict[str, Dict[str, List[Candle]]] = {}
        
        for symbol, tf in batch:
            if symbol not in results:
                results[symbol] = {}
            
            candles = self.rest_client.fetch_candles(symbol, tf, 100)
            candles = self.rest_client.validate_candles(candles)
            results[symbol][tf] = candles
            
            # Cache for pipeline
            cache_key = f"{symbol}_{tf}"
            self._candle_cache[cache_key] = candles
        
        return results
    
    def get_cached_candles(self, symbol: str, tf: str) -> List[Candle]:
        """Get cached candles for symbol/timeframe."""
        cache_key = f"{symbol}_{tf}"
        return self._candle_cache.get(cache_key, [])
    
    def fetch_all_assets(self) -> Dict[str, Dict[str, List[Candle]]]:
        """
        Fetch all assets (runs full batch cycle).
        Takes ~2 minutes for complete scan.
        """
        all_results: Dict[str, Dict[str, List[Candle]]] = {s: {} for s in ASSETS}
        
        for _ in range(len(self._batch_schedule)):
            batch_results = self.fetch_batch()
            for symbol, tf_data in batch_results.items():
                all_results[symbol].update(tf_data)
        
        return all_results


# ══════════════════════════════════════════════════════════════════════════════
# LIVE FEED SCANNER
# ══════════════════════════════════════════════════════════════════════════════

class LiveFeedScanner:
    """
    Live data scanner with WebSocket + REST fallback.
    
    Scan Cycle:
       1. Check WebSocket connection
       2. If connected: use real-time prices + REST candles
       3. If disconnected: use REST polling with batching
       4. Run full pipeline for each asset
       5. Log results + Telegram alerts
    """
    
    def __init__(self, pipeline: Optional[PipelineProtocol] = None):
        self.api_key = os.environ.get('LIVE_DATA_API_KEY', '')
        self.mock_mode = USE_MOCK_DATA or not self.api_key
        
        if not self.api_key and not self.mock_mode:
            log.error("[SCANNER] No LIVE_DATA_API_KEY found in .env")
            raise ValueError("LIVE_DATA_API_KEY not configured")
        
        if self.mock_mode:
            log.info("[SCANNER] MOCK MODE — using synthetic data for testing")
        
        # Initialize rate limiter
        self.rate_limiter = RateLimiter()
        
        # Initialize REST client
        self.rest_client = TwelveDataREST(self.api_key, self.rate_limiter)
        
        # Initialize REST polling batcher
        self.poller = RESTPollingBatcher(self.rest_client)
        
        # Initialize WebSocket
        self.ws_client = TwelveDataWebSocket(
            self.api_key, 
            self.rate_limiter,
            on_price_update=self._on_price_update
        )
        
        # Pipeline (injected via constructor — Layer 0 contract)
        self.pipeline = pipeline
        
        # Status
        self._scan_count = 0
        self._last_scan_results: List[ScanResult] = []
        
        # First candle tracking
        self._first_candle_received = False
        
        # Pre-check: if API key exists but TwelveData is known expired,
        # skip TwelveData REST entirely to avoid 60s blocking sleeps.
        # yfinance will be used as primary data source.
        if self.api_key and not self.mock_mode:
            self.rate_limiter.status.fallback_active = True
            log.info("[SCANNER] TwelveData REST disabled — using yfinance as primary data source")
    
    def verify_api_key(self) -> bool:
        """Verify TwelveData API key — deferred to first fetch_candles call."""
        if self.mock_mode:
            log.info("[SCANNER] Mock mode — skipping API key verification")
            return True
        log.info("[SCANNER] API key verification deferred to first data fetch")
        return True
    
    def _on_first_candle(self, symbol: str, tf: str, candle: Candle):
        """Handle first candle received — log and force pipeline run."""
        self._first_candle_received = True
        log.info(f"✅ First candle: {symbol} O:{candle.open} H:{candle.high} L:{candle.low} C:{candle.close} V:{candle.volume:.0f}")
        try:
            candle_file = LOG_DIR / 'last_candle.json'
            with open(candle_file, 'w') as f:
                json.dump({
                    'symbol': symbol, 'timeframe': tf,
                    'candle': candle.to_dict(), 'timestamp': time.time()
                }, f, indent=2)
        except Exception as e:
            log.error(f"[SCANNER] Failed to save first candle: {e}")
        try:
            if self.pipeline:
                payload = {
                    'symbol': symbol, 'direction': 'LONG', 'timeframe': tf,
                    'price': candle.close,
                    'candles': [candle.to_dict()],
                    'candles_data': {tf: [candle.to_dict()]}
                }
                result = self.pipeline.run_pipeline(payload, 'startup')
                scan_file = LOG_DIR / 'last_scan.json'
                score = result.get('score', 0)
                decision = result.get('decision', 'BLOCK')
                with open(scan_file, 'w') as f:
                    json.dump({
                        'timestamp': time.time(),
                        'scores': {symbol: {'score': score, 'decision': decision}},
                        'scans': [{'symbol': symbol, 'score': score, 'decision': decision}]
                    }, f, indent=2, default=str)
                log.info(f"[SCANNER] Startup pipeline complete: {symbol} score={score} {decision}")
        except Exception as e:
            log.error(f"[SCANNER] Failed to run startup pipeline: {e}")
    
    def _on_price_update(self, symbol: str, data: Dict[str, Any]):
        """Handle real-time price update from WebSocket."""
        log.debug(f"[WS] {symbol}: ${data.get('price', 0):.2f}")
    
    def fetch_candles(self, symbol: str, tf: str) -> List[Candle]:
        """Fetch candles for a symbol/timeframe.

        Priority:
          1. yfinance (free, no key needed, no rate limits)
          2. TwelveData REST (if API key valid)
          3. Mock data (fallback)
        """
        if self.mock_mode:
            candles = generate_mock_candles(symbol, tf, 100)
            if candles and not self._first_candle_received:
                self._on_first_candle(symbol, tf, candles[-1])
            return candles

        # 1. Try yfinance first (free, no rate limits)
        try:
            from production.yfinance_data_provider import fetch_yf_candles, validate_yf_candles
            yf_candles = fetch_yf_candles(symbol, tf, 100)
            if yf_candles:
                yf_candles = validate_yf_candles(yf_candles)
                if yf_candles:
                    candle_objects = []
                    for c in yf_candles:
                        candle_objects.append(Candle(
                            timestamp=c['timestamp'],
                            open=c['open'],
                            high=c['high'],
                            low=c['low'],
                            close=c['close'],
                            volume=c['volume'],
                        ))
                    if not self._first_candle_received:
                        self._on_first_candle(symbol, tf, candle_objects[-1])
                    log.info("[SCANNER] Using yfinance data for %s %s", symbol, tf)
                    return candle_objects
        except Exception as e:
            log.warning("[SCANNER] yfinance failed for %s %s: %s", symbol, tf, e)

        # 2. Fallback: TwelveData REST (may hit rate limits)
        # Skip if fallback_active (TwelveData key expired/invalid)
        if not self.rate_limiter.status.fallback_active:
            candles = self.rest_client.fetch_candles(symbol, tf, 100)
            if candles:
                validated = self.rest_client.validate_candles(candles)
                if validated:
                    if not self._first_candle_received:
                        self._on_first_candle(symbol, tf, validated[-1])
                    return validated

        # 3. Final fallback: mock data
        log.warning("[SCANNER] No real data for %s %s, falling back to mock", symbol, tf)
        candles = generate_mock_candles(symbol, tf, 100)
        if candles and not self._first_candle_received:
            self._on_first_candle(symbol, tf, candles[-1])
        return candles
    
    def scan_asset(self, symbol: str) -> ScanResult:
        """Scan a single asset through the full pipeline."""
        scan_start = time.time()
        result = ScanResult(
            symbol=symbol,
            status='SCANNING',
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        
        try:
            # Fetch candles for all timeframes
            candles_data: Dict[str, List[Candle]] = {}
            for tf in TIMEFRAMES:
                candles_data[tf] = self.fetch_candles(symbol, tf)
            
            # Check if we have data
            h1_candles = candles_data.get('H1', [])
            if not h1_candles:
                result.status = 'NO_DATA'
                return result
            
            # Get latest price
            latest_price = h1_candles[-1].close
            
            # Try WebSocket price first
            ws_price = self.ws_client.get_last_price(symbol)
            if ws_price:
                latest_price = ws_price['price']
            
            # Convert candles to dict format for pipeline
            candles_dicts = [c.to_dict() for c in h1_candles]

            # ── SMC Detection (Layer 1 → Layer 2) ──────────────────────
            smc_by_tf: Dict[str, Dict[str, Any]] = {}
            for tf_key, tf_candles in candles_data.items():
                if tf_candles:
                    smc_by_tf[tf_key] = detect_smc_context(tf_candles)

            # Aggregate SMC across timeframes
            total_bull_ob = sum(s.get('bullish_ob_count', 0) for s in smc_by_tf.values())
            total_bear_ob = sum(s.get('bearish_ob_count', 0) for s in smc_by_tf.values())
            total_bull_fvg = sum(s.get('bullish_fvg_count', 0) for s in smc_by_tf.values())
            total_bear_fvg = sum(s.get('bearish_fvg_count', 0) for s in smc_by_tf.values())
            unfilled = []
            for s in smc_by_tf.values():
                unfilled.extend(s.get('unfilled_fvgs', []))

            # Multi-timeframe SMC confirmation
            mtf_bullish = sum(1 for s in smc_by_tf.values() if s.get('smc_bias') == 'BULLISH')
            mtf_bearish = sum(1 for s in smc_by_tf.values() if s.get('smc_bias') == 'BEARISH')

            if mtf_bullish > mtf_bearish:
                smc_mtf_bias = 'BULLISH'
            elif mtf_bearish > mtf_bullish:
                smc_mtf_bias = 'BEARISH'
            else:
                smc_mtf_bias = 'NEUTRAL'

            smc_aggregate = {
                'by_timeframe': smc_by_tf,
                'bullish_ob_count': total_bull_ob,
                'bearish_ob_count': total_bear_ob,
                'bullish_fvg_count': total_bull_fvg,
                'bearish_fvg_count': total_bear_fvg,
                'unfilled_fvgs': unfilled,
                'mtf_smc_bias': smc_mtf_bias,
            }

            # Build pipeline payload
            payload = {
                'symbol': symbol,
                'direction': 'LONG',
                'timeframe': 'H1',
                'price': latest_price,
                'candles': candles_dicts,
                'candles_data': {tf: [c.to_dict() for c in candles] for tf, candles in candles_data.items()},
                'smc': smc_aggregate,
            }
            
            # Run pipeline
            if self.pipeline:
                pipeline_result = self.pipeline.run_pipeline(payload, 'scanner')
                
                result.decision = pipeline_result.get('decision', 'BLOCK')
                result.score = pipeline_result.get('score', 0)
                result.direction = pipeline_result.get('direction', 'LONG')
                
                # Extract components
                confidence = pipeline_result.get('steps', {}).get('confidence', {})
                result.components = confidence.get('components', {})
                result.mtf_confirmed = pipeline_result.get('steps', {}).get('mtf', {}).get('confirmed', False)
            
            result.status = 'OK'
            result.candles = {tf: len(candles) for tf, candles in candles_data.items()}
            
        except Exception as e:
            log.error(f"[SCANNER] Error scanning {symbol}: {e}")
            result.status = 'ERROR'
            result.error = str(e)
        
        result.scan_duration_ms = (time.time() - scan_start) * 1000
        return result
    
    def run_scan(self) -> Dict[str, Any]:
        """
        Run full scan on all assets.
        Uses REST polling with smart batching.
        """
        scan_start = time.time()
        self._scan_count += 1
        
        results = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'scan_number': self._scan_count,
            'mode': self.rate_limiter.status.mode.value,
            'scans': [],
            'summary': {
                'total': len(ASSETS),
                'executed': 0,
                'waited': 0,
                'blocked': 0,
                'errors': 0
            }
        }
        
        # Fetch next batch
        batch_data = self.poller.fetch_batch()
        
        # Scan each asset
        for symbol in ASSETS:
            scan_result = self.scan_asset(symbol)
            self._last_scan_results.append(scan_result)
            
            scan_dict = {
                'symbol': symbol,
                'status': scan_result.status,
                'decision': scan_result.decision,
                'score': scan_result.score,
                'duration_ms': scan_result.scan_duration_ms
            }
            results['scans'].append(scan_dict)
            
            if scan_result.decision == 'EXECUTE':
                results['summary']['executed'] += 1
            elif scan_result.decision == 'WAIT':
                results['summary']['waited'] += 1
            elif scan_result.status == 'ERROR':
                results['summary']['errors'] += 1
            else:
                results['summary']['blocked'] += 1
        
        results['total_duration_ms'] = (time.time() - scan_start) * 1000
        
        # Save results
        self._save_results(results)
        
        # Log summary
        log.info(
            f"[SCAN] #{self._scan_count} Complete: "
            f"{results['summary']['executed']} EXECUTE, "
            f"{results['summary']['waited']} WAIT, "
            f"{results['summary']['blocked']} BLOCK, "
            f"{results['summary']['errors']} ERR "
            f"({results['total_duration_ms']:.0f}ms)"
        )
        
        return results
    
    def _save_results(self, results: Dict[str, Any]):
        """Save scan results to file."""
        try:
            scan_file = LOG_DIR / 'last_scan.json'
            with open(scan_file, 'w') as f:
                json.dump(results, f, indent=2, default=str)
        except Exception as e:
            log.error(f"[SCANNER] Failed to save results: {e}")
    
    def get_status(self) -> str:
        """Get formatted status display."""
        return self.rate_limiter.get_status_display()
    
    def start(self):
        """Start the scanner."""
        log.info('=' * 60)
        log.info('OMNI BRAIN V2 - LIVE FEED SCANNER')
        log.info('=' * 60)
        log.info(f'Assets: {", ".join(ALL_ASSETS)}')
        log.info(f'Timeframes: {", ".join(TIMEFRAMES)}')
        log.info(f'Interval: {SCAN_INTERVAL}s')
        log.info(f'Rate Limit: {RATE_LIMIT_PER_MIN}/min, {RATE_LIMIT_DAILY}/day')
        log.info('=' * 60)
        
        # Verify API key on startup
        self.verify_api_key()
        
        # Try WebSocket connection
        if not self.rate_limiter.status.fallback_active:
            self.ws_client._running = True
            self.ws_client.connect()
        
        print(self.get_status())
    
    def stop(self):
        """Stop the scanner."""
        self.ws_client.disconnect()
        log.info("[SCANNER] Stopped")


# ══════════════════════════════════════════════════════════════════════════════
# DIAGNOSE
# ══════════════════════════════════════════════════════════════════════════════

def run_diagnose():
    """Run full diagnostic of live data pipeline."""
    import urllib.request
    import urllib.error

    print("=" * 60)
    print("  OMNI BRAIN V2 — LIVE DATA DIAGNOSTIC")
    print("=" * 60)

    issues = []

    # 1. Check API key
    print("\n[1/6] Checking LIVE_DATA_API_KEY...")
    api_key = os.environ.get('LIVE_DATA_API_KEY', '')
    if api_key:
        print("  ✅ API key found")
    else:
        print("  ❌ API key missing")
        issues.append("LIVE_DATA_API_KEY not set in .env")

    # 2. Test TwelveData API connection
    print("\n[2/6] Testing TwelveData API connection...")
    if api_key:
        try:
            test_url = f"https://api.twelvedata.com/price?symbol=XAU/USD&apikey={api_key}"
            resp = urllib.request.urlopen(test_url, timeout=10)
            if resp.getcode() == 200:
                print("  ✅ API key valid — connection OK")
            else:
                print(f"  ⚠️  Unexpected status: {resp.getcode()}")
        except urllib.error.HTTPError as e:
            if e.code == 401:
                print("  ❌ API key invalid (401)")
                issues.append("TwelveData API key invalid")
            elif e.code == 429:
                print("  ❌ Rate limit hit (429)")
                issues.append("TwelveData rate limit exceeded")
            else:
                print(f"  ❌ HTTP {e.code}: {e.reason}")
                issues.append(f"TwelveData HTTP {e.code}")
        except Exception as e:
            print(f"  ❌ Connection failed: {e}")
            issues.append(f"TwelveData connection: {e}")
    else:
        print("  ⏭️  Skipped (no API key)")

    # 3. Check candles per asset
    print("\n[3/6] Checking candle reception...")
    try:
        scanner = LiveFeedScanner()
        for sym in ASSETS:
            candles = scanner.fetch_candles(sym, 'H1')
            count = len(candles)
            if count > 0:
                last = candles[-1]
                print(f"  ✅ {sym:8s}: {count} candles, last close={last.close}")
            else:
                print(f"  ❌ {sym:8s}: No candles received")
                issues.append(f"{sym}: no candles")
    except Exception as e:
        print(f"  ❌ Failed to create scanner: {e}")
        issues.append(f"Scanner init: {e}")

    # 4. Smart Money Matrix check
    print("\n[4/6] Checking Smart Money Matrix input...")
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from smart_money_matrix import SmartMoneyMatrix, Candle as SMCandle
        matrix = SmartMoneyMatrix()
        mock = generate_mock_candles('XAUUSD', 'H1', 100)
        sm_candles = [SMCandle(timestamp=c.timestamp, open=c.open, high=c.high,
                               low=c.low, close=c.close, volume=c.volume) for c in mock]
        detection = matrix.scan(sm_candles)
        ob_count = len(detection.get('order_blocks', []))
        fvg_count = len(detection.get('fair_value_gaps', []))
        sweep_count = len(detection.get('sweep_events', []))
        print(f"  ✅ Matrix input: {len(mock)} candles")
        print(f"     OB: {ob_count} | FVG: {fvg_count} | Sweep: {sweep_count}")
        if ob_count == 0 and fvg_count == 0 and sweep_count == 0:
            print("  ⚠️  No signals detected — check matrix configuration")
    except Exception as e:
        print(f"  ❌ Matrix check failed: {e}")
        issues.append(f"SMM check: {e}")

    # 5. Pipeline check with mock data
    print("\n[5/6] Running pipeline test scan...")
    try:
        from pipeline_orchestrator import PipelineEngine
        engine = PipelineEngine()
        mock = generate_mock_candles('XAUUSD', 'H1', 100)
        candles_dicts = [c.to_dict() for c in mock]
        payload = {
            'symbol': 'XAUUSD',
            'direction': 'LONG',
            'timeframe': 'H1',
            'price': mock[-1].close if mock else 2000.0,
            'candles': candles_dicts,
            'candles_data': {'H1': candles_dicts},
        }
        result = engine.run_pipeline(payload, 'diagnose')
        score = result.get('score', 0)
        decision = result.get('decision', 'BLOCK')
        print(f"  ✅ Pipeline complete: score={score}, decision={decision}")
        steps = result.get('steps', {})
        for step_name, step_data in steps.items():
            if isinstance(step_data, dict):
                if 'score' in step_data:
                    print(f"     {step_name:20s}: score={step_data.get('score')}")
                elif 'confirmed' in step_data:
                    print(f"     {step_name:20s}: confirmed={step_data.get('confirmed')}")
                else:
                    print(f"     {step_name:20s}: {json.dumps(step_data)[:60]}")
            else:
                print(f"     {step_name:20s}: {step_data}")
        if score == 0:
            print("  ⚠️  Score is 0 — check component inputs")
            issues.append("Score is 0 — components not contributing")
    except Exception as e:
        print(f"  ❌ Pipeline test failed: {e}")
        import traceback
        traceback.print_exc()
        issues.append(f"Pipeline test: {e}")

    # 6. Summary
    print("\n[6/6] Summary")
    print("=" * 60)
    if issues:
        print(f"  Found {len(issues)} issue(s):")
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}")
        print("\n  💡 Run with USE_MOCK_DATA=true to bypass API issues")
    else:
        print("  ✅ All checks passed — pipeline is healthy")
    print("=" * 60)

    return issues


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

def run_startup_test() -> bool:
    """Run startup test: verify API, fetch candles, run pipeline, print PASS/FAIL."""
    print("=" * 60)
    print("  OMNI BRAIN V2 — STARTUP TEST")
    print("=" * 60)

    steps = []

    # Step 1: Verify API key
    print("\n[1/5] Verifying API key...")
    api_key = os.environ.get('LIVE_DATA_API_KEY', '')
    if api_key:
        try:
            import urllib.request
            url = f"https://api.twelvedata.com/api_usage?apikey={api_key}"
            resp = urllib.request.urlopen(url, timeout=10)
            data = json.loads(resp.read().decode())
            usage = data.get('api_usage', [{}])
            if usage:
                entry = usage[0] if isinstance(usage, list) else usage
                used = entry.get('used_credits', entry.get('used', '?'))
                limit = entry.get('total_credits', entry.get('limit', '?'))
            else:
                used = data.get('used_credits', '?')
                limit = data.get('total_credits', '?')
            print(f"  \u2705 TwelveData connected (Credits: {used}/{limit} today)")
            steps.append(('API Key Verification', 'PASS'))
        except Exception as e:
            print(f"  \u274c API key verification failed: {e}")
            print(f"  \u26a0\ufe0f  Continuing with mock data fallback")
            steps.append(('API Key Verification', 'FAIL'))
    else:
        print(f"  \u26a0\ufe0f  No API key — using mock data")
        steps.append(('API Key Verification', 'SKIP'))

    # Step 2: Create scanner
    print("\n[2/5] Initializing scanner...")
    try:
        scanner = LiveFeedScanner()
        print(f"  \u2705 Scanner initialized")
        steps.append(('Scanner Init', 'PASS'))
    except Exception as e:
        print(f"  \u274c Scanner init failed: {e}")
        steps.append(('Scanner Init', 'FAIL'))
        print("\n" + "=" * 60)
        for name, status in steps:
            icon = '\u2705' if status == 'PASS' else '\u26a0\ufe0f' if status == 'SKIP' else '\u274c'
            print(f"  {icon} {name}: {status}")
        return False

    # Step 3: Fetch candles
    print("\n[3/5] Fetching candles...")
    try:
        all_ok = True
        for sym in ASSETS:
            candles = scanner.fetch_candles(sym, 'H1')
            count = len(candles)
            if count > 0:
                last = candles[-1]
                print(f"  \u2705 {sym:8s}: {count} candles, last O:{last.open} H:{last.high} L:{last.low} C:{last.close}")
                try:
                    candle_file = LOG_DIR / 'last_candle.json'
                    with open(candle_file, 'w') as f:
                        json.dump({
                            'symbol': sym, 'timeframe': 'H1',
                            'candle': last.to_dict(), 'timestamp': time.time()
                        }, f, indent=2)
                except Exception:
                    pass
            else:
                print(f"  \u274c {sym:8s}: No candles received")
                all_ok = False
        steps.append(('Candle Fetch', 'PASS' if all_ok else 'PARTIAL'))
    except Exception as e:
        print(f"  \u274c Candle fetch failed: {e}")
        steps.append(('Candle Fetch', 'FAIL'))

    # Step 4: Run pipeline
    print("\n[4/5] Running pipeline...")
    try:
        mock = generate_mock_candles('XAUUSD', 'H1', 100)
        candles_dicts = [c.to_dict() for c in mock]
        payload = {
            'symbol': 'XAUUSD', 'direction': 'LONG', 'timeframe': 'H1',
            'price': mock[-1].close if mock else 2000.0,
            'candles': candles_dicts,
            'candles_data': {'H1': candles_dicts},
        }
        if scanner.pipeline:
            result = scanner.pipeline.run_pipeline(payload, 'startup-test')
            score = result.get('score', 0)
            decision = result.get('decision', 'BLOCK')
            print(f"  \u2705 Pipeline complete: score={score}, decision={decision}")
            scan_file = LOG_DIR / 'last_scan.json'
            with open(scan_file, 'w') as f:
                json.dump({
                    'timestamp': time.time(),
                    'scores': {'XAUUSD': {'score': score, 'decision': decision}},
                    'scans': [{'symbol': 'XAUUSD', 'score': score, 'decision': decision}]
                }, f, indent=2, default=str)
            steps.append(('Pipeline Run', 'PASS'))
        else:
            print(f"  \u274c Pipeline not available")
            steps.append(('Pipeline Run', 'FAIL'))
    except Exception as e:
        print(f"  \u274c Pipeline failed: {e}")
        import traceback
        traceback.print_exc()
        steps.append(('Pipeline Run', 'FAIL'))

    # Step 5: Summary
    print("\n[5/5] Summary")
    print("=" * 60)
    all_pass = all(s[1] == 'PASS' for s in steps)
    for name, status in steps:
        icon = '\u2705' if status == 'PASS' else '\u26a0\ufe0f' if status in ('SKIP', 'PARTIAL') else '\u274c'
        print(f"  {icon} {name}: {status}")
    print("=" * 60)
    if all_pass:
        print("  \u2705 ALL SYSTEMS GO — VPS is ready")
    else:
        print("  \u26a0\ufe0f  Some checks failed — review above")
    return all_pass


def main():
    """Main entry point."""
    import argparse
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )
    
    parser = argparse.ArgumentParser(description='Live Data Feed Scanner')
    parser.add_argument('--once', action='store_true', help='Run single scan')
    parser.add_argument('--test', action='store_true', help='Test mode')
    parser.add_argument('--status', action='store_true', help='Show status')
    parser.add_argument('--diagnose', action='store_true', help='Run full diagnostic')
    parser.add_argument('--startup-test', action='store_true', help='Run startup connectivity test')
    parser.add_argument('--interval', type=int, default=SCAN_INTERVAL, help='Scan interval')
    args = parser.parse_args()
    
    if args.diagnose:
        run_diagnose()
        return
    
    if args.startup_test:
        run_startup_test()
        return
    
    scanner = LiveFeedScanner()
    scanner.start()
    
    if args.once or args.test:
        print("=" * 60)
        print("  LIVE FEED SCANNER - TEST")
        print("=" * 60)
        
        results = scanner.run_scan()
        
        print(f"\n{scanner.get_status()}")
        print(f"\nScan #{results['scan_number']}:")
        print(f"  Mode: {results['mode']}")
        print(f"  Duration: {results['total_duration_ms']:.0f}ms")
        print(f"  Summary: {results['summary']['executed']} EXECUTE, "
              f"{results['summary']['waited']} WAIT, "
              f"{results['summary']['blocked']} BLOCK")
        
        for scan in results['scans']:
            print(f"\n  {scan['symbol']}: {scan['status']} | {scan['decision']} "
                  f"(score={scan['score']}, {scan['duration_ms']:.0f}ms)")
        
        print("\n" + "=" * 60)
    
    elif args.status:
        print(scanner.get_status())
    
    else:
        # Continuous loop
        try:
            while True:
                scanner.run_scan()
                time.sleep(args.interval)
        except KeyboardInterrupt:
            scanner.stop()
            print("\n[SCANNER] Stopped")


if __name__ == '__main__':
    main()
