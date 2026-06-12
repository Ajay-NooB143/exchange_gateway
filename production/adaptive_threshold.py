"""
Adaptive Threshold Engine - OMNI BRAIN V2
==========================================
Track last 20 trade signal results per asset and adapt thresholds.

Adaptation Rules:
  Win streak >= 3  → tighten entry threshold +5pts
  Loss streak >= 3 → widen filter threshold -5pts
  Win rate > 70%   → threshold cap at 80
  Win rate < 40%   → threshold floor at 60
  Default threshold: 75
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from pathlib import Path
from collections import deque
import threading

log = logging.getLogger('AdaptiveThreshold')

LOG_DIR = Path(__file__).parent / 'logs'
LOG_DIR.mkdir(exist_ok=True)


@dataclass
class TradeResult:
    """Result of a trade signal."""
    symbol: str
    tf: str
    direction: str
    score: int
    result: str  # WIN, LOSS, NEUTRAL
    timestamp: str = ''
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class AdaptiveThreshold:
    """
    Adaptive threshold engine that adjusts entry thresholds
    based on recent performance.
    
    Rules:
      Win streak >= 3  → threshold +5pts
      Loss streak >= 3 → threshold -5pts
      Win rate > 70%   → threshold cap at 80
      Win rate < 40%   → threshold floor at 60
    """
    
    DEFAULT_THRESHOLD = 75
    MIN_THRESHOLD = 60
    MAX_THRESHOLD = 80
    MAX_HISTORY = 20
    STREAK_LENGTH = 3
    
    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or LOG_DIR
        self.data_dir.mkdir(exist_ok=True)
        
        # Per-symbol state
        self.thresholds: Dict[str, int] = {}
        self.histories: Dict[str, deque] = {}
        self.streaks: Dict[str, Dict[str, int]] = {}
    
    def _load_state(self, symbol: str) -> None:
        """Load state from file."""
        filepath = self.data_dir / f'threshold_{symbol}.json'
        
        if filepath.exists():
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                
                self.thresholds[symbol] = data.get('threshold', self.DEFAULT_THRESHOLD)
                self.streaks[symbol] = data.get('streaks', {'wins': 0, 'losses': 0})
                
                # Rebuild history
                history = data.get('history', [])
                self.histories[symbol] = deque(history[-self.MAX_HISTORY:], maxlen=self.MAX_HISTORY)
            except Exception as e:
                log.error(f"Failed to load state for {symbol}: {e}")
                self._init_symbol(symbol)
        else:
            self._init_symbol(symbol)
    
    def _init_symbol(self, symbol: str) -> None:
        """Initialize state for a symbol."""
        self.thresholds[symbol] = self.DEFAULT_THRESHOLD
        self.histories[symbol] = deque(maxlen=self.MAX_HISTORY)
        self.streaks[symbol] = {'wins': 0, 'losses': 0}
    
    def _save_state(self, symbol: str) -> None:
        """Save state to file."""
        filepath = self.data_dir / f'threshold_{symbol}.json'
        
        data = {
            'symbol': symbol,
            'threshold': self.thresholds.get(symbol, self.DEFAULT_THRESHOLD),
            'streaks': self.streaks.get(symbol, {'wins': 0, 'losses': 0}),
            'history': list(self.histories.get(symbol, [])),
            'last_updated': datetime.now(timezone.utc).isoformat()
        }
        
        try:
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            log.error(f"Failed to save state for {symbol}: {e}")
    
    def _ensure_loaded(self, symbol: str) -> None:
        """Ensure symbol state is loaded."""
        if symbol not in self.thresholds:
            self._load_state(symbol)
    
    def get_threshold(self, symbol: str) -> int:
        """Get current threshold for symbol."""
        self._ensure_loaded(symbol)
        return self.thresholds.get(symbol, self.DEFAULT_THRESHOLD)
    
    def record_result(self, symbol: str, tf: str, result: str, score: int) -> None:
        """
        Record a trade result and adapt threshold.
        
        Args:
            symbol: Trading symbol
            tf: Timeframe
            result: WIN, LOSS, or NEUTRAL
            score: Confidence score
        """
        self._ensure_loaded(symbol)
        
        # Create trade result
        trade = TradeResult(
            symbol=symbol,
            tf=tf,
            direction='',
            score=score,
            result=result
        )
        
        # Add to history
        self.histories[symbol].append({
            'result': result,
            'score': score,
            'tf': tf,
            'timestamp': trade.timestamp
        })
        
        # Update streaks
        if result == 'WIN':
            self.streaks[symbol]['wins'] += 1
            self.streaks[symbol]['losses'] = 0
        elif result == 'LOSS':
            self.streaks[symbol]['losses'] += 1
            self.streaks[symbol]['wins'] = 0
        else:
            # NEUTRAL resets streaks
            self.streaks[symbol]['wins'] = 0
            self.streaks[symbol]['losses'] = 0
        
        # Adapt threshold
        self._adapt_threshold(symbol)
        
        # Save state
        self._save_state(symbol)
        
        log.info(f"Recorded {result} for {symbol}/{tf} (score: {score})")
    
    def _adapt_threshold(self, symbol: str) -> None:
        """Adapt threshold based on recent performance."""
        old_threshold = self.thresholds.get(symbol, self.DEFAULT_THRESHOLD)
        new_threshold = old_threshold
        
        streaks = self.streaks.get(symbol, {'wins': 0, 'losses': 0})
        history = list(self.histories.get(symbol, []))
        
        # Rule 1: Win streak >= 3 → tighten (+5)
        if streaks['wins'] >= self.STREAK_LENGTH:
            new_threshold = min(old_threshold + 5, self.MAX_THRESHOLD)
            log.info(f"[ADAPTIVE] {symbol} win streak {streaks['wins']} → threshold +5")
        
        # Rule 2: Loss streak >= 3 → widen (-5)
        elif streaks['losses'] >= self.STREAK_LENGTH:
            new_threshold = max(old_threshold - 5, self.MIN_THRESHOLD)
            log.info(f"[ADAPTIVE] {symbol} loss streak {streaks['losses']} → threshold -5")
        
        # Rule 3: Win rate based adjustments
        if len(history) >= 10:
            wins = sum(1 for h in history if h['result'] == 'WIN')
            win_rate = wins / len(history) * 100
            
            if win_rate > 70:
                new_threshold = min(new_threshold + 2, self.MAX_THRESHOLD)
                log.info(f"[ADAPTIVE] {symbol} win rate {win_rate:.0f}% → threshold cap {self.MAX_THRESHOLD}")
            elif win_rate < 40:
                new_threshold = max(new_threshold - 2, self.MIN_THRESHOLD)
                log.info(f"[ADAPTIVE] {symbol} win rate {win_rate:.0f}% → threshold floor {self.MIN_THRESHOLD}")
        
        # Apply change
        if new_threshold != old_threshold:
            log.info(f"[ADAPTIVE] {symbol} threshold: {old_threshold} → {new_threshold}")
            self.thresholds[symbol] = new_threshold
    
    def get_stats(self, symbol: str) -> Dict[str, Any]:
        """Get statistics for symbol."""
        self._ensure_loaded(symbol)
        
        history = list(self.histories.get(symbol, []))
        streaks = self.streaks.get(symbol, {'wins': 0, 'losses': 0})
        
        total = len(history)
        wins = sum(1 for h in history if h['result'] == 'WIN')
        losses = sum(1 for h in history if h['result'] == 'LOSS')
        
        return {
            'symbol': symbol,
            'threshold': self.thresholds.get(symbol, self.DEFAULT_THRESHOLD),
            'total_trades': total,
            'wins': wins,
            'losses': losses,
            'win_rate': (wins / total * 100) if total > 0 else 0,
            'streaks': streaks,
            'avg_score': sum(h['score'] for h in history) / total if total > 0 else 0
        }
    
    def get_all_thresholds(self) -> Dict[str, int]:
        """Get all symbol thresholds."""
        for symbol in ['XAUUSD', 'EURUSD', 'GBPUSD', 'SP500']:
            self._ensure_loaded(symbol)
        return dict(self.thresholds)


# Global instance
_threshold_engine: Optional[AdaptiveThreshold] = None
_lock = threading.Lock()


def get_threshold_engine() -> AdaptiveThreshold:
    """Get or create global threshold engine."""
    global _threshold_engine
    if _threshold_engine is None:
        with _lock:
            if _threshold_engine is None:
                _threshold_engine = AdaptiveThreshold()
    return _threshold_engine


def get_threshold(symbol: str) -> int:
    """Get threshold for symbol (convenience function)."""
    return get_threshold_engine().get_threshold(symbol)


def record_result(symbol: str, tf: str, result: str, score: int) -> None:
    """Record trade result (convenience function)."""
    get_threshold_engine().record_result(symbol, tf, result, score)


# ══════════════════════════════════════════════════════════════════════════════
# CLI TEST
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import sys
    
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    if '--test' in sys.argv:
        print("=" * 60)
        print("  ADAPTIVE THRESHOLD ENGINE - TEST")
        print("=" * 60)
        
        engine = AdaptiveThreshold()
        
        # Simulate wins
        print("\nSimulating win streak for XAUUSD...")
        for i in range(5):
            engine.record_result('XAUUSD', 'H1', 'WIN', 80)
            print(f"  Trade {i+1}: WIN → Threshold: {engine.get_threshold('XAUUSD')}")
        
        # Simulate losses
        print("\nSimulating loss streak for EURUSD...")
        for i in range(5):
            engine.record_result('EURUSD', 'M15', 'LOSS', 60)
            print(f"  Trade {i+1}: LOSS → Threshold: {engine.get_threshold('EURUSD')}")
        
        # Show stats
        print("\nStats:")
        for symbol in ['XAUUSD', 'EURUSD']:
            stats = engine.get_stats(symbol)
            print(f"  {symbol}: threshold={stats['threshold']}, win_rate={stats['win_rate']:.0f}%, "
                  f"streaks={stats['streaks']}")
        
        print("\n" + "=" * 60)
    else:
        print("Usage: python adaptive_threshold.py --test")
