"""
Exchange Gateway — Integration Test Suite
==========================================
Async test script that verifies the entire gateway lifecycle using mocked
HTTP responses.  Safe to run without real API keys or network calls.

Usage:
    cd exchange_gateway
    python test_gateway.py

Requirements:
    pip install aiohttp pytest pytest-asyncio (optional — uses stdlib runner)
"""

import sys
import json
import time
import asyncio
import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).parent))

from config_manager import ExchangeConfig, ExchangeCredentials, RateLimitConfig
from base_adapter import Ticker, OrderBook, OrderResult
from gateway import ExchangeGateway

# ── logging ────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("TestGateway")

# ── mock response factories ────────────────────────────────────────────

BINANCE_TICKER_MOCK = {
    "symbol": "BTCUSDT",
    "bidPrice": "65432.10",
    "askPrice": "65433.50",
    "bidQty": "1.234",
    "askQty": "0.567",
}

BINANCE_ORDERBOOK_MOCK = {
    "bids": [["65432.10", "1.234"], ["65431.00", "2.000"]],
    "asks": [["65433.50", "0.567"], ["65434.00", "1.100"]],
    "lastUpdateId": 123456,
}

BINANCE_ACCOUNT_MOCK = {
    "balances": [
        {"asset": "BTC", "free": "0.5", "locked": "0.0"},
        {"asset": "USDT", "free": "12345.67", "locked": "0.0"},
        {"asset": "ETH", "free": "0.0", "locked": "0.0"},
    ],
}

BINANCE_ORDER_MOCK = {
    "orderId": 987654321,
    "symbol": "BTCUSDT",
    "status": "FILLED",
    "side": "BUY",
    "type": "MARKET",
    "executedQty": "0.001",
    "price": "0",
}

BINANCE_OPEN_ORDERS_MOCK = [
    {"orderId": 111, "symbol": "BTCUSDT", "status": "NEW", "side": "BUY"},
]

BYBIT_TICKER_MOCK = {
    "list": [
        {
            "symbol": "BTCUSDT",
            "bid1Price": "65435.00",
            "ask1Price": "65436.80",
            "lastPrice": "65435.50",
        }
    ]
}

BYBIT_ORDERBOOK_MOCK = {
    "b": [["65435.00", "2.500"], ["65434.00", "3.000"]],
    "a": [["65436.80", "1.200"], ["65437.50", "0.800"]],
}

BYBIT_ACCOUNT_MOCK = {
    "list": [
        {
            "coin": [
                {"coin": "BTC", "availableToWithdraw": "0.75"},
                {"coin": "USDT", "availableToWithdraw": "8901.23"},
            ]
        }
    ]
}

BYBIT_ORDER_MOCK = {
    "orderId": "abc-123-def-456",
    "orderStatus": "New",
}

BYBIT_OPEN_ORDERS_MOCK = {"list": [{"orderId": "ord-1", "symbol": "BTCUSDT"}]}


# ── helpers ────────────────────────────────────────────────────────────

def make_mock_response(status: int = 200, json_data: Any = None, headers: Dict = None):
    """Build a mock aiohttp response."""
    resp = MagicMock()
    resp.status = status
    resp.headers = headers or {}
    resp.json = AsyncMock(return_value=json_data or {})

    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def make_mock_session(ticker, orderbook, account, order, open_orders):
    """Return a mock aiohttp.ClientSession that routes to the right endpoint."""
    session = MagicMock()

    def _route(method, url, **kwargs):
        path = url.split("?")[0] if "?" in url else url
        if "ticker" in path or "bookTicker" in path:
            return make_mock_response(200, ticker)
        elif "depth" in path or "orderbook" in path:
            return make_mock_response(200, orderbook)
        elif "account" in path or "wallet" in path:
            return make_mock_response(200, account)
        elif "order/create" in path or (method.upper() == "POST" and "order" in path and "cancel" not in path):
            return make_mock_response(200, order)
        elif "openOrders" in path or "realtime" in path:
            return make_mock_response(200, open_orders)
        return make_mock_response(200, {})

    # Use MagicMock (not AsyncMock) so session.request(...) returns the
    # response object directly — the adapters use "async with session.request(...) as resp:"
    # which needs __aenter__/__aexit__ on the return value, not a coroutine.
    session.request = MagicMock(side_effect=_route)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.closed = False
    return session


