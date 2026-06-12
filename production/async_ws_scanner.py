"""
Async WebSocket Scanner — Binance/Bybit (Layer 1)
==================================================
Real-time price feeds via exchange WebSocket streams.

Replaces TwelveData WebSocket with native exchange WS:
  - Binance: wss://stream.binance.com:9443/ws/
  - Bybit:   wss://stream.bybit.com/v5/public/linear

Features:
  - Multi-symbol subscription
  - Auto-reconnect with exponential backoff
  - Price + volume + order book depth streams
  - Callback-based price updates (feeds pipeline)
  - Graceful shutdown

Env vars:
  WS_EXCHANGE (binance/bybit, default: binance)
  WS_SYMBOLS (comma-separated, default: BTCUSDT,ETHUSDT)

Usage:
    scanner = AsyncWSScanner(exchange='binance', symbols=['BTC/USDT', 'ETH/USDT'])
    scanner.on_price_update = my_callback
    await scanner.start()
"""

import os
import sys
import json
import time
import logging
import asyncio
import threading
from typing import Any, Dict, List, Optional, Callable, Set
from pathlib import Path
from collections import deque

log = logging.getLogger('AsyncWSScanner')

LOG_DIR = Path(__file__).parent / 'logs'
LOG_DIR.mkdir(exist_ok=True)

# ══════════════════════════════════════════════════════════════════════════════
# SYMBOL MAPPING — Our format → Exchange WS format
# ══════════════════════════════════════════════════════════════════════════════

BINANCE_WS_SYMBOLS = {
    'XAUUSD': 'paxgusdt',
    'EURUSD': 'eurusdt',
    'GBPUSD': 'gbpusdt',
    'BTCUSD': 'btcusdt',
    'ETHUSD': 'ethusdt',
    'BNBUSD': 'bnbusdt',
    'SOLUSD': 'solusdt',
    'XRPUSD': 'xrpusdt',
}

BYBIT_WS_SYMBOLS = {
    'XAUUSD': 'XAUUSD',
    'EURUSD': 'EURUSD',
    'GBPUSD': 'GBPUSD',
    'BTCUSD': 'BTCUSDT',
    'ETHUSD': 'ETHUSDT',
    'BNBUSD': 'BNBUSDT',
    'SOLUSD': 'SOLUSDT',
    'XRPUSD': 'XRPUSDT',
}

# Reverse maps for incoming WS messages
BINANCE_WS_REVERSE = {v: k for k, v in BINANCE_WS_SYMBOLS.items()}
BYBIT_WS_REVERSE = {v: k for k, v in BYBIT_WS_SYMBOLS.items()}


# ══════════════════════════════════════════════════════════════════════════════
# BINANCE WEBSOCKET
# ══════════════════════════════════════════════════════════════════════════════

