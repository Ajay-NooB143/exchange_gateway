"""
SMC Analyzer - High-Precision Institutional Market Structure
=============================================================
Integrates OrderBlockDetector, FairValueGapMapper, LiquiditySweepDetector
from smart_money_matrix.py into a consolidated H1/H4 structure analysis.

Features:
  - FVG auto-detection on H1/H4 with fill-status tracking
  - Premium/Discount Order Block detection with mitigation state
  - Institutional swing-level mapping (HH/HL/LH/LL)
  - Phase 64 Anti-Slippage Limit-Order Chaser
  - Support/Resistance hierarchy builder for /levels command
"""

import logging
import time
import json
import os
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
from dataclasses import dataclass, field, asdict

log = logging.getLogger('SMCAnalyzer')

DATA_DIR = Path(__file__).parent.parent / 'data' / 'smc_analysis'
DATA_DIR.mkdir(parents=True, exist_ok=True)

LEVELS_FILE = DATA_DIR / 'institutional_levels.json'
STRUCTURE_FILE = DATA_DIR / 'market_structure.json'
CHASER_FILE = DATA_DIR / 'chaser_state.json'


# ══════════════════════════════════════════════════════════════════════════════
# INSTITUTIONAL LEVEL STRUCTURES
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class FairValueGap:
    """A detected Fair Value Gap with fill tracking."""
    tf: str
    zone_type: str  # 'BULLISH' or 'BEARISH'
    top: float
    bottom: float
    midpoint: float
    detected_at: str
    filled: bool = False
    fill_pct: float = 0.0
    strength: float = 0.0  # 0-1 based on gap size relative to ATR

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class OrderBlock:
    """An institutional order block with mitigation state."""
    tf: str
    direction: str  # 'BULLISH' or 'BEARISH'
    premium_zone_top: float
    premium_zone_bottom: float
    discount_zone_top: float
    discount_zone_bottom: float
    pivot_high: float
    pivot_low: float
    mitigated: bool = False
    detected_at: str = ''
    strength: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class MarketSwing:
    """A detected market structure swing point."""
    tf: str
    type: str  # 'HH', 'HL', 'LH', 'LL'
    price: float
    index: int
    timestamp: str
    broken: bool = False


@dataclass
class ChaserOrder:
    """Phase 64 Anti-Slippage Limit-Order state."""
    symbol: str
    direction: str
    entry_price: float
    initial_price: float
    current_bid: float
    current_ask: float
    placed_price: float
    status: str  # 'SEEKING', 'PLACED', 'FILLED', 'CANCELLED'
    attempts: int = 0
    max_attempts: int = 64
    interval_ms: int = 200
    timestamp: str = ''

    def to_dict(self) -> dict:
        return asdict(self)


# ══════════════════════════════════════════════════════════════════════════════
# CORE ANALYZER
# ══════════════════════════════════════════════════════════════════════════════

