"""
MT5 Sync Split-Brain Guard - OMNI BRAIN V2
============================================
Protects MT5 data sync from concurrent write conflicts.

Architecture:
  - Per-symbol, per-timeframe atomic locking
  - Parallel assets OK, same asset/timeframe blocks
  - Lock timeout: 2 seconds (never crash)
  - Stale candle detection and validation
  - MT5 reconnect with CSV fallback

Lock Files:
  /tmp/mt5_sync_{symbol}_{tf}.lock

Pipeline:
  1. Acquire lock (O_CREAT|O_EXCL, 2s timeout)
  2. Fetch latest candles from MT5
  3. validate_candles() - stale/duplicate/gaps
  4. Write to CSV / memory cache
  5. Release lock
"""

import os
import sys
import fcntl
import json
import time
import atexit
import logging
import traceback
import subprocess
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum

log = logging.getLogger('MT5SyncGuard')

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

# ══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

ASSETS = ['XAUUSD', 'EURUSD', 'GBPUSD', 'SP500']
TIMEFRAMES = ['M15', 'H1', 'H4', 'D1']
LOCK_DIR = '/tmp'
LOCK_TIMEOUT_S = 2.0
RECONNECT_ATTEMPTS = 3
RECONNECT_DELAY_S = 3.0
FUTURE_CANDLE_BUFFER_MIN = 5
MAX_GAP_BARS = 3

LOG_DIR = Path(__file__).parent / 'logs'
LOG_DIR.mkdir(exist_ok=True)

CSV_DIR = Path(__file__).parent.parent / 'data' / 'csv'
CSV_DIR.mkdir(parents=True, exist_ok=True)

ERROR_LOG = LOG_DIR / 'mt5_errors.log'


class CandleStatus(Enum):
    """Candle validation status."""
    OK = 'OK'
    STALE = 'STALE'
    DUPLICATE = 'DUPLICATE'
    ZERO_VOL = 'ZERO_VOL'
    FUTURE = 'FUTURE'
    GAP = 'GAP'


@dataclass
class SyncResult:
    """Result of a sync operation."""
    symbol: str
    timeframe: str
    status: str
    lock_ms: float = 0
    fetch_ms: float = 0
    candles_count: int = 0
    validation_warnings: List[str] = field(default_factory=list)
    source: str = 'MT5'
    error: str = ''


@dataclass
class CandleValidation:
    """Candle validation result."""
    status: CandleStatus
    candle_index: int
    message: str
    timestamp: float = 0


# ══════════════════════════════════════════════════════════════════════════════
# TELEGRAM ALERTS
# ══════════════════════════════════════════════════════════════════════════════

