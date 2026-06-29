"""
MCP Bridge Server - OMNI BRAIN V2
=================================
Zero-dependency HTTP bridge using Python stdlib.
Replaces FastAPI to avoid pydantic-core Rust build on Termux/aarch64.

Endpoints:
  GET  /health
  GET  /api/signals
  GET  /api/positions
  GET  /api/order-blocks
  GET  /api/sentiment
  GET  /api/sentiment/{symbol}
  GET  /api/pipeline-status
  GET  /api/trades
  GET  /api/slippage
  GET  /api/system-vitals
  GET  /api/dashboard
  POST /api/signal/ingest
  POST /api/trade/execute
  POST /api/sentiment/update
  POST /api/sentiment/analyze
  POST /api/pipeline/log
  POST /api/positions/update
  POST /api/order-blocks/add
"""

import os
import sys
import json
import time
import logging
import threading
import re
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Set
from dataclasses import dataclass, field, asdict
from pathlib import Path
from collections import deque
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

log = logging.getLogger('MCPBridge')

LOG_DIR = Path(__file__).parent / 'logs'
LOG_DIR.mkdir(exist_ok=True)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'production'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'mcp_stack'))

ASSETS = ['XAUUSD', 'EURUSD', 'GBPUSD', 'SP500']
TIMEFRAMES = ['M15', 'H1', 'H4', 'D1']


# ══════════════════════════════════════════════════════════════════════════════
# DATA MODELS
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class SignalData:
    symbol: str
    direction: str
    score: int
    decision: str
    components: Dict[str, int] = field(default_factory=dict)
    entry_price: float = 0.0
    sl_price: float = 0.0
    tp_price: float = 0.0
    timeframe: str = 'H1'
    sentiment_score: int = 0
    timestamp: str = ''

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


@dataclass
class PositionData:
    symbol: str
    direction: str
    entry_price: float
    current_price: float
    pnl: float
    pnl_pips: float
    lot_size: float
    open_time: str
    sl: float = 0.0
    tp: float = 0.0


@dataclass
class OrderBlockData:
    symbol: str
    direction: str
    price_high: float
    price_low: float
    timeframe: str
    strength: float
    timestamp: str = ''

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


# ══════════════════════════════════════════════════════════════════════════════
# IN-MEMORY DATA STORE
# ══════════════════════════════════════════════════════════════════════════════

class DataStore:
    def __init__(self):
        self.signals: deque = deque(maxlen=200)
        self.positions: Dict[str, PositionData] = {}
        self.order_blocks: deque = deque(maxlen=100)
        self.sentiment: Dict[str, Dict] = {}
        self.pipeline_runs: deque = deque(maxlen=50)
        self.slippage_metrics: deque = deque(maxlen=100)
        self.system_vitals: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._start_time = time.time()

    def add_signal(self, signal: SignalData) -> None:
        with self._lock:
            self.signals.append(asdict(signal))

    def update_position(self, position: PositionData) -> None:
        with self._lock:
            self.positions[position.symbol] = asdict(position)

    def remove_position(self, symbol: str) -> None:
        with self._lock:
            self.positions.pop(symbol, None)

    def add_order_block(self, ob: OrderBlockData) -> None:
        with self._lock:
            self.order_blocks.append(asdict(ob))

    def update_sentiment(self, symbol: str, data: Dict) -> None:
        with self._lock:
            self.sentiment[symbol] = {
                **data,
                'updated_at': datetime.now(timezone.utc).isoformat()
            }

    def add_pipeline_run(self, run: Dict) -> None:
        with self._lock:
            self.pipeline_runs.append(run)

    def add_slippage(self, metric: Dict) -> None:
        with self._lock:
            self.slippage_metrics.append(metric)

    def update_vitals(self, vitals: Dict) -> None:
        with self._lock:
            self.system_vitals = {
                **vitals,
                'uptime_seconds': int(time.time() - self._start_time),
                'last_update': datetime.now(timezone.utc).isoformat()
            }

    def get_signals(self, limit: int = 50) -> List[Dict]:
        with self._lock:
            return list(self.signals)[-limit:]

    def get_positions(self) -> List[Dict]:
        with self._lock:
            return list(self.positions.values())

    def get_order_blocks(self, limit: int = 50) -> List[Dict]:
        with self._lock:
            return list(self.order_blocks)[-limit:]

    def get_sentiment(self) -> Dict[str, Dict]:
        with self._lock:
            return dict(self.sentiment)

    def get_pipeline_runs(self, limit: int = 20) -> List[Dict]:
        with self._lock:
            return list(self.pipeline_runs)[-limit:]

    def get_slippage(self, limit: int = 50) -> List[Dict]:
        with self._lock:
            return list(self.slippage_metrics)[-limit:]

    def get_vitals(self) -> Dict:
        with self._lock:
            return dict(self.system_vitals)

    def get_summary(self) -> Dict:
        with self._lock:
            return {
                'total_signals': len(self.signals),
                'active_positions': len(self.positions),
                'active_order_blocks': len(self.order_blocks),
                'assets_tracked': len(self.sentiment),
                'pipeline_runs': len(self.pipeline_runs),
                'uptime_seconds': int(time.time() - self._start_time),
                'timestamp': datetime.now(timezone.utc).isoformat()
            }


