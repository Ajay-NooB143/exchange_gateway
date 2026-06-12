"""
Tests for crypto assets expansion module.
"""

import os
import sys
import json
import time
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

os.environ.setdefault('LIVE_DATA_API_KEY', 'test_key_for_testing')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'production'))


class TestCryptoSymbolMapping:
    """Test crypto symbol mapping and constants."""

    def test_crypto_assets_present(self):
        from crypto_scanner import CRYPTO_ASSETS
        assert 'BTCUSD' in CRYPTO_ASSETS
        assert 'ETHUSD' in CRYPTO_ASSETS
        assert 'BNBUSD' in CRYPTO_ASSETS
        assert 'SOLUSD' in CRYPTO_ASSETS
        assert 'XRPUSD' in CRYPTO_ASSETS
        assert len(CRYPTO_ASSETS) == 5

    def test_symbol_map(self):
        from crypto_scanner import SYMBOL_MAP
        assert SYMBOL_MAP['BTCUSD'] == 'BTC/USD'
        assert SYMBOL_MAP['ETHUSD'] == 'ETH/USD'
        assert SYMBOL_MAP['XRPUSD'] == 'XRP/USD'

    def test_symbol_map_reverse(self):
        from crypto_scanner import SYMBOL_MAP_REVERSE
        assert SYMBOL_MAP_REVERSE['BTC/USD'] == 'BTCUSD'


class TestCryptoSpreadLimits:
    """Test crypto-specific spread filters."""

    def test_spread_limits_exist(self):
        from crypto_scanner import SPREAD_LIMITS
        assert SPREAD_LIMITS['BTCUSD'] == 50
        assert SPREAD_LIMITS['ETHUSD'] == 30
        assert SPREAD_LIMITS['BNBUSD'] == 20
        assert SPREAD_LIMITS['SOLUSD'] == 20
        assert SPREAD_LIMITS['XRPUSD'] == 20

    def test_get_spread_limit(self):
        from crypto_scanner import CryptoScanner
        cs = CryptoScanner()
        cs.api_key = 'test_key'
        assert cs.get_spread_limit('BTCUSD') == 50
        assert cs.get_spread_limit('XRPUSD') == 20
        assert cs.get_spread_limit('UNKNOWN') == 20


