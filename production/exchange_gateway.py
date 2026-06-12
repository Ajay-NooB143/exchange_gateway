"""
Exchange Gateway — ccxt Unified (Layer 2)
==========================================
Async exchange access via ccxt for Binance/Bybit.

Features:
  - Unified ccxt.async_support interface
  - Multi-exchange support (Binance, Bybit)
  - Market data: fetch_ticker, fetch_ohlcv, fetch_order_book
  - Order execution: create_order, cancel_order, fetch_balance
  - Paper mode by default (set PAPER_MODE=false for live)
  - Sync wrapper for pipeline orchestrator integration
  - All credentials from env vars (never hardcoded)

Env vars:
  EXCHANGE_GATEWAY_BINANCE_API_KEY / _SECRET
  EXCHANGE_GATEWAY_BYBIT_API_KEY / _SECRET
  EXCHANGE_GATEWAY_BINANCE_TESTNET / BYBIT_TESTNET (true/false)
  PAPER_MODE (true/false, default: true)

Usage (async):
    async with ExchangeGateway() as gw:
        ticker = await gw.fetch_ticker('binance', 'BTC/USDT')
        result = await gw.create_order('binance', 'BTC/USDT', 'buy', 'limit', 0.001, 65000)

Usage (sync, from pipeline):
    gw = get_exchange_gateway()
    result = gw.execute_signal(symbol='BTCUSD', side='BUY', price=65000, quantity=0.001)
"""

import os
import time
import json
import logging
import asyncio
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

log = logging.getLogger('ExchangeGateway')

LOG_DIR = Path(__file__).parent / 'logs'
LOG_DIR.mkdir(exist_ok=True)

# ══════════════════════════════════════════════════════════════════════════════
# SYMBOL MAPPING — Our format → ccxt unified format
# ══════════════════════════════════════════════════════════════════════════════

SYMBOL_MAP = {
    'binance': {
        'XAUUSD': 'PAXG/USDT',
        'EURUSD': 'EUR/USDT',
        'GBPUSD': 'GBP/USDT',
        'BTCUSD': 'BTC/USDT',
        'ETHUSD': 'ETH/USDT',
        'BNBUSD': 'BNB/USDT',
        'SOLUSD': 'SOL/USDT',
        'XRPUSD': 'XRP/USDT',
        'SP500': None,  # Not available on Binance
    },
    'bybit': {
        'XAUUSD': 'XAU/USD',
        'EURUSD': 'EUR/USD',
        'GBPUSD': 'GBP/USD',
        'BTCUSD': 'BTC/USDT',
        'ETHUSD': 'ETH/USDT',
        'BNBUSD': 'BNB/USDT',
        'SOLUSD': 'SOL/USDT',
        'XRPUSD': 'XRP/USDT',
        'SP500': 'US500',
    },
}

# Timeframe mapping for ccxt
TF_MAP = {
    'M1': '1m', 'M5': '5m', 'M15': '15m', 'M30': '30m',
    'H1': '1h', 'H4': '4h', 'D1': '1d',
}


class OrderSide(Enum):
    BUY = 'buy'
    SELL = 'sell'


class OrderType(Enum):
    MARKET = 'market'
    LIMIT = 'limit'


@dataclass
class GatewayResult:
    """Normalized result from gateway operations."""
    success: bool
    exchange: str
    symbol: str
    side: str = ''
    order_type: str = ''
    quantity: float = 0.0
    price: float = 0.0
    order_id: str = ''
    status: str = ''
    filled: float = 0.0
    average: float = 0.0
    error: str = ''
    raw: Dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0


# ══════════════════════════════════════════════════════════════════════════════
# EXCHANGE GATEWAY (async core)
# ══════════════════════════════════════════════════════════════════════════════

