"""
Confluence Memory Engine - Pattern-Outcome Expectancy Database
===============================================================
Persists signal pattern combinations → win/loss outcomes to SQLite.
Provides win-rate queries for dynamic confidence weight adjustment.

Pattern dimensions tracked:
  - FVG (present/absent)
  - OB  (bullish/bearish/absent)
  - Session (London/NY/Asian/Off)
  - Regime (EXPANSION/COMPRESSION/TRAP/VOLATILITY)
  - LiquidityTier (INSTITUTIONAL/HIGH/MODERATE/LOW)
"""

import logging
import json
import sqlite3
import os
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path

log = logging.getLogger('ConfluenceMemory')

DB_DIR = Path(__file__).parent / 'data'
DB_DIR.mkdir(exist_ok=True)
DB_PATH = str(DB_DIR / 'confluence_memory.db')

# In-memory lock for thread safety
_lock = threading.Lock()


class ConfluenceMemory:
    """
    SQLite-backed pattern-outcome memory.

    Stores each signal's pattern signature and its outcome (win/loss).
    Queries return win-rate expectancy for arbitrary pattern combos.
    """

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()
        self._cache: Dict[str, Dict] = {}
        self._cache_time = 0.0

    def _init_db(self):
        """Create tables if they don't exist."""
        try:
            with _lock:
                conn = sqlite3.connect(self.db_path, timeout=10)
                conn.execute('PRAGMA journal_mode=WAL')
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS pattern_outcome (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        symbol TEXT NOT NULL,
                        tf TEXT,
                        fvg INT DEFAULT 0,
                        ob_type TEXT DEFAULT '',
                        session TEXT DEFAULT '',
                        regime TEXT DEFAULT '',
                        liquidity_tier TEXT DEFAULT '',
                        score INT DEFAULT 0,
                        decision TEXT DEFAULT '',
                        outcome TEXT DEFAULT 'PENDING',
                        pnl REAL DEFAULT 0.0,
                        created_at TEXT DEFAULT (datetime('now'))
                    )
                ''')
                conn.execute('''
                    CREATE INDEX IF NOT EXISTS idx_pattern_outcome_lookup
                    ON pattern_outcome(symbol, fvg, ob_type, session, regime)
                ''')
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS weight_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        component TEXT NOT NULL,
                        weight INT DEFAULT 0,
                        win_rate REAL DEFAULT 0.0,
                        sample_count INT DEFAULT 0,
                        updated_at TEXT DEFAULT (datetime('now'))
                    )
                ''')
                conn.commit()
                conn.close()
        except Exception as e:
            log.warning(f"DB init failed: {e}")

    def _get_conn(self) -> sqlite3.Connection:
        """Get a new connection (thread-safe)."""
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def record_outcome(
        self,
        symbol: str,
        pattern: Dict[str, Any],
        outcome: str,
        pnl: float = 0.0,
    ) -> bool:
        """
        Record a pattern-outcome pair.

        Args:
            symbol: Trading symbol
            pattern: Dict with keys: fvg, ob_type, session, regime,
                     liquidity_tier, score, decision
            outcome: 'WIN', 'LOSS', or 'PENDING'
            pnl: Net PnL in pips/points

        Returns:
            True if recorded successfully
        """
        try:
            with _lock:
                conn = self._get_conn()
                conn.execute('''
                    INSERT INTO pattern_outcome
                        (symbol, tf, fvg, ob_type, session, regime,
                         liquidity_tier, score, decision, outcome, pnl)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    symbol,
                    pattern.get('tf', ''),
                    1 if pattern.get('fvg') else 0,
                    pattern.get('ob_type', 'NONE'),
                    pattern.get('session', ''),
                    pattern.get('regime', ''),
                    pattern.get('liquidity_tier', ''),
                    pattern.get('score', 0),
                    pattern.get('decision', ''),
                    outcome,
                    pnl,
                ))
                conn.commit()
                conn.close()
                self._bust_cache()
                return True
        except Exception as e:
            log.warning(f"Failed to record outcome: {e}")
            return False

    def query_win_rate(
        self,
        symbol: str,
        fvg: Optional[bool] = None,
        ob_type: Optional[str] = None,
        session: Optional[str] = None,
        regime: Optional[str] = None,
        min_samples: int = 5,
    ) -> Tuple[float, int]:
        """
        Query win-rate expectancy for a pattern combination.

        Args:
            symbol: Trading symbol
            fvg: Filter by FVG presence
            ob_type: Filter by OB type (BULLISH, BEARISH, NONE)
            session: Filter by session (LONDON, NY, ASIAN, OFF)
            regime: Filter by regime
            min_samples: Minimum number of samples to consider

        Returns:
            (win_rate_0_to_1, sample_count)
        """
        try:
            conditions = ['symbol = ?', "outcome IN ('WIN', 'LOSS')"]
            params: List[Any] = [symbol]

            if fvg is not None:
                conditions.append('fvg = ?')
                params.append(1 if fvg else 0)
            if ob_type:
                conditions.append('ob_type = ?')
                params.append(ob_type)
            if session:
                conditions.append('session = ?')
                params.append(session)
            if regime:
                conditions.append('regime = ?')
                params.append(regime)

            where = ' AND '.join(conditions)

            with _lock:
                conn = self._get_conn()
                # Total samples
                row = conn.execute(
                    f'SELECT COUNT(*) as cnt FROM pattern_outcome WHERE {where}',
                    params,
                ).fetchone()
                total = row['cnt'] if row else 0

                if total < min_samples:
                    conn.close()
                    return 0.5, total  # Neutral if insufficient data

                # Win count
                win_params = params[:]
                win_row = conn.execute(
                    f'SELECT COUNT(*) as cnt FROM pattern_outcome WHERE {where} AND outcome = "WIN"',
                    win_params,
                ).fetchone()
                wins = win_row['cnt'] if win_row else 0

                conn.close()

                win_rate = wins / max(total, 1)
                return win_rate, total

        except Exception as e:
            log.debug(f"Win rate query failed: {e}")
            return 0.5, 0

    def get_component_adjustment(
        self,
        symbol: str,
        component: str,
        pattern: Dict[str, Any],
    ) -> float:
        """
        Get dynamic weight adjustment factor for a confidence component.

        Returns multiplier 0.0-2.0:
          >1.0 → boost component weight
          <1.0 → reduce component weight

        Example:
          If FVG + BULLISH_OB + LONDON has 80% win rate,
          adjustment = 1.2 (boost).
        """
        try:
            # Build pattern context from the component
            context = dict(pattern)
            if component == 'OB':
                ob_filter = context.get('ob_type')
            else:
                ob_filter = None

            fvg_filter = None
            if component == 'FVG':
                fvg_filter = True

            win_rate, samples = self.query_win_rate(
                symbol=symbol,
                fvg=fvg_filter,
                ob_type=ob_filter,
                session=context.get('session'),
                regime=context.get('regime'),
                min_samples=3,
            )

            if samples < 3:
                return 1.0

            # Map win rate to adjustment (0.0-2.0)
            # 50% win rate → 1.0 (no change)
            # 80% win rate → 1.6
            # 30% win rate → 0.6
            adjustment = win_rate * 2.0
            return max(0.0, min(2.0, adjustment))

        except Exception:
            return 1.0

    def get_best_patterns(
        self,
        symbol: str,
        top_n: int = 5,
        min_samples: int = 10,
    ) -> List[Dict[str, Any]]:
        """Get top-N best performing pattern combinations."""
        try:
            with _lock:
                conn = self._get_conn()
                rows = conn.execute('''
                    SELECT
                        fvg, ob_type, session, regime,
                        COUNT(*) as samples,
                        SUM(CASE WHEN outcome = 'WIN' THEN 1 ELSE 0 END) as wins
                    FROM pattern_outcome
                    WHERE symbol = ? AND outcome IN ('WIN', 'LOSS')
                    GROUP BY fvg, ob_type, session, regime
                    HAVING samples >= ?
                    ORDER BY CAST(wins AS REAL) / samples DESC
                    LIMIT ?
                ''', (symbol, min_samples, top_n)).fetchall()
                conn.close()

                results = []
                for r in rows:
                    win_rate = r['wins'] / max(r['samples'], 1)
                    results.append({
                        'fvg': bool(r['fvg']),
                        'ob_type': r['ob_type'],
                        'session': r['session'],
                        'regime': r['regime'],
                        'samples': r['samples'],
                        'win_rate': round(win_rate, 3),
                    })
                return results
        except Exception as e:
            log.debug(f"Best patterns query failed: {e}")
            return []

    def get_summary_stats(self) -> Dict[str, Any]:
        """Get aggregate memory statistics."""
        try:
            with _lock:
                conn = self._get_conn()
                row = conn.execute('''
                    SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN outcome = 'WIN' THEN 1 ELSE 0 END) as wins,
                        SUM(CASE WHEN outcome = 'LOSS' THEN 1 ELSE 0 END) as losses,
                        SUM(CASE WHEN outcome = 'PENDING' THEN 1 ELSE 0 END) as pending
                    FROM pattern_outcome
                ''').fetchone()
                conn.close()

                if not row:
                    return {'total': 0, 'wins': 0, 'losses': 0, 'pending': 0, 'win_rate': 0.5}

                total = row['total'] or 0
                wins = row['wins'] or 0
                losses = row['losses'] or 0
                total_resolved = wins + losses

                return {
                    'total': total,
                    'wins': wins,
                    'losses': losses,
                    'pending': row['pending'] or 0,
                    'win_rate': round(wins / max(total_resolved, 1), 3),
                }
        except Exception:
            return {'total': 0, 'wins': 0, 'losses': 0, 'pending': 0, 'win_rate': 0.5}

    def _bust_cache(self):
        self._cache = {}
        self._cache_time = 0.0


# ══════════════════════════════════════════════════════════════════════════════
# GLOBAL INSTANCE
# ══════════════════════════════════════════════════════════════════════════════

_memory: Optional[ConfluenceMemory] = None


def get_memory() -> ConfluenceMemory:
    global _memory
    if _memory is None:
        _memory = ConfluenceMemory()
    return _memory


# ══════════════════════════════════════════════════════════════════════════════
# CLI TEST
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.INFO, format='%(message)s')

    if '--test' in sys.argv:
        mem = get_memory()

        # Record test outcomes
        for i in range(20):
            mem.record_outcome(
                'XAUUSD',
                {
                    'tf': 'H1',
                    'fvg': i % 2 == 0,
                    'ob_type': 'BULLISH' if i % 3 == 0 else 'NONE',
                    'session': 'LONDON' if i % 2 == 0 else 'NY',
                    'regime': 'EXPANSION' if i % 4 == 0 else 'COMPRESSION',
                    'liquidity_tier': 'HIGH',
                    'score': 80,
                    'decision': 'EXECUTE',
                },
                'WIN' if i < 12 else 'LOSS',
                pnl=15.0 if i < 12 else -8.0,
            )

        stats = mem.get_summary_stats()
        print(f"Summary: {stats}")

        wr, n = mem.query_win_rate('XAUUSD', fvg=True)
        print(f"Win rate (FVG=true): {wr:.1%} (n={n})")

        adj = mem.get_component_adjustment('XAUUSD', 'FVG', {
            'session': 'LONDON', 'regime': 'EXPANSION', 'ob_type': 'BULLISH',
        })
        print(f"FVG adjustment factor: {adj:.2f}")

        best = mem.get_best_patterns('XAUUSD', top_n=3)
        for b in best:
            print(f"  {b}")

        print("ConfluenceMemory OK")
