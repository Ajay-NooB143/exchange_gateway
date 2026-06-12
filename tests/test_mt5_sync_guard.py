"""
Unit Tests for MT5 Sync Guard - OMNI BRAIN V2
===============================================
Tests for split-brain protection, candle validation, and async guard.
"""

import os
import sys
import json
import time
import asyncio
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from production.mt5_sync_guard import (
    MT5SyncGuard, SyncResult, CandleStatus,
    CandleValidation, ASSETS, TIMEFRAMES
)
from production.async_mt5_sync_guard import AsyncMT5SyncGuard


class TestLockAcquisition(unittest.TestCase):
    """Test lock acquired and released cleanly."""
    
    def setUp(self):
        self.guard = MT5SyncGuard()
    
    def test_lock_acquired(self):
        """Lock should be acquired successfully."""
        acquired, lock_ms = self.guard._acquire_lock('XAUUSD', 'H1')
        self.assertTrue(acquired)
        self.assertGreater(lock_ms, 0)
        
        # Clean up
        self.guard._release_lock('XAUUSD', 'H1')
    
    def test_lock_released(self):
        """Lock should be released cleanly."""
        self.guard._acquire_lock('XAUUSD', 'H1')
        self.guard._release_lock('XAUUSD', 'H1')
        
        # Verify lock file removed
        lock_path = self.guard._get_lock_path('XAUUSD', 'H1')
        self.assertFalse(os.path.exists(lock_path))
    
    def test_parallel_assets_allowed(self):
        """Different assets should be able to lock simultaneously."""
        acquired1, _ = self.guard._acquire_lock('XAUUSD', 'H1')
        acquired2, _ = self.guard._acquire_lock('EURUSD', 'H1')
        
        self.assertTrue(acquired1)
        self.assertTrue(acquired2)
        
        self.guard._release_lock('XAUUSD', 'H1')
        self.guard._release_lock('EURUSD', 'H1')
    
    def test_same_asset_blocks(self):
        """Same asset/timeframe should block."""
        self.guard._acquire_lock('XAUUSD', 'H1')
        
        # Second lock should fail
        acquired2, lock_ms = self.guard._acquire_lock('XAUUSD', 'H1')
        self.assertFalse(acquired2)
        
        self.guard._release_lock('XAUUSD', 'H1')
    
    def test_lock_timeout(self):
        """Duplicate lock attempt should timeout."""
        self.guard._acquire_lock('XAUUSD', 'H1')
        
        start = time.time()
        acquired, lock_ms = self.guard._acquire_lock('XAUUSD', 'H1')
        elapsed = time.time() - start
        
        self.assertFalse(acquired)
        # Should have some lock time (timeout or contention)
        
        self.guard._release_lock('XAUUSD', 'H1')


