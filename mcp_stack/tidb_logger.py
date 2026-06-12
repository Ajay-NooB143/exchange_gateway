"""
TiDB Cloud Zero Logger - OMNI BRAIN V2 MCP Stack
=================================================
Central logging mechanism using TiDB Cloud Zero (serverless MySQL).
Every executed trade, slippage metric, and sentiment score is
automatically written to the database.

Tables:
  - trades: All executed trades with full metadata
  - sentiment_log: Sentiment scores per symbol
  - slippage_metrics: Execution quality tracking
  - pipeline_runs: Pipeline execution audit trail

Uses TiDB Serverless HTTP API (no MySQL driver required).
"""

import os
import sys
import json
import time
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger('TiDBLogger')

LOG_DIR = Path(__file__).parent / 'logs'
LOG_DIR.mkdir(exist_ok=True)


# ══════════════════════════════════════════════════════════════════════════════
# TIDB HTTP CLIENT
# ══════════════════════════════════════════════════════════════════════════════

class TiDBClient:
    """
    TiDB Cloud Zero HTTP API client.
    Uses the same API as the MCP server for consistency.
    """

    ZERO_API = "https://zero.tidbapi.com/v1alpha1/instances"

    def __init__(self):
        self.host = os.environ.get('TIDB_HOST', '')
        self.username = os.environ.get('TIDB_USERNAME', '')
        self.password = os.environ.get('TIDB_PASSWORD', '')
        self.database = os.environ.get('TIDB_DATABASE', 'omni_brain')
        self.instance_id = os.environ.get('TIDB_INSTANCE_ID', '')
        self._base_url = ""
        self._auth_token = ""
        self._load_state()

    @property
    def is_configured(self) -> bool:
        return bool(self.host and self.username and self.password)

    def _load_state(self) -> None:
        state_file = Path.home() / '.tidb-cloud-zero-mcp' / 'instance.json'
        if state_file.exists():
            try:
                with open(state_file, 'r') as f:
                    data = json.load(f)
                if not self.host:
                    self.host = data.get('host', '')
                if not self.username:
                    self.username = data.get('username', '')
                if not self.password:
                    self.password = data.get('password', '')
                self._base_url = data.get('base_url', '')
                self._auth_token = data.get('auth_token', '')
            except Exception as e:
                log.debug(f"Failed to load TiDB state: {e}")

    def _save_state(self) -> None:
        state_file = Path.home() / '.tidb-cloud-zero-mcp' / 'instance.json'
        state_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(state_file, 'w') as f:
                json.dump({
                    'host': self.host,
                    'username': self.username,
                    'password': self.password,
                    'base_url': self._base_url,
                    'auth_token': self._auth_token
                }, f, indent=2)
        except Exception as e:
            log.debug(f"Failed to save TiDB state: {e}")

    def execute_sql(self, sql: str) -> Dict[str, Any]:
        """Execute SQL via TiDB Serverless HTTP API."""
        if not self.is_configured:
            log.debug("TiDB not configured, skipping SQL execution")
            return {'ok': False, 'error': 'not_configured'}

        try:
            import urllib.request
            import base64

            encoded_sql = base64.b64encode(sql.encode()).decode()

            url = f"https://{self.host}/v1/statements"
            auth = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()

            payload = json.dumps({
                'sql': sql,
                'database': self.database
            })

            req = urllib.request.Request(
                url,
                data=payload.encode('utf-8'),
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': f'Basic {auth}'
                }
            )

            resp = urllib.request.urlopen(req, timeout=10)
            result = json.loads(resp.read().decode())
            return {'ok': True, 'result': result}

        except urllib.request.HTTPError as e:
            error_body = e.read().decode() if e.fp else str(e)
            log.error(f"TiDB execute failed: {e.code} - {error_body[:200]}")
            return {'ok': False, 'error': error_body[:200]}
        except Exception as e:
            log.error(f"TiDB execute error: {e}")
            return {'ok': False, 'error': str(e)}

    def query(self, sql: str) -> List[Dict[str, Any]]:
        """Execute read-only query and return rows."""
        result = self.execute_sql(sql)
        if result.get('ok'):
            return result.get('result', {}).get('rows', [])
        return []


