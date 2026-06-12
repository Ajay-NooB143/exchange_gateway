"""
═══════════════════════════════════════════════════════════════════════════════
LIQUIDITY CHASE — HFT Micro-Scalping Engine
Futures (GC, NQ, Crypto) — Level II DOM Data
Async Architecture — asyncio + WebSocket
═══════════════════════════════════════════════════════════════════════════════

Architecture:

┌─────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  WebSocket  │───►│  DOM Engine  │───►│  Strategy    │───►│  Executor    │
│  Feed       │    │  (OBI Calc)  │    │  (Chase)     │    │  (Orders)    │
└─────────────┘    └──────────────┘    └──────────────┘    └──────────────┘
       │                  │                   │                   │
       │                  │                   │                   │
   Level II          Order Book         Liquidity Chase      Market Orders
   Bids/Asks         Imbalance         + Spoof Filter       + Risk Mgmt
"""

import asyncio
import time
import json
import logging
from dataclasses import dataclass, field
from collections import deque
from typing import Optional, Callable
from enum import Enum

# ══════════════════════════════════════════════════════════════════════════════
# LOGGING
# ══════════════════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger('HFT')

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Config:
    # --- Instrument ---
    symbol: str = "GC"                    # Gold futures
    tick_size: float = 0.10               # Minimum price increment
    tick_value: float = 10.0              # Dollar value per tick (GC = $10/tick)
    
    # --- Order Book Imbalance ---
    obi_depth_ticks: int = 10             # Price range to analyze (ticks from mid)
    obi_threshold: float = 1.5            # Ratio threshold (bids/asks > 1.5 = bullish)
    
    # --- Spoofing Filter ---
    min_order_age_ms: int = 500           # Limit orders must exist ≥ 500ms
    spoof_check_window: int = 50          # Number of DOM snapshots to retain
    
    # --- Liquidity Chase ---
    chase_volume_threshold: float = 50.0  # Min resting size to qualify as "wall"
    chase_aggressive_ratio: float = 2.0   # Market buy volume / resting = chase
    
    # --- Risk Management ---
    tp_ticks: int = 4                     # Take profit in ticks
    sl_ticks: int = 3                     # Stop loss in ticks
    max_hold_seconds: float = 180.0       # 3 minutes time-stop
    max_position: int = 1                 # Max concurrent trades
    risk_per_trade_pct: float = 0.5       # % of equity per trade
    
    # --- Execution ---
    order_response_timeout: float = 1.0   # Max wait for fill confirmation
    ws_reconnect_delay: float = 1.0       # Delay before WebSocket reconnect

# ══════════════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ══════════════════════════════════════════════════════════════════════════════

class Side(Enum):
    LONG = "LONG"
    SHORT = "SHORT"

class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"

@dataclass
class DOMLevel:
    price: float
    size: float
    timestamp: float = 0.0
    order_count: int = 0

@dataclass
class DOMSnapshot:
    bids: list[DOMLevel] = field(default_factory=list)
    asks: list[DOMLevel] = field(default_factory=list)
    timestamp: float = 0.0
    sequence: int = 0
    
    @property
    def mid_price(self) -> float:
        if self.bids and self.asks:
            return (self.bids[0].price + self.asks[0].price) / 2
        return 0.0
    
    @property
    def spread(self) -> float:
        if self.bids and self.asks:
            return self.asks[0].price - self.bids[0].price
        return 0.0
    
    @property
    def best_bid(self) -> DOMLevel:
        return self.bids[0] if self.bids else DOMLevel(0, 0)
    
    @property
    def best_ask(self) -> DOMLevel:
        return self.asks[0] if self.asks else DOMLevel(0, 0)

@dataclass
class OrderBookImbalance:
    bid_volume: float = 0.0
    ask_volume: float = 0.0
    ratio: float = 1.0
    bid_wall_price: float = 0.0
    ask_wall_price: float = 0.0
    bid_wall_size: float = 0.0
    ask_wall_size: float = 0.0
    timestamp: float = 0.0
    
    @property
    def signal(self) -> str:
        if self.ratio > 1.5:
            return "BULLISH"
        elif self.ratio < 0.67:
            return "BEARISH"
        return "NEUTRAL"