class BinanceWS:
    """
    Binance combined stream WebSocket.

    Streams: <symbol>@ticker (24hr rolling window stats)
    URL: wss://stream.binance.com:9443/stream?streams=<streams>
    """

    BASE_URL = 'wss://stream.binance.com:9443/stream?streams='

    def __init__(self, symbols: List[str], on_update: Callable):
        self._ws_symbols = [BINANCE_WS_SYMBOLS.get(s, s.lower()) for s in symbols]
        self._on_update = on_update
        self._ws = None
        self._running = False
        self._retries = 0
        self._max_retries = 50

    def _build_url(self) -> str:
        streams = '/'.join(f'{s}@ticker' for s in self._ws_symbols)
        return f'{self.BASE_URL}{streams}'

    async def connect(self):
        """Connect to Binance WebSocket."""
        try:
            import websockets
        except ImportError:
            log.error('[WS-BINANCE] websockets not installed: pip install websockets')
            return

        url = self._build_url()
        self._running = True
        log.info('[WS-BINANCE] Connecting to %s', url[:80])

        while self._running and self._retries < self._max_retries:
            try:
                async with websockets.connect(url, ping_interval=20) as ws:
                    self._ws = ws
                    self._retries = 0
                    log.info('[WS-BINANCE] Connected — subscribed to %d symbols', len(self._ws_symbols))

                    async for message in ws:
                        if not self._running:
                            break
                        try:
                            data = json.loads(message)
                            payload = data.get('data', data)
                            self._handle_ticker(payload)
                        except Exception as e:
                            log.debug('[WS-BINANCE] Parse error: %s', e)

            except Exception as e:
                if self._running:
                    self._retries += 1
                    delay = min(5 * (2 ** (self._retries - 1)), 60)
                    log.warning('[WS-BINANCE] Disconnected (%s) — reconnecting in %ds (attempt %d)',
                                e, delay, self._retries)
                    await asyncio.sleep(delay)

    def _handle_ticker(self, data: Dict[str, Any]):
        """Parse Binance 24hr ticker stream."""
        raw_symbol = data.get('s', '')
        symbol = BINANCE_WS_REVERSE.get(raw_symbol, raw_symbol)
        try:
            update = {
                'symbol': symbol,
                'exchange': 'binance',
                'bid': float(data.get('b', 0)),
                'ask': float(data.get('a', 0)),
                'last': float(data.get('c', 0)),
                'volume': float(data.get('v', 0)),
                'change_pct': float(data.get('P', 0)),
                'timestamp': int(time.time() * 1000),
            }
            self._on_update(update)
        except Exception as e:
            log.debug('[WS-BINANCE] Ticker parse error for %s: %s', raw_symbol, e)

    def disconnect(self):
        self._running = False
        if self._ws:
            try:
                asyncio.get_event_loop().run_coroutine_threadsafe(
                    self._ws.close(), asyncio.get_event_loop()
                )
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════════════
# BYBIT WEBSOCKET
# ══════════════════════════════════════════════════════════════════════════════

class BybitWS:
    """
    Bybit V5 public WebSocket.

    Stream: tickers (real-time best bid/ask)
    URL: wss://stream.bybit.com/v5/public/linear
    """

    WS_URL = 'wss://stream.bybit.com/v5/public/linear'

    def __init__(self, symbols: List[str], on_update: Callable):
        self._ws_symbols = [BYBIT_WS_SYMBOLS.get(s, s) for s in symbols]
        self._on_update = on_update
        self._ws = None
        self._running = False
        self._retries = 0
        self._max_retries = 50

    async def connect(self):
        """Connect to Bybit WebSocket."""
        try:
            import websockets
        except ImportError:
            log.error('[WS-BYBIT] websockets not installed: pip install websockets')
            return

        self._running = True
        log.info('[WS-BYBIT] Connecting to %s', self.WS_URL)

        while self._running and self._retries < self._max_retries:
            try:
                async with websockets.connect(self.WS_URL, ping_interval=20) as ws:
                    self._ws = ws
                    self._retries = 0

                    # Subscribe to tickers
                    subscribe_msg = json.dumps({
                        'op': 'subscribe',
                        'args': [f'tickers.{s}' for s in self._ws_symbols],
                    })
                    await ws.send(subscribe_msg)
                    log.info('[WS-BYBIT] Connected — subscribed to %s', self._ws_symbols)

                    async for message in ws:
                        if not self._running:
                            break
                        try:
                            data = json.loads(message)
                            if data.get('topic', '').startswith('tickers.'):
                                self._handle_ticker(data)
                        except Exception as e:
                            log.debug('[WS-BYBIT] Parse error: %s', e)

            except Exception as e:
                if self._running:
                    self._retries += 1
                    delay = min(5 * (2 ** (self._retries - 1)), 60)
                    log.warning('[WS-BYBIT] Disconnected (%s) — reconnecting in %ds (attempt %d)',
                                e, delay, self._retries)
                    await asyncio.sleep(delay)

    def _handle_ticker(self, data: Dict[str, Any]):
        """Parse Bybit V5 ticker stream."""
        ticker = data.get('data', {})
        raw_symbol = ticker.get('symbol', '')
        symbol = BYBIT_WS_REVERSE.get(raw_symbol, raw_symbol)
        try:
            update = {
                'symbol': symbol,
                'exchange': 'bybit',
                'bid': float(ticker.get('bid1Price', 0)),
                'ask': float(ticker.get('ask1Price', 0)),
                'last': float(ticker.get('lastPrice', 0)),
                'volume': float(ticker.get('volume24h', 0)),
                'change_pct': float(ticker.get('price24hPcnt', 0)) * 100,
                'timestamp': int(time.time() * 1000),
            }
            self._on_update(update)
        except Exception as e:
            log.debug('[WS-BYBIT] Ticker parse error for %s: %s', raw_symbol, e)

    def disconnect(self):
        self._running = False
        if self._ws:
            try:
                asyncio.get_event_loop().run_coroutine_threadsafe(
                    self._ws.close(), asyncio.get_event_loop()
                )
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════════════
# ASYNC WS SCANNER
# ══════════════════════════════════════════════════════════════════════════════

