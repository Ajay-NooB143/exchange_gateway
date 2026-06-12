"""
Exchange Gateway — Orchestrator
================================
Routes incoming trading signals to the correct exchange adapter,
manages adapter lifecycle, and provides a unified async API.

Usage:
    from gateway import ExchangeGateway
    async with ExchangeGateway.from_config() as gw:
        ticker = await gw.fetch_ticker("binance", "BTCUSDT")
        result = await gw.place_order("bybit", "BTCUSDT", "BUY", "LIMIT", 0.001, price=65000)
"""

import sys
import logging
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure exchange_gateway is importable
sys.path.insert(0, str(Path(__file__).parent))

from config_manager import ExchangeConfig, ExchangeCredentials
from base_adapter import BaseAdapter, Ticker, OrderBook, OrderResult
from adapters.binance_adapter import BinanceAdapter
from adapters.bybit_adapter import BybitAdapter

log = logging.getLogger("ExchangeGateway")

# ── adapter registry ───────────────────────────────────────────────────

ADAPTER_CLASSES = {
    "binance": BinanceAdapter,
    "bybit": BybitAdapter,
}


class ExchangeGateway:
    """
    Unified exchange gateway.

    Manages multiple exchange adapters and routes calls to the correct one.
    """

    def __init__(self, config: ExchangeConfig):
        self._config = config
        self._adapters: Dict[str, BaseAdapter] = {}
        self._init_adapters()

    # ── lifecycle ──────────────────────────────────────────────────────

    @classmethod
    def from_config(cls, config: Optional[ExchangeConfig] = None) -> "ExchangeGateway":
        """Create gateway from config (or load from env/JSON)."""
        cfg = config or ExchangeConfig.from_env()
        return cls(cfg)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.close()

    async def close(self):
        """Close all adapter sessions."""
        for name, adapter in self._adapters.items():
            try:
                await adapter.close()
                log.info("[GW] Closed %s adapter", name)
            except Exception as e:
                log.error("[GW] Error closing %s: %s", name, e)

    # ── public API ─────────────────────────────────────────────────────

    def list_exchanges(self) -> List[str]:
        """Return names of all initialized exchanges."""
        return list(self._adapters.keys())

    def get_adapter(self, exchange: str) -> BaseAdapter:
        """Get the adapter for *exchange*."""
        if exchange not in self._adapters:
            raise KeyError(f"Exchange '{exchange}' not configured. Available: {self.list_exchanges()}")
        return self._adapters[exchange]

    # ── market data ────────────────────────────────────────────────────

    async def fetch_ticker(self, exchange: str, symbol: str) -> Ticker:
        return await self.get_adapter(exchange).fetch_ticker(symbol)

    async def fetch_order_book(self, exchange: str, symbol: str, depth: int = 20) -> OrderBook:
        return await self.get_adapter(exchange).fetch_order_book(symbol, depth)

    async def fetch_multi_ticker(self, exchanges: List[str], symbol: str) -> Dict[str, Ticker]:
        """Fetch ticker from multiple exchanges concurrently."""
        tasks = {e: self.fetch_ticker(e, symbol) for e in exchanges}
        results: Dict[str, Ticker] = {}
        for exchange, task in tasks.items():
            try:
                results[exchange] = await task
            except Exception as e:
                log.error("[GW] Ticker fetch failed on %s: %s", exchange, e)
        return results

    # ── account ────────────────────────────────────────────────────────

    async def get_balance(self, exchange: str) -> Dict[str, float]:
        return await self.get_adapter(exchange).get_balance()

    async def get_positions(self, exchange: str) -> List[Dict[str, Any]]:
        return await self.get_adapter(exchange).get_positions()

    async def get_multi_balance(self, exchanges: List[str]) -> Dict[str, Dict[str, float]]:
        """Fetch balances from multiple exchanges concurrently."""
        tasks = {e: self.get_balance(e) for e in exchanges}
        results: Dict[str, Dict[str, float]] = {}
        for exchange, task in tasks.items():
            try:
                results[exchange] = await task
            except Exception as e:
                log.error("[GW] Balance fetch failed on %s: %s", exchange, e)
        return results

    # ── orders ─────────────────────────────────────────────────────────

    async def place_order(
        self,
        exchange: str,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: Optional[float] = None,
    ) -> OrderResult:
        """Place an order on a specific exchange."""
        adapter = self.get_adapter(exchange)
        log.info(
            "[GW] %s %s %s %s qty=%.6f price=%s",
            exchange.upper(), side.upper(), order_type.upper(), symbol, quantity, price,
        )
        result = await adapter.place_order(symbol, side, order_type, quantity, price)
        log.info("[GW] Order placed: %s status=%s", result.order_id, result.status)
        return result

    async def cancel_order(self, exchange: str, symbol: str, order_id: str) -> bool:
        return await self.get_adapter(exchange).cancel_order(symbol, order_id)

    async def get_open_orders(self, exchange: str, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        return await self.get_adapter(exchange).get_open_orders(symbol)

    # ── arbitrage helper ───────────────────────────────────────────────

    async def find_best_spread(self, symbol: str) -> Dict[str, Any]:
        """Compare bid/ask across exchanges and return the best spread.

        Returns dict with 'buy_exchange', 'sell_exchange', 'spread_pct'.
        """
        tickers = await self.fetch_multi_ticker(self.list_exchanges(), symbol)
        if len(tickers) < 2:
            return {"error": "Need at least 2 exchanges"}

        # Best bid (highest) = where to sell
        best_bid_ex = max(tickers, key=lambda e: tickers[e].bid)
        # Best ask (lowest) = where to buy
        best_ask_ex = min(tickers, key=lambda e: tickers[e].ask)

        best_bid = tickers[best_bid_ex].bid
        best_ask = tickers[best_ask_ex].ask
        spread = best_bid - best_ask
        spread_pct = (spread / best_ask * 100) if best_ask > 0 else 0

        return {
            "symbol": symbol,
            "buy_exchange": best_ask_ex,
            "buy_price": best_ask,
            "sell_exchange": best_bid_ex,
            "sell_price": best_bid,
            "spread": spread,
            "spread_pct": round(spread_pct, 4),
            "profitable": spread > 0,
        }

    # ── init ───────────────────────────────────────────────────────────

    def _init_adapters(self):
        """Initialize adapters for all configured exchanges."""
        for exchange_name in self._config.list_exchanges():
            cls = ADAPTER_CLASSES.get(exchange_name)
            if cls is None:
                log.warning("[GW] No adapter for exchange '%s' — skipping", exchange_name)
                continue
            try:
                creds = self._config.get_credentials(exchange_name)
                rate_cfg = self._config.get_rate_limits(exchange_name)
                self._adapters[exchange_name] = cls(creds, rate_cfg)
                log.info("[GW] Initialized %s adapter", exchange_name)
            except Exception as e:
                log.error("[GW] Failed to init %s: %s", exchange_name, e)