@dataclass
class TapeEvent:
    price: float
    size: float
    side: str  # "BUY" or "SELL"
    timestamp: float = 0.0
    is_aggressive: bool = False  # Market order (hitting the book)

@dataclass
class Position:
    side: Side = Side.LONG
    entry_price: float = 0.0
    entry_time: float = 0.0
    size: int = 0
    sl_price: float = 0.0
    tp_price: float = 0.0
    pnl_ticks: float = 0.0
    pnl_dollars: float = 0.0
    
    @property
    def hold_time_seconds(self) -> float:
        return time.time() - self.entry_time
    
    @property
    def is_expired(self) -> bool:
        return self.hold_time_seconds >= 180.0  # 3 min
    
    def update_pnl(self, current_price: float, tick_size: float, tick_value: float):
        ticks = (current_price - self.entry_price) / tick_size
        if self.side == Side.SHORT:
            ticks = -ticks
        self.pnl_ticks = ticks
        self.pnl_dollars = ticks * tick_value

# ══════════════════════════════════════════════════════════════════════════════
# ORDER BOOK IMBALANCE ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class OBICalculator:
    """
    Calculates Order Book Imbalance within a tight price range.
    
    Logic:
    1. Sum all bid sizes within `depth_ticks` of mid price
    2. Sum all ask sizes within `depth_ticks` of mid price
    3. Ratio = bid_volume / ask_volume
    4. Ratio > 1.5 = bullish imbalance (more bids = support = price drawn up)
    5. Ratio < 0.67 = bearish imbalance (more asks = resistance = price drawn down)
    """
    
    def __init__(self, config: Config):
        self.config = config
        self.history: deque[OrderBookImbalance] = deque(maxlen=1000)
        self.order_timestamps: dict[float, float] = {}  # price -> first_seen_time
        self.spoof_history: deque[dict] = deque(maxlen=config.spoof_check_window)
    
    def calculate(self, dom: DOMSnapshot) -> OrderBookImbalance:
        """Calculate OBI from current DOM snapshot."""
        mid = dom.mid_price
        depth = self.config.obi_depth_ticks * self.config.tick_size
        
        # Sum volumes within range
        bid_volume = 0.0
        ask_volume = 0.0
        bid_wall_price = 0.0
        ask_wall_price = 0.0
        bid_wall_size = 0.0
        ask_wall_size = 0.0
        
        for level in dom.bids:
            if mid - level.price <= depth:
                bid_volume += level.size
                # Track largest resting order (potential wall)
                if level.size > bid_wall_size:
                    bid_wall_size = level.size
                    bid_wall_price = level.price
        
        for level in dom.asks:
            if level.price - mid <= depth:
                ask_volume += level.size
                if level.size > ask_wall_size:
                    ask_wall_size = level.size
                    ask_wall_price = level.price
        
        # Calculate ratio
        ratio = bid_volume / ask_volume if ask_volume > 0 else float('inf')
        
        obi = OrderBookImbalance(
            bid_volume=bid_volume,
            ask_volume=ask_volume,
            ratio=ratio,
            bid_wall_price=bid_wall_price,
            ask_wall_price=ask_wall_price,
            bid_wall_size=bid_wall_size,
            ask_wall_size=ask_wall_size,
            timestamp=dom.timestamp
        )
        
        self.history.append(obi)
        return obi
    
    def check_spoof(self, dom: DOMSnapshot) -> dict:
        """
        Spoofing Filter:
        - Track when each price level first appears
        - Only consider it "real" if it persists for ≥ min_order_age_ms
        - Returns dict of validated levels
        """
        now = time.time() * 1000  # ms
        valid_bids = []
        valid_asks = []
        
        # Update timestamps for current levels
        for level in dom.bids:
            if level.price not in self.order_timestamps:
                self.order_timestamps[level.price] = now
            age_ms = now - self.order_timestamps[level.price]
            if age_ms >= self.config.min_order_age_ms:
                valid_bids.append(level)
        
        for level in dom.asks:
            if level.price not in self.order_timestamps:
                self.order_timestamps[level.price] = now
            age_ms = now - self.order_timestamps[level.price]
            if age_ms >= self.config.min_order_age_ms:
                valid_asks.append(level)
        
        # Clean old entries
        cutoff = now - 10000  # 10 seconds
        self.order_timestamps = {
            p: t for p, t in self.order_timestamps.items() if t > cutoff
        }
        
        return {
            'valid_bids': valid_bids,
            'valid_asks': valid_asks,
            'spoofed_count': len(dom.bids) + len(dom.asks) - len(valid_bids) - len(valid_asks)
        }
    
    def detect_liquidity_chase(self, dom: DOMSnapshot, tape: list[TapeEvent]) -> Optional[str]:
        """
        Detect if price is chasing liquidity.
        
        LONG signal:
        - Dense resting bids (wall) above current price
        - Aggressive market buying (hitting asks)
        - OBI ratio > threshold
        
        SHORT signal:
        - Dense resting asks (wall) below current price  
        - Aggressive market selling (hitting bids)
        - OBI ratio < 1/threshold
        """
        obi = self.calculate(dom)
        mid = dom.mid_price
        threshold = self.config.obi_threshold
        
        # Check for aggressive tape activity
        recent_tape = [t for t in tape if time.time() - t.timestamp < 1.0]
        aggressive_buys = sum(t.size for t in recent_tape if t.side == "BUY" and t.is_aggressive)
        aggressive_sells = sum(t.size for t in recent_tape if t.side == "SELL" and t.is_aggressive)
        
        # LONG: Bids chasing price up
        if (obi.ratio > threshold and 
            obi.bid_wall_size >= self.config.chase_volume_threshold and
            obi.bid_wall_price > mid and
            aggressive_buys > aggressive_sells * self.config.chase_aggressive_ratio):
            
            log.info(f"CHASE LONG: OBI={obi.ratio:.2f} | Wall@{obi.bid_wall_price}={obi.bid_wall_size:.0f} | AggBuys={aggressive_buys:.0f}")
            return "LONG"
        
        # SHORT: Asks chasing price down
        if (obi.ratio < (1 / threshold) and
            obi.ask_wall_size >= self.config.chase_volume_threshold and
            obi.ask_wall_price < mid and
            aggressive_sells > aggressive_buys * self.config.chase_aggressive_ratio):
            
            log.info(f"CHASE SHORT: OBI={obi.ratio:.2f} | Wall@{obi.ask_wall_price}={obi.ask_wall_size:.0f} | AggSells={aggressive_sells:.0f}")
            return "SHORT"
        
        return None

