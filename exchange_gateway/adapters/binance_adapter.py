"""
Exchange Gateway — Binance Adapter
===================================
Binance REST/signed API implementation using HMAC-SHA256.

Endpoints used:
  - GET /api/v3/ticker/bookTicker  (ticker)
  - GET /api/v3/depth              (order book)
  - GET /api/v3/account            (balance)
  - POST /api/v3/order             (place order)
  - DELETE /api/v3/order           (cancel order)
  - GET /api/v3/openOrders         (open orders)
"""

import time
import hmac
import hashlib
import logging
import asyncio
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import aiohttp

from config_manager import ExchangeCredentials, RateLimitConfig
from base_adapter import BaseAdapter, Ticker, OrderBook, OrderResult

log = logging.getLogger("BinanceAdapter")

# ── endpoints ──────────────────────────────────────────────────────────

BASE_URL_LIVE = "https://api.binance.com"
BASE_URL_TEST = "https://testnet.binance.vision"

SYMBOL_MAP = {
    "BTCUSDT": "BTCUSDT",
    "ETHUSDT": "ETHUSDT",
    "XAUUSD": "PAXGUSDT",   # Binance has PAXG for gold
    "BNBUSDT": "BNBUSDT",
    "SOLUSDT": "SOLUSDT",
    "XRPUSDT": "XRPUSDT",
}


class BinanceAdapter(BaseAdapter):
    """Binance exchange adapter."""

    def __init__(self, creds: ExchangeCredentials, rate_cfg: RateLimitConfig):
        super().__init__(creds, rate_cfg)
        self._base_url = BASE_URL_TEST if self.testnet else BASE_URL_LIVE
        self._session: Optional[aiohttp.ClientSession] = None

    # ── session management ─────────────────────────────────────────────

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    # ── signing ────────────────────────────────────────────────────────

    def _sign(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """HMAC-SHA256 sign and return headers."""
        params["timestamp"] = int(time.time() * 1000)
        query = urlencode(params)
        signature = hmac.new(
            self.creds.api_secret.encode(),
            query.encode(),
            hashlib.sha256,
        ).hexdigest()
        params["signature"] = signature
        headers = {"X-MBX-APIKEY": self.creds.api_key}
        return {"params": params, "headers": headers}

    # ── internal request ───────────────────────────────────────────────

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        signed: bool = False,
        weight: int = 1,
    ) -> Dict[str, Any]:
        """Fire an HTTP request with rate limiting and error handling."""
        await self._throttle(weight)
        session = await self._get_session()
        url = f"{self._base_url}{path}"

        headers: Dict[str, str] = {}
        if signed:
            if params is None:
                params = {}
            signed_payload = self._sign(params)
            params = signed_payload["params"]
            headers = signed_payload["headers"]

        try:
            async with session.request(method, url, params=params, headers=headers) as resp:
                body = await resp.json()
                if resp.status == 429:
                    retry_after = int(resp.headers.get("Retry-After", 60))
                    log.warning("[BINANCE] 429 — sleeping %ds", retry_after)
                    await asyncio.sleep(retry_after)
                    return await self._request(method, path, params, signed, weight)
                if resp.status != 200:
                    log.error("[BINANCE] HTTP %d %s %s: %s", resp.status, method, path, body)
                    raise aiohttp.ClientResponseError(
                        resp.request_info, resp.history, status=resp.status, message=str(body)
                    )
                return body
        except aiohttp.ClientResponseError:
            raise
        except Exception as e:
            log.error("[BINANCE] Request failed %s %s: %s", method, path, e)
            raise

    # ── market data ────────────────────────────────────────────────────

    async def fetch_ticker(self, symbol: str) -> Ticker:
        bsym = SYMBOL_MAP.get(symbol, symbol)
        data = await self._request("GET", "/api/v3/ticker/bookTicker", {"symbol": bsym}, weight=2)
        return Ticker(
            symbol=symbol,
            bid=float(data.get("bidPrice", 0)),
            ask=float(data.get("askPrice", 0)),
            last=(float(data.get("bidPrice", 0)) + float(data.get("askPrice", 0))) / 2,
            timestamp=int(time.time() * 1000),
        )

    async def fetch_order_book(self, symbol: str, depth: int = 20) -> OrderBook:
        bsym = SYMBOL_MAP.get(symbol, symbol)
        data = await self._request("GET", "/api/v3/depth", {"symbol": bsym, "limit": depth}, weight=5)
        return OrderBook(
            symbol=symbol,
            bids=[[float(p), float(q)] for p, q in data.get("bids", [])],
            asks=[[float(p), float(q)] for p, q in data.get("asks", [])],
            timestamp=int(time.time() * 1000),
        )

    # ── account ────────────────────────────────────────────────────────

    async def get_balance(self) -> Dict[str, float]:
        data = await self._request("GET", "/api/v3/account", signed=True, weight=10)
        balances = {}
        for asset in data.get("balances", []):
            free = float(asset.get("free", 0))
            if free > 0:
                balances[asset["asset"]] = free
        return balances

    async def get_positions(self) -> List[Dict[str, Any]]:
        data = await self._request("GET", "/api/v3/account", signed=True, weight=10)
        positions = []
        for pos in data.get("positions", []):
            amt = float(pos.get("positionAmt", 0))
            if amt != 0:
                positions.append({
                    "symbol": pos["symbol"],
                    "side": "LONG" if amt > 0 else "SHORT",
                    "quantity": abs(amt),
                    "entry_price": float(pos.get("entryPrice", 0)),
                    "unrealized_pnl": float(pos.get("unrealizedProfit", 0)),
                })
        return positions

    # ── orders ─────────────────────────────────────────────────────────

    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: Optional[float] = None,
    ) -> OrderResult:
        bsym = SYMBOL_MAP.get(symbol, symbol)
        params: Dict[str, Any] = {
            "symbol": bsym,
            "side": side.upper(),
            "type": order_type.upper(),
            "quantity": f"{quantity}",
        }
        if order_type.upper() == "LIMIT" and price is not None:
            params["price"] = f"{price}"
            params["timeInForce"] = "GTC"

        data = await self._request("POST", "/api/v3/order", params, signed=True, weight=1)
        return OrderResult(
            order_id=str(data.get("orderId", "")),
            symbol=symbol,
            side=side.upper(),
            order_type=order_type.upper(),
            quantity=quantity,
            price=price,
            status=data.get("status", "UNKNOWN"),
            raw=data,
        )

    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        bsym = SYMBOL_MAP.get(symbol, symbol)
        try:
            await self._request(
                "DELETE", "/api/v3/order",
                {"symbol": bsym, "orderId": int(order_id)},
                signed=True, weight=1,
            )
            log.info("[BINANCE] Cancelled order %s", order_id)
            return True
        except Exception as e:
            log.error("[BINANCE] Cancel failed for %s: %s", order_id, e)
            return False

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {}
        if symbol:
            params["symbol"] = SYMBOL_MAP.get(symbol, symbol)
        data = await self._request("GET", "/api/v3/openOrders", params, signed=True, weight=3)
        return data