class TestCryptoSessionScoring:
    """Test 24/7 session scoring for crypto."""

    def test_session_bonus_us_market(self):
        from crypto_scanner import get_session_bonus
        from datetime import datetime, timezone
        with patch('crypto_scanner.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 6, 11, 14, 0, 0, tzinfo=timezone.utc)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw) if a else mock_dt.now.return_value
            mock_dt.timezone = timezone.utc
            bonus = get_session_bonus()
            assert bonus == 15

    def test_session_bonus_asian(self):
        from crypto_scanner import get_session_bonus
        from datetime import datetime, timezone
        with patch('crypto_scanner.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 6, 11, 2, 0, 0, tzinfo=timezone.utc)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw) if a else mock_dt.now.return_value
            mock_dt.timezone = timezone.utc
            bonus = get_session_bonus()
            assert bonus == 10

    def test_session_bonus_weekend(self):
        from crypto_scanner import get_session_bonus
        from datetime import datetime, timezone
        with patch('crypto_scanner.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 6, 13, 12, 0, 0, tzinfo=timezone.utc)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw) if a else mock_dt.now.return_value
            mock_dt.timezone = timezone.utc
            bonus = get_session_bonus()
            assert bonus == -10

    def test_session_bonus_normal(self):
        from crypto_scanner import get_session_bonus
        from datetime import datetime, timezone
        with patch('crypto_scanner.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2026, 6, 11, 8, 0, 0, tzinfo=timezone.utc)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw) if a else mock_dt.now.return_value
            mock_dt.timezone = timezone.utc
            bonus = get_session_bonus()
            assert bonus == 0


class TestCryptoCorrelation:
    """Test crypto correlation constants."""

    def test_crypto_correlation_exists(self):
        from crypto_scanner import CORRELATION
        assert CORRELATION['BTCUSD_ETHUSD'] == 0.92
        assert CORRELATION['BTCUSD_SP500'] == 0.65
        assert CORRELATION['ETHUSD_BNBUSD'] == 0.88

    def test_correlation_keys(self):
        from crypto_scanner import CORRELATION
        assert len(CORRELATION) >= 5


class TestCryptoPositionSizing:
    """Test position size reduction for crypto."""

    def test_position_size_multiplier(self):
        from crypto_scanner import CryptoScanner
        cs = CryptoScanner()
        cs.api_key = 'test_key'
        assert cs.get_position_size_multiplier() == 0.5

    def test_position_size_halves(self):
        from crypto_scanner import CryptoScanner
        cs = CryptoScanner()
        cs.api_key = 'test_key'
        forex_position = 0.1
        crypto_position = forex_position * cs.get_position_size_multiplier()
        assert crypto_position == 0.05


class TestCryptoScanner:
    """Test CryptoScanner run_scan method."""

    def test_scan_returns_structure(self):
        from crypto_scanner import CryptoScanner, CRYPTO_ASSETS
        cs = CryptoScanner()
        cs.api_key = 'test_key'
        with patch.object(cs, 'fetch_prices', return_value={s: None for s in CRYPTO_ASSETS}):
            with patch.object(cs, 'fetch_coin_gecko_trending', return_value=[]):
                with patch.object(cs, 'fetch_fear_greed', return_value=None):
                    result = cs.run_scan()
                    assert 'timestamp' in result
                    assert 'results' in result
                    assert len(result['results']) == 5

    def test_scan_results_have_keys(self):
        from crypto_scanner import CryptoScanner
        cs = CryptoScanner()
        cs.api_key = 'test_key'
        with patch.object(cs, 'fetch_prices', return_value={'BTCUSD': 67500.0, 'ETHUSD': 3450.0}):
            with patch.object(cs, 'fetch_coin_gecko_trending', return_value=[]):
                with patch.object(cs, 'fetch_fear_greed', return_value=50):
                    result = cs.run_scan()
                    for r in result['results']:
                        assert 'symbol' in r
                        assert 'score' in r
                        assert 'decision' in r

    def test_no_data_for_unavailable(self):
        from crypto_scanner import CryptoScanner
        cs = CryptoScanner()
        cs.api_key = 'test_key'
        with patch.object(cs, 'fetch_prices', return_value={'BTCUSD': None}):
            with patch.object(cs, 'fetch_coin_gecko_trending', return_value=[]):
                with patch.object(cs, 'fetch_fear_greed', return_value=None):
                    result = cs.run_scan()
                    btc = [r for r in result['results'] if r['symbol'] == 'BTCUSD'][0]
                    assert btc['decision'] == 'NO_DATA'

    def test_fear_greed_extreme_fear(self):
        from crypto_scanner import CryptoScanner
        cs = CryptoScanner()
        cs.api_key = 'test_key'
        with patch.object(cs, 'fetch_prices', return_value={'BTCUSD': 67500.0}):
            with patch.object(cs, 'fetch_coin_gecko_trending', return_value=[]):
                with patch.object(cs, 'fetch_fear_greed', return_value=20):
                    with patch('crypto_scanner.get_session_bonus', return_value=0):
                        result = cs.run_scan()
                        btc = [r for r in result['results'] if r['symbol'] == 'BTCUSD'][0]
                        assert btc['score'] >= 50

    def test_trending_coin_bonus(self):
        from crypto_scanner import CryptoScanner
        cs = CryptoScanner()
        cs.api_key = 'test_key'
        with patch.object(cs, 'fetch_prices', return_value={'BTCUSD': 67500.0}):
            with patch.object(cs, 'fetch_coin_gecko_trending', return_value=['BTC']):
                with patch.object(cs, 'fetch_fear_greed', return_value=50):
                    with patch('crypto_scanner.get_session_bonus', return_value=0):
                        result = cs.run_scan()
                        btc = [r for r in result['results'] if r['symbol'] == 'BTCUSD'][0]
                        assert btc['score'] >= 55


class TestLiveFeedScannerCrypto:
    """Test that live_feed_scanner includes crypto symbols."""

    def test_assets_includes_crypto(self):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'production'))
        import importlib
        import live_feed_scanner
        importlib.reload(live_feed_scanner)
        assert 'BTCUSD' in live_feed_scanner.ALL_ASSETS
        assert 'ETHUSD' in live_feed_scanner.ALL_ASSETS
        assert len(live_feed_scanner.ALL_ASSETS) == 9

    def test_symbol_map_includes_crypto(self):
        import importlib
        import live_feed_scanner
        importlib.reload(live_feed_scanner)
        assert live_feed_scanner.SYMBOL_MAP['BTCUSD'] == 'BTC/USD'
        assert live_feed_scanner.SYMBOL_MAP['XRPUSD'] == 'XRP/USD'


class TestEcosystemConfigCrypto:
    """Test that ecosystem config includes omni-crypto."""

    def test_omni_crypto_in_ecosystem(self):
        config_path = Path(__file__).parent.parent / 'ecosystem.config.js'
        content = config_path.read_text()
        assert 'omni-crypto' in content
        assert 'crypto_scanner.py' in content


class TestPipelineAPIEndpoint:
    """Test monetization API includes crypto data."""

    def test_monetization_endpoint_includes_crypto(self):
        orchestrator_path = Path(__file__).parent.parent / 'pipeline_orchestrator.py'
        content = orchestrator_path.read_text()
        assert 'crypto' in content
        assert 'fear_greed' in content
        assert 'session_bonus' in content