# ══════════════════════════════════════════════════════════════════════════════
# TAPE READER
# ══════════════════════════════════════════════════════════════════════════════

class TapeReader:
    """
    Analyzes trade tape for aggressive market orders.
    
    Aggressive = hitting the opposite side of the book (market order).
    Passive = resting limit order being filled.
    """
    
    def __init__(self, config: Config):
        self.config = config
        self.tape: deque[TapeEvent] = deque(maxlen=10000)
        self.aggressive_window: deque[TapeEvent] = deque(maxlen=1000)
    
    def ingest(self, trade: dict) -> TapeEvent:
        """Process a trade from the exchange."""
        price = trade.get('price', 0)
        size = trade.get('size', 0)
        side = trade.get('side', 'BUY')
        timestamp = trade.get('timestamp', time.time())
        
        # Determine if aggressive (hitting the book)
        # In real implementation, compare against resting orders
        is_aggressive = trade.get('is_aggressive', False)
        
        event = TapeEvent(
            price=price,
            size=size,
            side=side,
            timestamp=timestamp,
            is_aggressive=is_aggressive
        )
        
        self.tape.append(event)
        if is_aggressive:
            self.aggressive_window.append(event)
        
        return event
    
    def get_aggressive_flow(self, window_seconds: float = 1.0) -> dict:
        """Get aggressive buy/sell volume in recent window."""
        cutoff = time.time() - window_seconds
        recent = [t for t in self.aggressive_window if t.timestamp > cutoff]
        
        buys = sum(t.size for t in recent if t.side == "BUY")
        sells = sum(t.size for t in recent if t.side == "SELL")
        
        return {
            'aggressive_buys': buys,
            'aggressive_sells': sells,
            'net_flow': buys - sells,
            'ratio': buys / sells if sells > 0 else float('inf')
        }