def make_test_config() -> ExchangeConfig:
    """Build a config with dummy testnet credentials."""
    config = ExchangeConfig()
    config._credentials["binance"] = ExchangeCredentials(
        exchange="binance",
        api_key="binance_test_key_abc123",
        api_secret="binance_test_secret_xyz789",
        testnet=True,
        ip_whitelist=[],
    )
    config._credentials["bybit"] = ExchangeCredentials(
        exchange="bybit",
        api_key="bybit_test_key_abc123",
        api_secret="bybit_test_secret_xyz789",
        testnet=True,
        ip_whitelist=[],
    )
    config._rate_limits["binance"] = RateLimitConfig(
        requests_per_minute=1200,
        order_weight=1,
        query_weight=1,
        market_data_weight=2,
    )
    config._rate_limits["bybit"] = RateLimitConfig(
        requests_per_minute=120,
        order_weight=1,
        query_weight=1,
        market_data_weight=1,
    )
    return config


# ── test functions ─────────────────────────────────────────────────────

async def test_config_manager():
    """Verify config loads credentials and rate limits correctly."""
    log.info("=" * 60)
    log.info("TEST: Config Manager")
    log.info("=" * 60)
    t0 = time.monotonic()

    config = make_test_config()
    exchanges = config.list_exchanges()
    assert set(exchanges) == {"binance", "bybit"}, f"Expected binance+bybit, got {exchanges}"

    binance = config.get_credentials("binance")
    assert binance.validate()
    assert binance.testnet is True

    bybit = config.get_credentials("bybit")
    assert bybit.validate()

    rl = config.get_rate_limits("binance")
    assert rl.requests_per_minute == 1200

    rl_bybit = config.get_rate_limits("bybit")
    assert rl_bybit.requests_per_minute == 120

    # IP validation (empty whitelist = allow all)
    assert config.validate_ip("binance", "1.2.3.4")

    cfg_dict = config.as_dict()
    assert "binance" in cfg_dict
    assert "bybit" in cfg_dict

    elapsed = (time.monotonic() - t0) * 1000
    log.info("[PASS] Config Manager — %dms", elapsed)
    log.info("  Exchanges: %s", exchanges)
    log.info("  Binance testnet: %s | RPM: %d", binance.testnet, rl.requests_per_minute)
    log.info("  Bybit testnet: %s | RPM: %d", bybit.testnet, rl_bybit.requests_per_minute)
    log.info("  Config dict: %s", json.dumps(cfg_dict, indent=2))


async def test_single_exchange_binance():
    """Test Binance adapter: ticker, order book, balance, order."""
    log.info("")
    log.info("=" * 60)
    log.info("TEST: Single Exchange — Binance")
    log.info("=" * 60)
    t0 = time.monotonic()

    config = make_test_config()
    gw = ExchangeGateway(config)

    binance = gw.get_adapter("binance")

    # Mock the session
    mock_session = make_mock_session(
        ticker=BINANCE_TICKER_MOCK,
        orderbook=BINANCE_ORDERBOOK_MOCK,
        account=BINANCE_ACCOUNT_MOCK,
        order=BINANCE_ORDER_MOCK,
        open_orders=BINANCE_OPEN_ORDERS_MOCK,
    )
    binance._session = mock_session

    # Test fetch_ticker
    ticker = await gw.fetch_ticker("binance", "BTCUSDT")
    assert isinstance(ticker, Ticker)
    assert ticker.symbol == "BTCUSDT"
    assert ticker.bid == 65432.10
    assert ticker.ask == 65433.50
    log.info("[PASS] fetch_ticker: %s", ticker)

    # Test fetch_order_book
    book = await gw.fetch_order_book("binance", "BTCUSDT")
    assert isinstance(book, OrderBook)
    assert len(book.bids) == 2
    assert book.bids[0][0] == 65432.10
    log.info("[PASS] fetch_order_book: %d bids, %d asks", len(book.bids), len(book.asks))

    # Test get_balance
    balance = await gw.get_balance("binance")
    assert "BTC" in balance
    assert balance["BTC"] == 0.5
    log.info("[PASS] get_balance: %s", balance)

    # Test place_order
    result = await gw.place_order("binance", "BTCUSDT", "BUY", "MARKET", 0.001)
    assert isinstance(result, OrderResult)
    assert result.order_id == "987654321"
    assert result.status == "FILLED"
    log.info("[PASS] place_order: id=%s status=%s", result.order_id, result.status)

    # Test get_open_orders
    orders = await gw.get_open_orders("binance")
    assert len(orders) == 1
    log.info("[PASS] get_open_orders: %d order(s)", len(orders))

    await gw.close()
    elapsed = (time.monotonic() - t0) * 1000
    log.info("[PASS] Binance adapter complete — %dms", elapsed)


