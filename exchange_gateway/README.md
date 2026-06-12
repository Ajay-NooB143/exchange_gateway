# Exchange Gateway

Unified async exchange framework for Binance and Bybit. Provides a single API for market data, account queries, and order management across multiple exchanges with built-in rate limiting, HMAC-SHA256 signing, and arbitrage spread detection.

## Architecture

```
┌─────────────────────────────────────────────────┐
│                ExchangeGateway                   │
│         (gateway.py — orchestrator)              │
│                                                  │
│  fetch_ticker()  place_order()  find_best_spread │
└──────────┬──────────────────────┬────────────────┘
           │                      │
    ┌──────▼──────┐        ┌──────▼──────┐
    │  BinanceAdapter  │        │  BybitAdapter   │
    │  (HMAC-SHA256)  │        │  (HMAC-SHA256)  │
    └──────┬──────┘        └──────┬──────┘
           │                      │
    ┌──────▼──────┐        ┌──────▼──────┐
    │  RateLimiter │        │  RateLimiter │
    │ (token-bucket)│        │ (token-bucket)│
    └──────┬──────┘        └──────┬──────┘
           │                      │
    ┌──────▼──────┐        ┌──────▼──────┐
    │   aiohttp   │        │   aiohttp   │
    └─────────────┘        └─────────────┘
```

**Key components:**

| File | Purpose |
|------|---------|
| `config_manager.py` | Loads credentials from `config/exchanges.json` or env vars; manages IP whitelists and rate-limit policies |
| `base_adapter.py` | Abstract `BaseAdapter` interface, `Ticker`/`OrderBook`/`OrderResult` dataclasses, async token-bucket `RateLimiter` |
| `gateway.py` | `ExchangeGateway` orchestrator — routes calls to the correct adapter, provides concurrent multi-exchange methods and arbitrage detection |
| `adapters/binance_adapter.py` | Binance REST adapter (testnet + live), HMAC-SHA256 signing, symbol mapping |
| `adapters/bybit_adapter.py` | Bybit v5 REST adapter (testnet + live), HMAC-SHA256 signing, symbol mapping |
| `config/exchanges.json.example` | Sample configuration file |

## Directory Layout

```
exchange_gateway/
├── README.md
├── requirements.txt
├── deploy.sh
├── __init__.py
├── config_manager.py
├── base_adapter.py
├── gateway.py
├── test_gateway.py
├── config/
│   └── exchanges.json.example
└── adapters/
    ├── __init__.py
    ├── binance_adapter.py
    └── bybit_adapter.py
```

## Configuration

### Option 1: JSON file (recommended)

1. Copy the example config:
   ```bash
   cp config/exchanges.json.example config/exchanges.json
   ```

2. Fill in your API credentials:
   ```json
   {
     "exchanges": {
       "binance": {
         "api_key": "your-binance-api-key",
         "api_secret": "your-binance-api-secret",
         "testnet": true,
         "ip_whitelist": [],
         "rate_limits": {
           "requests_per_minute": 1200,
           "order_weight": 1,
           "query_weight": 1,
           "market_data_weight": 2
         }
       },
       "bybit": {
         "api_key": "your-bybit-api-key",
         "api_secret": "your-bybit-api-secret",
         "testnet": true,
         "ip_whitelist": [],
         "rate_limits": {
           "requests_per_minute": 120,
           "order_weight": 1,
           "query_weight": 1,
           "market_data_weight": 1
         }
       }
     }
   }
   ```

### Option 2: Environment variables

```bash
export EXCHANGE_GATEWAY_BINANCE_API_KEY="your-key"
export EXCHANGE_GATEWAY_BINANCE_API_SECRET="your-secret"
export EXCHANGE_GATEWAY_BINANCE_TESTNET="true"

export EXCHANGE_GATEWAY_BYBIT_API_KEY="your-key"
export EXCHANGE_GATEWAY_BYBIT_API_SECRET="your-secret"
export EXCHANGE_GATEWAY_BYBIT_TESTNET="true"
```