# ══════════════════════════════════════════════════════════════════════════════
# RISK MANAGER
# ══════════════════════════════════════════════════════════════════════════════

class RiskManager:
    """
    Micro-risk management for HFT scalping.
    
    Rules:
    1. Time-Stop: Exit at 3 minutes regardless of P&L
    2. Tick-TP: Exit at +4 ticks (or ahead of liquidity wall)
    3. Tick-SL: Exit at -3 ticks (behind defensive wall)
    4. Wall-Pull: If defensive wall disappears, exit instantly
    """
    
    def __init__(self, config: Config):
        self.config = config
        self.positions: list[Position] = []
        self.daily_pnl: float = 0.0
        self.max_daily_loss: float = 500.0  # $500 daily loss limit
    
    @property
    def open_positions(self) -> int:
        return len(self.positions)
    
    @property
    def can_trade(self) -> bool:
        return (self.open_positions < self.config.max_position and
                self.daily_pnl > -self.max_daily_loss)
    
    def calculate_sl(self, entry_price: float, side: Side) -> float:
        """Place SL immediately behind defensive wall."""
        ticks = self.config.sl_ticks
        tick_size = self.config.tick_size
        
        if side == Side.LONG:
            return entry_price - (ticks * tick_size)
        else:
            return entry_price + (ticks * tick_size)
    
    def calculate_tp(self, entry_price: float, side: Side, wall_price: float = 0) -> float:
        """
        Take profit: either fixed ticks or ahead of liquidity wall.
        If wall exists, target 1 tick before it.
        """
        tick_size = self.config.tick_size
        
        if wall_price > 0:
            # Target 1 tick before the wall
            if side == Side.LONG:
                return wall_price - tick_size
            else:
                return wall_price + tick_size
        
        # Fixed tick TP
        ticks = self.config.tp_ticks
        if side == Side.LONG:
            return entry_price + (ticks * tick_size)
        else:
            return entry_price - (ticks * tick_size)
    
    def check_exits(self, current_price: float, dom: DOMSnapshot) -> list[dict]:
        """Check all positions for exit conditions."""
        exits = []
        
        for pos in self.positions[:]:
            # 1. Time-Stop (3 minutes)
            if pos.is_expired:
                exits.append({
                    'position': pos,
                    'reason': 'TIME_STOP',
                    'price': current_price
                })
                continue
            
            # 2. Take Profit
            if pos.side == Side.LONG and current_price >= pos.tp_price:
                exits.append({
                    'position': pos,
                    'reason': 'TAKE_PROFIT',
                    'price': pos.tp_price
                })
                continue
            
            if pos.side == Side.SHORT and current_price <= pos.tp_price:
                exits.append({
                    'position': pos,
                    'reason': 'TAKE_PROFIT',
                    'price': pos.tp_price
                })
                continue
            
            # 3. Stop Loss
            if pos.side == Side.LONG and current_price <= pos.sl_price:
                exits.append({
                    'position': pos,
                    'reason': 'STOP_LOSS',
                    'price': pos.sl_price
                })
                continue
            
            if pos.side == Side.SHORT and current_price >= pos.sl_price:
                exits.append({
                    'position': pos,
                    'reason': 'STOP_LOSS',
                    'price': pos.sl_price
                })
                continue
            
            # 4. Wall-Pull Detection
            if self._check_wall_pulled(pos, dom):
                exits.append({
                    'position': pos,
                    'reason': 'WALL_PULLED',
                    'price': current_price
                })
                continue
        
        return exits
    
    def _check_wall_pulled(self, pos: Position, dom: DOMSnapshot) -> bool:
        """Check if defensive wall has been pulled/consumed."""
        if pos.side == Side.LONG:
            # Check if bid wall below SL has disappeared
            for level in dom.bids:
                if abs(level.price - pos.sl_price) < self.config.tick_size * 2:
                    return False  # Wall still present
            return True  # Wall gone
        else:
            for level in dom.asks:
                if abs(level.price - pos.sl_price) < self.config.tick_size * 2:
                    return False
            return True
    
    def open_position(self, side: Side, entry_price: float, dom: DOMSnapshot) -> Position:
        """Open a new position."""
        tick_size = self.config.tick_size
        
        # Determine wall for TP
        if side == Side.LONG:
            wall_price = max(
                (l.price for l in dom.asks if l.price > entry_price),
                default=0
            )
        else:
            wall_price = min(
                (l.price for l in dom.bids if l.price < entry_price),
                default=0
            )
        
        pos = Position(
            side=side,
            entry_price=entry_price,
            entry_time=time.time(),
            size=1,
            sl_price=self.calculate_sl(entry_price, side),
            tp_price=self.calculate_tp(entry_price, side, wall_price)
        )
        
        self.positions.append(pos)
        return pos
    
    def close_position(self, pos: Position, exit_price: float, reason: str):
        """Close a position and calculate P&L."""
        pos.update_pnl(exit_price, self.config.tick_size, self.config.tick_value)
        self.daily_pnl += pos.pnl_dollars
        
        log.info(f"CLOSE {pos.side.value}: Entry={pos.entry_price} Exit={exit_price} "
                 f"PnL={pos.pnl_dollars:+.2f} ({pos.pnl_ticks:+.1f} ticks) Reason={reason}")
        
        if pos in self.positions:
            self.positions.remove(pos)