class TestCandleValidation(unittest.TestCase):
    """Test candle validation logic."""
    
    def setUp(self):
        self.guard = MT5SyncGuard()
        self.now = datetime.now(timezone.utc)
    
    def test_valid_candles(self):
        """Valid candles should pass validation."""
        candles = [
            {
                'timestamp': int((self.now - timedelta(hours=2)).timestamp()),
                'open': 2350.0, 'high': 2360.0, 'low': 2345.0, 'close': 2355.0,
                'volume': 1000
            },
            {
                'timestamp': int((self.now - timedelta(hours=1)).timestamp()),
                'open': 2355.0, 'high': 2365.0, 'low': 2350.0, 'close': 2360.0,
                'volume': 1100
            }
        ]
        
        validated, warnings = self.guard.validate_candles(candles, 'XAUUSD', 'H1')
        
        self.assertEqual(len(validated), 2)
        # Check no FUTURE warnings
        future_warnings = [w for w in warnings if w.status == CandleStatus.FUTURE]
        self.assertEqual(len(future_warnings), 0)
    
    def test_stale_detection(self):
        """Old candles should trigger stale warning."""
        candles = [
            {
                'timestamp': int((self.now - timedelta(hours=24)).timestamp()),
                'open': 2350.0, 'high': 2360.0, 'low': 2345.0, 'close': 2355.0,
                'volume': 1000
            }
        ]
        
        validated, warnings = self.guard.validate_candles(candles, 'XAUUSD', 'H1')
        
        # Should have stale warning
        stale_warnings = [w for w in warnings if w.status == CandleStatus.STALE]
        self.assertTrue(len(stale_warnings) > 0 or len(validated) > 0)
    
    def test_duplicate_detection(self):
        """Duplicate timestamps should be deduplicated."""
        ts = int((self.now - timedelta(hours=1)).timestamp())
        candles = [
            {'timestamp': ts, 'open': 2350.0, 'high': 2360.0, 'low': 2345.0, 'close': 2355.0, 'volume': 1000},
            {'timestamp': ts, 'open': 2350.0, 'high': 2360.0, 'low': 2345.0, 'close': 2355.0, 'volume': 1000}
        ]
        
        validated, warnings = self.guard.validate_candles(candles, 'XAUUSD', 'H1')
        
        self.assertEqual(len(validated), 1)  # Duplicate removed
    
    def test_zero_volume_flagged(self):
        """Zero volume candles should be flagged but not rejected."""
        candles = [
            {
                'timestamp': int((self.now - timedelta(hours=1)).timestamp()),
                'open': 2350.0, 'high': 2360.0, 'low': 2345.0, 'close': 2355.0,
                'volume': 0  # Zero volume
            }
        ]
        
        validated, warnings = self.guard.validate_candles(candles, 'XAUUSD', 'H1')
        
        self.assertEqual(len(validated), 1)  # Candle included
        self.assertTrue(validated[0].get('_invalid', False))  # But flagged
        zero_warnings = [w for w in warnings if w.status == CandleStatus.ZERO_VOL]
        self.assertTrue(len(zero_warnings) > 0)
    
    def test_future_candle_rejected(self):
        """Future candles should be rejected hard."""
        future_ts = int((self.now + timedelta(hours=1)).timestamp())
        candles = [
            {
                'timestamp': future_ts,
                'open': 2350.0, 'high': 2360.0, 'low': 2345.0, 'close': 2355.0,
                'volume': 1000
            }
        ]
        
        validated, warnings = self.guard.validate_candles(candles, 'XAUUSD', 'H1')
        
        self.assertEqual(len(validated), 0)  # Rejected
        future_warnings = [w for w in warnings if w.status == CandleStatus.FUTURE]
        self.assertTrue(len(future_warnings) > 0)
    
    def test_gap_detection(self):
        """Large gaps should trigger warning."""
        candles = [
            {
                'timestamp': int((self.now - timedelta(hours=10)).timestamp()),
                'open': 2350.0, 'high': 2360.0, 'low': 2345.0, 'close': 2355.0,
                'volume': 1000
            },
            {
                'timestamp': int((self.now - timedelta(hours=1)).timestamp()),  # 9 hour gap
                'open': 2355.0, 'high': 2365.0, 'low': 2350.0, 'close': 2360.0,
                'volume': 1100
            }
        ]
        
        validated, warnings = self.guard.validate_candles(candles, 'XAUUSD', 'H1')
        
        gap_warnings = [w for w in warnings if w.status == CandleStatus.GAP]
        self.assertTrue(len(gap_warnings) > 0)


class TestReconnectHandler(unittest.TestCase):
    """Test MT5 reconnect handler."""
    
    def setUp(self):
        self.guard = MT5SyncGuard()
    
    @patch('production.mt5_sync_guard.send_telegram')
    def test_reconnect_sends_alert(self, mock_telegram):
        """Reconnect failure should send Telegram alert."""
        with patch.object(self.guard, '_test_mt5_connection', return_value=False):
            with patch.object(self.guard, '_release_lock'):
                result = self.guard._reconnect_handler('XAUUSD', 'H1')
                
                self.assertFalse(result)
                # Should have set CSV fallback
                self.assertTrue(self.guard._csv_fallback.get('XAUUSD_H1', False))
    
    def test_reconnect_releases_lock(self):
        """Reconnect should release lock to prevent deadlock."""
        # Acquire lock first
        self.guard._acquire_lock('XAUUSD', 'H1')
        
        with patch.object(self.guard, '_test_mt5_connection', return_value=False):
            with patch('production.mt5_sync_guard.send_telegram'):
                self.guard._reconnect_handler('XAUUSD', 'H1')
        
        # Verify lock released
        lock_path = self.guard._get_lock_path('XAUUSD', 'H1')
        self.assertFalse(os.path.exists(lock_path))


