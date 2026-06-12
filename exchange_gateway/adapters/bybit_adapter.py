"""
Exchange Gateway — Bybit Adapter
=================================
Bybit REST/signed API implementation using HMAC-SHA256.

Endpoints used (v5 unified):
  - GET /v5/market/tickers        (ticker)
  - GET /v5/market/orderbook      (order book)
  - GET /v5/account/wallet-balance (balance)
  - POST /v5/order/create         (place order)
  - POST /v5/order/cancel         (cancel order)
  - GET /v5/order/realtime        (open orders)
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

log = logging.getLogger("BybitAdapter")

# ── endpoints ──────────────────────────────────────────────────────────

BASE_URL_LIVE = "https://api.bybit.com"
BASE_URL_TEST = "https://api-testnet.bybit.com"

SYMBOL_MAP = {
    "BTCUSDT": "BTCUSDT",
    "ETHUSDT": "ETHUSDT",
    "XAUUSD": "XAUUSD",
    "BNBUSDT": "BNBUSDT",
    "SOLUSDT": "SOLUSDT",
    "XRPUSDT": "XRPUSDT",
}


class BybitAdapter(BaseAdapter):
    """Bybit exchange adapter."""

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
        """HMAC-SHA256 sign per Bybit v5 spec.

        Bybit signs: HMAC(timestamp + api_key + recv_window + body, secret)
        """
        timestamp = int(time.time() * 1000)
        recv_window = 5000
        body = urlencode(sorted(params.items())) if params else ""

        sign_str = f"{timestamp}{self.creds.api_key}{recv_window}{body}"
        signature = hmac.new(
            self.creds.api_secret.encode(),
            sign_str.encode(),
            hashlib.sha256,
        ).hexdigest()

        headers = {
            "X-BAPI-API-KEY": self.creds.api_key,
            "X-BAPI-SIGN": signature,
            "X-BAPI-TIMESTAMP": str(timestamp),
            "X-BAPI-RECV-WINDOW": str(recv_window),
        }
        return {"headers": headers, "body": body}

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
        body_data = None

        if signed:
            signed_payload = self._sign(params or {})
            headers = signed_payload["headers"]
            if method == "POST":
                body_data = params
            else:
                url = f"{url}?{urlencode(params)}" if params else url

        try:
            kwargs: Dict[str, Any] = {"headers": headers}
            if method == "POST" and body_data:
                kwargs["json"] = body_data

            async with session.request(method, url, **kwargs) as resp:
                body = await resp.json()
                if resp.status == 429:
                    retry_after = int(resp.headers.get("Retry-After", 60))
                    log.warning("[BYBIT] 429 — sleeping %ds", retry_after)
                    await asyncio.sleep(retry_after)
                    return await self._request(method, path, params, signed, weight)
                if resp.status != 200:
                    log.error("[BYBIT] HTTP %d %s %s: %s", resp.status, method, path, body)
                    raise aiohttp.ClientResponseError(
                        resp.request_info, resp.history, status=resp.status, message=str(body)
                    )
                ret_code = body.get("retCode", 0)
                if ret_code != 0:
                    log.error("[BYBIT] API error %s: %s", ret_code, body.get("retMsg", ""))
                    raise ValueError(f"Bybit error {ret_code}: {body.get('retMsg', '')}")
                return body.get("result", body)
        except (aiohttp.ClientResponseError, ValueError):
            raise
        except Exception as e:
            log.error("[BYBIT] Request failed %s %s: %s", method, path, e)
            raise

    # ── market data ────────────────────────────────────────────────────

    async def fetch_ticker(self, symbol: str) -> Ticker:
        bsym = SYMBOL_MAP.get(symbol, symbol)
        data = await self._request(
            "GET", "/v5/market/tickers",
            {"category": "spot", "symbol": bsym},
            weight=1,
        )
        ticker = data.get("list", [{}])[0] if data.get("list") else {}
        bid = float(ticker.get("bid1Price", 0))
        ask = float(ticker.get("ask1Price", 0))
        return Ticker(
            symbol=symbol,
            bid=bid,
            ask=ask,
            last=float(ticker.get("lastPrice", 0)),
            timestamp=int(time.time() * 1000),
        )

    async def fetch_order_book(self, symbol: str, depth: int = 20) -> OrderBook:
        bsym = SYMBOL_MAP.get(symbol, symbol)
        data = await self._request(
            "GET", "/v5/market/orderbook",
            {"category": "spot", "symbol": bsym, "limit": depth},
            weight=1,
        )
        return OrderBook(
            symbol=symbol,
            bids=[[float(p), float(q)] for p, q in data.get("b", [])],
            asks=[[float(p), float(q)] for p, q in data.get("a", [])],
            timestamp=int(time.time() * 1000),
        )

    # ── account ────────────────────────────────────────────────────────

    async def get_balance(self) -> Dict[str, float]:
        data = await self._request(
            "GET", "/v5/account/wallet-balance",
            {"accountType": "UNIFIED"},
            signed=True, weight=1,
        )
        balances = {}
        for coin in data.get("list", [{}])[0].get("coin", []):
            free = float(coin.get("availableToWithdraw", 0))
            if free > 0:
                balances[coin["coin"]] = free
        return balances

    async def get_positions(self) -> List[Dict[str, Any]]:
        data = await self._request(
            "GET", "/v5/position/list",
            {"category": "linear"},
            signed=True, weight=1,
        )
        positions = []
        for pos in data.get("list", []):
            size = float(pos.get("size", 0))
            if size > 0:
                positions.append({
                    "symbol": pos.get("symbol", ""),
                    "side": pos.get("side", ""),
                    "quantity": size,
                    "entry_price": float(pos.get("avgPrice", 0)),
                    "unrealized_pnl": float(pos.get("unrealisedPnl", 0)),
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
            "category": "spot",
            "symbol": bsym,
            "side": "Buy" if side.upper() == "BUY" else "Sell",
            "orderType": order_type.capitalize(),
            "qty": str(quantity),
        }
        if order_type.upper() == "LIMIT" and price is not None:
            params["price"] = str(price)

        data = await self._request("POST", "/v5/order/create", params, signed=True, weight=1)
        return OrderResult(
            order_id=data.get("orderId", ""),
            symbol=symbol,
            side=side.upper(),
            order_type=order_type.upper(),
            quantity=quantity,
            price=price,
            status="NEW",
            raw=data,
        )

    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        bsym = SYMBOL_MAP.get(symbol, symbol)
        try:
            await self._request(
                "POST", "/v5/order/cancel",
                {"category": "spot", "symbol": bsym, "orderId": order_id},
                signed=True, weight=1,
            )
            log.info("[BYBIT] Cancelled order %s", order_id)
            return True
        except Exception as e:
            log.error("[BYBIT] Cancel failed for %s: %s", order_id, e)
            return False

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"category": "spot"}
        if symbol:
            params["symbol"] = SYMBOL_MAP.get(symbol, symbol)
        data = await self._request("GET", "/v5/order/realtime", params, signed=True, weight=1)
        return data.get("list", [])
