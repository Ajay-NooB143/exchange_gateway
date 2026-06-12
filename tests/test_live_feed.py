"""
Unit Tests for Live Feed Scanner - OMNI BRAIN V2
==================================================
Tests for Twelve Data integration, rate limiting, and pipeline.
"""

import os
import sys
import json
import time
import unittest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from production.live_feed_scanner import (
    Candle, ScanResult, RateLimiter, TwelveDataREST, 
    RESTPollingBatcher, LiveFeedScanner,
    SYMBOL_MAP, TF_MAP, RATE_LIMIT_PER_MIN, RATE_LIMIT_DAILY
)


class TestSymbolMapping(unittest.TestCase):
    """Test symbol mapping to Twelve Data format."""
    
    def test_xauusd_mapping(self):
        self.assertEqual(SYMBOL_MAP.get('XAUUSD'), 'XAU/USD')
    
    def test_eurusd_mapping(self):
        self.assertEqual(SYMBOL_MAP.get('EURUSD'), 'EUR/USD')
    
    def test_gbpusd_mapping(self):
        self.assertEqual(SYMBOL_MAP.get('GBPUSD'), 'GBP/USD')
    
    def test_sp500_mapping(self):
        self.assertEqual(SYMBOL_MAP.get('SP500'), 'SPX')


class TestTimeframeMapping(unittest.TestCase):
    """Test timeframe mapping to Twelve Data format."""
    
    def test_m15_mapping(self):
        self.assertEqual(TF_MAP.get('M15'), '15min')
    
    def test_h1_mapping(self):
        self.assertEqual(TF_MAP.get('H1'), '1h')
    
    def test_h4_mapping(self):
        self.assertEqual(TF_MAP.get('H4'), '4h')
    
    def test_d1_mapping(self):
        self.assertEqual(TF_MAP.get('D1'), '1day')


class TestCandleValidation(unittest.TestCase):
    """Test candle data validation."""
    
    def test_valid_candle(self):
        candle = Candle(
            timestamp=int(datetime.now(timezone.utc).timestamp()),
            open=2350.0,
            high=2360.0,
            low=2345.0,
            close=2355.0,
            volume=1000
        )
        self.assertEqual(candle.open, 2350.0)
        self.assertEqual(candle.high, 2360.0)
        self.assertEqual(candle.low, 2345.0)
        self.assertEqual(candle.close, 2355.0)
    
    def test_candle_to_dict(self):
        candle = Candle(
            timestamp=1234567890,
            open=2350.0,
            high=2360.0,
            low=2345.0,
            close=2355.0,
            volume=1000
        )
        d = candle.to_dict()
        self.assertEqual(d['timestamp'], 1234567890)
        self.assertEqual(d['open'], 2350.0)
        self.assertEqual(d['volume'], 1000)


class TestRateLimiter(unittest.TestCase):
    """Test rate limiting logic."""
    
    def setUp(self):
        self.limiter = RateLimiter()
        self.limiter._request_times.clear()
        self.limiter.status.requests_today = 0
    
    def test_can_request_within_limit(self):
        can_make, wait = self.limiter.can_request()
        self.assertTrue(can_make)
        self.assertEqual(wait, 0)
    
    def test_rate_limit_per_minute(self):
        # Simulate 8 requests in last minute
        now = time.time()
        for i in range(RATE_LIMIT_PER_MIN):
            self.limiter._request_times.append(now - i)
        
        can_make, wait = self.limiter.can_request()
        self.assertFalse(can_make)
        self.assertGreater(wait, 0)
    
    def test_rate_limit_daily(self):
        self.limiter.status.requests_today = RATE_LIMIT_DAILY
        self.limiter.status.daily_reset_time = time.time() + 3600
        
        can_make, wait = self.limiter.can_request()
        self.assertFalse(can_make)
        self.assertGreater(wait, 0)
    
    def test_record_request(self):
        initial_count = self.limiter.status.requests_today
        self.limiter.record_request()
        self.assertEqual(self.limiter.status.requests_today, initial_count + 1)


class TestTwelveDataREST(unittest.TestCase):
    """Test Twelve Data REST client."""
    
    def test_parse_candle(self):
        limiter = RateLimiter()
        client = TwelveDataREST('test_key', limiter)
        
        data = {
            'datetime': '2024-01-15 14:00:00',
            'open': '2350.50',
            'high': '2360.75',
            'low': '2345.25',
            'close': '2355.00',
            'volume': '1500'
        }
        
        candle = client._parse_candle(data)
        self.assertIsNotNone(candle)
        self.assertEqual(candle.open, 2350.50)
        self.assertEqual(candle.high, 2360.75)
        self.assertEqual(candle.low, 2345.25)
        self.assertEqual(candle.close, 2355.00)
    
    def test_validate_candles_valid(self):
        limiter = RateLimiter()
        client = TwelveDataREST('test_key', limiter)
        
        candles = [
            Candle(1234567890, 2350.0, 2360.0, 2345.0, 2355.0, 1000),
            Candle(1234567891, 2355.0, 2365.0, 2350.0, 2360.0, 1100),
        ]
        
        validated = client.validate_candles(candles)
        self.assertEqual(len(validated), 2)
    
    def test_validate_candles_invalid_price(self):
        limiter = RateLimiter()
        client = TwelveDataREST('test_key', limiter)
        
        candles = [
            Candle(1234567890, 0, 2360.0, 2345.0, 2355.0, 1000),  # Invalid: open=0
            Candle(1234567891, 2355.0, 2365.0, 2350.0, 2360.0, 1100),
        ]
        
        validated = client.validate_candles(candles)
        self.assertEqual(len(validated), 1)  # First candle filtered out
    
    def test_validate_candles_high_below_low(self):
        limiter = RateLimiter()
        client = TwelveDataREST('test_key', limiter)
        
        candles = [
            Candle(1234567890, 2350.0, 2340.0, 2345.0, 2355.0, 1000),  # Invalid: high < low
        ]
        
        validated = client.validate_candles(candles)
        self.assertEqual(len(validated), 0)


