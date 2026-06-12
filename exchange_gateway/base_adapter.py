"""
Exchange Gateway — Base Adapter (Abstract Interface)
====================================================
Defines the unified interface every exchange adapter must implement.

All adapters:
  - Accept ExchangeCredentials + RateLimitConfig at construction.
  - Expose async methods for market data, account, and order operations.
  - Return normalized response dicts with a common shape.
"""

import abc
import time
import logging
import asyncio
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from config_manager import ExchangeCredentials, RateLimitConfig

log = logging.getLogger("BaseAdapter")


# ── normalized response types ──────────────────────────────────────────

@dataclass
class Ticker:
    """Normalized ticker snapshot."""
    symbol: str
    bid: float
    ask: float
    last: float
    timestamp: int  # epoch ms


@dataclass
class OrderBook:
    """Normalized order book."""
    symbol: str
    bids: List[List[float]]  # [[price, qty], ...]
    asks: List[List[float]]
    timestamp: int


@dataclass
class OrderResult:
    """Normalized order placement result."""
    order_id: str
    symbol: str
    side: str          # "BUY" or "SELL"
    order_type: str    # "MARKET" or "LIMIT"
    quantity: float
    price: Optional[float]
    status: str        # "FILLED", "NEW", "PARTIALLY_FILLED"
    raw: Dict[str, Any] = field(default_factory=dict)


# ── rate limiter ───────────────────────────────────────────────────────

class RateLimiter:
    """Token-bucket rate limiter (async-safe)."""

    def __init__(self, cfg: RateLimitConfig):
        self.rpm = cfg.requests_per_minute
        self.tokens = float(self.rpm)
        self.last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, weight: int = 1):
        """Block until *weight* tokens are available."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            self.tokens = min(self.rpm, self.tokens + elapsed * (self.rpm / 60.0))
            self.last_refill = now

            while self.tokens < weight:
                wait = (weight - self.tokens) / (self.rpm / 60.0)
                log.debug("[RATE] %s — sleeping %.2fs for %d tokens", type(self).__name__, wait, weight)
                await asyncio.sleep(wait)
                now = time.monotonic()
                elapsed = now - self.last_refill
                self.tokens = min(self.rpm, self.tokens + elapsed * (self.rpm / 60.0))
                self.last_refill = now

            self.tokens -= weight


# ── abstract base adapter ─────────────────────────────────────────────

class BaseAdapter(abc.ABC):
    """
    Abstract base class for exchange adapters.

    Subclasses MUST implement every @abstractmethod.
    """

    def __init__(self, creds: ExchangeCredentials, rate_cfg: RateLimitConfig):
        self.creds = creds
        self.rate_limiter = RateLimiter(rate_cfg)
        self.exchange = creds.exchange
        self.testnet = creds.testnet
        log.info("[%s] Adapter initialized (testnet=%s)", self.exchange.upper(), self.testnet)

    # ── market data ────────────────────────────────────────────────────

    @abc.abstractmethod
    async def fetch_ticker(self, symbol: str) -> Ticker:
        """Fetch latest bid/ask/last for *symbol*."""
        ...

    @abc.abstractmethod
    async def fetch_order_book(self, symbol: str, depth: int = 20) -> OrderBook:
        """Fetch L2 order book for *symbol*."""
        ...

    # ── account ────────────────────────────────────────────────────────

    @abc.abstractmethod
    async def get_balance(self) -> Dict[str, float]:
        """Return {asset: free_balance} mapping."""
        ...

    @abc.abstractmethod
    async def get_positions(self) -> List[Dict[str, Any]]:
        """Return list of open positions."""
        ...

    # ── orders ─────────────────────────────────────────────────────────

    @abc.abstractmethod
    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: Optional[float] = None,
    ) -> OrderResult:
        """Place an order and return a normalized result."""
        ...

    @abc.abstractmethod
    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        """Cancel an open order. Returns True on success."""
        ...

    @abc.abstractmethod
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return list of open orders, optionally filtered by symbol."""
        ...

    # ── signing (exchange-specific) ────────────────────────────────────

    @abc.abstractmethod
    def _sign(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Sign request params and return headers/payload."""
        ...

    # ── helpers ────────────────────────────────────────────────────────

    async def _throttle(self, weight: int = 1):
        """Convenience: wait for rate-limit tokens."""
        await self.rate_limiter.acquire(weight)

    def _normalize_symbol(self, symbol: str) -> str:
        """Override in subclass if exchange uses different symbol format."""
        return symbol.upper()