# ══════════════════════════════════════════════════════════════════════════════
# ORDER EXECUTOR
# ══════════════════════════════════════════════════════════════════════════════

class OrderExecutor:
    """
    Handles order submission and fill confirmation.
    
    In production, replace simulate_order() with actual broker API calls:
    - CME: CME iLink 3 / CQG API
    - Crypto: Binance Futures / Bybit / OKX WebSocket
    """
    
    def __init__(self, config: Config):
        self.config = config
        self.order_queue: asyncio.Queue = asyncio.Queue()
        self.pending_orders: dict[str, dict] = {}
    
    async def submit_market_order(self, side: Side, size: int, symbol: str) -> dict:
        """Submit a market order."""
        order_id = f"ORD-{int(time.time() * 1000)}"
        
        order = {
            'id': order_id,
            'symbol': symbol,
            'side': side.value,
            'type': 'MARKET',
            'size': size,
            'timestamp': time.time(),
            'status': 'SUBMITTED'
        }
        
        log.info(f"ORDER: {side.value} {size} {symbol} | ID={order_id}")
        
        # Simulate fill (replace with broker API)
        fill = await self._simulate_fill(order)
        
        return fill
    
    async def _simulate_fill(self, order: dict) -> dict:
        """Simulate order fill (replace with real broker API)."""
        await asyncio.sleep(0.001)  # 1ms simulated latency
        
        return {
            'order_id': order['id'],
            'status': 'FILLED',
            'fill_price': 0.0,  # Would be actual fill price
            'fill_size': order['size'],
            'timestamp': time.time(),
            'latency_ms': 1.0
        }
    
    async def cancel_all(self):
        """Emergency cancel all pending orders."""
        log.warning("CANCEL ALL ORDERS")
        self.pending_orders.clear()

# ══════════════════════════════════════════════════════════════════════════════
# WEBSOCKET FEED HANDLER
# ══════════════════════════════════════════════════════════════════════════════