def send_telegram(message: str) -> bool:
    """Send message via Telegram."""
    try:
        import urllib.request
        import urllib.error
        
        bot_token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
        chat_id = os.environ.get('TELEGRAM_CHAT_ID', '')
        
        if not bot_token or not chat_id:
            return False
        
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = json.dumps({'chat_id': chat_id, 'text': message}).encode('utf-8')
        
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
        urllib.request.urlopen(req, timeout=10)
        return True
    except urllib.error.HTTPError as e:
        if e.code == 400:
            log.warning("Telegram 400 — send /start to @omnibrainsignals_free from your Telegram app first")
        else:
            log.warning(f"Telegram HTTP {e.code}: {e}")
        return False
    except Exception as e:
        log.warning(f"Telegram send failed: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# MT5 SYNC GUARD
# ══════════════════════════════════════════════════════════════════════════════

class MT5SyncGuard:
    """
    Split-brain guard for MT5 data synchronization.
    
    Per-symbol, per-timeframe locking:
      - Parallel assets allowed (XAUUSD + EURUSD can sync simultaneously)
      - Same asset/timeframe blocks (two XAUUSD/H1 cannot sync together)
    
    Usage:
        guard = MT5SyncGuard()
        result = guard.safe_fetch('XAUUSD', 'H1')
        if result.status == 'OK':
            process_candles(result.candles)
    """
    
    def __init__(self):
        self._locks: Dict[str, int] = {}  # lock_key -> fd
        self._cache: Dict[str, List[Dict]] = {}  # cache_key -> candles
        self._cache_time: Dict[str, float] = {}
        self._sync_status: Dict[str, SyncResult] = {}
        self._csv_fallback: Dict[str, bool] = {}  # track CSV fallback mode
        self._error_count: Dict[str, int] = {}
        
        # Register cleanup
        atexit.register(self._cleanup_all)
        
        log.info(f"[MT5] SyncGuard initialized for {len(ASSETS)} assets × {len(TIMEFRAMES)} timeframes")
    
    def _get_lock_path(self, symbol: str, tf: str) -> Path:
        """Get lock file path for symbol/timeframe."""
        return Path(LOCK_DIR) / f"mt5_sync_{symbol}_{tf}.lock"
    
    def _get_cache_key(self, symbol: str, tf: str) -> str:
        """Get cache key."""
        return f"{symbol}_{tf}"
    
    def _get_csv_path(self, symbol: str, tf: str) -> Path:
        """Get CSV fallback path."""
        return CSV_DIR / f"{symbol}_{tf}.csv"
    
    def _acquire_lock(self, symbol: str, tf: str) -> Tuple[bool, float]:
        """
        Acquire atomic lock for symbol/timeframe.
        Returns: (acquired, lock_time_ms)
        """
        start = time.time()
        lock_path = self._get_lock_path(symbol, tf)
        lock_key = self._get_cache_key(symbol, tf)
        
        try:
            # Check for stale lock
            if lock_path.exists():
                lock_age = time.time() - lock_path.stat().st_mtime
                if lock_age > LOCK_TIMEOUT_S * 2:
                    log.warning(f"[MT5] Stale lock detected for {lock_key} ({lock_age:.1f}s), cleaning")
                    lock_path.unlink(missing_ok=True)
            
            # Atomic lock creation
            fd = os.open(
                str(lock_path),
                os.O_CREAT | os.O_EXCL | os.O_WRONLY
            )
            
            # Write owner info
            owner_info = {
                'pid': os.getpid(),
                'symbol': symbol,
                'timeframe': tf,
                'acquired_at': time.time()
            }
            os.write(fd, json.dumps(owner_info).encode())
            os.fsync(fd)
            
            self._locks[lock_key] = fd
            lock_ms = (time.time() - start) * 1000
            
            log.debug(f"[MT5] Lock acquired: {lock_key} ({lock_ms:.1f}ms)")
            return True, lock_ms
            
        except FileExistsError:
            lock_ms = (time.time() - start) * 1000
            log.debug(f"[MT5] Lock held by another process: {lock_key}")
            return False, lock_ms
            
        except Exception as e:
            lock_ms = (time.time() - start) * 1000
            log.error(f"[MT5] Lock error for {lock_key}: {e}")
            return False, lock_ms
    
    def _release_lock(self, symbol: str, tf: str):
        """Release lock for symbol/timeframe."""
        lock_key = self._get_cache_key(symbol, tf)
        lock_path = self._get_lock_path(symbol, tf)
        
        fd = self._locks.pop(lock_key, None)
        if fd is not None:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)
            except Exception as e:
                log.debug(f"Failed to release lock: {e}")

        try:
            lock_path.unlink(missing_ok=True)
        except Exception as e:
            log.debug(f"Failed to unlink {lock_path}: {e}")
    
    def _release_all_locks(self):
        """Release all held locks."""
        for lock_key in list(self._locks.keys()):
            parts = lock_key.split('_', 1)
            if len(parts) == 2:
                self._release_lock(parts[0], parts[1])
    
    # ══════════════════════════════════════════════════════════════════════════
    # CANDLE VALIDATION (Task 2)
    # ══════════════════════════════════════════════════════════════════════════
    
    def validate_candles(
        self,
        candles: List[Dict[str, Any]],
        symbol: str,
        tf: str
    ) -> Tuple[List[Dict[str, Any]], List[CandleValidation]]:
        """
        Validate candle data for quality issues.
        
        Returns:
            (validated_candles, warnings)
        """
        if not candles:
            return [], []
        
        warnings = []
        validated = []
        now = datetime.now(timezone.utc)
        future_limit = now + timedelta(minutes=FUTURE_CANDLE_BUFFER_MIN)
        
        # Sort by timestamp
        candles = sorted(candles, key=lambda c: c.get('timestamp', 0))
        
        seen_timestamps = set()
        last_timestamp = None
        gap_start = None
        
        for i, candle in enumerate(candles):
            ts = candle.get('timestamp', 0)
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            volume = candle.get('volume', 0)
            
            # Check: FUTURE candle
            if dt > future_limit:
                warnings.append(CandleValidation(
                    status=CandleStatus.FUTURE,
                    candle_index=i,
                    message=f"Future candle rejected: {dt.isoformat()} > {future_limit.isoformat()}",
                    timestamp=ts
                ))
                log.error(f"[MT5] FUTURE candle rejected: {symbol}/{tf} at {dt.isoformat()}")
                continue  # Reject hard
            
            # Check: DUPLICATE timestamp
            if ts in seen_timestamps:
                warnings.append(CandleValidation(
                    status=CandleStatus.DUPLICATE,
                    candle_index=i,
                    message=f"Duplicate timestamp: {dt.isoformat()}",
                    timestamp=ts
                ))
                log.debug(f"[MT5] DUPLICATE candle deduped: {symbol}/{tf} at {dt.isoformat()}")
                continue  # Skip duplicate
            
            seen_timestamps.add(ts)
            
            # Check: ZERO volume
            zero_vol = volume == 0
            if zero_vol:
                warnings.append(CandleValidation(
                    status=CandleStatus.ZERO_VOL,
                    candle_index=i,
                    message=f"Zero volume candle flagged: {dt.isoformat()}",
                    timestamp=ts
                ))
                log.debug(f"[MT5] ZERO_VOL candle flagged: {symbol}/{tf} at {dt.isoformat()}")
                candle = candle.copy()
                candle['_invalid'] = True
                candle['_reason'] = 'ZERO_VOL'
            
            # Check: GAP detection
            if last_timestamp is not None:
                gap_seconds = ts - last_timestamp
                expected_interval = self._get_expected_interval(tf)
                
                if gap_seconds > expected_interval * (MAX_GAP_BARS + 1):
                    missing_bars = int(gap_seconds / expected_interval) - 1
                    gap_start_dt = datetime.fromtimestamp(last_timestamp, tz=timezone.utc)
                    
                    warnings.append(CandleValidation(
                        status=CandleStatus.GAP,
                        candle_index=i,
                        message=f"Gap detected: {missing_bars} bars missing from {gap_start_dt.isoformat()} to {dt.isoformat()}",
                        timestamp=ts
                    ))
                    
                    log.warning(f"[MT5] GAP detected: {symbol}/{tf} - {missing_bars} bars missing")
                    
                    # Telegram alert for gaps
                    send_telegram(
                        f"⚠️ CANDLE GAP DETECTED\n"
                        f"Asset: {symbol}\n"
                        f"TF: {tf}\n"
                        f"Missing: {missing_bars} bars\n"
                        f"From: {gap_start_dt.strftime('%Y-%m-%d %H:%M')}\n"
                        f"To: {dt.strftime('%Y-%m-%d %H:%M')}\n"
                        f"Time: {now.strftime('%Y-%m-%d %H:%M:%S UTC')}"
                    )
            
            last_timestamp = ts
            validated.append(candle)
        
        # Check: STALE detection (no new candles)
        if validated:
            last_candle_ts = validated[-1].get('timestamp', 0)
            candle_age = now.timestamp() - last_candle_ts
            expected_interval = self._get_expected_interval(tf)
            
            if candle_age > expected_interval * 3:
                warnings.append(CandleValidation(
                    status=CandleStatus.STALE,
                    candle_index=len(validated) - 1,
                    message=f"Stale data: last candle {candle_age:.0f}s old",
                    timestamp=last_candle_ts
                ))
                log.warning(f"[MT5] STALE data: {symbol}/{tf} - {candle_age:.0f}s since last candle")
        
        return validated, warnings
    
    def _get_expected_interval(self, tf: str) -> int:
        """Get expected interval in seconds for timeframe."""
        intervals = {
            'M1': 60, 'M5': 300, 'M15': 900, 'M30': 1800,
            'H1': 3600, 'H4': 14400, 'D1': 86400
        }
        return intervals.get(tf, 3600)
    
    # ══════════════════════════════════════════════════════════════════════════
    # MT5 RECONNECT HANDLER (Task 3)
    # ══════════════════════════════════════════════════════════════════════════
    
    def _reconnect_handler(self, symbol: str, tf: str) -> bool:
        """
        Handle MT5 connection drops.
        
        Returns: True if reconnected, False if fallback to CSV
        """
        lock_key = self._get_cache_key(symbol, tf)
        self._error_count[lock_key] = self._error_count.get(lock_key, 0) + 1
        
        # Release lock immediately to prevent deadlock
        self._release_lock(symbol, tf)
        log.warning(f"[MT5] Releasing lock for {lock_key} due to connection drop")
        
        for attempt in range(1, RECONNECT_ATTEMPTS + 1):
            log.info(f"[MT5] Reconnect attempt {attempt}/{RECONNECT_ATTEMPTS} for {lock_key}")
            time.sleep(RECONNECT_DELAY_S)
            
            try:
                # Try to reconnect to MT5
                if self._test_mt5_connection():
                    log.info(f"[MT5] Reconnected successfully on attempt {attempt}")
                    self._error_count[lock_key] = 0
                    return True
            except Exception as e:
                log.error(f"[MT5] Reconnect attempt {attempt} failed: {e}")
        
        # All attempts failed - switch to CSV fallback
        self._csv_fallback[lock_key] = True
        log.error(f"[MT5] All {RECONNECT_ATTEMPTS} reconnect attempts failed for {lock_key}")
        
        # Log full traceback
        with open(ERROR_LOG, 'a') as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"[{datetime.now(timezone.utc).isoformat()}] MT5 RECONNECT FAILED\n")
            f.write(f"Asset: {symbol}\n")
            f.write(f"TF: {tf}\n")
            f.write(f"Attempts: {RECONNECT_ATTEMPTS}\n")
            f.write(f"Traceback:\n{traceback.format_exc()}\n")
        
        # Telegram alert
        now = datetime.now(timezone.utc)
        send_telegram(
            f"⚠️ MT5 DISCONNECT\n"
            f"Asset: {symbol}\n"
            f"Timeframe: {tf}\n"
            f"Attempts: {RECONNECT_ATTEMPTS}/{RECONNECT_ATTEMPTS} failed\n"
            f"Fallback: CSV MODE ACTIVE\n"
            f"Time: {now.strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )
        
        return False
    
    def _test_mt5_connection(self) -> bool:
        """Test if MT5 connection is alive."""
        try:
            # Try to import MetaTrader5
            import MetaTrader5 as mt5
            
            if not mt5.terminal_info().connected:
                return False
            
            # Quick test - get account info
            account = mt5.account_info()
            return account is not None
            
        except ImportError:
            # MT5 not available, assume OK for CSV fallback
            return True
        except Exception:
            return False
    
    # ══════════════════════════════════════════════════════════════════════════
    # CSV FALLBACK
    # ══════════════════════════════════════════════════════════════════════════
    
    def _load_csv_fallback(self, symbol: str, tf: str) -> List[Dict[str, Any]]:
        """Load candles from CSV fallback file."""
        csv_path = self._get_csv_path(symbol, tf)
        
        if not csv_path.exists():
            log.warning(f"[MT5] No CSV fallback for {symbol}/{tf}")
            return []
        
        try:
            import csv
            candles = []
            
            with open(csv_path, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    candles.append({
                        'timestamp': int(row.get('timestamp', 0)),
                        'open': float(row.get('open', 0)),
                        'high': float(row.get('high', 0)),
                        'low': float(row.get('low', 0)),
                        'close': float(row.get('close', 0)),
                        'volume': float(row.get('volume', 0))
                    })
            
            log.info(f"[MT5] Loaded {len(candles)} candles from CSV fallback: {symbol}/{tf}")
            return candles[-100:]  # Last 100 candles
            
        except Exception as e:
            log.error(f"[MT5] CSV load error: {e}")
            return []
    
    def _save_csv_fallback(self, symbol: str, tf: str, candles: List[Dict[str, Any]]):
        """Save candles to CSV fallback file."""
        csv_path = self._get_csv_path(symbol, tf)
        
        try:
            import csv
            
            with open(csv_path, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                writer.writeheader()
                for candle in candles:
                    writer.writerow(candle)
            
            log.debug(f"[MT5] Saved {len(candles)} candles to CSV: {symbol}/{tf}")
            
        except Exception as e:
            log.error(f"[MT5] CSV save error: {e}")
    
    # ══════════════════════════════════════════════════════════════════════════
    # SAFE FETCH
    # ══════════════════════════════════════════════════════════════════════════
    
    def safe_fetch(self, symbol: str, tf: str) -> SyncResult:
        """
        Safely fetch candles with split-brain protection.
        
        Pipeline:
          1. Acquire lock
          2. Fetch from MT5 (or CSV fallback)
          3. Validate candles
          4. Save to CSV/cache
          5. Release lock
        
        Returns:
            SyncResult with candles and status
        """
        lock_key = self._get_cache_key(symbol, tf)
        result = SyncResult(symbol=symbol, timeframe=tf, status='ERROR')
        
        # Check if in CSV fallback mode
        if self._csv_fallback.get(lock_key, False):
            candles = self._load_csv_fallback(symbol, tf)
            result.candles_count = len(candles)
            result.source = 'CSV_FALLBACK'
            result.status = 'OK' if candles else 'NO_DATA'
            self._cache[lock_key] = candles
            self._cache_time[lock_key] = time.time()
            return result
        
        # Acquire lock
        acquired, lock_ms = self._acquire_lock(symbol, tf)
        result.lock_ms = lock_ms
        
        if not acquired:
            # Lock timeout - return cached data if available
            cached = self._cache.get(lock_key, [])
            if cached:
                result.status = 'CACHED'
                result.candles_count = len(cached)
                result.source = 'CACHE'
                log.warning(f"[MT5] Lock timeout for {lock_key}, using cache ({len(cached)} candles)")
            else:
                result.status = 'LOCK_TIMEOUT'
                log.warning(f"[MT5] Lock timeout for {lock_key}, no cache available")
            return result
        
        try:
            # Fetch candles
            fetch_start = time.time()
            candles = self._fetch_from_mt5(symbol, tf)
            result.fetch_ms = (time.time() - fetch_start) * 1000
            
            if candles is None:
                # MT5 connection failed - try reconnect
                if not self._reconnect_handler(symbol, tf):
                    # Switched to CSV fallback
                    candles = self._load_csv_fallback(symbol, tf)
                    result.source = 'CSV_FALLBACK'
                else:
                    # Reconnected - try again
                    candles = self._fetch_from_mt5(symbol, tf)
                    if candles is None:
                        result.status = 'FETCH_FAILED'
                        return result
            
            if not candles:
                result.status = 'NO_DATA'
                return result
            
            # Validate candles
            validated, warnings = self._validate_and_report(candles, symbol, tf)
            result.validation_warnings = [w.message for w in warnings]
            
            # Save to CSV fallback
            self._save_csv_fallback(symbol, tf, validated)
            
            # Update cache
            self._cache[lock_key] = validated
            self._cache_time[lock_key] = time.time()
            
            result.candles_count = len(validated)
            result.status = 'OK'
            
            # Update sync status
            self._sync_status[lock_key] = result
            
            return result
            
        except Exception as e:
            result.status = 'ERROR'
            result.error = str(e)
            log.error(f"[MT5] Fetch error for {lock_key}: {e}")
            return result
            
        finally:
            # Always release lock
            self._release_lock(symbol, tf)
    
    def _fetch_from_mt5(self, symbol: str, tf: str) -> Optional[List[Dict[str, Any]]]:
        """Fetch candles from MT5."""
        try:
            import MetaTrader5 as mt5
            
            # Initialize MT5 if needed
            if not mt5.terminal_info().connected:
                login = int(os.environ.get('MT5_LOGIN', '0'))
                password = os.environ.get('MT5_PASSWORD', '')
                server = os.environ.get('MT5_SERVER', '')
                
                if not mt5.initialize(login=int(login), password=password, server=server):
                    log.error(f"[MT5] Initialize failed: {mt5.last_error()}")
                    return None
            
            # Map timeframe
            tf_map = {
                'M1': mt5.TIMEFRAME_M1, 'M5': mt5.TIMEFRAME_M5,
                'M15': mt5.TIMEFRAME_M15, 'M30': mt5.TIMEFRAME_M30,
                'H1': mt5.TIMEFRAME_H1, 'H4': mt5.TIMEFRAME_H4,
                'D1': mt5.TIMEFRAME_D1
            }
            
            mt5_tf = tf_map.get(tf, mt5.TIMEFRAME_H1)
            
            # Fetch rates
            rates = mt5.copy_rates_from_pos(symbol, mt5_tf, 0, 100)
            
            if rates is None or len(rates) == 0:
                log.warning(f"[MT5] No data returned for {symbol}/{tf}")
                return []
            
            # Convert to dict format
            candles = []
            for rate in rates:
                candles.append({
                    'timestamp': int(rate['time']),
                    'open': float(rate['open']),
                    'high': float(rate['high']),
                    'low': float(rate['low']),
                    'close': float(rate['close']),
                    'volume': float(rate.get('tick_volume', 0))
                })
            
            return candles
            
        except ImportError:
            log.warning("[MT5] MetaTrader5 not installed, using CSV fallback")
            return self._load_csv_fallback(symbol, tf)
        except Exception as e:
            log.error(f"[MT5] MT5 fetch error: {e}")
            return None
    
    def _validate_and_report(
        self,
        candles: List[Dict[str, Any]],
        symbol: str,
        tf: str
    ) -> Tuple[List[Dict[str, Any]], List[CandleValidation]]:
        """Validate candles and report warnings."""
        validated, warnings = self.validate_candles(candles, symbol, tf)
        
        # Log warnings
        for w in warnings:
            if w.status == CandleStatus.STALE:
                log.warning(f"[MT5] {symbol}/{tf} STALE: {w.message}")
            elif w.status == CandleStatus.FUTURE:
                log.error(f"[MT5] {symbol}/{tf} FUTURE: {w.message}")
            elif w.status == CandleStatus.GAP:
                log.warning(f"[MT5] {symbol}/{tf} GAP: {w.message}")
        
        return validated, warnings
    
    # ══════════════════════════════════════════════════════════════════════════
    # STATUS & MONITORING
    # ══════════════════════════════════════════════════════════════════════════
    
    def get_status(self) -> Dict[str, Any]:
        """Get current sync status for all assets."""
        status = {}
        
        for symbol in ASSETS:
            for tf in TIMEFRAMES:
                key = self._get_cache_key(symbol, tf)
                sync = self._sync_status.get(key)
                
                if sync:
                    status[key] = {
                        'status': sync.status,
                        'source': sync.source,
                        'lock_ms': sync.lock_ms,
                        'fetch_ms': sync.fetch_ms,
                        'candles': sync.candles_count,
                        'warnings': len(sync.validation_warnings)
                    }
                else:
                    status[key] = {
                        'status': 'NOT_SYNCED',
                        'source': 'NONE',
                        'lock_ms': 0,
                        'fetch_ms': 0,
                        'candles': 0,
                        'warnings': 0
                    }
        
        return status
    
    def get_panel_display(self) -> str:
        """Get ASCII panel display for status."""
        lines = [
            '╔══════════════════════════════════════════╗',
            '║        MT5 SYNC GUARD STATUS             ║',
            '╠══════════════════════════════════════════╣',
        ]
        
        for symbol in ASSETS:
            for tf in TIMEFRAMES:
                key = self._get_cache_key(symbol, tf)
                sync = self._sync_status.get(key)
                
                if sync:
                    if sync.status == 'OK':
                        icon = '🟢'
                        detail = f'{sync.lock_ms:.1f}ms'
                    elif sync.status == 'STALE':
                        icon = '🟡'
                        detail = 'cache'
                    elif sync.status in ('LOCK_TIMEOUT', 'CACHED'):
                        icon = '🟡'
                        detail = 'cache'
                    elif sync.status == 'CSV_FALLBACK' or sync.source == 'CSV_FALLBACK':
                        icon = '🔴'
                        detail = 'CSV fallback'
                    else:
                        icon = '🔴'
                        detail = sync.status
                else:
                    icon = '⚪'
                    detail = 'not synced'
                
                lines.append(f'║ {symbol:8s}/{tf:3s} {icon} {detail:16s} ║')
        
        lines.append('╚══════════════════════════════════════════╝')
        
        return '\n'.join(lines)
    
    def _cleanup_all(self):
        """Cleanup all locks on exit."""
        self._release_all_locks()
        log.info("[MT5] All locks released on exit")


# ══════════════════════════════════════════════════════════════════════════════
# GLOBAL INSTANCE
# ══════════════════════════════════════════════════════════════════════════════

_guard: Optional[MT5SyncGuard] = None


def get_mt5_guard() -> MT5SyncGuard:
    """Get or create global MT5 sync guard."""
    global _guard
    if _guard is None:
        _guard = MT5SyncGuard()
    return _guard


def safe_fetch(symbol: str, tf: str) -> SyncResult:
    """Convenience function for safe fetch."""
    guard = get_mt5_guard()
    return guard.safe_fetch(symbol, tf)


# ══════════════════════════════════════════════════════════════════════════════
# CLI TEST
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import argparse
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )
    
    parser = argparse.ArgumentParser(description='MT5 Sync Guard')
    parser.add_argument('--test', action='store_true', help='Test mode')
    parser.add_argument('--once', action='store_true', help='Single sync')
    parser.add_argument('--status', action='store_true', help='Show status')
    args = parser.parse_args()
    
    guard = MT5SyncGuard()
    
    if args.test or args.once:
        print("=" * 60)
        print("  MT5 SYNC GUARD - TEST")
        print("=" * 60)
        
        # Test single fetch
        for symbol in ['XAUUSD', 'EURUSD']:
            for tf in ['H1']:
                print(f"\nFetching {symbol}/{tf}...")
                result = guard.safe_fetch(symbol, tf)
                print(f"  Status: {result.status}")
                print(f"  Source: {result.source}")
                print(f"  Lock: {result.lock_ms:.1f}ms")
                print(f"  Fetch: {result.fetch_ms:.1f}ms")
                print(f"  Candles: {result.candles_count}")
                if result.validation_warnings:
                    print(f"  Warnings: {len(result.validation_warnings)}")
                    for w in result.validation_warnings[:3]:
                        print(f"    - {w}")
        
        # Show panel
        print(f"\n{guard.get_panel_display()}")
        
        print("\n" + "=" * 60)
    
    elif args.status:
        print(guard.get_panel_display())
    
    else:
        parser.print_help()