# ══════════════════════════════════════════════════════════════════════════════
# SCHEMA MIGRATION
# ══════════════════════════════════════════════════════════════════════════════

SCHEMA_SQL = [
    """
    CREATE TABLE IF NOT EXISTS trades (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        symbol VARCHAR(20) NOT NULL,
        direction VARCHAR(10) NOT NULL,
        entry_price DOUBLE NOT NULL,
        exit_price DOUBLE DEFAULT NULL,
        sl_price DOUBLE DEFAULT NULL,
        tp_price DOUBLE DEFAULT NULL,
        lot_size DOUBLE DEFAULT 0.1,
        score INT DEFAULT 0,
        sentiment_score INT DEFAULT 0,
        decision VARCHAR(20) NOT NULL,
        status VARCHAR(20) DEFAULT 'OPEN',
        pnl DOUBLE DEFAULT 0,
        slippage DOUBLE DEFAULT 0,
        execution_ms DOUBLE DEFAULT 0,
        components JSON,
        metadata JSON,
        opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        closed_at TIMESTAMP NULL,
        INDEX idx_symbol (symbol),
        INDEX idx_status (status),
        INDEX idx_opened (opened_at)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sentiment_log (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        symbol VARCHAR(20) NOT NULL,
        score INT NOT NULL,
        direction VARCHAR(20) NOT NULL,
        news_score INT DEFAULT 0,
        calendar_score INT DEFAULT 0,
        trend_score INT DEFAULT 0,
        news_summary TEXT,
        calendar_events JSON,
        source VARCHAR(50) DEFAULT 'perplexity+firecrawl',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_symbol (symbol),
        INDEX idx_created (created_at)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS slippage_metrics (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        symbol VARCHAR(20) NOT NULL,
        intended_price DOUBLE NOT NULL,
        actual_price DOUBLE NOT NULL,
        slippage_pips DOUBLE NOT NULL,
        slippage_ms DOUBLE DEFAULT 0,
        broker VARCHAR(50) DEFAULT '',
        account VARCHAR(50) DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_symbol (symbol)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pipeline_runs (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        symbol VARCHAR(20) NOT NULL,
        timeframe VARCHAR(10) NOT NULL,
        score INT DEFAULT 0,
        decision VARCHAR(20) NOT NULL,
        cb_state VARCHAR(20) DEFAULT 'ACTIVE',
        mtf_confirmed BOOLEAN DEFAULT FALSE,
        total_ms DOUBLE DEFAULT 0,
        step_times JSON,
        error TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_symbol (symbol),
        INDEX idx_created (created_at)
    )
    """
]


# ══════════════════════════════════════════════════════════════════════════════
# TIDB LOGGER
# ══════════════════════════════════════════════════════════════════════════════