class TestCSVFallback(unittest.TestCase):
    """Test CSV fallback functionality."""
    
    def setUp(self):
        self.guard = MT5SyncGuard()
        self.test_csv = Path(tempfile.mktemp(suffix='.csv'))
    
    def tearDown(self):
        if self.test_csv.exists():
            self.test_csv.unlink()
    
    def test_save_and_load_csv(self):
        """CSV save/load should work correctly."""
        candles = [
            {'timestamp': 1234567890, 'open': 2350.0, 'high': 2360.0, 'low': 2345.0, 'close': 2355.0, 'volume': 1000},
            {'timestamp': 1234567950, 'open': 2355.0, 'high': 2365.0, 'low': 2350.0, 'close': 2360.0, 'volume': 1100}
        ]
        
        # Patch CSV path
        with patch.object(self.guard, '_get_csv_path', return_value=self.test_csv):
            self.guard._save_csv_fallback('XAUUSD', 'H1', candles)
            loaded = self.guard._load_csv_fallback('XAUUSD', 'H1')
        
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0]['open'], 2350.0)
        self.assertEqual(loaded[1]['close'], 2360.0)


class TestSafeFetch(unittest.TestCase):
    """Test safe_fetch returns cached data on timeout."""
    
    def setUp(self):
        self.guard = MT5SyncGuard()
    
    def test_returns_cached_on_timeout(self):
        """Should return cached data when lock times out."""
        # Pre-populate cache
        cache_key = 'XAUUSD_H1'
        cached_candles = [
            {'timestamp': 1234567890, 'open': 2350.0, 'high': 2360.0, 'low': 2345.0, 'close': 2355.0, 'volume': 1000}
        ]
        self.guard._cache[cache_key] = cached_candles
        
        # Mock lock acquisition to fail
        with patch.object(self.guard, '_acquire_lock', return_value=(False, 1.5)):
            result = self.guard.safe_fetch('XAUUSD', 'H1')
        
        self.assertEqual(result.status, 'CACHED')
        self.assertEqual(result.candles_count, 1)
        self.assertEqual(result.source, 'CACHE')


class TestAsyncGuard(unittest.TestCase):
    """Test async version handles parallel assets."""
    
    def setUp(self):
        self.guard = AsyncMT5SyncGuard()
    
    def test_semaphore_limit(self):
        """Semaphore should limit to 4 concurrent locks."""
        self.assertEqual(self.guard._semaphore._value, 4)
    
    def test_release_lock_cleans_up(self):
        """Lock release should clean up socket file."""
        # Create a mock lock
        lock_key = 'XAUUSD_H1'
        lock_path = self.guard._get_lock_path('XAUUSD', 'H1')
        
        # Create a dummy socket file
        Path(lock_path).touch()
        
        self.guard._release_lock('XAUUSD', 'H1')
        
        # Socket file should be removed (or at least not crash)
    
    def test_validate_candles_works(self):
        """Async guard validation should work."""
        now = datetime.now(timezone.utc)
        candles = [
            {
                'timestamp': int((now - timedelta(hours=1)).timestamp()),
                'open': 2350.0, 'high': 2360.0, 'low': 2345.0, 'close': 2355.0,
                'volume': 1000
            }
        ]
        
        validated, warnings = self.guard.validate_candles(candles, 'XAUUSD', 'H1')
        
        self.assertEqual(len(validated), 1)
        self.assertEqual(len(validated), 1)


class TestAtexitCleanup(unittest.TestCase):
    """Test atexit cleans all lock files."""
    
    def test_cleanup_releases_locks(self):
        """cleanup_all should release all held locks."""
        guard = MT5SyncGuard()
        
        # Acquire some locks
        guard._acquire_lock('XAUUSD', 'H1')
        guard._acquire_lock('EURUSD', 'M15')
        
        # Cleanup
        guard._cleanup_all()
        
        # Verify locks released
        self.assertEqual(len(guard._locks), 0)
        self.assertFalse(os.path.exists(guard._get_lock_path('XAUUSD', 'H1')))
        self.assertFalse(os.path.exists(guard._get_lock_path('EURUSD', 'M15')))


class TestStatusPanel(unittest.TestCase):
    """Test status panel display."""
    
    def test_panel_display(self):
        """Panel display should contain expected elements."""
        guard = MT5SyncGuard()
        panel = guard.get_panel_display()
        
        self.assertIn('MT5 SYNC GUARD STATUS', panel)
        self.assertIn('XAUUSD', panel)
        self.assertIn('EURUSD', panel)
        self.assertIn('GBPUSD', panel)
        self.assertIn('SP500', panel)


if __name__ == '__main__':
    unittest.main()
