"""
═══════════════════════════════════════════════════════════════════════════════
SMC SCALPER — Python Execution Companion
Broker integration + risk management + logging
═══════════════════════════════════════════════════════════════════════════════
"""

import os
import json
import hmac
import hashlib
import time
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import Optional

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Config:
    # Server
    port: int = 3000
    webhook_secret: str = os.getenv("WEBHOOK_SECRET", "CHANGE-ME")
    
    # Broker
    broker_api_key: str = os.getenv("BROKER_API_KEY", "")
    broker_api_secret: str = os.getenv("BROKER_API_SECRET", "")
    broker_base_url: str = os.getenv("BROKER_BASE_URL", "https://api.broker.com/v1")
    
    # Risk
    risk_pct: float = 1.0
    max_position_size: int = 10
    max_daily_trades: int = 20
    max_daily_loss: float = 300.0
    max_drawdown_pct: float = 3.0
    
    # Spread
    max_spread_pips: float = 3.0
    pip_size: float = 0.1  # XAUUSD
    
    # Allowed symbols
    allowed_symbols: list = None
    
    def __post_init__(self):
        if self.allowed_symbols is None:
            self.allowed_symbols = ["XAUUSD"]

config = Config()

# ══════════════════════════════════════════════════════════════════════════════
# TRADE STATE
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class TradeState:
    daily_pnl: float = 0.0
    daily_trades: int = 0
    total_trades: int = 0
    total_pnl: float = 0.0
    peak_equity: float = 10000.0
    current_equity: float = 10000.0
    trading_halted: bool = False
    halt_reason: Optional[str] = None
    last_signal_time: float = time.time()
    last_reset_date: str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    def reset_daily(self):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self.last_reset_date != today:
            self.daily_pnl = 0.0
            self.daily_trades = 0
            self.trading_halted = False
            self.halt_reason = None
            self.last_reset_date = today
    
    def record_trade(self, pnl: float):
        self.daily_pnl += pnl
        self.daily_trades += 1
        self.total_trades += 1
        self.total_pnl += pnl
        self.current_equity += pnl
        if self.current_equity > self.peak_equity:
            self.peak_equity = self.current_equity
        self.last_signal_time = time.time()
    
    def get_drawdown_pct(self) -> float:
        if self.peak_equity <= 0:
            return 0.0
        return ((self.peak_equity - self.current_equity) / self.peak_equity) * 100
    
    def check_hard_stop(self) -> tuple[bool, str]:
        self.reset_daily()
        
        if self.trading_halted:
            return False, self.halt_reason or "HALTED"
        
        if self.daily_pnl <= -config.max_daily_loss:
            reason = f"DAILY_LOSS_LIMIT: ${self.daily_pnl:.2f}"
            self.trading_halted = True
            self.halt_reason = reason
            return False, reason
        
        dd = self.get_drawdown_pct()
        if dd >= config.max_drawdown_pct:
            reason = f"DRAWDOWN_LIMIT: {dd:.2f}%"
            self.trading_halted = True
            self.halt_reason = reason
            return False, reason
        
        if self.daily_trades >= config.max_daily_trades:
            reason = f"TRADE_LIMIT: {self.daily_trades}"
            self.trading_halted = True
            self.halt_reason = reason
            return False, reason
        
        return True, "OK"

state = TradeState()

# ══════════════════════════════════════════════════════════════════════════════
# PAYLOAD VALIDATOR
# ══════════════════════════════════════════════════════════════════════════════

def validate_payload(payload: dict, secret: str) -> tuple[bool, list[str]]:
    errors = []
    
    # Signature
    if secret != config.webhook_secret:
        errors.append("AUTH_FAILED")
    
    # Required fields
    required = ["symbol", "side", "entry_price", "stop_loss", "position_size"]
    for field in required:
        if field not in payload or payload[field] is None:
            errors.append(f"MISSING_{field.upper()}")
    
    # Symbol
    if payload.get("symbol") not in config.allowed_symbols:
        errors.append("SYMBOL_NOT_ALLOWED")
    
    # Side
    if payload.get("side") not in ["Long", "Short"]:
        errors.append("INVALID_SIDE")
    
    # Stop loss direction
    if payload.get("side") == "Long" and payload.get("stop_loss", 0) >= payload.get("entry_price", 0):
        errors.append("LONG_SL_ABOVE_ENTRY")
    if payload.get("side") == "Short" and payload.get("stop_loss", 0) <= payload.get("entry_price", 0):
        errors.append("SHORT_SL_BELOW_ENTRY")
    
    # Position size
    if payload.get("position_size", 0) > config.max_position_size:
        errors.append("SIZE_EXCEEDS_MAX")
    
    return len(errors) == 0, errors

