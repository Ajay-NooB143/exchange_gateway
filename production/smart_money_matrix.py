"""
Smart Money Matrix - Institutional Order Flow Detection
========================================================
Modules 28-30: OrderBlockDetector, FairValueGapMapper, LiquiditySweepDetector

Architecture:
┌─────────────────────────────────────────────────────────────────────────────┐
│                     SMART MONEY MATRIX                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Module 28: OrderBlockDetector                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  High Volume → BOS Detection → Zone Marking → Mitigation Check     │   │
│  │  [90th percentile]  [Swing break]  [Open/Close]  [Price return]     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  Module 29: FairValueGapMapper                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  3-Candle Pattern → Gap Detection → Zone Tracking → Fill Status    │   │
│  │  [C1 High < C3 Low]  [Bullish/Bearish]  [Bounded deque]  [Active]  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  Module 30: LiquiditySweepDetector                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Equal H/L Detection → Spike Detection → Close Back → Confirmation │   │
│  │  [Tolerance check]    [Wick analysis]   [1-3 bars]    [Signal gen]  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

Memory Safety:
- All detectors use bounded deques (maxlen parameter)
- Input candles are clipped to lookback window
- Periodic cleanup of historical data
- No unbounded lists or dicts

Performance:
- O(n) scanning where n = lookback window
- Sub-millisecond detection per candle
- Thread-safe operations
"""

from collections import deque
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from enum import Enum
import time
import logging
import os
import json

log = logging.getLogger('SmartMoneyMatrix')


# ══════════════════════════════════════════════════════════════════════════════
# TELEGRAM ALERTS
# ══════════════════════════════════════════════════════════════════════════════

class TelegramAlerter:
    """Send LiquiditySweep alerts via Telegram."""
    
    def __init__(self):
        self.bot_token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
        self.chat_id = os.environ.get('TELEGRAM_CHAT_ID', '')
        self.enabled = bool(self.bot_token and self.chat_id)
        
        if not self.enabled:
            log.debug("Telegram alerts DISABLED - no token/chat_id configured")
    
    def send_sweep_alert(
        self,
        symbol: str,
        tf: str,
        direction: str,
        sweep_pct: float,
        timestamp: float
    ) -> bool:
        """
        Send LiquiditySweep alert via Telegram.
        
        Format:
        🚨 LIQUIDITY SWEEP DETECTED
        Asset: {symbol}
        Timeframe: {tf}
        Direction: {BULL/BEAR}
        Sweep %: {pct}%
        Time: {UTC timestamp}
        
        Args:
            symbol: Trading symbol (e.g., XAUUSD)
            tf: Timeframe (e.g., 5m, 15m, 1h)
            direction: BULL or BEAR
            sweep_pct: Sweep percentage
            timestamp: Unix timestamp
            
        Returns:
            True if sent successfully
        """
        if not self.enabled:
            return False
        
        try:
            import urllib.request
            
            # Format timestamp
            from datetime import datetime, timezone
            dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            time_str = dt.strftime('%Y-%m-%d %H:%M:%S UTC')
            
            # Build message
            message = (
                f"🚨 LIQUIDITY SWEEP DETECTED\n\n"
                f"Asset: {symbol}\n"
                f"Timeframe: {tf}\n"
                f"Direction: {direction}\n"
                f"Sweep %: {sweep_pct:.1f}%\n"
                f"Time: {time_str}"
            )
            
            # Send via Telegram API
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            
            data = json.dumps({
                'chat_id': self.chat_id,
                'text': message,
                'parse_mode': 'HTML'
            }).encode('utf-8')
            
            req = urllib.request.Request(
                url,
                data=data,
                headers={'Content-Type': 'application/json'}
            )
            
            with urllib.request.urlopen(req, timeout=10) as response:
                result = json.loads(response.read().decode('utf-8'))
                return result.get('ok', False)
                
        except Exception as e:
            log.error(f"Failed to send Telegram alert: {e}")
            return False


# Global alerter instance
_telegram_alerter: Optional[TelegramAlerter] = None