class ExchangeGateway:
    """
    Unified async exchange gateway using ccxt.

    Manages multiple exchange instances and routes calls.
    All operations are async; use SyncGatewayWrapper for sync access.
    """

    def __init__(self, paper_mode: bool = True):
        self.paper_mode = paper_mode
        self._exchanges: Dict[str, Any] = {}
        self._initialized = False

    async def initialize(self):
        """Initialize ccxt exchange instances from env vars."""
        if self._initialized:
            return

        import ccxt.async_support as ccxt

        exchange_configs = [
            {
                'name': 'binance',
                'class': ccxt.binance,
                'env_prefix': 'EXCHANGE_GATEWAY_BINANCE',
                'default_testnet': True,
            },
            {
                'name': 'bybit',
                'class': ccxt.bybit,
                'env_prefix': 'EXCHANGE_GATEWAY_BYBIT',
                'default_testnet': True,
            },
        ]

        for cfg in exchange_configs:
            api_key = os.environ.get(f'{cfg["env_prefix"]}_API_KEY', '')
            api_secret = os.environ.get(f'{cfg["env_prefix"]}_API_SECRET', '')
            testnet = os.environ.get(
                f'{cfg["env_prefix"]}_TESTNET', str(cfg['default_testnet'])
            ).lower() in ('true', '1', 'yes')

            if not api_key or not api_secret:
                log.debug('[GW] %s: no credentials — skipped', cfg['name'])
                continue

            try:
                exchange = cfg['class']({
                    'apiKey': api_key,
                    'secret': api_secret,
                    'enableRateLimit': True,
                    'options': {'defaultType': 'spot'},
                })
                if testnet:
                    exchange.set_sandbox_mode(True)
                self._exchanges[cfg['name']] = exchange
                log.info('[GW] %s initialized (testnet=%s)', cfg['name'], testnet)
            except Exception as e:
                log.error('[GW] Failed to init %s: %s', cfg['name'], e)

        self._initialized = True
        log.info('[GW] Exchanges ready: %s', list(self._exchanges.keys()))

    async def close(self):
        """Close all exchange sessions."""
        for name, exchange in self._exchanges.items():
            try:
                await exchange.close()
                log.info('[GW] Closed %s', name)
            except Exception as e:
                log.error('[GW] Error closing %s: %s', name, e)

    async def __aenter__(self):
        await self.initialize()
        return self

    async def __aexit__(self, *exc):
        await self.close()

    def list_exchanges(self) -> List[str]:
        return list(self._exchanges.keys())

    def _get_exchange(self, name: str):
        if name not in self._exchanges:
            raise KeyError(f"Exchange '{name}' not configured. Available: {self.list_exchanges()}")
        return self._exchanges[name]

    def _map_symbol(self, exchange: str, symbol: str) -> Optional[str]:
        """Map our symbol to ccxt unified symbol. Returns None if not supported."""
        mapping = SYMBOL_MAP.get(exchange, {})
        return mapping.get(symbol)

    # ── market data ────────────────────────────────────────────────────

    async def fetch_ticker(self, exchange: str, symbol: str) -> Dict[str, Any]:
        """Fetch latest ticker (bid/ask/last/volume)."""
        ex = self._get_exchange(exchange)
        ccxt_symbol = self._map_symbol(exchange, symbol)
        if not ccxt_symbol:
            raise ValueError(f"{symbol} not supported on {exchange}")
        ticker = await ex.fetch_ticker(ccxt_symbol)
        return {
            'symbol': symbol,
            'exchange': exchange,
            'bid': ticker.get('bid', 0),
            'ask': ticker.get('ask', 0),
            'last': ticker.get('last', 0),
            'volume': ticker.get('baseVolume', 0),
            'timestamp': ticker.get('timestamp', int(time.time() * 1000)),
        }

    async def fetch_ohlcv(
        self, exchange: str, symbol: str, timeframe: str = '1h', limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Fetch OHLCV candles."""
        ex = self._get_exchange(exchange)
        ccxt_symbol = self._map_symbol(exchange, symbol)
        if not ccxt_symbol:
            raise ValueError(f"{symbol} not supported on {exchange}")
        ccxt_tf = TF_MAP.get(timeframe, '1h')
        candles = await ex.fetch_ohlcv(ccxt_symbol, ccxt_tf, limit=limit)
        return [
            {
                'timestamp': int(c[0]),
                'open': c[1],
                'high': c[2],
                'low': c[3],
                'close': c[4],
                'volume': c[5],
            }
            for c in candles
        ]

    async def fetch_order_book(self, exchange: str, symbol: str, depth: int = 20) -> Dict[str, Any]:
        """Fetch L2 order book."""
        ex = self._get_exchange(exchange)
        ccxt_symbol = self._map_symbol(exchange, symbol)
        if not ccxt_symbol:
            raise ValueError(f"{symbol} not supported on {exchange}")
        book = await ex.fetch_order_book(ccxt_symbol, limit=depth)
        return {
            'symbol': symbol,
            'exchange': exchange,
            'bids': book.get('bids', [])[:depth],
            'asks': book.get('asks', [])[:depth],
            'timestamp': book.get('timestamp', int(time.time() * 1000)),
        }

    # ── account ────────────────────────────────────────────────────────

    async def fetch_balance(self, exchange: str) -> Dict[str, float]:
        """Fetch free balances (non-zero only)."""
        ex = self._get_exchange(exchange)
        balance = await ex.fetch_balance()
        return {
            k: v for k, v in balance.get('free', {}).items()
            if v and float(v) > 0
        }

    async def fetch_positions(self, exchange: str) -> List[Dict[str, Any]]:
        """Fetch open positions (unified account)."""
        ex = self._get_exchange(exchange)
        try:
            positions = await ex.fetch_positions()
            return [
                {
                    'symbol': p.get('symbol'),
                    'side': p.get('side'),
                    'contracts': p.get('contracts', 0),
                    'entry_price': p.get('entryPrice', 0),
                    'unrealized_pnl': p.get('unrealizedPnl', 0),
                    'liquidation_price': p.get('liquidationPrice', 0),
                }
                for p in positions if p.get('contracts', 0) != 0
            ]
        except Exception as e:
            log.warning('[GW] fetch_positions not supported on %s: %s', exchange, e)
            return []

    # ── orders ─────────────────────────────────────────────────────────

    async def create_order(
        self,
        exchange: str,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: Optional[float] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> GatewayResult:
        """
        Place an order.

        Args:
            exchange: 'binance' or 'bybit'
            symbol: Our format (e.g., 'BTCUSD')
            side: 'buy' or 'sell'
            order_type: 'market' or 'limit'
            quantity: Order quantity
            price: Limit price (required for limit orders)
            params: Additional exchange-specific params
        """
        t0 = time.time()
        ex = self._get_exchange(exchange)
        ccxt_symbol = self._map_symbol(exchange, symbol)
        if not ccxt_symbol:
            return GatewayResult(
                success=False, exchange=exchange, symbol=symbol,
                error=f"{symbol} not supported on {exchange}"
            )

        if self.paper_mode:
            log.info('[GW][PAPER] %s %s %s %s qty=%.6f price=%s',
                     exchange, side, order_type, ccxt_symbol, quantity, price)
            return GatewayResult(
                success=True, exchange=exchange, symbol=symbol,
                side=side, order_type=order_type,
                quantity=quantity, price=price or 0,
                order_id=f"PAPER_{exchange}_{int(time.time())}",
                status='FILLED', filled=quantity,
                average=price or 0,
                latency_ms=(time.time() - t0) * 1000,
            )

        try:
            params = params or {}
            order = await ex.create_order(
                symbol=ccxt_symbol,
                type=order_type,
                side=side,
                amount=quantity,
                price=price,
                params=params,
            )
            latency = (time.time() - t0) * 1000
            result = GatewayResult(
                success=True, exchange=exchange, symbol=symbol,
                side=side, order_type=order_type,
                quantity=quantity, price=price or 0,
                order_id=str(order.get('id', '')),
                status=order.get('status', 'unknown'),
                filled=order.get('filled', 0),
                average=order.get('average', 0) or order.get('price', 0),
                raw=order,
                latency_ms=latency,
            )
            log.info('[GW] Order placed: %s %s %s %s qty=%.6f → id=%s status=%s (%.0fms)',
                     exchange, side, order_type, ccxt_symbol, quantity,
                     result.order_id, result.status, latency)
            return result
        except Exception as e:
            latency = (time.time() - t0) * 1000
            log.error('[GW] Order failed %s %s %s: %s (%.0fms)',
                      exchange, side, ccxt_symbol, e, latency)
            return GatewayResult(
                success=False, exchange=exchange, symbol=symbol,
                side=side, order_type=order_type,
                quantity=quantity, price=price or 0,
                error=str(e), latency_ms=latency,
            )

    async def cancel_order(self, exchange: str, symbol: str, order_id: str) -> bool:
        """Cancel an open order."""
        ex = self._get_exchange(exchange)
        ccxt_symbol = self._map_symbol(exchange, symbol)
        if not ccxt_symbol:
            return False
        try:
            await ex.cancel_order(order_id, ccxt_symbol)
            log.info('[GW] Cancelled %s on %s', order_id, exchange)
            return True
        except Exception as e:
            log.error('[GW] Cancel failed %s: %s', order_id, e)
            return False

    async def fetch_open_orders(self, exchange: str, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch open orders."""
        ex = self._get_exchange(exchange)
        ccxt_symbol = self._map_symbol(exchange, symbol) if symbol else None
        orders = await ex.fetch_open_orders(ccxt_symbol)
        return [
            {
                'id': o.get('id'),
                'symbol': o.get('symbol'),
                'side': o.get('side'),
                'type': o.get('type'),
                'amount': o.get('amount'),
                'price': o.get('price'),
                'status': o.get('status'),
                'timestamp': o.get('timestamp'),
            }
            for o in orders
        ]

    # ── convenience: multi-exchange ────────────────────────────────────

    async def fetch_multi_ticker(self, symbol: str) -> Dict[str, Dict[str, Any]]:
        """Fetch ticker from all configured exchanges concurrently."""
        tasks = {
            name: self.fetch_ticker(name, symbol)
            for name in self._exchanges
            if self._map_symbol(name, symbol)
        }
        results = {}
        for name, task in tasks.items():
            try:
                results[name] = await task
            except Exception as e:
                log.error('[GW] Multi-ticker failed on %s: %s', name, e)
        return results


# ══════════════════════════════════════════════════════════════════════════════
# SYNC WRAPPER — For pipeline orchestrator integration
# ══════════════════════════════════════════════════════════════════════════════

class SyncGatewayWrapper:
    """
    Synchronous wrapper around the async ExchangeGateway.

    Runs async operations in a dedicated background thread with its own
    event loop. Safe to call from sync code (pipeline orchestrator).
    """

    def __init__(self, paper_mode: bool = True):
        self._gateway = ExchangeGateway(paper_mode=paper_mode)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()
        self._paper_mode = paper_mode

    def _run_loop(self):
        """Background thread: run event loop."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._gateway.initialize())
        self._ready.set()
        self._loop.run_forever()

    def start(self):
        """Start the background event loop thread."""
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=30)
        log.info('[GW-SYNC] Gateway thread started (paper=%s)', self._paper_mode)

    def stop(self):
        """Stop the background event loop."""
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=5)
        log.info('[GW-SYNC] Gateway thread stopped')

    def _run_async(self, coro):
        """Run an async coroutine in the background loop and wait for result."""
        if not self._loop or not self._loop.is_running():
            self.start()
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=30)

    # ── sync public API ────────────────────────────────────────────────

    def execute_signal(
        self,
        symbol: str,
        side: str,
        price: float,
        quantity: float,
        exchange: str = 'binance',
        order_type: str = 'limit',
    ) -> GatewayResult:
        """
        Execute a trading signal (sync).

        Called by pipeline orchestrator when decision is EXECUTE.
        """
        ccxt_side = 'buy' if side.upper() in ('BUY', 'LONG', 'BULLISH') else 'sell'

        # Paper mode fallback: no exchanges configured
        if self._paper_mode and not self._gateway.list_exchanges():
            log.info('[GW][PAPER] %s %s %s qty=%.6f price=%s (no exchange configured)',
                     exchange, ccxt_side, order_type, quantity, price)
            return GatewayResult(
                success=True, exchange=exchange, symbol=symbol,
                side=ccxt_side, order_type=order_type,
                quantity=quantity, price=price,
                order_id=f"PAPER_{exchange}_{int(time.time())}",
                status='FILLED', filled=quantity,
                average=price,
            )

        return self._run_async(
            self._gateway.create_order(
                exchange=exchange,
                symbol=symbol,
                side=ccxt_side,
                order_type=order_type,
                quantity=quantity,
                price=price if order_type == 'limit' else None,
            )
        )

    def get_ticker(self, exchange: str, symbol: str) -> Dict[str, Any]:
        """Fetch ticker (sync)."""
        return self._run_async(self._gateway.fetch_ticker(exchange, symbol))

    def get_candles(self, exchange: str, symbol: str, timeframe: str = '1h', limit: int = 100) -> List[Dict[str, Any]]:
        """Fetch OHLCV candles (sync)."""
        return self._run_async(self._gateway.fetch_ohlcv(exchange, symbol, timeframe, limit))

    def get_order_book(self, exchange: str, symbol: str, depth: int = 20) -> Dict[str, Any]:
        """Fetch order book (sync)."""
        return self._run_async(self._gateway.fetch_order_book(exchange, symbol, depth))

    def get_balance(self, exchange: str) -> Dict[str, float]:
        """Fetch balance (sync)."""
        return self._run_async(self._gateway.fetch_balance(exchange))

    def list_exchanges(self) -> List[str]:
        return self._gateway.list_exchanges()


# ══════════════════════════════════════════════════════════════════════════════
# MODULE SINGLETON
# ══════════════════════════════════════════════════════════════════════════════

_gateway: Optional[SyncGatewayWrapper] = None


def get_exchange_gateway(paper_mode: Optional[bool] = None) -> SyncGatewayWrapper:
    """
    Get or create the module-level gateway singleton.

    paper_mode defaults to True unless PAPER_MODE env var is 'false'.
    """
    global _gateway
    if _gateway is None:
        if paper_mode is None:
            paper_mode = os.environ.get('PAPER_MODE', 'true').lower() != 'false'
        _gateway = SyncGatewayWrapper(paper_mode=paper_mode)
        _gateway.start()
    return _gateway


def shutdown_gateway():
    """Shutdown the module-level gateway."""
    global _gateway
    if _gateway is not None:
        _gateway.stop()
        _gateway = None
