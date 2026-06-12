"""
Institutional Footprint - Python Execution Engine v1.0
=====================================================
Architecture:
  Pine Script v6 → Node.js Bridge (port 3000) → This Engine → Broker

This engine receives validated webhooks from the Node.js bridge and performs:
  1. CVD (Cumulative Volume Delta) divergence validation
  2. Order flow absorption detection
  3. Risk-adjusted position sizing
  4. Broker execution with proper fill management

Requires: aiohttp, numpy, pandas
Install: pip install aiohttp numpy pandas
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, List, Tuple
from collections import deque

import numpy as np

# ============================================================================
# CONFIGURATION
# ============================================================================

@dataclass
class Config:
    # Server
    host: str = "0.0.0.0"
    port: int = 8080
    
    # Risk Management
    risk_per_trade: float = 0.01  # 1%
    max_daily_loss: float = 0.03  # 3%
    max_daily_trades: int = 3
    max_slippage_pips: float = 2.0
    sl_buffer_pips: float = 1.0
    
    # CVD Validation
    cvd_lookback: int = 10  # bars to check for divergence
    cvd_threshold: float = 0.3  # minimum divergence ratio
    min_absorption_volume: float = 50.0  # minimum ticks for absorption
    
    # Execution
    use_limit_orders: bool = True
    limit_offset_pips: float = 0.5
    market_timeout_ms: int = 500
    
    # Logging
    log_file: str = "execution_log.csv"
    state_file: str = "engine_state.json"

# ============================================================================
# DATA STRUCTURES
# ============================================================================

class SignalType(Enum):
    LONG = "long"
    SHORT = "short"

class SignalSource(Enum):
    SWEEP_RETURN = "sweep_return"
    IOB_MITIGATION = "iob_mitigation"

class ValidationStatus(Enum):
    APPROVED = "approved"
    REJECTED_CVD = "rejected_cvd"
    REJECTED_RISK = "rejected_risk"
    REJECTED_SESSION = "rejected_session"
    REJECTED_ABSORPTION = "rejected_absorption"

@dataclass
class TickData:
    timestamp: float
    price: float
    volume: float
    bid_volume: float
    ask_volume: float
    
    @property
    def delta(self) -> float:
        """Positive = buying pressure, Negative = selling pressure"""
        return self.bid_volume - self.ask_volume

@dataclass
class CVDState:
    """Tracks Cumulative Volume Delta"""
    current: float = 0.0
    history: deque = field(default_factory=lambda: deque(maxlen=1000))
    
    def update(self, delta: float):
        self.current += delta
        self.history.append(self.current)
    
    def get_lookback(self, n: int) -> List[float]:
        return list(self.history)[-n:] if len(self.history) >= n else list(self.history)
    
    def detect_divergence(self, prices: List[float], lookback: int = 10) -> Tuple[bool, str]:
        """
        Detect CVD divergence:
        - Bullish: Price makes lower low, CVD makes higher low
        - Bearish: Price makes higher high, CVD makes lower high
        """
        if len(prices) < lookback or len(self.history) < lookback:
            return False, "none"
        
        cvd_values = self.get_lookback(lookback)
        price_values = prices[-lookback:]
        
        # Check for bullish divergence
        price_ll = min(price_values[:-1]) > price_values[-1]  # Current is lower
        cvd_hl = min(cvd_values[:-1]) < cvd_values[-1]  # Current is higher
        
        if price_ll and cvd_hl:
            return True, "bullish"
        
        # Check for bearish divergence
        price_hh = max(price_values[:-1]) < price_values[-1]
        cvd_lh = max(cvd_values[:-1]) > cvd_values[-1]
        
        if price_hh and cvd_lh:
            return True, "bearish"
        
        return False, "none"

@dataclass
class WebhookSignal:
    """Parsed signal from Pine Script"""
    signal: SignalType
    entry: float
    sl: float
    tp: float
    sl_pips: float
    tp_pips: float
    source: SignalSource
    cvd_divergent: bool
    regime: str
    atr: float
    volume_pct: float
    session: str
    risk_pct: float
    timestamp: str
    secret: str
    
    # Computed fields
    rr_ratio: float = 0.0
    arrival_time: float = 0.0
    
    def __post_init__(self):
        self.rr_ratio = self.tp_pips / self.sl_pips if self.sl_pips > 0 else 0
        self.arrival_time = time.time()

@dataclass
class ExecutionResult:
    """Result of execution attempt"""
    status: str
    order_id: Optional[str]
    fill_price: Optional[float]
    fill_time_ms: Optional[float]
    slippage_pips: Optional[float]
    validation: ValidationStatus
    cvd_confirmed: bool
    error: Optional[str] = None

# ============================================================================
# CVD ENGINE
# ============================================================================

class CVDEngine:
    """Calculates and tracks Cumulative Volume Delta"""
    
    def __init__(self, config: Config):
        self.config = config
        self.cvd_state = CVDState()
        self.price_history: deque = deque(maxlen=1000)
        self.tick_buffer: deque = deque(maxlen=10000)
        
    def process_tick(self, tick: TickData) -> None:
        """Process incoming tick data"""
        self.cvd_state.update(tick.delta)
        self.price_history.append(tick.price)
        self.tick_buffer.append(tick)
    
    def validate_signal(self, signal: WebhookSignal) -> Tuple[ValidationStatus, bool]:
        """
        Validate signal using CVD analysis
        
        For sweep_return signals:
        - If price swept lows and CVD shows higher low = absorption = CONFIRM
        - If price swept highs and CVD shows lower high = absorption = CONFIRM
        
        For iob_mitigation signals:
        - Check if CVD supports the direction
        """
        
        prices = list(self.price_history)
        
        if len(prices) < self.config.cvd_lookback:
            # Not enough data - use Pine Script's CVD flag
            return ValidationStatus.APPROVED, signal.cvd_divergent
        
        # Detect divergence
        has_divergence, div_type = self.cvd_state.detect_divergence(
            prices, self.config.cvd_lookback
        )
        
        # Validate based on signal type
        if signal.source == SignalSource.SWEEP_RETURN:
            # Sweep return requires CVD divergence confirmation
            if signal.signal == SignalType.LONG and div_type == "bullish":
                return ValidationStatus.APPROVED, True
            elif signal.signal == SignalType.SHORT and div_type == "bearish":
                return ValidationStatus.APPROVED, True
            elif signal.cvd_divergent:
                # Trust Pine Script's calculation if Python can't confirm
                return ValidationStatus.APPROVED, True
            else:
                return ValidationStatus.REJECTED_CVD, False
                
        elif signal.source == SignalSource.IOB_MITIGATION:
            # IOB mitigation is less strict - check CVD direction
            if signal.signal == SignalType.LONG:
                # Verify selling pressure absorbed
                recent_deltas = [t.delta for t in list(self.tick_buffer)[-20:]]
                if recent_deltas:
                    avg_delta = np.mean(recent_deltas)
                    if avg_delta < 0 and self.cvd_state.current > min(self.cvd_state.get_lookback(20)):
                        return ValidationStatus.APPROVED, True
                return ValidationStatus.APPROVED, signal.cvd_divergent
            else:
                recent_deltas = [t.delta for t in list(self.tick_buffer)[-20:]]
                if recent_deltas:
                    avg_delta = np.mean(recent_deltas)
                    if avg_delta > 0 and self.cvd_state.current < max(self.cvd_state.get_lookback(20)):
                        return ValidationStatus.APPROVED, True
                return ValidationStatus.APPROVED, signal.cvd_divergent
        
        return ValidationStatus.APPROVED, False
    
    def detect_absorption(self, lookback: int = 50) -> Tuple[bool, str]:
        """
        Detect order absorption:
        - Large market orders being absorbed by passive limit orders
        - Indicates institutional accumulation/distribution
        """
        ticks = list(self.tick_buffer)[-lookback:]
        if len(ticks) < 10:
            return False, "none"
        
        # Calculate buying/selling pressure
        buy_volume = sum(t.ask_volume for t in ticks)
        sell_volume = sum(t.bid_volume for t in ticks)
        total_volume = buy_volume + sell_volume
        
        if total_volume < self.config.min_absorption_volume:
            return False, "insufficient_volume"
        
        # Absorption: high volume but price doesn't move much
        price_range = max(t.price for t in ticks) - min(t.price for t in ticks)
        avg_price = np.mean([t.price for t in ticks])
        
        # Volume per pip
        vpp = total_volume / (price_range / 0.1) if price_range > 0 else 0
        
        # High volume, tight range = absorption
        if vpp > 100 and price_range < 5:  # Thresholds may need tuning
            if buy_volume > sell_volume * 1.5:
                return True, "bullish_absorption"
            elif sell_volume > buy_volume * 1.5:
                return True, "bearish_absorption"
        
        return False, "none"

# ============================================================================
# RISK MANAGER
# ============================================================================

class RiskManager:
    """Position sizing and risk management"""
    
    def __init__(self, config: Config):
        self.config = config
        self.daily_trades = 0
        self.daily_pnl = 0.0
        self.daily_start_equity = 100000.0
        self.last_reset_date = None
    
    def reset_daily(self) -> None:
        today = datetime.now(timezone.utc).date()
        if self.last_reset_date != today:
            self.daily_trades = 0
            self.daily_pnl = 0.0
            self.last_reset_date = today
    
    def check_risk(self, signal: WebhookSignal, equity: float) -> ValidationStatus:
        """Check if trade passes risk filters"""
        self.reset_daily()
        
        # Daily trade limit
        if self.daily_trades >= self.config.max_daily_trades:
            return ValidationStatus.REJECTED_RISK
        
        # Daily loss limit
        max_loss = equity * self.config.max_daily_loss
        if abs(self.daily_pnl) >= max_loss:
            return ValidationStatus.REJECTED_RISK
        
        # Session check (additional validation)
        if signal.session == "inactive":
            return ValidationStatus.REJECTED_SESSION
        
        # Minimum R:R
        if signal.rr_ratio < 1.5:
            return ValidationStatus.REJECTED_RISK
        
        return ValidationStatus.APPROVED
    
    def calculate_position_size(self, signal: WebhookSignal, equity: float) -> float:
        """Calculate position size based on risk"""
        risk_amount = equity * self.config.risk_per_trade
        sl_pips = signal.sl_pips
        
        if sl_pips <= 0:
            return 0.0
        
        # Position size = risk amount / (sl_pips * pip_value)
        # For XAUUSD: 1 pip = $0.10 per 0.01 lot
        pip_value = 0.10  # Per 0.01 lot
        position_size = risk_amount / (sl_pips * pip_value)
        
        # Normalize to valid lot sizes
        position_size = round(position_size, 2)
        
        # Maximum position size check (20% of equity)
        max_position = (equity * 0.20) / (sl_pips * pip_value)
        position_size = min(position_size, max_position)
        
        return max(position_size, 0.01)  # Minimum 0.01 lot
    
    def update_pnl(self, pnl: float) -> None:
        self.daily_pnl += pnl
        self.daily_trades += 1

# ============================================================================
# BROKER EXECUTOR
# ============================================================================

class BrokerExecutor:
    """
    Handles broker communication.
    This is a template - implement for your specific broker.
    """
    
    def __init__(self, config: Config):
        self.config = config
        self.connected = False
        
    async def connect(self) -> bool:
        """Connect to broker API"""
        # Implement for your broker (OANDA, Interactive Brokers, etc.)
        logging.info("Broker executor connected (simulated)")
        self.connected = True
        return True
    
    async def submit_order(self, 
                          signal: WebhookSignal,
                          position_size: float,
                          equity: float) -> ExecutionResult:
        """
        Submit order to broker.
        Returns ExecutionResult with fill details.
        """
        start_time = time.time()
        
        # SIMULATED EXECUTION
        # Replace with actual broker API calls
        
        fill_price = signal.entry
        slippage = np.random.uniform(0, self.config.max_slippage_pips)
        fill_time_ms = (time.time() - start_time) * 1000
        
        return ExecutionResult(
            status="filled",
            order_id=f"SIM-{int(time.time()*1000)}",
            fill_price=fill_price,
            fill_time_ms=fill_time_ms,
            slippage_pips=slippage,
            validation=ValidationStatus.APPROVED,
            cvd_confirmed=True
        )
    
    async def close_position(self, order_id: str) -> bool:
        """Close a position"""
        logging.info(f"Closing position {order_id}")
        return True
    
    async def get_position(self) -> Optional[Dict]:
        """Get current position"""
        return None

# ============================================================================
# TRADE LOGGER
# ============================================================================

class TradeLogger:
    """Logs all trades for analysis"""
    
    def __init__(self, config: Config):
        self.config = config
        self._init_log_file()
    
    def _init_log_file(self) -> None:
        """Initialize CSV log file with headers"""
        import os
        if not os.path.exists(self.config.log_file):
            headers = [
                "timestamp", "signal", "entry", "sl", "tp", 
                "sl_pips", "tp_pips", "rr_ratio", "source",
                "cvd_validated", "cvd_divergent", "regime",
                "atr", "volume_pct", "session", "position_size",
                "fill_price", "slippage_pips", "fill_time_ms",
                "pnl", "status", "validation_status"
            ]
            with open(self.config.log_file, 'w') as f:
                f.write(','.join(headers) + '\n')
    
    def log_trade(self, signal: WebhookSignal, result: ExecutionResult, 
                  position_size: float, pnl: float = 0.0) -> None:
        """Log a trade to CSV"""
        row = [
            signal.timestamp,
            signal.signal.value,
            signal.entry,
            signal.sl,
            signal.tp,
            signal.sl_pips,
            signal.tp_pips,
            f"{signal.rr_ratio:.2f}",
            signal.signal.value,
            result.cvd_confirmed,
            signal.cvd_divergent,
            signal.regime,
            signal.atr,
            signal.volume_pct,
            signal.session,
            position_size,
            result.fill_price or 0,
            result.slippage_pips or 0,
            f"{result.fill_time_ms:.2f}" if result.fill_time_ms else 0,
            f"{pnl:.2f}",
            result.status,
            result.validation.value
        ]
        
        with open(self.config.log_file, 'a') as f:
            f.write(','.join(str(r) for r in row) + '\n')

# ============================================================================
# MAIN ENGINE
# ============================================================================

class InstitutionalFootprintEngine:
    """Main execution engine orchestrating all components"""
    
    def __init__(self, config: Config):
        self.config = config
        self.cvd_engine = CVDEngine(config)
        self.risk_manager = RiskManager(config)
        self.broker = BrokerExecutor(config)
        self.logger = TradeLogger(config)
        
        self.active_order = None
        self.order_history: List[ExecutionResult] = []
    
    async def initialize(self) -> bool:
        """Initialize all components"""
        return await self.broker.connect()
    
    async def process_signal(self, signal_dict: dict) -> dict:
        """
        Process incoming webhook signal.
        This is called by the aiohttp server.
        """
        try:
            # Parse signal
            signal = WebhookSignal(
                signal=SignalType(signal_dict.get("signal", "")),
                entry=float(signal_dict.get("entry", 0)),
                sl=float(signal_dict.get("sl", 0)),
                tp=float(signal_dict.get("tp", 0)),
                sl_pips=float(signal_dict.get("sl_pips", 0)),
                tp_pips=float(signal_dict.get("tp_pips", 0)),
                source=SignalSource(signal_dict.get("type", "")),
                cvd_divergent=signal_dict.get("cvd_divergent", False),
                regime=signal_dict.get("regime", "unknown"),
                atr=float(signal_dict.get("atr", 0)),
                volume_pct=float(signal_dict.get("volume_pct", 0)),
                session=signal_dict.get("session", "unknown"),
                risk_pct=float(signal_dict.get("risk_pct", 1.0)),
                timestamp=signal_dict.get("timestamp", ""),
                secret=signal_dict.get("secret", "")
            )
            
            # Validate secret
            if signal.secret != self.config.secret:
                return {"status": "rejected", "error": "Invalid secret"}
            
            logging.info(f"Processing {signal.signal.value} signal from {signal.source.value}")
            
            # Step 1: CVD Validation
            validation_status, cvd_confirmed = self.cvd_engine.validate_signal(signal)
            if validation_status != ValidationStatus.APPROVED:
                return {
                    "status": "rejected",
                    "error": f"CVD validation failed: {validation_status.value}",
                    "cvd_confirmed": False
                }
            
            # Step 2: Risk Check
            equity = 100000.0  # Get from broker in production
            risk_status = self.risk_manager.check_risk(signal, equity)
            if risk_status != ValidationStatus.APPROVED:
                return {
                    "status": "rejected",
                    "error": f"Risk check failed: {risk_status.value}"
                }
            
            # Step 3: Position Sizing
            position_size = self.risk_manager.calculate_position_size(signal, equity)
            
            # Step 4: Execute
            result = await self.broker.submit_order(signal, position_size, equity)
            
            # Step 5: Log
            self.logger.log_trade(signal, result, position_size)
            self.order_history.append(result)
            
            # Step 6: Update risk manager
            if result.status == "filled":
                self.risk_manager.update_pnl(0)  # Update with actual P&L later
            
            return {
                "status": result.status,
                "order_id": result.order_id,
                "fill_price": result.fill_price,
                "slippage_pips": result.slippage_pips,
                "fill_time_ms": result.fill_time_ms,
                "cvd_confirmed": cvd_confirmed,
                "position_size": position_size
            }
            
        except Exception as e:
            logging.error(f"Error processing signal: {e}")
            return {"status": "error", "error": str(e)}
    
    async def process_tick(self, tick_data: dict) -> None:
        """Process incoming tick data for CVD calculation"""
        tick = TickData(
            timestamp=tick_data.get("timestamp", time.time()),
            price=float(tick_data.get("price", 0)),
            volume=float(tick_data.get("volume", 0)),
            bid_volume=float(tick_data.get("bid_volume", 0)),
            ask_volume=float(tick_data.get("ask_volume", 0))
        )
        self.cvd_engine.process_tick(tick)

# ============================================================================
# AIOHTTP SERVER
# ============================================================================

from aiohttp import web

class WebhookServer:
    """aiohttp server for receiving webhooks"""
    
    def __init__(self, engine: InstitutionalFootprintEngine, config: Config):
        self.engine = engine
        self.config = config
        self.app = web.Application()
        self._setup_routes()
    
    def _setup_routes(self) -> None:
        self.app.router.add_post('/webhook', self.handle_webhook)
        self.app.router.add_post('/tick', self.handle_tick)
        self.app.router.add_get('/health', self.handle_health)
        self.app.router.add_get('/stats', self.handle_stats)
    
    async def handle_webhook(self, request: web.Request) -> web.Response:
        """Handle incoming webhook from Node.js bridge"""
        try:
            data = await request.json()
            result = await self.engine.process_signal(data)
            
            status_code = 200 if result.get("status") == "filled" else 400
            return web.json_response(result, status=status_code)
            
        except Exception as e:
            logging.error(f"Webhook error: {e}")
            return web.json_response({"error": str(e)}, status=500)
    
    async def handle_tick(self, request: web.Request) -> web.Response:
        """Handle incoming tick data"""
        try:
            data = await request.json()
            await self.engine.process_tick(data)
            return web.json_response({"status": "processed"})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)
    
    async def handle_health(self, request: web.Request) -> web.Response:
        """Health check endpoint"""
        return web.json_response({
            "status": "healthy",
            "engine": "institutional_footprint",
            "cvd_history_size": len(self.engine.cvd_engine.cvd_state.history),
            "daily_trades": self.engine.risk_manager.daily_trades,
            "daily_pnl": self.engine.risk_manager.daily_pnl
        })
    
    async def handle_stats(self, request: web.Request) -> web.Response:
        """Statistics endpoint"""
        return web.json_response({
            "total_orders": len(self.engine.order_history),
            "daily_trades": self.engine.risk_manager.daily_trades,
            "daily_pnl": self.engine.risk_manager.daily_pnl,
            "cvd_current": self.engine.cvd_engine.cvd_state.current
        })
    
    async def start(self) -> None:
        """Start the server"""
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, self.config.host, self.config.port)
        await site.start()
        logging.info(f"Execution engine listening on {self.config.host}:{self.config.port}")

# ============================================================================
# MAIN
# ============================================================================

async def main():
    """Main entry point"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )
    
    # Load config
    config = Config()
    
    # Initialize engine
    engine = InstitutionalFootprintEngine(config)
    await engine.initialize()
    
    # Start server
    server = WebhookServer(engine, config)
    await server.start()
    
    # Keep running
    try:
        while True:
            await asyncio.sleep(3600)
    except KeyboardInterrupt:
        logging.info("Shutting down...")

if __name__ == "__main__":
    asyncio.run(main())