class TiDBLogger:
    """
    Central logging mechanism for OMNI BRAIN V2.
    Writes trade, sentiment, slippage, and pipeline data to TiDB.
    """

    def __init__(self):
        self.client = TiDBClient()
        self._initialized = False

    def initialize(self) -> bool:
        """Create all tables if they don't exist."""
        if self._initialized:
            return True

        if not self.client.is_configured:
            log.warning("TiDB not configured, using local fallback")
            self._initialized = True
            return True

        for sql in SCHEMA_SQL:
            result = self.client.execute_sql(sql.strip())
            if not result.get('ok'):
                log.error(f"Schema migration failed: {result.get('error')}")
                return False

        self._initialized = True
        log.info("TiDB schema initialized")
        return True

    def log_trade(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        score: int,
        decision: str,
        sentiment_score: int = 0,
        sl_price: float = 0,
        tp_price: float = 0,
        lot_size: float = 0.1,
        components: Dict = None,
        execution_ms: float = 0
    ) -> bool:
        """Log an executed trade to TiDB."""
        components_json = json.dumps(components or {})
        metadata = json.dumps({
            'source': 'omni_brain_v2',
            'version': '2.0'
        })

        sql = f"""
        INSERT INTO trades (symbol, direction, entry_price, sl_price, tp_price,
            lot_size, score, sentiment_score, decision, components, metadata, execution_ms)
        VALUES ("{symbol}", "{direction}", {entry_price}, {sl_price}, {tp_price},
            {lot_size}, {score}, {sentiment_score}, "{decision}",
            '{components_json}', '{metadata}', {execution_ms})
        """

        result = self.client.execute_sql(sql)
        if result.get('ok'):
            log.info(f"[TiDB] Trade logged: {symbol} {direction} {decision}")
            return True
        else:
            self._fallback_log('trade', {
                'symbol': symbol, 'direction': direction,
                'entry_price': entry_price, 'score': score,
                'decision': decision
            })
            return False

    def log_sentiment(
        self,
        symbol: str,
        score: int,
        direction: str,
        news_score: int = 0,
        calendar_score: int = 0,
        trend_score: int = 0,
        news_summary: str = '',
        calendar_events: List[Dict] = None
    ) -> bool:
        """Log sentiment analysis to TiDB."""
        events_json = json.dumps(calendar_events or [])
        summary_escaped = news_summary.replace('"', '\\"')[:500]

        sql = f"""
        INSERT INTO sentiment_log (symbol, score, direction, news_score,
            calendar_score, trend_score, news_summary, calendar_events)
        VALUES ("{symbol}", {score}, "{direction}", {news_score},
            {calendar_score}, {trend_score}, "{summary_escaped}", '{events_json}')
        """

        result = self.client.execute_sql(sql)
        if result.get('ok'):
            log.info(f"[TiDB] Sentiment logged: {symbol} {score} ({direction})")
            return True
        else:
            self._fallback_log('sentiment', {
                'symbol': symbol, 'score': score, 'direction': direction
            })
            return False

    def log_slippage(
        self,
        symbol: str,
        intended_price: float,
        actual_price: float,
        slippage_pips: float,
        slippage_ms: float = 0,
        broker: str = '',
        account: str = ''
    ) -> bool:
        """Log slippage metrics to TiDB."""
        sql = f"""
        INSERT INTO slippage_metrics (symbol, intended_price, actual_price,
            slippage_pips, slippage_ms, broker, account)
        VALUES ("{symbol}", {intended_price}, {actual_price},
            {slippage_pips}, {slippage_ms}, "{broker}", "{account}")
        """

        result = self.client.execute_sql(sql)
        if result.get('ok'):
            log.info(f"[TiDB] Slippage logged: {symbol} {slippage_pips} pips")
            return True
        else:
            self._fallback_log('slippage', {
                'symbol': symbol, 'slippage_pips': slippage_pips
            })
            return False

    def log_pipeline_run(
        self,
        symbol: str,
        timeframe: str,
        score: int,
        decision: str,
        cb_state: str = 'ACTIVE',
        mtf_confirmed: bool = False,
        total_ms: float = 0,
        step_times: Dict = None,
        error: str = ''
    ) -> bool:
        """Log pipeline execution to TiDB."""
        steps_json = json.dumps(step_times or {})
        error_escaped = error.replace('"', '\\"')[:500] if error else ''

        sql = f"""
        INSERT INTO pipeline_runs (symbol, timeframe, score, decision,
            cb_state, mtf_confirmed, total_ms, step_times, error)
        VALUES ("{symbol}", "{timeframe}", {score}, "{decision}",
            "{cb_state}", {mtf_confirmed}, {total_ms}, '{steps_json}', "{error_escaped}")
        """

        result = self.client.execute_sql(sql)
        if result.get('ok'):
            return True
        else:
            self._fallback_log('pipeline', {
                'symbol': symbol, 'decision': decision, 'score': score
            })
            return False

    def _fallback_log(self, log_type: str, data: Dict) -> None:
        """Local JSONL fallback when TiDB is unavailable."""
        try:
            filepath = LOG_DIR / f'tidb_fallback_{log_type}.jsonl'
            entry = {
                **data,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'fallback': True
            }
            with open(filepath, 'a') as f:
                f.write(json.dumps(entry) + '\n')
        except Exception:
            pass

    def get_recent_trades(self, symbol: str = None, limit: int = 50) -> List[Dict]:
        """Get recent trades from TiDB or fallback."""
        where = f"WHERE symbol = '{symbol}'" if symbol else ""
        sql = f"SELECT * FROM trades {where} ORDER BY opened_at DESC LIMIT {limit}"
        result = self.client.query(sql)
        if result:
            return result
        return self._fallback_read('trade')

    def get_sentiment_history(self, symbol: str = None, limit: int = 50) -> List[Dict]:
        where = f"WHERE symbol = '{symbol}'" if symbol else ""
        sql = f"SELECT * FROM sentiment_log {where} ORDER BY created_at DESC LIMIT {limit}"
        result = self.client.query(sql)
        if result:
            return result
        return self._fallback_read('sentiment')

    def _fallback_read(self, log_type: str) -> List[Dict]:
        filepath = LOG_DIR / f'tidb_fallback_{log_type}.jsonl'
        if not filepath.exists():
            return []
        try:
            entries = []
            with open(filepath, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        entries.append(json.loads(line))
            return entries[-50:]
        except Exception:
            return []


# ══════════════════════════════════════════════════════════════════════════════
# GLOBAL INSTANCE
# ══════════════════════════════════════════════════════════════════════════════

_logger: Optional[TiDBLogger] = None


def get_tidb_logger() -> TiDBLogger:
    global _logger
    if _logger is None:
        _logger = TiDBLogger()
    return _logger


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import sys

    logging.basicConfig(level=logging.INFO, format='%(message)s')

    if '--test' in sys.argv:
        print("=" * 60)
        print("  TIDB LOGGER - TEST")
        print("=" * 60)

        logger = TiDBLogger()

        print(f"\n  TiDB configured: {logger.client.is_configured}")
        print(f"  Host: {logger.client.host or 'not set'}")
        print(f"  Database: {logger.client.database}")

        print("\n--- Initializing schema ---")
        init_ok = logger.initialize()
        print(f"  Schema init: {'OK' if init_ok else 'FAILED'}")

        print("\n--- Logging test trade ---")
        trade_ok = logger.log_trade(
            symbol="XAUUSD",
            direction="BULLISH",
            entry_price=2350.50,
            score=85,
            decision="EXECUTE",
            sentiment_score=72,
            sl_price=2343.20,
            tp_price=2357.80,
            lot_size=0.1,
            components={'OB': 20, 'FVG': 20, 'SWEEP': 30, 'VWAP': 10, 'SESSION': 5},
            execution_ms=125.3
        )
        print(f"  Trade logged: {'OK' if trade_ok else 'FALLBACK'}")

        print("\n--- Logging sentiment ---")
        sent_ok = logger.log_sentiment(
            symbol="XAUUSD",
            score=72,
            direction="BULLISH",
            news_score=75,
            calendar_score=60,
            trend_score=80,
            news_summary="Fed paused rate hikes, USD weakening"
        )
        print(f"  Sentiment logged: {'OK' if sent_ok else 'FALLBACK'}")

        print("\n--- Logging slippage ---")
        slip_ok = logger.log_slippage(
            symbol="XAUUSD",
            intended_price=2350.50,
            actual_price=2350.55,
            slippage_pips=0.5,
            slippage_ms=45.2,
            broker="JustMarkets",
            account="1100086011"
        )
        print(f"  Slippage logged: {'OK' if slip_ok else 'FALLBACK'}")

        print("\n--- Recent trades ---")
        trades = logger.get_recent_trades("XAUUSD")
        print(f"  Found: {len(trades)} trades")

        print("\n" + "=" * 60)
    else:
        print("Usage: python tidb_logger.py --test")