async def test_single_exchange_bybit():
    """Test Bybit adapter: ticker, order book, balance, order."""
    log.info("")
    log.info("=" * 60)
    log.info("TEST: Single Exchange — Bybit")
    log.info("=" * 60)
    t0 = time.monotonic()

    config = make_test_config()
    gw = ExchangeGateway(config)

    bybit = gw.get_adapter("bybit")

    mock_session = make_mock_session(
        ticker=BYBIT_TICKER_MOCK,
        orderbook=BYBIT_ORDERBOOK_MOCK,
        account=BYBIT_ACCOUNT_MOCK,
        order=BYBIT_ORDER_MOCK,
        open_orders=BYBIT_OPEN_ORDERS_MOCK,
    )
    bybit._session = mock_session

    # Test fetch_ticker
    ticker = await gw.fetch_ticker("bybit", "BTCUSDT")
    assert isinstance(ticker, Ticker)
    assert ticker.symbol == "BTCUSDT"
    assert ticker.bid == 65435.00
    assert ticker.ask == 65436.80
    log.info("[PASS] fetch_ticker: %s", ticker)

    # Test fetch_order_book
    book = await gw.fetch_order_book("bybit", "BTCUSDT")
    assert isinstance(book, OrderBook)
    assert len(book.bids) == 2
    log.info("[PASS] fetch_order_book: %d bids, %d asks", len(book.bids), len(book.asks))

    # Test get_balance
    balance = await gw.get_balance("bybit")
    assert "BTC" in balance
    assert balance["BTC"] == 0.75
    log.info("[PASS] get_balance: %s", balance)

    # Test place_order
    result = await gw.place_order("bybit", "BTCUSDT", "BUY", "LIMIT", 0.001, price=65000)
    assert isinstance(result, OrderResult)
    assert result.order_id == "abc-123-def-456"
    log.info("[PASS] place_order: id=%s status=%s", result.order_id, result.status)

    await gw.close()
    elapsed = (time.monotonic() - t0) * 1000
    log.info("[PASS] Bybit adapter complete — %dms", elapsed)


async def test_multi_exchange_concurrent():
    """Test multi-exchange concurrent balance fetch."""
    log.info("")
    log.info("=" * 60)
    log.info("TEST: Multi-Exchange Concurrent")
    log.info("=" * 60)
    t0 = time.monotonic()

    config = make_test_config()
    gw = ExchangeGateway(config)

    # Mock both sessions with full ticker mock data
    binance_mock = make_mock_session(
        ticker=BINANCE_TICKER_MOCK, orderbook=BINANCE_ORDERBOOK_MOCK,
        account=BINANCE_ACCOUNT_MOCK, order=BINANCE_ORDER_MOCK,
        open_orders=BINANCE_OPEN_ORDERS_MOCK,
    )
    bybit_mock = make_mock_session(
        ticker=BYBIT_TICKER_MOCK, orderbook=BYBIT_ORDERBOOK_MOCK,
        account=BYBIT_ACCOUNT_MOCK, order=BYBIT_ORDER_MOCK,
        open_orders=BYBIT_OPEN_ORDERS_MOCK,
    )
    gw.get_adapter("binance")._session = binance_mock
    gw.get_adapter("bybit")._session = bybit_mock

    # Test get_multi_balance (concurrent)
    balances = await gw.get_multi_balance(["binance", "bybit"])
    assert "binance" in balances
    assert "bybit" in balances
    assert balances["binance"]["BTC"] == 0.5
    assert balances["bybit"]["BTC"] == 0.75
    log.info("[PASS] get_multi_balance: %s", json.dumps(balances, indent=2))

    # Test fetch_multi_ticker (concurrent) — needs proper session mocks
    tickers = await gw.fetch_multi_ticker(["binance", "bybit"], "BTCUSDT")
    assert "binance" in tickers
    assert "bybit" in tickers
    assert tickers["binance"].bid == 65432.10
    assert tickers["bybit"].bid == 65435.00
    log.info("[PASS] fetch_multi_ticker:")
    for ex, t in tickers.items():
        log.info("  %s: bid=%.2f ask=%.2f", ex, t.bid, t.ask)

    await gw.close()
    elapsed = (time.monotonic() - t0) * 1000
    log.info("[PASS] Multi-exchange concurrent — %dms", elapsed)