class WebSocketFeed:
    """
    Handles Level II WebSocket data ingestion.
    
    Replace connect() with your actual exchange WebSocket:
    - CME: CME Market Data (via CQG/Continuum)
    - Crypto: Binance / Bybit / OKX WebSocket API
    """
    
    def __init__(self, config: Config, on_dom_update: Callable, on_trade: Callable):
        self.config = config
        self.on_dom_update = on_dom_update
        self.on_trade = on_trade
        self.connected = False
        self.sequence = 0
    
    async def connect(self):
        """Connect to exchange WebSocket."""
        log.info(f"Connecting to {self.config.symbol} feed...")
        
        # === REPLACE WITH REAL WEBSOCKET CONNECTION ===
        # import websockets
        # self.ws = await websockets.connect("wss://exchange.com/ws")
        # self.connected = True
        # await self._listen()
        
        # Simulated feed for testing
        self.connected = True
        log.info(f"Connected to {self.config.symbol} feed")
        await self._simulate_feed()
    
    async def _simulate_feed(self):
        """Simulate DOM updates for testing."""
        import random
        
        base_price = 2350.00  # Gold
        tick = self.config.tick_size
        
        while self.connected:
            # Generate simulated DOM
            mid = base_price + random.uniform(-2, 2)
            
            bids = []
            asks = []
            
            for i in range(20):
                bid_price = mid - (i * tick)
                ask_price = mid + ((i + 1) * tick)
                
                # Random sizes with occasional "walls"
                bid_size = random.uniform(10, 100)
                ask_size = random.uniform(10, 100)
                
                if random.random() < 0.1:  # 10% chance of wall
                    bid_size = random.uniform(200, 500)
                if random.random() < 0.1:
                    ask_size = random.uniform(200, 500)
                
                bids.append(DOMLevel(bid_price, bid_size, time.time()))
                asks.append(DOMLevel(ask_price, ask_size, time.time()))
            
            dom = DOMSnapshot(
                bids=sorted(bids, key=lambda x: -x.price),
                asks=sorted(asks, key=lambda x: x.price),
                timestamp=time.time(),
                sequence=self.sequence
            )
            
            await self.on_dom_update(dom)
            
            # Simulate trade
            if random.random() < 0.3:
                trade = {
                    'price': mid + random.choice([-tick, 0, tick]),
                    'size': random.uniform(1, 20),
                    'side': random.choice(['BUY', 'SELL']),
                    'timestamp': time.time(),
                    'is_aggressive': random.random() < 0.4
                }
                await self.on_trade(trade)
            
            self.sequence += 1
            await asyncio.sleep(0.05)  # 50ms updates
    
    async def disconnect(self):
        self.connected = False
        log.info("Disconnected from feed")