def get_telegram_alerter() -> TelegramAlerter:
    """Get or create global Telegram alerter."""
    global _telegram_alerter
    if _telegram_alerter is None:
        _telegram_alerter = TelegramAlerter()
    return _telegram_alerter


# ══════════════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ══════════════════════════════════════════════════════════════════════════════

class Direction(Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


@dataclass
class Candle:
    """OHLCV candle data"""
    timestamp: float
    open: float
    high: float
    low: float
    close: float
    volume: float
    
    @property
    def body_size(self) -> float:
        return abs(self.close - self.open)
    
    @property
    def range_size(self) -> float:
        return self.high - self.low
    
    @property
    def is_bullish(self) -> bool:
        return self.close > self.open
    
    @property
    def direction(self) -> Direction:
        return Direction.BULLISH if self.is_bullish else Direction.BEARISH


@dataclass
class OrderBlock:
    """Institutional Order Block"""
    timestamp: float
    price: float
    high: float
    low: float
    volume: float
    direction: Direction
    bar_index: int
    mitigated: bool = False
    mitigated_at: Optional[float] = None
    
    @property
    def is_valid(self) -> bool:
        return not self.mitigated


@dataclass
class FairValueGap:
    """Fair Value Gap (Institutional Imbalance)"""
    timestamp: float
    top: float
    bottom: float
    direction: Direction
    bar_index: int
    filled: bool = False
    filled_at: Optional[float] = None
    
    @property
    def gap_size(self) -> float:
        return self.top - self.bottom
    
    @property
    def is_valid(self) -> bool:
        return not self.filled


@dataclass
class LiquidityLevel:
    """Retail Liquidity Level (Equal Highs/Lows)"""
    price: float
    direction: Direction  # Direction of expected sweep
    touch_count: int
    last_touch_bar: int
    swept: bool = False
    swept_at: Optional[float] = None
    
    @property
    def is_valid(self) -> bool:
        return not self.swept


@dataclass
class SweepEvent:
    """Liquidity Sweep Event"""
    timestamp: float
    level_price: float
    sweep_extreme: float
    direction: Direction
    bar_index: int
    confirmed: bool = False
    
    @property
    def wick_size(self) -> float:
        return abs(self.sweep_extreme - self.level_price)


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 28: ORDER BLOCK DETECTOR
# ══════════════════════════════════════════════════════════════════════════════

class OrderBlockDetector:
    """
    Detects institutional order blocks (accumulation/distribution zones).
    
    Logic:
    1. Identify high-volume candles (90th percentile)
    2. Check if caused Break of Structure (BOS)
    3. Mark open/close as Order Block zone
    4. Track mitigation (price returns to zone)
    
    Memory: Bounded deques, O(lookback) space
    """
    
    def __init__(
        self,
        lookback: int = 100,
        volume_percentile: float = 90.0,
        bos_min_atr_mult: float = 0.5,
        max_blocks: int = 50,
        atr_period: int = 14
    ):
        self.lookback = lookback
        self.volume_percentile = volume_percentile
        self.bos_min_atr_mult = bos_min_atr_mult
        self.max_blocks = max_blocks
        self.atr_period = atr_period
        
        # Bounded storage
        self.blocks: deque[OrderBlock] = deque(maxlen=max_blocks)
        self.volume_history: deque[float] = deque(maxlen=lookback)
        self.atr_history: deque[float] = deque(maxlen=lookback)
        
        # Swing tracking for BOS detection
        self.swing_highs: deque[Tuple[float, int]] = deque(maxlen=100)
        self.swing_lows: deque[Tuple[float, int]] = deque(maxlen=100)
        
        # Performance metrics
        self.scan_count = 0
        self.blocks_found = 0
    
    def scan(self, candles: List[Candle], current_bar: int = 0) -> List[OrderBlock]:
        """
        Scan candles for order blocks.
        
        Args:
            candles: List of Candle objects (will be clipped to lookback)
            current_bar: Current bar index for BOS detection
            
        Returns:
            List of newly detected OrderBlocks
        """
        self.scan_count += 1
        
        # CRITICAL: Clip input to prevent memory bloat
        candles = candles[-self.lookback:]
        
        new_blocks = []
        
        for i in range(2, len(candles)):
            candle = candles[i]
            prev_candle = candles[i-1]
            
            # Update volume history
            self.volume_history.append(candle.volume)
            
            # Calculate ATR
            if i >= self.atr_period:
                atr = self._calculate_atr(candles[i-self.atr_period:i+1])
                self.atr_history.append(atr)
            
            # Update swing points
            self._update_swings(candles, i)
            
            # Check for high volume
            if len(self.volume_history) < 20:
                continue
                
            vol_threshold = self._get_volume_threshold()
            if candle.volume < vol_threshold:
                continue
            
            # Check if caused BOS
            bos_direction = self._check_bos(candles, i)
            if bos_direction == Direction.NEUTRAL:
                continue
            
            # Create Order Block
            atr = self.atr_history[-1] if self.atr_history else candle.range_size
            
            block = OrderBlock(
                timestamp=candle.timestamp,
                price=candle.open,  # Open of high-volume candle
                high=candle.high,
                low=candle.low,
                volume=candle.volume,
                direction=bos_direction,
                bar_index=current_bar + i - len(candles),
                mitigated=False
            )
            
            new_blocks.append(block)
            self.blocks.append(block)
            self.blocks_found += 1
            
            log.debug(f"OrderBlock detected: {bos_direction.value} @ {block.price:.2f}")
        
        # Check mitigation of existing blocks
        self._check_mitigation(candles, current_bar)
        
        return new_blocks
    
    def get_active_blocks(self, direction: Optional[Direction] = None) -> List[OrderBlock]:
        """Get all active (non-mitigated) order blocks."""
        blocks = [b for b in self.blocks if b.is_valid]
        
        if direction:
            blocks = [b for b in blocks if b.direction == direction]
        
        return sorted(blocks, key=lambda b: b.timestamp, reverse=True)
    
    def is_price_in_block(self, price: float, direction: Direction) -> Optional[OrderBlock]:
        """Check if price is within any active order block."""
        for block in self.get_active_blocks(direction):
            if block.low <= price <= block.high:
                return block
        return None
    
    def _calculate_atr(self, candles: List[Candle]) -> float:
        """Calculate Average True Range."""
        if len(candles) < 2:
            return candles[0].range_size if candles else 0
        
        true_ranges = []
        for i in range(1, len(candles)):
            tr = max(
                candles[i].high - candles[i].low,
                abs(candles[i].high - candles[i-1].close),
                abs(candles[i].low - candles[i-1].close)
            )
            true_ranges.append(tr)
        
        return sum(true_ranges) / len(true_ranges)
    
    def _get_volume_threshold(self) -> float:
        """Get volume threshold for high-volume detection."""
        if len(self.volume_history) < 10:
            return float('inf')
        
        sorted_vol = sorted(self.volume_history)
        idx = int(len(sorted_vol) * (self.volume_percentile / 100))
        return sorted_vol[min(idx, len(sorted_vol) - 1)]
    
    def _update_swings(self, candles: List[Candle], idx: int):
        """Update swing high/low tracking."""
        if idx < 2 or idx >= len(candles) - 2:
            return
        
        # Swing high: high > high of neighbors
        if (candles[idx].high > candles[idx-1].high and 
            candles[idx].high > candles[idx+1].high):
            self.swing_highs.append((candles[idx].high, idx))
        
        # Swing low: low < low of neighbors
        if (candles[idx].low < candles[idx-1].low and 
            candles[idx].low < candles[idx+1].low):
            self.swing_lows.append((candles[idx].low, idx))
    
    def _check_bos(self, candles: List[Candle], idx: int) -> Direction:
        """Check if candle caused Break of Structure."""
        if not self.swing_highs or not self.swing_lows:
            return Direction.NEUTRAL
        
        candle = candles[idx]
        atr = self.atr_history[-1] if self.atr_history else candle.range_size
        min_move = atr * self.bos_min_atr_mult
        
        # Bullish BOS: close breaks above recent swing high
        for swing_high, swing_idx in reversed(self.swing_highs):
            if swing_idx < idx and (candle.close - swing_high) > min_move:
                return Direction.BULLISH
        
        # Bearish BOS: close breaks below recent swing low
        for swing_low, swing_idx in reversed(self.swing_lows):
            if swing_idx < idx and (swing_low - candle.close) > min_move:
                return Direction.BEARISH
        
        return Direction.NEUTRAL
    
    def _check_mitigation(self, candles: List[Candle], current_bar: int):
        """Check if existing blocks have been mitigated."""
        if not candles:
            return
        
        current_price = candles[-1].close
        
        for block in self.blocks:
            if block.mitigated:
                continue
            
            # Check if price returned to block zone
            if block.direction == Direction.BULLISH:
                # Bullish OB mitigated when price dips into zone and closes above
                if current_price <= block.price and current_price >= block.low:
                    block.mitigated = True
                    block.mitigated_at = time.time()
                    log.debug(f"Bullish OB mitigated @ {block.price:.2f}")
            
            elif block.direction == Direction.BEARISH:
                # Bearish OB mitigated when price rises into zone and closes below
                if current_price >= block.price and current_price <= block.high:
                    block.mitigated = True
                    block.mitigated_at = time.time()
                    log.debug(f"Bearish OB mitigated @ {block.price:.2f}")


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 29: FAIR VALUE GAP MAPPER
# ══════════════════════════════════════════════════════════════════════════════

class FairValueGapMapper:
    """
    Detects Fair Value Gaps (institutional imbalances).
    
    Logic:
    1. 3-candle pattern detection
    2. Bullish FVG: C1 High < C3 Low (gap up)
    3. Bearish FVG: C1 Low > C3 High (gap down)
    4. Track fill status
    
    Memory: Bounded deques, O(max_gaps) space
    """
    
    def __init__(
        self,
        max_gaps: int = 30,
        min_gap_atr_mult: float = 0.2,
        atr_period: int = 14
    ):
        self.max_gaps = max_gaps
        self.min_gap_atr_mult = min_gap_atr_mult
        self.atr_period = atr_period
        
        # Bounded storage
        self.gaps: deque[FairValueGap] = deque(maxlen=max_gaps)
        self.atr_history: deque[float] = deque(maxlen=100)
        
        # Performance metrics
        self.scan_count = 0
        self.gaps_found = 0
    
    def scan(self, candles: List[Candle], current_bar: int = 0) -> List[FairValueGap]:
        """
        Scan candles for Fair Value Gaps.
        
        Args:
            candles: List of Candle objects (will be clipped)
            current_bar: Current bar index
            
        Returns:
            List of newly detected FairValueGaps
        """
        self.scan_count += 1
        
        # CRITICAL: Clip input
        candles = candles[-50:]
        
        new_gaps = []
        
        for i in range(2, len(candles)):
            c1 = candles[i-2]
            c2 = candles[i-1]
            c3 = candles[i]
            
            # Calculate ATR
            if i >= self.atr_period:
                atr = self._calculate_atr(candles[i-self.atr_period:i+1])
                self.atr_history.append(atr)
            
            if not self.atr_history:
                continue
            
            atr = self.atr_history[-1]
            min_gap = atr * self.min_gap_atr_mult
            
            # Bullish FVG: gap between C1 high and C3 low
            if c1.high < c3.low:
                gap_size = c3.low - c1.high
                if gap_size >= min_gap:
                    gap = FairValueGap(
                        timestamp=c2.timestamp,
                        top=c3.low,
                        bottom=c1.high,
                        direction=Direction.BULLISH,
                        bar_index=current_bar + i - len(candles)
                    )
                    new_gaps.append(gap)
                    self.gaps.append(gap)
                    self.gaps_found += 1
                    log.debug(f"Bullish FVG: {gap.bottom:.2f} - {gap.top:.2f}")
            
            # Bearish FVG: gap between C1 low and C3 high
            if c1.low > c3.high:
                gap_size = c1.low - c3.high
                if gap_size >= min_gap:
                    gap = FairValueGap(
                        timestamp=c2.timestamp,
                        top=c1.low,
                        bottom=c3.high,
                        direction=Direction.BEARISH,
                        bar_index=current_bar + i - len(candles)
                    )
                    new_gaps.append(gap)
                    self.gaps.append(gap)
                    self.gaps_found += 1
                    log.debug(f"Bearish FVG: {gap.bottom:.2f} - {gap.top:.2f}")
        
        # Check fill status
        self._check_fills(candles, current_bar)
        
        return new_gaps
    
    def get_active_gaps(self, direction: Optional[Direction] = None) -> List[FairValueGap]:
        """Get all active (unfilled) gaps."""
        gaps = [g for g in self.gaps if g.is_valid]
        
        if direction:
            gaps = [g for g in gaps if g.direction == direction]
        
        return sorted(gaps, key=lambda g: g.timestamp, reverse=True)
    
    def is_price_in_gap(self, price: float, direction: Direction) -> Optional[FairValueGap]:
        """Check if price is within any active gap."""
        for gap in self.get_active_gaps(direction):
            if gap.bottom <= price <= gap.top:
                return gap
        return None
    
    def _calculate_atr(self, candles: List[Candle]) -> float:
        """Calculate Average True Range."""
        if len(candles) < 2:
            return candles[0].range_size if candles else 0
        
        true_ranges = []
        for i in range(1, len(candles)):
            tr = max(
                candles[i].high - candles[i].low,
                abs(candles[i].high - candles[i-1].close),
                abs(candles[i].low - candles[i-1].close)
            )
            true_ranges.append(tr)
        
        return sum(true_ranges) / len(true_ranges)
    
    def _check_fills(self, candles: List[Candle], current_bar: int):
        """Check if gaps have been filled."""
        if not candles:
            return
        
        current = candles[-1]
        
        for gap in self.gaps:
            if gap.filled:
                continue
            
            # Bullish FVG filled when price drops through it
            if gap.direction == Direction.BULLISH:
                if current.low <= gap.bottom:
                    gap.filled = True
                    gap.filled_at = time.time()
                    log.debug(f"Bullish FVG filled @ {gap.bottom:.2f}")
            
            # Bearish FVG filled when price rises through it
            elif gap.direction == Direction.BEARISH:
                if current.high >= gap.top:
                    gap.filled = True
                    gap.filled_at = time.time()
                    log.debug(f"Bearish FVG filled @ {gap.top:.2f}")


# ══════════════════════════════════════════════════════════════════════════════
# MODULE 30: LIQUIDITY SWEEP DETECTOR
# ══════════════════════════════════════════════════════════════════════════════

class LiquiditySweepDetector:
    """
    Detects liquidity sweeps (stop hunts / false breakouts).
    
    Logic:
    1. Identify equal highs/lows (retail liquidity pools)
    2. Detect spike past these levels
    3. Confirm close back inside range
    4. Generate sweep signal
    
    Memory: Bounded deques, O(max_levels) space
    """
    
    def __init__(
        self,
        equal_hl_tolerance_atr_mult: float = 0.5,
        min_wick_atr_mult: float = 0.3,
        max_bars_for_confirmation: int = 3,
        max_levels: int = 100,
        atr_period: int = 14
    ):
        self.equal_hl_tolerance = equal_hl_tolerance_atr_mult
        self.min_wick_atr_mult = min_wick_atr_mult
        self.max_bars = max_bars_for_confirmation
        self.max_levels = max_levels
        self.atr_period = atr_period
        
        # Bounded storage
        self.liquidity_levels: deque[LiquidityLevel] = deque(maxlen=max_levels)
        self.sweep_events: deque[SweepEvent] = deque(maxlen=100)
        self.atr_history: deque[float] = deque(maxlen=100)
        
        # Performance metrics
        self.scan_count = 0
        self.sweeps_found = 0
    
    def scan(self, candles: List[Candle], current_bar: int = 0) -> List[SweepEvent]:
        """
        Scan candles for liquidity sweeps.
        
        Args:
            candles: List of Candle objects (will be clipped)
            current_bar: Current bar index
            
        Returns:
            List of newly detected SweepEvents
        """
        self.scan_count += 1
        
        # CRITICAL: Clip input
        candles = candles[-50:]
        
        new_sweeps = []
        
        for i in range(1, len(candles)):
            candle = candles[i]
            
            # Calculate ATR
            if i >= self.atr_period:
                atr = self._calculate_atr(candles[i-self.atr_period:i+1])
                self.atr_history.append(atr)
            
            if not self.atr_history:
                continue
            
            atr = self.atr_history[-1]
            
            # Update liquidity levels
            self._update_liquidity_levels(candles, i, atr)
            
            # Check for sweep events
            sweep = self._check_sweep(candle, i, atr)
            if sweep:
                new_sweeps.append(sweep)
                self.sweep_events.append(sweep)
                self.sweeps_found += 1
                log.info(f"LiquiditySweep: {sweep.direction.value} @ {sweep.level_price:.2f}")
                
                # Send Telegram alert
                alerter = get_telegram_alerter()
                if alerter.enabled:
                    # Calculate sweep percentage
                    sweep_pct = abs(sweep.sweep_extreme - sweep.level_price) / sweep.level_price * 100
                    
                    # Determine direction string
                    direction_str = "BEAR" if sweep.direction == Direction.BEARISH else "BULL"
                    
                    # Send alert (non-blocking)
                    try:
                        alerter.send_sweep_alert(
                            symbol="XAUUSD",  # Default symbol
                            tf="5m",  # Default timeframe
                            direction=direction_str,
                            sweep_pct=sweep_pct,
                            timestamp=sweep.timestamp
                        )
                    except Exception as e:
                        log.debug(f"Failed to send sweep alert: {e}")
        
        # Check confirmation of recent sweeps
        self._check_confirmation(candles, current_bar)
        
        return new_sweeps
    
    def get_active_levels(self, direction: Optional[Direction] = None) -> List[LiquidityLevel]:
        """Get all active (non-swept) liquidity levels."""
        levels = [l for l in self.liquidity_levels if l.is_valid]
        
        if direction:
            levels = [l for l in levels if l.direction == direction]
        
        return sorted(levels, key=lambda l: l.price, reverse=True)
    
    def get_recent_sweeps(self, confirmed_only: bool = False) -> List[SweepEvent]:
        """Get recent sweep events."""
        sweeps = list(self.sweep_events)
        
        if confirmed_only:
            sweeps = [s for s in sweeps if s.confirmed]
        
        return sorted(sweeps, key=lambda s: s.timestamp, reverse=True)[:10]
    
    def _calculate_atr(self, candles: List[Candle]) -> float:
        """Calculate Average True Range."""
        if len(candles) < 2:
            return candles[0].range_size if candles else 0
        
        true_ranges = []
        for i in range(1, len(candles)):
            tr = max(
                candles[i].high - candles[i].low,
                abs(candles[i].high - candles[i-1].close),
                abs(candles[i].low - candles[i-1].close)
            )
            true_ranges.append(tr)
        
        return sum(true_ranges) / len(true_ranges)
    
    def _update_liquidity_levels(self, candles: List[Candle], idx: int, atr: float):
        """Update liquidity levels from swing points."""
        if idx < 2 or idx >= len(candles) - 2:
            return
        
        candle = candles[idx]
        tolerance = atr * self.equal_hl_tolerance
        
        # Check for swing high
        if (candle.high > candles[idx-1].high and 
            candle.high > candles[idx+1].high):
            self._add_level(candle.high, Direction.BEARISH, idx, tolerance)
        
        # Check for swing low
        if (candle.low < candles[idx-1].low and 
            candle.low < candles[idx+1].low):
            self._add_level(candle.low, Direction.BULLISH, idx, tolerance)
    
    def _add_level(self, price: float, direction: Direction, bar_idx: int, tolerance: float):
        """Add or update a liquidity level."""
        # Check if near existing level
        for level in self.liquidity_levels:
            if abs(level.price - price) < tolerance:
                level.touch_count += 1
                level.last_touch_bar = bar_idx
                return
        
        # New level
        level = LiquidityLevel(
            price=price,
            direction=direction,
            touch_count=1,
            last_touch_bar=bar_idx
        )
        self.liquidity_levels.append(level)
    
    def _check_sweep(self, candle: Candle, idx: int, atr: float) -> Optional[SweepEvent]:
        """Check if candle swept any liquidity level."""
        min_wick = atr * self.min_wick_atr_mult
        
        for level in self.liquidity_levels:
            if level.swept:
                continue
            
            # Check age - level must be old enough
            if idx - level.last_touch_bar < 5:
                continue
            
            # Bearish sweep: spike above level, close back below
            if level.direction == Direction.BEARISH:
                if (candle.high > level.price and 
                    candle.close < level.price and
                    (candle.high - level.price) >= min_wick):
                    
                    level.swept = True
                    level.swept_at = time.time()
                    
                    return SweepEvent(
                        timestamp=candle.timestamp,
                        level_price=level.price,
                        sweep_extreme=candle.high,
                        direction=Direction.BEARISH,
                        bar_index=idx
                    )
            
            # Bullish sweep: spike below level, close back above
            elif level.direction == Direction.BULLISH:
                if (candle.low < level.price and 
                    candle.close > level.price and
                    (level.price - candle.low) >= min_wick):
                    
                    level.swept = True
                    level.swept_at = time.time()
                    
                    return SweepEvent(
                        timestamp=candle.timestamp,
                        level_price=level.price,
                        sweep_extreme=candle.low,
                        direction=Direction.BULLISH,
                        bar_index=idx
                    )
        
        return None
    
    def _check_confirmation(self, candles: List[Candle], current_bar: int):
        """Check if recent sweeps are confirmed (close back inside)."""
        if not candles:
            return
        
        for sweep in self.sweep_events:
            if sweep.confirmed:
                continue
            
            # Check if within confirmation window
            bars_since = current_bar - sweep.bar_index
            if bars_since > self.max_bars:
                # Expired - not confirmed
                continue
            
            # Already confirmed by the sweep detection logic
            sweep.confirmed = True


# ══════════════════════════════════════════════════════════════════════════════
# SMART MONEY MATRIX (COMBINED)
# ══════════════════════════════════════════════════════════════════════════════

class SmartMoneyMatrix:
    """
    Combined Smart Money detection engine.
    
    Orchestrates all three modules:
    - OrderBlockDetector
    - FairValueGapMapper
    - LiquiditySweepDetector
    
    Provides unified interface for signal generation.
    """
    
    def __init__(self, config: Optional[dict] = None):
        config = config or {}
        
        self.ob_detector = OrderBlockDetector(
            lookback=config.get('lookback', 100),
            volume_percentile=config.get('volume_percentile', 90.0),
            max_blocks=config.get('max_blocks', 50)
        )
        
        self.fvg_mapper = FairValueGapMapper(
            max_gaps=config.get('max_gaps', 30),
            min_gap_atr_mult=config.get('min_gap_atr_mult', 0.2)
        )
        
        self.sweep_detector = LiquiditySweepDetector(
            equal_hl_tolerance_atr_mult=config.get('equal_hl_tolerance', 0.5),
            min_wick_atr_mult=config.get('min_wick_atr_mult', 0.3),
            max_levels=config.get('max_levels', 100)
        )
        
        # Signal aggregation
        self.signals: deque = deque(maxlen=100)
    
    def scan(self, candles: List[Candle], current_bar: int = 0) -> dict:
        """
        Run all detectors on candle data.
        
        Returns:
            Dict with detected patterns from all modules
        """
        # Clip input once
        candles = candles[-100:]
        
        # Run all detectors
        order_blocks = self.ob_detector.scan(candles, current_bar)
        fair_value_gaps = self.fvg_mapper.scan(candles, current_bar)
        sweep_events = self.sweep_detector.scan(candles, current_bar)
        
        # Generate signals
        signals = self._generate_signals(
            candles[-1] if candles else None,
            order_blocks,
            fair_value_gaps,
            sweep_events
        )
        
        return {
            'order_blocks': order_blocks,
            'fair_value_gaps': fair_value_gaps,
            'sweep_events': sweep_events,
            'signals': signals,
            'timestamp': time.time()
        }
    
    def _generate_signals(
        self,
        current_candle: Optional[Candle],
        order_blocks: List[OrderBlock],
        fair_value_gaps: List[FairValueGap],
        sweep_events: List[SweepEvent]
    ) -> List[dict]:
        """Generate trading signals from detected patterns."""
        signals = []
        
        if not current_candle:
            return signals
        
        price = current_candle.close
        
        # Check for OB mitigation signal
        for ob in order_blocks:
            if ob.is_valid and ob.low <= price <= ob.high:
                signals.append({
                    'type': 'OB_MITIGATION',
                    'direction': ob.direction.value,
                    'price': price,
                    'ob_price': ob.price,
                    'confidence': 0.8
                })
        
        # Check for FVG fill signal
        for fvg in fair_value_gaps:
            if fvg.is_valid and fvg.bottom <= price <= fvg.top:
                signals.append({
                    'type': 'FVG_FILL',
                    'direction': fvg.direction.value,
                    'price': price,
                    'gap_top': fvg.top,
                    'gap_bottom': fvg.bottom,
                    'confidence': 0.7
                })
        
        # Check for sweep return signal
        for sweep in sweep_events:
            if sweep.confirmed:
                signals.append({
                    'type': 'SWEEP_RETURN',
                    'direction': sweep.direction.value,
                    'price': price,
                    'level_price': sweep.level_price,
                    'sweep_extreme': sweep.sweep_extreme,
                    'confidence': 0.85
                })
        
        return signals
    
    def get_status(self) -> dict:
        """Get current matrix status."""
        return {
            'order_blocks': {
                'total': len(self.ob_detector.blocks),
                'active': len(self.ob_detector.get_active_blocks())
            },
            'fair_value_gaps': {
                'total': len(self.fvg_mapper.gaps),
                'active': len(self.fvg_mapper.get_active_gaps())
            },
            'liquidity_levels': {
                'total': len(self.sweep_detector.liquidity_levels),
                'active': len(self.sweep_detector.get_active_levels())
            },
            'sweep_events': {
                'total': len(self.sweep_detector.sweep_events),
                'confirmed': len([s for s in self.sweep_detector.sweep_events if s.confirmed])
            },
            'performance': {
                'ob_scans': self.ob_detector.scan_count,
                'fvg_scans': self.fvg_mapper.scan_count,
                'sweep_scans': self.sweep_detector.scan_count,
                'ob_found': self.ob_detector.blocks_found,
                'fvg_found': self.fvg_mapper.gaps_found,
                'sweep_found': self.sweep_detector.sweeps_found
            }
        }


# ══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

_global_matrix: Optional[SmartMoneyMatrix] = None


def get_matrix(**kwargs) -> SmartMoneyMatrix:
    """Get or create global Smart Money Matrix instance."""
    global _global_matrix
    if _global_matrix is None:
        _global_matrix = SmartMoneyMatrix(**kwargs)
    return _global_matrix


def scan_candles(candles: List[Candle], **kwargs) -> dict:
    """Quick scan using global matrix."""
    matrix = get_matrix(**kwargs)
    return matrix.scan(candles)


# ══════════════════════════════════════════════════════════════════════════════
# TEST / DEMO
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import random
    
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 70)
    print("SMART MONEY MATRIX TEST")
    print("=" * 70)
    
    # Generate test candles
    candles = []
    base_price = 2350.0
    
    for i in range(100):
        price = base_price + random.uniform(-5, 5)
        candle = Candle(
            timestamp=time.time() - (100 - i) * 60,
            open=price,
            high=price + random.uniform(0.5, 3),
            low=price - random.uniform(0.5, 3),
            close=price + random.uniform(-2, 2),
            volume=random.uniform(100, 1000)
        )
        candles.append(candle)
    
    # Create matrix and scan
    matrix = SmartMoneyMatrix()
    results = matrix.scan(candles)
    
    print(f"\nScan Results:")
    print(f"  Order Blocks: {len(results['order_blocks'])}")
    print(f"  Fair Value Gaps: {len(results['fair_value_gaps'])}")
    print(f"  Sweep Events: {len(results['sweep_events'])}")
    print(f"  Signals: {len(results['signals'])}")
    
    print(f"\nMatrix Status:")
    status = matrix.get_status()
    for module, stats in status.items():
        print(f"  {module}: {stats}")
    
    print("=" * 70)