Env vars take priority over the JSON file. IP whitelists can be set via `EXCHANGE_GATEWAY_BINANCE_IP_WHITELIST="1.2.3.4,10.0.0.0/8"`.

### Rate Limits

| Exchange | Default RPM | Type |
|----------|------------|------|
| Binance | 1200 | Weight-based (market data = 2 weight) |
| Bybit | 120 | Linear (each request = 1) |

The token-bucket rate limiter enforces these limits automatically. When a 429 is received, adapters wait the server-specified `Retry-After` period and retry.

## Usage

### Single Exchange

```python
import asyncio
from gateway import ExchangeGateway

async def main():
    gw = ExchangeGateway.from_config()

    # Market data
    ticker = await gw.fetch_ticker("binance", "BTCUSDT")
    print(f"Binance BTC: bid={ticker.bid} ask={ticker.ask}")

    book = await gw.fetch_order_book("binance", "BTCUSDT", depth=10)
    print(f"Top bid: {book.bids[0]}, Top ask: {book.asks[0]}")

    # Account
    balance = await gw.get_balance("binance")
    print(f"Balances: {balance}")

    # Place order
    result = await gw.place_order(
        exchange="binance",
        symbol="BTCUSDT",
        side="BUY",
        order_type="LIMIT",
        quantity=0.001,
        price=65000,
    )
    print(f"Order {result.order_id}: {result.status}")

    # Cancel order
    await gw.cancel_order("binance", "BTCUSDT", result.order_id)

    # Open orders
    orders = await gw.get_open_orders("binance", "BTCUSDT")

    await gw.close()

asyncio.run(main())
```

### Multi-Exchange

```python
import asyncio
from gateway import ExchangeGateway

async def main():
    async with ExchangeGateway.from_config() as gw:
        # Concurrent ticker fetch
        tickers = await gw.fetch_multi_ticker(["binance", "bybit"], "BTCUSDT")
        for exchange, t in tickers.items():
            print(f"{exchange}: bid={t.bid} ask={t.ask}")

        # Concurrent balance fetch
        balances = await gw.get_multi_balance(["binance", "bybit"])
        for exchange, b in balances.items():
            print(f"{exchange}: {b}")

asyncio.run(main())
```

### Arbitrage Detection

```python
import asyncio
from gateway import ExchangeGateway

async def main():
    async with ExchangeGateway.from_config() as gw:
        spread = await gw.find_best_spread("BTCUSDT")

        if spread.get("profitable"):
            print(f"Arbitrage opportunity!")
            print(f"  Buy on:  {spread['buy_exchange']} @ {spread['buy_price']}")
            print(f"  Sell on: {spread['sell_exchange']} @ {spread['sell_price']}")
            print(f"  Spread:  {spread['spread_pct']}%")
        else:
            print("No profitable spread found")

asyncio.run(main())
```

### Context Manager (recommended)

```python
async with ExchangeGateway.from_config() as gw:
    # All operations here
    ...
# Sessions automatically closed on exit
```

## Running Tests

```bash
pip install -r requirements.txt
python test_gateway.py
```

All 6 tests should pass. Tests use mocked HTTP sessions — no real API calls are made.

## Deployment

```bash
chmod +x deploy.sh
./deploy.sh
```

The deploy script:
1. Creates/activates a virtual environment
2. Installs dependencies from `requirements.txt`
3. Validates that `config/exchanges.json` exists
4. Runs a syntax check on all Python files
5. Runs the test suite

## Supported Symbols

| Symbol | Binance | Bybit | Notes |
|--------|---------|-------|-------|
| BTCUSDT | BTCUSDT | BTCUSDT | |
| ETHUSDT | ETHUSDT | ETHUSDT | |
| XAUUSD | PAXGUSDT | XAUUSD | Binance maps gold to PAXG |
| BNBUSDT | BNBUSDT | BNBUSDT | |
| SOLUSDT | SOLUSDT | SOLUSDT | |
| XRPUSDT | XRPUSDT | XRPUSDT | |

## License

Internal use only.