class AsyncWSScanner:
    """
    Async WebSocket scanner connecting to Binance or Bybit.

    Manages connection lifecycle, price caching, and callbacks.
    Runs in a background thread with its own event loop.
    """

    def __init__(
        self,
        exchange: str = 'binance',
        symbols: Optional[List[str]] = None,
        on_price_update: Optional[Callable] = None,
    ):
        self.exchange = exchange
        self.symbols = symbols or ['BTCUSD', 'ETHUSD', 'XAUUSD']
        self.on_price_update = on_price_update

        self._ws = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

        # Price cache
        self._last_prices: Dict[str, Dict[str, Any]] = {}
        self._update_count = 0

    def _default_callback(self, update: Dict[str, Any]):
        """Default price update handler — cache prices."""
        symbol = update.get('symbol', '')
        self._last_prices[symbol] = update
        self._update_count += 1
        log.debug('[WS] %s: bid=%.4f ask=%.4f last=%.4f vol=%.0f',
                  symbol, update.get('bid', 0), update.get('ask', 0),
                  update.get('last', 0), update.get('volume', 0))

    async def _run(self):
        """Background async loop: connect WS and run forever."""
        callback = self.on_price_update or self._default_callback

        if self.exchange == 'binance':
            self._ws = BinanceWS(self.symbols, callback)
        elif self.exchange == 'bybit':
            self._ws = BybitWS(self.symbols, callback)
        else:
            log.error('[WS] Unknown exchange: %s', self.exchange)
            return

        self._running = True
        await self._ws.connect()

    def _thread_entry(self):
        """Thread entry point: create event loop and run."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._run())

    def start(self):
        """Start the WebSocket scanner in a background thread."""
        if self._thread and self._thread.is_alive():
            log.warning('[WS] Already running')
            return

        self._thread = threading.Thread(target=self._thread_entry, daemon=True)
        self._thread.start()
        log.info('[WS] Scanner thread started (exchange=%s, symbols=%s)',
                 self.exchange, self.symbols)

    def stop(self):
        """Stop the WebSocket scanner."""
        self._running = False
        if self._ws:
            self._ws.disconnect()
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=5)
        log.info('[WS] Scanner stopped')

    def get_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get last cached price for a symbol."""
        return self._last_prices.get(symbol)

    def get_all_prices(self) -> Dict[str, Dict[str, Any]]:
        """Get all cached prices."""
        return dict(self._last_prices)

    def get_status(self) -> Dict[str, Any]:
        """Get scanner status."""
        return {
            'exchange': self.exchange,
            'symbols': self.symbols,
            'running': self._running,
            'connected': self._ws is not None and self._running,
            'update_count': self._update_count,
            'cached_symbols': list(self._last_prices.keys()),
        }


# ══════════════════════════════════════════════════════════════════════════════
# MODULE SINGLETON
# ══════════════════════════════════════════════════════════════════════════════

_scanner: Optional[AsyncWSScanner] = None


def get_ws_scanner(
    exchange: Optional[str] = None,
    symbols: Optional[List[str]] = None,
) -> AsyncWSScanner:
    """Get or create the module-level WS scanner singleton."""
    global _scanner
    if _scanner is None:
        exchange = exchange or os.environ.get('WS_EXCHANGE', 'binance')
        if symbols is None:
            raw = os.environ.get('WS_SYMBOLS', 'BTCUSD,ETHUSD,XAUUSD')
            symbols = [s.strip() for s in raw.split(',') if s.strip()]
        _scanner = AsyncWSScanner(exchange=exchange, symbols=symbols)
        _scanner.start()
    return _scanner


def shutdown_ws_scanner():
    """Shutdown the module-level WS scanner."""
    global _scanner
    if _scanner is not None:
        _scanner.stop()
        _scanner = None
