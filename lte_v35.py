"""
OmniSignalApexV35 - Trading Signal Aggregator
================================================
Multi-module signal processing with Smart Money Matrix integration.

Architecture:
┌─────────────────────────────────────────────────────────────────────────────┐
│                        OMNISIGNALAPEXV35                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐            │
│  │  Trend Module    │  │ Momentum Module │  │  Volume Module   │            │
│  │  (EMA/SMA)       │  │  (RSI/MACD)     │  │  (OBV/CVD)      │            │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘            │
│           │                     │                     │                      │
│           └─────────────────────┼─────────────────────┘                      │
│                                 │                                            │
│                                 ▼                                            │
│                    ┌────────────────────────┐                                │
│                    │  Confluence Scorer      │                                │
│                    │  (Weighted Aggregation) │                                │
│                    └───────────┬────────────┘                                │
│                                │                                             │
│  ┌─────────────────────────────┼─────────────────────────────┐              │
│  │                             │                             │              │
│  │  ┌─────────────┐  ┌─────────┴───────┐  ┌──────────────┐ │              │
│  │  │ SmartMoney   │  │ Signal Router   │  │ Telegram     │ │              │
│  │  │ Matrix       │  │ (Entry/Exit)    │  │ Alerts       │ │              │
│  │  │ • OB         │  │                 │  │              │ │              │
│  │  │ • FVG        │  │                 │  │              │ │              │
│  │  │ • Sweep      │  │                 │  │              │ │              │
│  │  └─────────────┘  └─────────────────┘  └──────────────┘ │              │
│  │                                                           │              │
│  └───────────────────────────────────────────────────────────┘              │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

Signal Flow:
1. Raw OHLCV → Trend/Momentum/Volume modules
2. Raw OHLCV → Smart Money Matrix (OB, FVG, Sweep)
3. All signals → Confluence Scorer
4. Score ≥ threshold → Signal Router → Trade execution
"""

import os
import sys
import time
import logging
import subprocess
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from collections import deque
from pathlib import Path

# Add production directory to path for Smart Money Matrix
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'production'))

from smart_money_matrix import (
    Candle, SmartMoneyMatrix, Direction,
    OrderBlock, FairValueGap, SweepEvent
)

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

LOG_DIR = Path(__file__).parent / 'logs'
LOG_DIR.mkdir(exist_ok=True)

# Signal log file
SIGNAL_LOG_FILE = LOG_DIR / 'signal_log.csv'
SIGNAL_LOG_HEADERS = 'timestamp,symbol,direction,score,trend,momentum,volume,ob,fvg,sweep\n'

# Initialize log file
if not SIGNAL_LOG_FILE.exists():
    SIGNAL_LOG_FILE.write_text(SIGNAL_LOG_HEADERS)


# ══════════════════════════════════════════════════════════════════════════════
# SIGNAL LOGGER WITH GIT AUTO-COMMIT
# ══════════════════════════════════════════════════════════════════════════════