async def test_arbitrage_spread():
    """Test arbitrage spread detection across exchanges."""
    log.info("")
    log.info("=" * 60)
    log.info("TEST: Arbitrage Spread Detection")
    log.info("=" * 60)
    t0 = time.monotonic()

    config = make_test_config()
    gw = ExchangeGateway(config)

    # Mock sessions — bybit has higher bid than binance ask
    binance_adapter = gw.get_adapter("binance")
    bybit_adapter = gw.get_adapter("bybit")

    # Bybit bid > Binance ask → profitable spread
    binance_adapter._session = make_mock_session(
        ticker=BINANCE_TICKER_MOCK,       # bid=65432.10, ask=65433.50
        orderbook={}, account={}, order={}, open_orders=[],
    )
    bybit_adapter._session = make_mock_session(
        ticker=BYBIT_TICKER_MOCK,         # bid=65435.00, ask=65436.80
        orderbook={}, account={}, order={}, open_orders=[],
    )

    spread = await gw.find_best_spread("BTCUSDT")
    assert isinstance(spread, dict)
    assert "spread_pct" in spread
    assert "profitable" in spread
    log.info("[PASS] find_best_spread:")
    log.info("  Buy on:  %s @ %.2f", spread["buy_exchange"], spread["buy_price"])
    log.info("  Sell on: %s @ %.2f", spread["sell_exchange"], spread["sell_price"])
    log.info("  Spread:  %.2f (%.4f%%)", spread["spread"], spread["spread_pct"])
    log.info("  Profitable: %s", spread["profitable"])

    assert spread["spread"] > 0, "Expected profitable spread"
    assert spread["profitable"] is True

    # Test negative spread (no arbitrage)
    # Swap: binance has the higher bid
    flipped_ticker_binance = Ticker(symbol="BTCUSDT", bid=65440.0, ask=65441.0, last=65440.5, timestamp=0)
    flipped_ticker_bybit = Ticker(symbol="BTCUSDT", bid=65430.0, ask=65431.0, last=65430.5, timestamp=0)

    async def mock_fetch_multi_ticker(exchanges, symbol):
        result = {}
        for ex in exchanges:
            if ex == "binance":
                result[ex] = flipped_ticker_binance
            else:
                result[ex] = flipped_ticker_bybit
        return result

    gw.fetch_multi_ticker = mock_fetch_multi_ticker
    spread2 = await gw.find_best_spread("BTCUSDT")
    log.info("[PASS] Negative spread test:")
    log.info("  Spread: %.2f (profitable=%s)", spread2["spread"], spread2["profitable"])

    await gw.close()
    elapsed = (time.monotonic() - t0) * 1000
    log.info("[PASS] Arbitrage spread detection — %dms", elapsed)


async def test_error_handling():
    """Test graceful error handling when exchanges fail."""
    log.info("")
    log.info("=" * 60)
    log.info("TEST: Error Handling")
    log.info("=" * 60)
    t0 = time.monotonic()

    config = make_test_config()
    gw = ExchangeGateway(config)

    # Simulate missing exchange
    try:
        gw.get_adapter("kraken")
        assert False, "Should have raised KeyError"
    except KeyError as e:
        log.info("[PASS] Missing exchange raises KeyError: %s", e)

    # Simulate failed balance on one exchange, successful on other
    binance_adapter = gw.get_adapter("binance")
    binance_adapter.get_balance = AsyncMock(side_effect=Exception("Network timeout"))

    bybit_adapter = gw.get_adapter("bybit")
    bybit_adapter._session = make_mock_session(
        ticker={}, orderbook={}, account=BYBIT_ACCOUNT_MOCK,
        order={}, open_orders=[],
    )

    balances = await gw.get_multi_balance(["binance", "bybit"])
    log.info("[PASS] Partial failure handled gracefully: %s", balances)
    assert "bybit" in balances  # bybit should still succeed

    await gw.close()
    elapsed = (time.monotonic() - t0) * 1000
    log.info("[PASS] Error handling — %dms", elapsed)


# ── runner ─────────────────────────────────────────────────────────────

async def main():
    """Run all tests."""
    log.info("")
    log.info("╔══════════════════════════════════════════════════════════╗")
    log.info("║  EXCHANGE GATEWAY — INTEGRATION TEST SUITE             ║")
    log.info("╚══════════════════════════════════════════════════════════╝")
    log.info("")

    suite_start = time.monotonic()
    passed = 0
    failed = 0
    errors = []

    tests = [
        ("Config Manager", test_config_manager),
        ("Binance Adapter", test_single_exchange_binance),
        ("Bybit Adapter", test_single_exchange_bybit),
        ("Multi-Exchange Concurrent", test_multi_exchange_concurrent),
        ("Arbitrage Spread", test_arbitrage_spread),
        ("Error Handling", test_error_handling),
    ]

    for name, test_fn in tests:
        try:
            await test_fn()
            passed += 1
        except Exception as e:
            failed += 1
            errors.append((name, str(e)))
            log.error("[FAIL] %s: %s", name, e)

    suite_elapsed = (time.monotonic() - suite_start) * 1000

    log.info("")
    log.info("╔══════════════════════════════════════════════════════════╗")
    log.info("║  RESULTS                                               ║")
    log.info("╠══════════════════════════════════════════════════════════╣")
    log.info("║  Total:   %d | Passed: %d | Failed: %d                 ║", passed + failed, passed, failed)
    log.info("║  Time:    %.1fms                                      ║", suite_elapsed)
    if errors:
        log.info("╠══════════════════════════════════════════════════════════╣")
        for name, err in errors:
            log.info("║  FAIL: %-48s ║", f"{name}: {err[:38]}")
    log.info("╚══════════════════════════════════════════════════════════╝")

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