_store = DataStore()


# ══════════════════════════════════════════════════════════════════════════════
# LAZY LOADERS
# ══════════════════════════════════════════════════════════════════════════════

def _get_tidb():
    try:
        from tidb_logger import get_tidb_logger
        return get_tidb_logger()
    except ImportError:
        return None


def _get_sentiment():
    try:
        from sentiment_analyzer import get_sentiment_analyzer
        return get_sentiment_analyzer()
    except ImportError:
        return None


# ══════════════════════════════════════════════════════════════════════════════
# HTTP HANDLER
# ══════════════════════════════════════════════════════════════════════════════

PIPELINE_API_KEY = os.getenv('PIPELINE_API_KEY', '')


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class MCPHandler(BaseHTTPRequestHandler):
    """Handles all MCP Bridge HTTP requests."""

    def log_message(self, format, *args):
        log.info(f"{self.address_string()} - {format % args}")

    def _cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-API-Key')

    def _json_response(self, data: Dict, status: int = 200):
        body = json.dumps(data, default=str).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self._cors_headers()
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> Dict:
        length = int(self.headers.get('Content-Length', 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw)

    def _check_auth(self) -> bool:
        if not PIPELINE_API_KEY:
            return True
        if self.path.startswith('/health') or self.path.startswith('/ws/'):
            return True
        return self.headers.get('X-API-Key', '') == PIPELINE_API_KEY

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def do_GET(self):
        if not self._check_auth():
            return self._json_response({'error': 'Unauthorized'}, 401)

        path = self.path.split('?')[0]

        if path == '/health':
            return self._json_response({
                'status': 'healthy', 'service': 'mcp-bridge',
                'timestamp': datetime.now(timezone.utc).isoformat()
            })

        if path == '/api/signals':
            return self._json_response({
                'signals': _store.get_signals(50),
                'total': len(_store.signals)
            })

        if path == '/api/positions':
            return self._json_response({'positions': _store.get_positions()})

        if path == '/api/order-blocks':
            return self._json_response({
                'order_blocks': _store.get_order_blocks(50)
            })

        if path == '/api/sentiment':
            return self._json_response({'sentiment': _store.get_sentiment()})

        m = re.match(r'/api/sentiment/([A-Z0-9]+)', path)
        if m:
            symbol = m.group(1)
            s = _store.get_sentiment().get(symbol)
            if not s:
                s = {'symbol': symbol, 'score': 50, 'direction': 'NEUTRAL', 'source': 'no_data'}
            return self._json_response(s)

        if path == '/api/pipeline-status':
            return self._json_response({
                'recent_runs': _store.get_pipeline_runs(),
                'summary': _store.get_summary()
            })

        if path == '/api/trades':
            tidb = _get_tidb()
            if tidb:
                trades = tidb.get_recent_trades(None, 50)
                return self._json_response({'trades': trades, 'source': 'tidb'})
            return self._json_response({'trades': [], 'source': 'no_tidb'})

        if path == '/api/slippage':
            return self._json_response({'slippage': _store.get_slippage(50)})

        if path == '/api/system-vitals':
            return self._json_response(_store.get_vitals())

        if path == '/api/dashboard':
            return self._json_response({
                'signals': _store.get_signals(10),
                'positions': _store.get_positions(),
                'order_blocks': _store.get_order_blocks(10),
                'sentiment': _store.get_sentiment(),
                'pipeline': _store.get_pipeline_runs(5),
                'vitals': _store.get_vitals(),
                'summary': _store.get_summary()
            })

        return self._json_response({'error': 'Not found'}, 404)

    def do_POST(self):
        if not self._check_auth():
            return self._json_response({'error': 'Unauthorized'}, 401)

        path = self.path.split('?')[0]
        body = self._read_body()

        if path == '/api/signal/ingest':
            sd = SignalData(
                symbol=body.get('symbol', 'UNKNOWN'),
                direction=body.get('direction', 'LONG'),
                score=body.get('score', 0),
                decision=body.get('decision', 'BLOCK'),
                components=body.get('components', {}),
                entry_price=body.get('entry_price', 0),
                sl_price=body.get('sl_price', 0),
                tp_price=body.get('tp_price', 0),
                timeframe=body.get('timeframe', 'H1'),
                sentiment_score=body.get('sentiment_score', 0)
            )
            _store.add_signal(sd)
            tidb = _get_tidb()
            if tidb:
                tidb.log_trade(
                    symbol=sd.symbol, direction=sd.direction,
                    entry_price=sd.entry_price, score=sd.score,
                    decision=sd.decision, sentiment_score=sd.sentiment_score,
                    sl_price=sd.sl_price, tp_price=sd.tp_price,
                    components=sd.components
                )
            return self._json_response({'status': 'ok', 'signal_id': len(_store.signals)})

        if path == '/api/trade/execute':
            tidb = _get_tidb()
            if tidb:
                tidb.log_trade(
                    symbol=body.get('symbol', ''),
                    direction=body.get('direction', ''),
                    entry_price=body.get('entry_price', 0),
                    score=body.get('score', 0),
                    decision=body.get('decision', 'EXECUTE'),
                    sentiment_score=body.get('sentiment_score', 0),
                    sl_price=body.get('sl_price', 0),
                    tp_price=body.get('tp_price', 0),
                    lot_size=body.get('lot_size', 0.1),
                    components=body.get('components', {}),
                    execution_ms=body.get('execution_ms', 0)
                )
            if body.get('slippage_pips', 0) > 0:
                _store.add_slippage({
                    'symbol': body.get('symbol'),
                    'intended_price': body.get('entry_price', 0),
                    'actual_price': body.get('actual_price', 0),
                    'slippage_pips': body.get('slippage_pips', 0),
                    'timestamp': datetime.now(timezone.utc).isoformat()
                })
            return self._json_response({'status': 'ok'})

        if path == '/api/sentiment/update':
            symbol = body.get('symbol', 'XAUUSD')
            _store.update_sentiment(symbol, body)
            tidb = _get_tidb()
            if tidb:
                tidb.log_sentiment(
                    symbol=symbol, score=body.get('score', 50),
                    direction=body.get('direction', 'NEUTRAL'),
                    news_score=body.get('news_score', 0),
                    calendar_score=body.get('calendar_score', 0),
                    trend_score=body.get('trend_score', 0),
                    news_summary=body.get('news_summary', ''),
                    calendar_events=body.get('calendar_events', [])
                )
            return self._json_response({'status': 'ok'})

        if path == '/api/sentiment/analyze':
            symbol = body.get('symbol', 'XAUUSD')
            price = body.get('price', 0.0)
            bias = body.get('technical_bias', 'NEUTRAL')
            analyzer = _get_sentiment()
            if analyzer:
                result = analyzer.analyze(symbol, price, bias)
                sd = {
                    'symbol': result.symbol, 'score': result.score,
                    'direction': result.direction.value,
                    'news_score': result.news_score,
                    'calendar_score': result.calendar_score,
                    'trend_score': result.trend_score,
                    'news_summary': result.news_summary,
                    'calendar_events': result.calendar_events
                }
                _store.update_sentiment(symbol, sd)
                tidb = _get_tidb()
                if tidb:
                    tidb.log_sentiment(**sd)
                return self._json_response(sd)
            return self._json_response({
                'symbol': symbol, 'score': 50,
                'direction': 'NEUTRAL', 'source': 'no_analyzer'
            })

        if path == '/api/pipeline/log':
            _store.add_pipeline_run(body)
            tidb = _get_tidb()
            if tidb:
                tidb.log_pipeline_run(
                    symbol=body.get('symbol', ''),
                    timeframe=body.get('timeframe', 'H1'),
                    score=body.get('score', 0),
                    decision=body.get('decision', 'BLOCK'),
                    cb_state=body.get('cb_state', 'ACTIVE'),
                    mtf_confirmed=body.get('mtf_confirmed', False),
                    total_ms=body.get('total_ms', 0),
                    step_times=body.get('step_times', {}),
                    error=body.get('error', '')
                )
            return self._json_response({'status': 'ok'})

        if path == '/api/positions/update':
            pd = PositionData(
                symbol=body.get('symbol', ''),
                direction=body.get('direction', ''),
                entry_price=body.get('entry_price', 0),
                current_price=body.get('current_price', 0),
                pnl=body.get('pnl', 0),
                pnl_pips=body.get('pnl_pips', 0),
                lot_size=body.get('lot_size', 0.1),
                open_time=body.get('open_time', ''),
                sl=body.get('sl', 0),
                tp=body.get('tp', 0)
            )
            _store.update_position(pd)
            return self._json_response({'status': 'ok'})

        if path == '/api/order-blocks/add':
            ob = OrderBlockData(
                symbol=body.get('symbol', ''),
                direction=body.get('direction', ''),
                price_high=body.get('price_high', 0),
                price_low=body.get('price_low', 0),
                timeframe=body.get('timeframe', 'H1'),
                strength=body.get('strength', 0)
            )
            _store.add_order_block(ob)
            return self._json_response({'status': 'ok'})

        return self._json_response({'error': 'Not found'}, 404)


# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE INTEGRATION BRIDGE (unchanged)
# ══════════════════════════════════════════════════════════════════════════════

class PipelineBridge:
    def __init__(self, bridge_url: str = "http://127.0.0.1:8080"):
        self.bridge_url = bridge_url

    def push_signal(self, signal_data: Dict) -> bool:
        return self._post('/api/signal/ingest', signal_data)

    def push_trade(self, trade_data: Dict) -> bool:
        return self._post('/api/trade/execute', trade_data)

    def push_sentiment(self, sentiment_data: Dict) -> bool:
        return self._post('/api/sentiment/update', sentiment_data)

    def push_pipeline_run(self, run_data: Dict) -> bool:
        return self._post('/api/pipeline/log', run_data)

    def push_order_block(self, ob_data: Dict) -> bool:
        return self._post('/api/order-blocks/add', ob_data)

    def push_position(self, position_data: Dict) -> bool:
        return self._post('/api/positions/update', position_data)

    def analyze_and_push_sentiment(
        self, symbol: str, price: float = 0, technical_bias: str = "NEUTRAL"
    ) -> Dict:
        try:
            import urllib.request
            payload = json.dumps({
                'symbol': symbol, 'price': price, 'technical_bias': technical_bias
            })
            url = f"{self.bridge_url}/api/sentiment/analyze"
            req = urllib.request.Request(
                url, data=payload.encode('utf-8'),
                headers={'Content-Type': 'application/json'}
            )
            resp = urllib.request.urlopen(req, timeout=30)
            return json.loads(resp.read().decode())
        except Exception as e:
            log.debug(f"Bridge sentiment analyze failed: {e}")
            return {'score': 50, 'direction': 'NEUTRAL', 'source': 'bridge_error'}

    def _post(self, endpoint: str, data: Dict) -> bool:
        try:
            import urllib.request
            url = f"{self.bridge_url}{endpoint}"
            payload = json.dumps(data, default=str)
            req = urllib.request.Request(
                url, data=payload.encode('utf-8'),
                headers={'Content-Type': 'application/json'}
            )
            urllib.request.urlopen(req, timeout=5)
            return True
        except Exception as e:
            log.debug(f"Bridge post failed ({endpoint}): {e}")
            return False


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    port = int(os.environ.get('MCP_BRIDGE_PORT', '8080'))

    tidb = _get_tidb()
    if tidb:
        tidb.initialize()
        log.info("TiDB logger initialized")

    server = ThreadingHTTPServer(('0.0.0.0', port), MCPHandler)

    log.info('=' * 60)
    log.info('OMNI BRAIN V2 - MCP BRIDGE SERVER (stdlib)')
    log.info('=' * 60)
    log.info(f'Port: {port}')
    log.info(f'Endpoints:')
    log.info(f'  GET  /health')
    log.info(f'  GET  /api/signals')
    log.info(f'  GET  /api/positions')
    log.info(f'  GET  /api/order-blocks')
    log.info(f'  GET  /api/sentiment')
    log.info(f'  GET  /api/pipeline-status')
    log.info(f'  GET  /api/trades')
    log.info(f'  GET  /api/dashboard')
    log.info(f'  POST /api/signal/ingest')
    log.info(f'  POST /api/trade/execute')
    log.info(f'  POST /api/sentiment/update')
    log.info(f'  POST /api/sentiment/analyze')
    log.info('=' * 60)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutting down MCP Bridge")
        server.shutdown()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    main()