class SignalLogger:
    """
    Log trading signals to CSV with auto-commit to git.
    
    Features:
    - Logs signals to CSV file
    - Auto-commits to git after each log write
    - Only commits if git repo is initialized
    - Runs in subprocess with timeout=5s
    - Suppresses output unless error
    """
    
    def __init__(self, log_file: Path = SIGNAL_LOG_FILE):
        self.log_file = log_file
        self._check_git_repo()
    
    def _check_git_repo(self):
        """Check if git repo is initialized."""
        try:
            result = subprocess.run(
                ['git', 'rev-parse', '--git-dir'],
                capture_output=True,
                timeout=5
            )
            self.is_git_repo = result.returncode == 0
        except Exception:
            self.is_git_repo = False
    
    def log_signal(
        self,
        symbol: str,
        direction: str,
        score: int,
        trend: int = 0,
        momentum: int = 0,
        volume: int = 0,
        ob: int = 0,
        fvg: int = 0,
        sweep: int = 0,
        auto_commit: bool = True
    ):
        """
        Log signal to CSV and optionally auto-commit.
        
        Args:
            symbol: Trading symbol
            direction: LONG or SHORT
            score: Total confluence score
            trend: Trend module score
            momentum: Momentum module score
            volume: Volume module score
            ob: Order Block score
            fvg: Fair Value Gap score
            sweep: Liquidity Sweep score
            auto_commit: Whether to auto-commit to git
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Write to CSV
        row = f'{timestamp},{symbol},{direction},{score},{trend},{momentum},{volume},{ob},{fvg},{sweep}\n'
        
        with open(self.log_file, 'a') as f:
            f.write(row)
        
        log.info(f'LOGGED: {direction} {symbol} | Score: {score}')
        
        # Auto-commit to git
        if auto_commit and self.is_git_repo:
            self._git_commit(symbol, direction, score, timestamp)
    
    def _git_commit(self, symbol: str, direction: str, score: int, timestamp: str):
        """
        Commit signal log to git.
        
        Runs: git add logs/ && git commit -m "signal: {symbol} {direction} {score} {timestamp}"
        """
        try:
            # Build commit message
            commit_msg = f"signal: {symbol} {direction} {score} {timestamp}"
            
            # Run git add and commit
            result = subprocess.run(
                ['git', 'add', 'logs/'],
                capture_output=True,
                timeout=5
            )
            
            if result.returncode != 0:
                log.debug(f"git add failed: {result.stderr.decode()}")
                return
            
            result = subprocess.run(
                ['git', 'commit', '-m', commit_msg],
                capture_output=True,
                timeout=5
            )
            
            if result.returncode == 0:
                log.debug(f"Git committed: {commit_msg}")
            else:
                # May fail if nothing to commit
                log.debug(f"git commit result: {result.stderr.decode()}")
                
        except subprocess.TimeoutExpired:
            log.debug("Git commit timed out")
        except Exception as e:
            log.debug(f"Git commit error: {e}")


# Global signal logger
_signal_logger: Optional[SignalLogger] = None


def get_signal_logger() -> SignalLogger:
    """Get or create global signal logger."""
    global _signal_logger
    if _signal_logger is None:
        _signal_logger = SignalLogger()
    return _signal_logger


# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(LOG_DIR, 'omnisignal.log'))
    ]
)
log = logging.getLogger('OmniSignalApexV35')


# ══════════════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Signal:
    """Trading signal"""
    symbol: str
    direction: str  # 'LONG' or 'SHORT'
    strength: float  # 0.0 to 1.0
    score: int  # Confluence score
    source: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OHLCV:
    """OHLCV candle data"""
    timestamp: float
    open: float
    high: float
    low: float
    close: float
    volume: float


# ══════════════════════════════════════════════════════════════════════════════
# TREND MODULE
# ══════════════════════════════════════════════════════════════════════════════

class TrendModule:
    """
    Trend detection using EMA/SMA crossovers.
    
    Signals:
    - Bullish: Fast EMA > Slow EMA
    - Bearish: Fast EMA < Slow EMA
    """
    
    def __init__(self, fast_period: int = 9, slow_period: int = 21):
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.closes: deque = deque(maxlen=slow_period * 2)
        
    def update(self, close: float) -> Optional[str]:
        """Update with new close price, return trend direction."""
        self.closes.append(close)
        
        if len(self.closes) < self.slow_period:
            return None
        
        # Calculate EMAs
        fast_ema = self._ema(list(self.closes), self.fast_period)
        slow_ema = self._ema(list(self.closes), self.slow_period)
        
        if fast_ema > slow_ema:
            return 'BULLISH'
        elif fast_ema < slow_ema:
            return 'BEARISH'
        return 'NEUTRAL'
    
    def _ema(self, data: list, period: int) -> float:
        """Calculate EMA."""
        if len(data) < period:
            return sum(data) / len(data)
        
        multiplier = 2 / (period + 1)
        ema = sum(data[:period]) / period
        
        for price in data[period:]:
            ema = (price - ema) * multiplier + ema
        
        return ema
    
    def get_score(self) -> int:
        """Get trend confluence score (-1 to +1)."""
        trend = self.update(self.closes[-1]) if self.closes else 'NEUTRAL'
        if trend == 'BULLISH':
            return 1
        elif trend == 'BEARISH':
            return -1
        return 0


# ══════════════════════════════════════════════════════════════════════════════
# MOMENTUM MODULE
# ══════════════════════════════════════════════════════════════════════════════

class MomentumModule:
    """
    Momentum detection using RSI.
    
    Signals:
    - Oversold (RSI < 30): Potential LONG
    - Overbought (RSI > 70): Potential SHORT
    """
    
    def __init__(self, period: int = 14, oversold: float = 30, overbought: float = 70):
        self.period = period
        self.oversold = oversold
        self.overbought = overbought
        self.closes: deque = deque(maxlen=period * 2)
        
    def update(self, close: float) -> Optional[float]:
        """Update with new close price, return RSI."""
        self.closes.append(close)
        
        if len(self.closes) < self.period + 1:
            return None
        
        return self._rsi(list(self.closes), self.period)
    
    def _rsi(self, data: list, period: int) -> float:
        """Calculate RSI."""
        deltas = [data[i] - data[i-1] for i in range(1, len(data))]
        gains = [d if d > 0 else 0 for d in deltas[-period:]]
        losses = [-d if d < 0 else 0 for d in deltas[-period:]]
        
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        
        if avg_loss == 0:
            return 100
        
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
    
    def get_score(self) -> int:
        """Get momentum confluence score (-1 to +1)."""
        rsi = self.update(self.closes[-1]) if self.closes else 50
        if rsi is None:
            return 0
        
        if rsi < self.oversold:
            return 1  # Oversold = potential LONG
        elif rsi > self.overbought:
            return -1  # Overbought = potential SHORT
        return 0


# ══════════════════════════════════════════════════════════════════════════════
# VOLUME MODULE
# ══════════════════════════════════════════════════════════════════════════════

class VolumeModule:
    """
    Volume analysis using OBV (On-Balance Volume).
    
    Signals:
    - Rising OBV with price: Bullish confirmation
    - Falling OBV with price: Bearish confirmation
    """
    
    def __init__(self, period: int = 20):
        self.period = period
        self.obv: deque = deque(maxlen=period)
        self.volumes: deque = deque(maxlen=period)
        
    def update(self, close: float, volume: float) -> Optional[float]:
        """Update with new candle, return OBV trend."""
        if self.volumes and close > self.volumes[-1]:
            obv_change = volume
        elif self.volumes and close < self.volumes[-1]:
            obv_change = -volume
        else:
            obv_change = 0
        
        new_obv = (self.obv[-1] if self.obv else 0) + obv_change
        self.obv.append(new_obv)
        self.volumes.append(close)
        
        if len(self.obv) < 2:
            return None
        
        return new_obv
    
    def get_score(self) -> int:
        """Get volume confluence score (-1 to +1)."""
        if len(self.obv) < 2:
            return 0
        
        if self.obv[-1] > self.obv[-2]:
            return 1  # Rising volume = bullish
        elif self.obv[-1] < self.obv[-2]:
            return -1  # Falling volume = bearish
        return 0


# ══════════════════════════════════════════════════════════════════════════════
# SMART MONEY MATRIX INTEGRATION
# ══════════════════════════════════════════════════════════════════════════════

class SmartMoneyModule:
    """
    Smart Money Matrix integration for institutional signal detection.
    
    Provides:
    - Order Block (OB) detection → +1 score
    - Fair Value Gap (FVG) detection → +1 score
    - Liquidity Sweep detection → +2 score (higher weight)
    """
    
    def __init__(self):
        self.matrix = SmartMoneyMatrix()
        self.candles: List[Candle] = []
        self.max_candles = 100
        
    def update(self, ohlcv: OHLCV) -> Dict[str, Any]:
        """
        Update with new candle and scan for patterns.
        
        Returns:
            Dict with detected patterns and scores
        """
        # Convert to Candle object
        candle = Candle(
            timestamp=ohlcv.timestamp,
            open=ohlcv.open,
            high=ohlcv.high,
            low=ohlcv.low,
            close=ohlcv.close,
            volume=ohlcv.volume
        )
        
        self.candles.append(candle)
        
        # Keep bounded
        if len(self.candles) > self.max_candles:
            self.candles = self.candles[-self.max_candles:]
        
        # Run scan
        results = self.matrix.scan(self.candles)
        
        return results
    
    def get_scores(self, scan_results: Dict[str, Any]) -> Dict[str, int]:
        """
        Get confluence scores from scan results.
        
        Returns:
            Dict with OB, FVG, and Sweep scores
        """
        scores = {
            'OB_SIGNAL': 0,
            'FVG_SIGNAL': 0,
            'SWEEP_SIGNAL': 0
        }
        
        # Check for Order Blocks
        order_blocks = scan_results.get('order_blocks', [])
        if order_blocks:
            scores['OB_SIGNAL'] = 1
        
        # Check for Fair Value Gaps
        fair_value_gaps = scan_results.get('fair_value_gaps', [])
        if fair_value_gaps:
            scores['FVG_SIGNAL'] = 1
        
        # Check for Liquidity Sweeps (higher weight)
        sweep_events = scan_results.get('sweep_events', [])
        if sweep_events:
            scores['SWEEP_SIGNAL'] = 2
        
        return scores
    
    def get_direction(self, scan_results: Dict[str, Any]) -> Optional[str]:
        """
        Determine direction from Smart Money patterns.
        
        Returns:
            'BULLISH', 'BEARISH', or None
        """
        # Check for bullish signals
        bullish_count = 0
        bearish_count = 0
        
        # Order Blocks
        for ob in scan_results.get('order_blocks', []):
            if ob.direction == Direction.BULLISH:
                bullish_count += 1
            elif ob.direction == Direction.BEARISH:
                bearish_count += 1
        
        # Fair Value Gaps
        for fvg in scan_results.get('fair_value_gaps', []):
            if fvg.direction == Direction.BULLISH:
                bullish_count += 1
            elif fvg.direction == Direction.BEARISH:
                bearish_count += 1
        
        # Sweeps
        for sweep in scan_results.get('sweep_events', []):
            if sweep.direction == Direction.BULLISH:
                bullish_count += 1
            elif sweep.direction == Direction.BEARISH:
                bearish_count += 1
        
        if bullish_count > bearish_count:
            return 'BULLISH'
        elif bearish_count > bullish_count:
            return 'BEARISH'
        return None


# ══════════════════════════════════════════════════════════════════════════════
# CONFLUENCE SCORER
# ══════════════════════════════════════════════════════════════════════════════

class ConfluenceScorer:
    """
    Aggregate all module scores into final signal.
    
    Weighting:
    - Trend: 1x
    - Momentum: 1x
    - Volume: 1x
    - Smart Money OB: 1x
    - Smart Money FVG: 1x
    - Smart Money Sweep: 2x (highest confidence)
    """
    
    SCORE_THRESHOLD = 3  # Minimum score for signal
    
    def __init__(self):
        self.scores: Dict[str, int] = {}
        
    def add_score(self, module: str, score: int):
        """Add score from a module."""
        self.scores[module] = score
    
    def get_total_score(self) -> int:
        """Get weighted total score."""
        return sum(self.scores.values())
    
    def get_direction(self) -> Optional[str]:
        """Determine direction from total score."""
        total = self.get_total_score()
        
        if total >= self.SCORE_THRESHOLD:
            return 'LONG'
        elif total <= -self.SCORE_THRESHOLD:
            return 'SHORT'
        return None
    
    def should_signal(self) -> bool:
        """Check if signal should be generated."""
        return abs(self.get_total_score()) >= self.SCORE_THRESHOLD
    
    def reset(self):
        """Reset all scores."""
        self.scores.clear()


# ══════════════════════════════════════════════════════════════════════════════
# OMNISIGNAL APEX V35
# ══════════════════════════════════════════════════════════════════════════════

class OmniSignalApexV35:
    """
    Main signal processing engine.
    
    Orchestrates all modules:
    - Trend (EMA/SMA)
    - Momentum (RSI)
    - Volume (OBV)
    - Smart Money Matrix (OB, FVG, Sweep)
    """
    
    def __init__(self):
        # Modules
        self.trend = TrendModule()
        self.momentum = MomentumModule()
        self.volume = VolumeModule()
        self.smart_money = SmartMoneyModule()
        
        # Scorer
        self.scorer = ConfluenceScorer()
        
        # State
        self.last_signal: Optional[Signal] = None
        self.signal_count = 0
        
    def process_candle(self, ohlcv: OHLCV, symbol: str = 'XAUUSD') -> Optional[Signal]:
        """
        Process a new candle through all modules.
        
        Args:
            ohlcv: New candle data
            symbol: Trading symbol
            
        Returns:
            Signal if threshold met, None otherwise
        """
        # Reset scorer
        self.scorer.reset()
        
        # 1. Trend Module
        trend_score = self.trend.get_score()
        self.scorer.add_score('TREND', trend_score)
        
        # 2. Momentum Module
        momentum_score = self.momentum.get_score()
        self.scorer.add_score('MOMENTUM', momentum_score)
        
        # 3. Volume Module
        volume_score = self.volume.get_score()
        self.scorer.add_score('VOLUME', volume_score)
        
        # 4. Smart Money Matrix
        sm_results = self.smart_money.update(ohlcv)
        sm_scores = self.smart_money.get_scores(sm_results)
        
        for module, score in sm_scores.items():
            self.scorer.add_score(module, score)
        
        # Check for signal
        if self.scorer.should_signal():
            direction = self.scorer.get_direction()
            
            signal = Signal(
                symbol=symbol,
                direction=direction,
                strength=min(abs(self.scorer.get_total_score()) / 10.0, 1.0),
                score=self.scorer.get_total_score(),
                source='OmniSignalApexV35',
                metadata={
                    'trend': trend_score,
                    'momentum': momentum_score,
                    'volume': volume_score,
                    **sm_scores
                }
            )
            
            self.last_signal = signal
            self.signal_count += 1
            
            log.info(
                f"SIGNAL: {direction} {symbol} | "
                f"Score: {signal.score} | "
                f"Trend: {trend_score} | Mom: {momentum_score} | "
                f"Vol: {volume_score} | OB: {sm_scores['OB_SIGNAL']} | "
                f"FVG: {sm_scores['FVG_SIGNAL']} | Sweep: {sm_scores['SWEEP_SIGNAL']}"
            )
            
            # Log signal with auto-commit
            logger = get_signal_logger()
            logger.log_signal(
                symbol=symbol,
                direction=direction,
                score=signal.score,
                trend=trend_score,
                momentum=momentum_score,
                volume=volume_score,
                ob=sm_scores['OB_SIGNAL'],
                fvg=sm_scores['FVG_SIGNAL'],
                sweep=sm_scores['SWEEP_SIGNAL'],
                auto_commit=True
            )
            
            return signal
        
        return None
    
    def get_status(self) -> Dict[str, Any]:
        """Get current engine status."""
        return {
            'modules': {
                'trend': self.trend.get_score(),
                'momentum': self.momentum.get_score(),
                'volume': self.volume.get_score(),
            },
            'smart_money': self.smart_money.matrix.get_status(),
            'last_signal': {
                'direction': self.last_signal.direction if self.last_signal else None,
                'score': self.last_signal.score if self.last_signal else 0,
                'timestamp': self.last_signal.timestamp.isoformat() if self.last_signal else None,
            },
            'signal_count': self.signal_count
        }
    
    def display_status(self):
        """Display current status in terminal."""
        status = self.get_status()
        
        print("\n" + "=" * 60)
        print("  OMNISIGNAL APEX V35 - STATUS")
        print("=" * 60)
        
        print("\n  Module Scores:")
        print(f"    Trend:     {status['modules']['trend']:+d}")
        print(f"    Momentum:  {status['modules']['momentum']:+d}")
        print(f"    Volume:    {status['modules']['volume']:+d}")
        
        print("\n  Smart Money:")
        sm = status['smart_money']
        print(f"    Order Blocks:   {sm['order_blocks']['active']} active")
        print(f"    Fair Value Gaps: {sm['fair_value_gaps']['active']} active")
        print(f"    Liquidity Levels: {sm['liquidity_levels']['active']} active")
        print(f"    Sweep Events:   {sm['sweep_events']['confirmed']} confirmed")
        
        print("\n  Last Signal:")
        if status['last_signal']['direction']:
            print(f"    Direction: {status['last_signal']['direction']}")
            print(f"    Score:     {status['last_signal']['score']}")
            print(f"    Time:      {status['last_signal']['timestamp']}")
        else:
            print("    No signal")
        
        print(f"\n  Total Signals: {status['signal_count']}")
        print("=" * 60)


# ══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE
# ══════════════════════════════════════════════════════════════════════════════

_global_engine: Optional[OmniSignalApexV35] = None


def get_engine() -> OmniSignalApexV35:
    """Get or create global engine instance."""
    global _global_engine
    if _global_engine is None:
        _global_engine = OmniSignalApexV35()
    return _global_engine


def process_ohlcv(ohlcv: OHLCV, symbol: str = 'XAUUSD') -> Optional[Signal]:
    """Quick process using global engine."""
    engine = get_engine()
    return engine.process_candle(ohlcv, symbol)


# ══════════════════════════════════════════════════════════════════════════════
# CLI / SCAN LOOP
# ══════════════════════════════════════════════════════════════════════════════

def run_scan_loop(asset: str, interval: int = 60):
    """
    Run continuous scan loop for a single asset.
    
    Uses MT5 Sync Guard for safe data synchronization.
    
    Args:
        asset: Trading symbol (XAUUSD, EURUSD, etc.)
        interval: Scan interval in seconds
    """
    import random
    
    print(f"\n{'=' * 60}")
    print(f"  OMNI BRAIN V2 - {asset} SCANNER")
    print(f"{'=' * 60}\n")
    
    engine = OmniSignalApexV35()
    
    # Initialize MT5 Sync Guard
    try:
        from production.mt5_sync_guard import get_mt5_guard
        mt5_guard = get_mt5_guard()
        print("[MT5] Sync Guard initialized")
    except ImportError:
        mt5_guard = None
        print("[MT5] Sync Guard not available, using mock data")
    
    print(f"Scanning {asset} every {interval} seconds...")
    print("Press Ctrl+C to stop.\n")
    
    base_prices = {
        'XAUUSD': 2350.0,
        'EURUSD': 1.0850,
        'GBPUSD': 1.2700,
        'SP500': 5200.0,
        'BTCUSD': 67500.0,
        'ETHUSD': 3450.0,
        'BNBUSD': 580.0,
        'SOLUSD': 145.0,
        'XRPUSD': 0.52,
    }
    
    base_price = base_prices.get(asset, 100.0)
    scan_count = 0
    
    try:
        while True:
            scan_count += 1
            
            # Try to fetch real data via MT5 Sync Guard
            if mt5_guard:
                sync_result = mt5_guard.safe_fetch(asset, 'H1')
                
                if sync_result.status == 'OK' and sync_result.candles_count > 0:
                    # Use real data
                    cached_candles = mt5_guard._cache.get(f"{asset}_H1", [])
                    if cached_candles:
                        last_candle = cached_candles[-1]
                        ohlcv = OHLCV(
                            timestamp=last_candle['timestamp'],
                            open=last_candle['open'],
                            high=last_candle['high'],
                            low=last_candle['low'],
                            close=last_candle['close'],
                            volume=last_candle['volume']
                        )
                        
                        # Show sync status every 10 scans
                        if scan_count % 10 == 1:
                            print(f"[MT5] {asset}/H1 ✓ {sync_result.source} "
                                  f"Lock:{sync_result.lock_ms:.1f}ms "
                                  f"Fetch:{sync_result.fetch_ms:.1f}ms "
                                  f"Candles:{sync_result.candles_count}")
                    else:
                        # Fallback to mock
                        ohlcv = _generate_mock_ohlcv(base_price)
                else:
                    # Use mock data
                    ohlcv = _generate_mock_ohlcv(base_price)
                    
                    if scan_count % 10 == 1:
                        print(f"[MT5] {asset}/H1 ⚠ {sync_result.status} - using mock data")
            else:
                # Generate mock OHLCV (replace with real data feed)
                ohlcv = _generate_mock_ohlcv(base_price)
            
            signal = engine.process_candle(ohlcv, asset)
            
            if signal:
                print(f"[{asset}] {signal.direction} Score:{signal.score} | {datetime.now(timezone.utc).strftime('%H:%M:%S')}")
            
            # Show MT5 status panel every 50 scans
            if mt5_guard and scan_count % 50 == 0:
                print(f"\n{mt5_guard.get_panel_display()}\n")
            
            time.sleep(interval)
    
    except KeyboardInterrupt:
        print(f"\n{asset} scanner stopped.")
        if mt5_guard:
            print("[MT5] Cleaning up locks...")
            mt5_guard._cleanup_all()
            print("[MT5] Done")


def _generate_mock_ohlcv(base_price: float):
    """Generate mock OHLCV data."""
    import random
    price = base_price + random.uniform(-5, 5)
    return OHLCV(
        timestamp=time.time(),
        open=price,
        high=price + random.uniform(0.5, 2),
        low=price - random.uniform(0.5, 2),
        close=price + random.uniform(-1, 1),
        volume=random.uniform(100, 1000)
    )


# ══════════════════════════════════════════════════════════════════════════════
# TEST / DEMO
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    import random
    
    # Parse CLI arguments
    if '--asset' in sys.argv:
        idx = sys.argv.index('--asset')
        if idx + 1 < len(sys.argv):
            asset = sys.argv[idx + 1].upper()
            run_scan_loop(asset)
        else:
            print("Error: --asset requires a value")
            sys.exit(1)
    elif '--test' in sys.argv:
        print("=" * 60)
        print("  OMNISIGNAL APEX V35 - TEST")
        print("=" * 60)
        
        engine = OmniSignalApexV35()
        
        # Generate test data
        base_price = 2350.0
        
        print("\nProcessing 100 test candles...")
        for i in range(100):
            price = base_price + random.uniform(-10, 10)
            ohlcv = OHLCV(
                timestamp=time.time() - (100 - i) * 60,
                open=price,
                high=price + random.uniform(0.5, 3),
                low=price - random.uniform(0.5, 3),
                close=price + random.uniform(-2, 2),
                volume=random.uniform(100, 1000)
            )
            
            signal = engine.process_candle(ohlcv)
            if signal:
                print(f"\n  SIGNAL at candle {i}: {signal.direction} (score: {signal.score})")
        
        engine.display_status()
        print("=" * 60)
    else:
        print("Usage:")
        print("  python lte_v35.py --asset XAUUSD    # Run scan loop")
        print("  python lte_v35.py --test             # Run test")