# ══════════════════════════════════════════════════════════════════════════════
# MAIN HFT ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class LiquidityChaseEngine:
    """
    Main HFT engine coordinating all components.
    
    Flow:
    1. WebSocket receives DOM update
    2. OBICalculator computes imbalance
    3. TapeReader analyzes aggression
    4. Strategy decides entry/exit
    5. RiskManager validates
    6. OrderExecutor submits
    """
    
    def __init__(self, config: Config):
        self.config = config
        self.obi_calc = OBICalculator(config)
        self.tape_reader = TapeReader(config)
        self.risk_manager = RiskManager(config)
        self.executor = OrderExecutor(config)
        self.feed = WebSocketFeed(config, self._on_dom_update, self._on_trade)
        
        self.current_dom: Optional[DOMSnapshot] = None
        self.running = False
        
        # Performance metrics
        self.metrics = {
            'dom_updates': 0,
            'signals_generated': 0,
            'orders_submitted': 0,
            'trades_executed': 0,
            'latencies': deque(maxlen=1000)
        }
    
    async def start(self):
        """Start the HFT engine."""
        log.info("═══════════════════════════════════════════════════")
        log.info("  LIQUIDITY CHASE ENGINE — STARTING")
        log.info(f"  Symbol: {self.config.symbol}")
        log.info(f"  TP: {self.config.tp_ticks} ticks | SL: {self.config.sl_ticks} ticks")
        log.info(f"  Max Hold: {self.config.max_hold_seconds}s")
        log.info("═══════════════════════════════════════════════════")
        
        self.running = True
        
        # Start feed and strategy concurrently
        await asyncio.gather(
            self.feed.connect(),
            self._strategy_loop(),
            self._risk_monitor_loop()
        )
    
    async def _on_dom_update(self, dom: DOMSnapshot):
        """Called on every DOM update from WebSocket."""
        self.current_dom = dom
        self.metrics['dom_updates'] += 1
    
    async def _on_trade(self, trade: dict):
        """Called on every trade from WebSocket."""
        self.tape_reader.ingest(trade)
    
    async def _strategy_loop(self):
        """Main strategy loop — runs on every DOM update."""
        while self.running:
            if self.current_dom is None:
                await asyncio.sleep(0.01)
                continue
            
            dom = self.current_dom
            
            # Check for liquidity chase signal
            signal = self.obi_calc.detect_liquidity_chase(dom, list(self.tape_reader.tape))
            
            if signal and self.risk_manager.can_trade:
                start_time = time.time()
                
                # Execute entry
                side = Side.LONG if signal == "LONG" else Side.SHORT
                
                pos = self.risk_manager.open_position(side, dom.mid_price, dom)
                
                # Submit market order
                await self.executor.submit_market_order(side, pos.size, self.config.symbol)
                
                # Track latency
                latency_ms = (time.time() - start_time) * 1000
                self.metrics['latencies'].append(latency_ms)
                self.metrics['trades_executed'] += 1
                
                log.info(f"ENTRY: {side.value} @ {dom.mid_price} | SL={pos.sl_price} TP={pos.tp_price} | Latency={latency_ms:.2f}ms")
            
            await asyncio.sleep(0.01)  # 10ms strategy tick
    
    async def _risk_monitor_loop(self):
        """Risk monitor — checks exits every 100ms."""
        while self.running:
            if self.current_dom and self.risk_manager.positions:
                exits = self.risk_manager.check_exits(
                    self.current_dom.mid_price,
                    self.current_dom
                )
                
                for exit_info in exits:
                    pos = exit_info['position']
                    price = exit_info['price']
                    reason = exit_info['reason']
                    
                    # Submit exit order
                    opposite_side = Side.SHORT if pos.side == Side.LONG else Side.LONG
                    await self.executor.submit_market_order(opposite_side, pos.size, self.config.symbol)
                    
                    # Record close
                    self.risk_manager.close_position(pos, price, reason)
            
            await asyncio.sleep(0.1)  # 100ms risk check
    
    def get_metrics(self) -> dict:
        """Get current performance metrics."""
        latencies = list(self.metrics['latencies'])
        return {
            'dom_updates': self.metrics['dom_updates'],
            'trades_executed': self.metrics['trades_executed'],
            'open_positions': self.risk_manager.open_positions,
            'daily_pnl': f"${self.risk_manager.daily_pnl:+.2f}",
            'avg_latency_ms': f"{sum(latencies) / len(latencies):.2f}" if latencies else "N/A",
            'max_latency_ms': f"{max(latencies):.2f}" if latencies else "N/A"
        }
    
    async def stop(self):
        """Graceful shutdown."""
        log.info("Stopping engine...")
        self.running = False
        await self.feed.disconnect()
        
        # Close all positions
        for pos in self.risk_manager.positions[:]:
            if self.current_dom:
                self.risk_manager.close_position(pos, self.current_dom.mid_price, "SHUTDOWN")
        
        log.info(f"Final Metrics: {self.get_metrics()}")

# ══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

async def main():
    config = Config(
        symbol="GC",
        tick_size=0.10,
        tick_value=10.0,
        obi_depth_ticks=10,
        obi_threshold=1.5,
        min_order_age_ms=500,
        chase_volume_threshold=50.0,
        tp_ticks=4,
        sl_ticks=3,
        max_hold_seconds=180.0,
        max_position=1
    )
    
    engine = LiquidityChaseEngine(config)
    
    try:
        await engine.start()
    except KeyboardInterrupt:
        await engine.stop()
    except Exception as e:
        log.error(f"Fatal error: {e}")
        await engine.stop()
        raise

if __name__ == "__main__":
    asyncio.run(main())