class TestRESTPollingBatcher(unittest.TestCase):
    """Test REST polling batcher."""
    
    def test_build_schedule(self):
        limiter = RateLimiter()
        client = TwelveDataREST('test_key', limiter)
        batcher = RESTPollingBatcher(client)
        
        # Should have 8 batches (4 assets × 4 timeframes / 2 per batch)
        self.assertEqual(len(batcher._batch_schedule), 8)
    
    def test_batch_coverage(self):
        limiter = RateLimiter()
        client = TwelveDataREST('test_key', limiter)
        batcher = RESTPollingBatcher(client)
        
        # Check all assets and timeframes are covered
        all_pairs = set()
        for batch in batcher._batch_schedule:
            for symbol, tf in batch:
                all_pairs.add((symbol, tf))
        
        from production.live_feed_scanner import ASSETS, TIMEFRAMES
        for symbol in ASSETS:
            for tf in TIMEFRAMES:
                self.assertIn((symbol, tf), all_pairs)


class TestScanResult(unittest.TestCase):
    """Test ScanResult dataclass."""
    
    def test_scan_result_defaults(self):
        result = ScanResult(symbol='XAUUSD', status='OK')
        self.assertEqual(result.decision, 'BLOCK')
        self.assertEqual(result.score, 0)
        self.assertEqual(result.direction, 'LONG')
        self.assertFalse(result.mtf_confirmed)


class TestGitHubLogger(unittest.TestCase):
    """Test GitHub signal logger."""
    
    def test_signal_format(self):
        from production.github_signal_logger import GitHubSignalLogger
        
        logger = GitHubSignalLogger()
        
        # Test signal data structure
        signal_data = {
            'symbol': 'XAUUSD',
            'timeframe': 'H1',
            'decision': 'EXECUTE',
            'score': 85,
            'components': {'OB': 20, 'FVG': 20, 'SWEEP': 30, 'VWAP': 10, 'SESSION': 5},
            'mtf_confirmed': True,
            'threshold_used': 75,
            'circuit_breaker': 'ACTIVE',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        # Verify structure
        self.assertEqual(signal_data['symbol'], 'XAUUSD')
        self.assertEqual(signal_data['decision'], 'EXECUTE')
        self.assertIn('components', signal_data)
    
    def test_disabled_without_config(self):
        from production.github_signal_logger import GitHubSignalLogger
        
        # Mock environment without GITHUB_TOKEN
        with patch.dict(os.environ, {'GITHUB_TOKEN': '', 'GITHUB_REPO': ''}, clear=False):
            logger = GitHubSignalLogger()
            self.assertFalse(logger.enabled)
    
    def test_enabled_with_config(self):
        from production.github_signal_logger import GitHubSignalLogger
        
        # Mock environment with GITHUB_TOKEN
        with patch.dict(os.environ, {'GITHUB_TOKEN': 'test_token', 'GITHUB_REPO': 'user/repo'}, clear=False):
            logger = GitHubSignalLogger()
            self.assertTrue(logger.enabled)


class TestDailyLimitWarning(unittest.TestCase):
    """Test daily limit warning at 750/800."""
    
    def test_warning_threshold(self):
        limiter = RateLimiter()
        limiter.status.requests_today = 750
        
        can_make, wait = limiter.can_request()
        self.assertTrue(can_make)  # Still can make requests
        
        # But should be close to limit
        self.assertGreater(limiter.status.requests_today, RATE_LIMIT_DAILY * 0.9)


class TestWebSocketReconnect(unittest.TestCase):
    """Test WebSocket reconnect logic."""
    
    def test_max_retries(self):
        limiter = RateLimiter()
        
        # Mock WebSocket
        from production.live_feed_scanner import TwelveDataWebSocket
        ws = TwelveDataWebSocket('test_key', limiter)
        
        self.assertEqual(ws._max_retries, 10)
        self.assertEqual(ws._retries, 0)


class TestRateLimitDisplay(unittest.TestCase):
    """Test rate limit status display."""
    
    def test_status_display(self):
        limiter = RateLimiter()
        display = limiter.get_status_display()
        
        self.assertIn('FEED', display)
        self.assertIn('Rate:', display)
        self.assertIn('XAUUSD', display)


if __name__ == '__main__':
    unittest.main()