# ══════════════════════════════════════════════════════════════════════════════
# POSITION SIZE CALCULATOR
# ══════════════════════════════════════════════════════════════════════════════

def calculate_position_size(equity: float, risk_pct: float, stop_distance: float, entry_price: float) -> int:
    risk_amount = equity * (risk_pct / 100)
    raw_units = int(risk_amount / stop_distance)
    max_alloc = int((equity * 0.20) / entry_price)
    qty = min(raw_units, max_alloc)
    return max(qty, 0)

# ══════════════════════════════════════════════════════════════════════════════
# BROKER EXECUTOR (Replace with your broker's API)
# ══════════════════════════════════════════════════════════════════════════════

async def execute_order(payload: dict) -> dict:
    """
    Replace this with your broker's actual API call.
    
    Example for a generic broker:
    
    import aiohttp
    
    async with aiohttp.ClientSession() as session:
        order = {
            "symbol": payload["symbol"],
            "side": payload["side"].upper(),
            "type": "LIMIT",
            "quantity": payload["position_size"],
            "price": payload["entry_price"],
            "stopLoss": payload["stop_loss"],
            "timeInForce": "GTC"
        }
        
        headers = {
            "Authorization": f"Bearer {config.broker_api_key}",
            "Content-Type": "application/json"
        }
        
        async with session.post(
            f"{config.broker_base_url}/orders",
            json=order,
            headers=headers
        ) as resp:
            result = await resp.json()
            return {
                "success": resp.status == 200,
                "orderId": result.get("orderId"),
                "fillPrice": payload["entry_price"]
            }
    """
    
    # Simulated execution
    await asyncio.sleep(0.05)  # simulate network latency
    
    return {
        "success": True,
        "orderId": f"SMC-{int(time.time() * 1000)}",
        "fillPrice": payload["entry_price"],
        "latency_ms": 50
    }

# ══════════════════════════════════════════════════════════════════════════════
# HTTP SERVER
# ══════════════════════════════════════════════════════════════════════════════

from aiohttp import web

async def health_handler(request):
    state.reset_daily()
    dd = state.get_drawdown_pct()
    
    return web.json_response({
        "status": "ok",
        "daily_pnl": f"${state.daily_pnl:.2f}",
        "daily_trades": state.daily_trades,
        "drawdown": f"{dd:.2f}%",
        "trading_halted": state.trading_halted,
        "halt_reason": state.halt_reason,
        "total_trades": state.total_trades,
        "equity": f"${state.current_equity:.2f}"
    })

async def kill_handler(request):
    state.trading_halted = True
    state.halt_reason = "MANUAL_KILL_SWITCH"
    return web.json_response({"status": "halted", "reason": "Manual kill switch"})

async def resume_handler(request):
    state.trading_halted = False
    state.halt_reason = None
    return web.json_response({"status": "resumed"})

async def webhook_handler(request):
    # Parse URL params
    secret = request.query.get("secret", "")
    
    # Parse body
    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"status": "error", "message": "Invalid JSON"}, status=400)
    
    # Validate
    valid, errors = validate_payload(payload, secret)
    if not valid:
        return web.json_response({"status": "rejected", "errors": errors}, status=400)
    
    # Check hard-stop
    allowed, reason = state.check_hard_stop()
    if not allowed:
        return web.json_response({"status": "halted", "reason": reason}, status=403)
    
    # Execute
    try:
        result = await execute_order(payload)
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=500)
    
    # Record trade
    state.record_trade(0)  # PnL updated on exit
    
    return web.json_response({
        "status": "executed",
        "orderId": result["orderId"],
        "fillPrice": result["fillPrice"],
        "daily_pnl": f"${state.daily_pnl:.2f}",
        "drawdown": f"{state.get_drawdown_pct():.2f}%"
    })

def create_app():
    app = web.Application()
    app.router.add_get("/health", health_handler)
    app.router.add_post("/kill", kill_handler)
    app.router.add_post("/resume", resume_handler)
    app.router.add_post("/webhook", webhook_handler)
    return app

# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import asyncio
    
    print("═══════════════════════════════════════════════════")
    print("  SMC SCALPER — Execution Bridge")
    print(f"  Port: {config.port}")
    print(f"  Risk: {config.risk_pct}% | Max DD: {config.max_drawdown_pct}%")
    print(f"  Max Spread: {config.max_spread_pips} pips")
    print("═══════════════════════════════════════════════════")
    
    app = create_app()
    web.run_app(app, port=config.port)