class SMCAnalyzer:
    """Consolidated SMC analysis engine."""

    def __init__(self):
        self._mm_detector = None
        self._pattern_engine = None
        self._levels: List[dict] = []
        self._structure: List[MarketSwing] = []
        self._fvgs: List[FairValueGap] = []
        self._obs: List[OrderBlock] = []
        self._chaser: Optional[ChaserOrder] = None
        self._load_state()

    # ── Lazy imports ──────────────────────────────────────────────────────

    def _get_matrix(self):
        if self._mm_detector is None:
            sys.path.insert(0, str(Path(__file__).parent))
            from smart_money_matrix import OrderBlockDetector, FairValueGapMapper, LiquiditySweepDetector
            self._mm_detector = {
                'ob': OrderBlockDetector(),
                'fvg': FairValueGapMapper(),
                'sweep': LiquiditySweepDetector(),
            }
        return self._mm_detector

    def _get_patterns(self):
        if self._pattern_engine is None:
            sys.path.insert(0, str(Path(__file__).parent))
            from pattern_engine import PatternEngine
            self._pattern_engine = PatternEngine()
        return self._pattern_engine

    # ── State persistence ─────────────────────────────────────────────────

    def _load_state(self):
        try:
            if LEVELS_FILE.exists():
                with open(LEVELS_FILE) as f:
                    data = json.load(f)
                    self._levels = data.get('levels', [])
                    self._fvgs = [FairValueGap(**g) for g in data.get('fvgs', [])]
                    self._obs = [OrderBlock(**o) for o in data.get('obs', [])]
            if STRUCTURE_FILE.exists():
                with open(STRUCTURE_FILE) as f:
                    data = json.load(f)
                    self._structure = [MarketSwing(**s) for s in data.get('swings', [])]
            if CHASER_FILE.exists():
                with open(CHASER_FILE) as f:
                    data = json.load(f)
                    if data.get('order'):
                        self._chaser = ChaserOrder(**data['order'])
        except Exception as e:
            log.debug(f"Load state failed: {e}")

    def _save_levels(self):
        try:
            with open(LEVELS_FILE, 'w') as f:
                json.dump({
                    'levels': self._levels,
                    'fvgs': [g.to_dict() for g in self._fvgs],
                    'obs': [o.to_dict() for o in self._obs],
                    'updated': datetime.now(timezone.utc).isoformat(),
                }, f, indent=2)
        except Exception as e:
            log.debug(f"Save levels failed: {e}")

    def _save_structure(self):
        try:
            with open(STRUCTURE_FILE, 'w') as f:
                json.dump({
                    'swings': [{'tf': s.tf, 'type': s.type, 'price': s.price,
                                'index': s.index, 'timestamp': s.timestamp,
                                'broken': s.broken} for s in self._structure],
                    'updated': datetime.now(timezone.utc).isoformat(),
                }, f, indent=2)
        except Exception as e:
            log.debug(f"Save structure failed: {e}")

    def _save_chaser(self):
        try:
            with open(CHASER_FILE, 'w') as f:
                json.dump({
                    'order': self._chaser.to_dict() if self._chaser else None,
                    'updated': datetime.now(timezone.utc).isoformat(),
                }, f, indent=2)
        except Exception as e:
            log.debug(f"Save chaser failed: {e}")

    # ── FVG Detection ─────────────────────────────────────────────────────

    def detect_fvgs(self, candles: List[Dict], tf: str = 'H1') -> List[FairValueGap]:
        """Auto-detect FVGs with fill tracking."""
        if not candles or len(candles) < 3:
            return self._fvgs

        matrix = self._get_matrix()
        mapper = matrix['fvg']
        detected = []
        current_price = candles[-1].get('close', 0) if candles else 0

        for i in range(2, len(candles)):
            c1 = candles[i - 2]
            c2 = candles[i - 1]
            c3 = candles[i]

            if not all(k in c1 for k in ('high', 'low', 'open', 'close')):
                continue

            gap_top = min(c1['high'], c3['high'])
            gap_bottom = max(c1['low'], c3['low'])

            if gap_top > gap_bottom:
                zone_type = 'BULLISH' if c3['close'] > c1['high'] else 'BEARISH'
                gap_size = gap_top - gap_bottom
                avg_range = sum(abs(c['high'] - c['low']) for c in candles[-10:]) / max(len(candles[-10:]), 1)
                strength = min(gap_size / max(avg_range, 0.01), 1.0)

                fill_pct = 0.0
                if current_price:
                    if zone_type == 'BULLISH':
                        if current_price >= gap_top:
                            fill_pct = 100.0
                        elif current_price > gap_bottom:
                            fill_pct = ((current_price - gap_bottom) / (gap_top - gap_bottom)) * 100
                    else:
                        if current_price <= gap_bottom:
                            fill_pct = 100.0
                        elif current_price < gap_top:
                            fill_pct = ((gap_top - current_price) / (gap_top - gap_bottom)) * 100

                fvg = FairValueGap(
                    tf=tf,
                    zone_type=zone_type,
                    top=max(gap_top, gap_bottom),
                    bottom=min(gap_top, gap_bottom),
                    midpoint=(gap_top + gap_bottom) / 2,
                    detected_at=datetime.now(timezone.utc).isoformat(),
                    filled=fill_pct >= 100.0,
                    fill_pct=fill_pct,
                    strength=strength,
                )
                detected.append(fvg)

        self._fvgs = detected[-20:]  # Keep last 20
        self._save_levels()
        return self._fvgs

    # ── Order Block Detection ─────────────────────────────────────────────

    def detect_order_blocks(self, candles: List[Dict], tf: str = 'H1') -> List[OrderBlock]:
        """Detect premium/discount order blocks with mitigation state."""
        if not candles or len(candles) < 5:
            return self._obs

        blocks = []
        current_price = candles[-1].get('close', 0) if candles else 0
        atr = self._estimate_atr(candles)

        for i in range(4, len(candles)):
            c = candles[i]
            prev = candles[i - 1]
            prev2 = candles[i - 2]

            if not all(k in c for k in ('high', 'low', 'open', 'close')):
                continue

            swing_high = max(c['high'], prev['high'], prev2['high'])
            swing_low = min(c['low'], prev['low'], prev2['low'])
            body = abs(c['close'] - c['open'])
            avg_body = sum(abs(x['close'] - x['open']) for x in candles[max(0, i - 10):i + 1]) / max(len(candles[max(0, i - 10):i + 1]), 1)

            if body < avg_body * 0.5:
                continue

            direction = 'BULLISH' if c['close'] > c['open'] else 'BEARISH'

            if direction == 'BULLISH':
                ob_high = max(c['high'], prev['high'])
                ob_low = min(c['low'], prev['low'])
                premium_top = ob_high + atr * 0.5
                premium_bottom = ob_high
                discount_top = ob_low
                discount_bottom = ob_low - atr * 0.5
            else:
                ob_high = max(c['high'], prev['high'])
                ob_low = min(c['low'], prev['low'])
                premium_top = ob_high + atr * 0.5
                premium_bottom = ob_high
                discount_top = ob_low
                discount_bottom = ob_low - atr * 0.5

            mitigated = False
            if direction == 'BULLISH':
                mitigated = current_price <= ob_high
            else:
                mitigated = current_price >= ob_low

            strength = min(body / max(avg_body, 0.01) * 0.5, 1.0)

            ob = OrderBlock(
                tf=tf,
                direction=direction,
                premium_zone_top=round(premium_top, 2),
                premium_zone_bottom=round(premium_bottom, 2),
                discount_zone_top=round(discount_top, 2),
                discount_zone_bottom=round(discount_bottom, 2),
                pivot_high=round(swing_high, 2),
                pivot_low=round(swing_low, 2),
                mitigated=mitigated,
                detected_at=datetime.now(timezone.utc).isoformat(),
                strength=strength,
            )
            blocks.append(ob)

        self._obs = blocks[-10:]  # Keep last 10
        self._save_levels()
        return self._obs

    # ── Structure Mapping ─────────────────────────────────────────────────

    def map_market_structure(self, candles: List[Dict], tf: str = 'H1') -> List[MarketSwing]:
        """Map HH/HL/LH/LL swing structure."""
        if not candles or len(candles) < 10:
            return self._structure

        swings = []
        lookback = 5

        for i in range(lookback, len(candles) - lookback):
            segment = candles[i - lookback:i + lookback + 1]
            current = candles[i]

            highs = [c['high'] for c in segment if 'high' in c]
            lows = [c['low'] for c in segment if 'low' in c]
            if not highs or not lows:
                continue

            is_swing_high = current['high'] >= max(segment[-1]['high'], segment[0]['high'])
            is_swing_low = current['low'] <= min(segment[-1]['low'], segment[0]['low'])

            if is_swing_high:
                prev_highs = [s for s in swings if s.type in ('HH', 'LH')]
                if prev_highs:
                    prev = prev_highs[-1]
                    stype = 'HH' if current['high'] > prev.price else 'LH'
                else:
                    stype = 'HH'

                swings.append(MarketSwing(
                    tf=tf, type=stype, price=current['high'],
                    index=i, timestamp=datetime.now(timezone.utc).isoformat()
                ))

            if is_swing_low:
                prev_lows = [s for s in swings if s.type in ('HL', 'LL')]
                if prev_lows:
                    prev = prev_lows[-1]
                    stype = 'HL' if current['low'] > prev.price else 'LL'
                else:
                    stype = 'HL'

                swings.append(MarketSwing(
                    tf=tf, type=stype, price=current['low'],
                    index=i, timestamp=datetime.now(timezone.utc).isoformat()
                ))

        if len(swings) > 2:
            for i in range(1, len(swings)):
                if swings[i].type in ('LH', 'LL'):
                    for j in range(i):
                        if swings[j].type in ('HH', 'HL') and swings[j].price >= swings[i].price:
                            swings[j].broken = True

        self._structure = swings[-50:]
        self._save_structure()
        return self._structure

    # ── Institutional Levels Builder ──────────────────────────────────────

    def build_levels(self, candles: List[Dict], tf: str = 'H1') -> List[dict]:
        """Build complete institutional structure map."""
        self.detect_fvgs(candles, tf)
        self.detect_order_blocks(candles, tf)
        self.map_market_structure(candles, tf)

        current_price = candles[-1].get('close', 0) if candles else 0

        levels = []

        for ob in self._obs:
            ob_label = 'MITIGATED' if ob.mitigated else 'ACTIVE'
            levels.append({
                'type': f'OB_{ob.direction}',
                'zone': f'{ob.premium_zone_top} - {ob.discount_zone_bottom}',
                'pivot': f'{ob.pivot_high} / {ob.pivot_low}',
                'tf': ob.tf,
                'state': ob_label,
                'strength': f'{ob.strength:.1f}',
            })

        for fvg in self._fvgs:
            fill_state = f'{fvg.fill_pct:.0f}%' if not fvg.filled else 'FILLED'
            levels.append({
                'type': f'FVG_{fvg.zone_type}',
                'zone': f'{fvg.top} - {fvg.bottom}',
                'midpoint': f'{fvg.midpoint:.2f}',
                'tf': fvg.tf,
                'state': fill_state,
                'strength': f'{fvg.strength:.1f}',
            })

        swings = self._structure[-10:]
        for s in swings:
            levels.append({
                'type': f'SWING_{s.type}',
                'price': s.price,
                'tf': s.tf,
                'state': 'BROKEN' if s.broken else 'ACTIVE',
            })

        self._levels = levels
        self._save_levels()
        return levels

    def get_levels_table(self, current_price: float = 0) -> str:
        """Format institutional levels as a text table for Telegram."""
        if not self._levels:
            return "No institutional levels available yet."

        header = (
            "\U0001f4ca INSTITUTIONAL STRUCTURE MAP\n"
            "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        )

        if current_price:
            header += f"Price: {current_price}\n\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"

        lines = [header]
        for lvl in self._levels:
            ltype = lvl.get('type', '?')
            zone = lvl.get('zone', lvl.get('price', '?'))
            state = lvl.get('state', '')
            tf = lvl.get('tf', '')
            strength = lvl.get('strength', '')

            prefix = '\U0001f7e2' if 'ACTIVE' in state else '\u26aa'
            if 'FILLED' in state:
                prefix = '\u26aa'

            line = f"{prefix} {ltype:15s} {str(zone):>12s}  {state:10s}"
            if strength:
                line += f"  str:{strength}"
            lines.append(line)

        lines.append("\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501")
        lines.append(f"FVGs: {len([g for g in self._fvgs if not g.filled])} unmitigated")
        lines.append(f"OBs : {len([o for o in self._obs if not o.mitigated])} active")
        lines.append(f"Swings: {len(self._structure[-20:])} mapped")

        return '\n'.join(lines)

    # ── Phase 64 Anti-Slippage Limit-Order Chaser ─────────────────────────

    def init_chaser(self, symbol: str, direction: str, entry_price: float,
                    current_bid: float, current_ask: float) -> ChaserOrder:
        """Initialize a Phase 64 chaser order."""
        placed_price = current_bid if direction.upper() == 'LONG' else current_ask

        self._chaser = ChaserOrder(
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            initial_price=(current_bid + current_ask) / 2,
            current_bid=current_bid,
            current_ask=current_ask,
            placed_price=placed_price,
            status='SEEKING',
            max_attempts=64,
            interval_ms=200,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self._save_chaser()
        log.info(f"Phase 64 chaser INIT: {symbol} {direction} @ {placed_price}")
        return self._chaser

    def chase_tick(self, bid: float, ask: float) -> ChaserOrder:
        """
        Micro-adjust limit order every 200ms.
        Returns the current chaser state.

        Logic:
          - LONG: place limit at best ask, move up if price runs away
          - SHORT: place limit at best bid, move down if price runs away
          - Cancel after 64 attempts or if price moves beyond slippage tolerance
        """
        if not self._chaser or self._chaser.status in ('FILLED', 'CANCELLED'):
            return self._chaser

        self._chaser.attempts += 1
        self._chaser.current_bid = bid
        self._chaser.current_ask = ask

        direction = self._chaser.direction.upper()
        entry = self._chaser.entry_price
        slippage_tolerance = abs(entry) * 0.002  # 0.2% max slippage

        if direction == 'LONG':
            self._chaser.placed_price = min(ask, entry)
            if ask > entry + slippage_tolerance:
                log.info(f"Phase 64 CANCELLED: price ran {ask} vs entry {entry}")
                self._chaser.status = 'CANCELLED'
            elif ask <= entry:
                self._chaser.status = 'FILLED'
                log.info(f"Phase 64 FILLED: {self._chaser.symbol} LONG @ {ask}")
            else:
                self._chaser.status = 'SEEKING'
        else:
            self._chaser.placed_price = max(bid, entry)
            if bid < entry - slippage_tolerance:
                log.info(f"Phase 64 CANCELLED: price fell {bid} vs entry {entry}")
                self._chaser.status = 'CANCELLED'
            elif bid >= entry:
                self._chaser.status = 'FILLED'
                log.info(f"Phase 64 FILLED: {self._chaser.symbol} SHORT @ {bid}")
            else:
                self._chaser.status = 'SEEKING'

        if self._chaser.attempts >= self._chaser.max_attempts:
            self._chaser.status = 'CANCELLED'
            log.info(f"Phase 64 CANCELLED: max attempts ({self._chaser.max_attempts}) reached")

        self._save_chaser()
        return self._chaser

    def get_chaser_status(self) -> Optional[dict]:
        """Get current chaser state summary."""
        if not self._chaser:
            return None
        return {
            'symbol': self._chaser.symbol,
            'direction': self._chaser.direction,
            'entry': self._chaser.entry_price,
            'placed': self._chaser.placed_price,
            'attempts': f"{self._chaser.attempts}/{self._chaser.max_attempts}",
            'status': self._chaser.status,
        }

    def cancel_chaser(self) -> None:
        """Cancel active chaser order."""
        if self._chaser:
            self._chaser.status = 'CANCELLED'
            self._save_chaser()
            log.info(f"Phase 64 CANCELLED: {self._chaser.symbol} {self._chaser.direction}")

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _estimate_atr(candles: List[Dict], period: int = 14) -> float:
        """Simple ATR estimate from candle data."""
        if not candles or len(candles) < 2:
            return 5.0
        ranges = []
        for i in range(max(1, len(candles) - period), len(candles)):
            c = candles[i]
            prev = candles[i - 1]
            tr = max(c['high'] - c['low'], abs(c['high'] - prev.get('close', c['close'])),
                     abs(c['low'] - prev.get('close', c['close'])))
            ranges.append(tr)
        return sum(ranges) / max(len(ranges), 1) if ranges else 5.0

    def get_metrics(self) -> dict:
        """Return analyzer performance metrics."""
        return {
            'fvgs_tracked': len(self._fvgs),
            'fvgs_filled': sum(1 for g in self._fvgs if g.filled),
            'obs_tracked': len(self._obs),
            'obs_mitigated': sum(1 for o in self._obs if o.mitigated),
            'swings_mapped': len(self._structure),
            'chaser_active': self._chaser.status if self._chaser else 'NONE',
            'chaser_attempts': self._chaser.attempts if self._chaser else 0,
        }


# ══════════════════════════════════════════════════════════════════════════════
# GLOBAL INSTANCE
# ══════════════════════════════════════════════════════════════════════════════

_analyzer: Optional[SMCAnalyzer] = None


def get_analyzer() -> SMCAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = SMCAnalyzer()
    return _analyzer
