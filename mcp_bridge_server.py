"""
MCP Bridge Server - OMNI BRAIN V2
=================================
FastAPI bridge between MT5 trading logic and OpenStock dashboard.

Endpoints:
  GET  /api/signals          → Live signal feed (last 50 signals)
  GET  /api/positions        → Active positions from MT5
  GET  /api/order-blocks     → Order Block detections
  GET  /api/sentiment        → Latest sentiment scores
  GET  /api/pipeline-status  → Pipeline health + timing
  GET  /api/trades           → Trade history from TiDB
  GET  /api/slippage         → Slippage metrics
  GET  /api/system-vitals    → Memory, CPU, uptime
  POST /api/signal/ingest    → Receive signal from pipeline
  POST /api/trade/execute    → Log executed trade
  POST /api/sentiment/update → Update sentiment data
  WS   /ws/live              → WebSocket for real-time updates

Architecture:
  MT5 Scanner → Pipeline Orchestrator → MCP Bridge → OpenStock UI
                                          ↓
                                       TiDB Logger
                                          ↓
                                       Sentiment Analyzer
"""

import os
import sys
import json
import time
import logging
import asyncio
import threading
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Set
from dataclasses import dataclass, field, asdict
from pathlib import Path
from collections import deque

log = logging.getLogger('MCPBridge')

LOG_DIR = Path(__file__).parent / 'logs'
LOG_DIR.mkdir(exist_ok=True)

# Add production and mcp_stack to path
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
    """Thread-safe in-memory data store for real-time dashboard."""

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
        self._ws_clients: Set = set()

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


# Global store
_store = DataStore()


# ══════════════════════════════════════════════════════════════════════════════
# TIDB INTEGRATION (lazy load)
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
# FASTAPI SERVER
# ══════════════════════════════════════════════════════════════════════════════

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    import uvicorn
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    log.warning("FastAPI not installed. Run: pip install fastapi uvicorn")

if FASTAPI_AVAILABLE:
    app = FastAPI(
        title="OMNI BRAIN V2 - MCP Bridge",
        description="FastAPI bridge between MT5 trading logic and OpenStock dashboard",
        version="2.0.0"
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── WebSocket Manager ──────────────────────────────────────────────────

    class ConnectionManager:
        def __init__(self):
            self.active_connections: List[WebSocket] = []

        async def connect(self, websocket: WebSocket):
            await websocket.accept()
            self.active_connections.append(websocket)

        def disconnect(self, websocket: WebSocket):
            self.active_connections.remove(websocket)

        async def broadcast(self, message: Dict):
            for conn in self.active_connections:
                try:
                    await conn.send_json(message)
                except Exception:
                    pass

    ws_manager = ConnectionManager()

    # ── GET Endpoints ──────────────────────────────────────────────────────

    @app.get("/health")
    async def health():
        return {"status": "healthy", "service": "mcp-bridge", "timestamp": datetime.now(timezone.utc).isoformat()}

    @app.get("/api/signals")
    async def get_signals(limit: int = 50):
        return {"signals": _store.get_signals(limit), "total": len(_store.signals)}

    @app.get("/api/positions")
    async def get_positions():
        return {"positions": _store.get_positions()}

    @app.get("/api/order-blocks")
    async def get_order_blocks(limit: int = 50):
        return {"order_blocks": _store.get_order_blocks(limit)}

    @app.get("/api/sentiment")
    async def get_sentiment():
        return {"sentiment": _store.get_sentiment()}

    @app.get("/api/sentiment/{symbol}")
    async def get_sentiment_for_symbol(symbol: str):
        sentiment = _store.get_sentiment().get(symbol.upper())
        if not sentiment:
            return {"symbol": symbol.upper(), "score": 50, "direction": "NEUTRAL", "source": "no_data"}
        return sentiment

    @app.get("/api/pipeline-status")
    async def get_pipeline_status():
        runs = _store.get_pipeline_runs()
        return {
            "recent_runs": runs,
            "summary": _store.get_summary()
        }

    @app.get("/api/trades")
    async def get_trades(symbol: str = None, limit: int = 50):
        tidb = _get_tidb()
        if tidb:
            trades = tidb.get_recent_trades(symbol, limit)
            return {"trades": trades, "source": "tidb"}
        return {"trades": [], "source": "no_tidb"}

    @app.get("/api/slippage")
    async def get_slippage(symbol: str = None, limit: int = 50):
        return {"slippage": _store.get_slippage(limit)}

    @app.get("/api/system-vitals")
    async def get_system_vitals():
        return _store.get_vitals()

    @app.get("/api/dashboard")
    async def get_dashboard():
        return {
            "signals": _store.get_signals(10),
            "positions": _store.get_positions(),
            "order_blocks": _store.get_order_blocks(10),
            "sentiment": _store.get_sentiment(),
            "pipeline": _store.get_pipeline_runs(5),
            "vitals": _store.get_vitals(),
            "summary": _store.get_summary()
        }

    # ── POST Endpoints ─────────────────────────────────────────────────────

    @app.post("/api/signal/ingest")
    async def ingest_signal(signal: Dict[str, Any]):
        sd = SignalData(
            symbol=signal.get('symbol', 'UNKNOWN'),
            direction=signal.get('direction', 'LONG'),
            score=signal.get('score', 0),
            decision=signal.get('decision', 'BLOCK'),
            components=signal.get('components', {}),
            entry_price=signal.get('entry_price', 0),
            sl_price=signal.get('sl_price', 0),
            tp_price=signal.get('tp_price', 0),
            timeframe=signal.get('timeframe', 'H1'),
            sentiment_score=signal.get('sentiment_score', 0)
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

        await ws_manager.broadcast({
            'type': 'signal',
            'data': asdict(sd)
        })

        return {"status": "ok", "signal_id": len(_store.signals)}

    @app.post("/api/trade/execute")
    async def log_trade_execution(trade: Dict[str, Any]):
        tidb = _get_tidb()
        if tidb:
            tidb.log_trade(
                symbol=trade.get('symbol', ''),
                direction=trade.get('direction', ''),
                entry_price=trade.get('entry_price', 0),
                score=trade.get('score', 0),
                decision=trade.get('decision', 'EXECUTE'),
                sentiment_score=trade.get('sentiment_score', 0),
                sl_price=trade.get('sl_price', 0),
                tp_price=trade.get('tp_price', 0),
                lot_size=trade.get('lot_size', 0.1),
                components=trade.get('components', {}),
                execution_ms=trade.get('execution_ms', 0)
            )

        if trade.get('slippage_pips', 0) > 0:
            _store.add_slippage({
                'symbol': trade.get('symbol'),
                'intended_price': trade.get('entry_price', 0),
                'actual_price': trade.get('actual_price', 0),
                'slippage_pips': trade.get('slippage_pips', 0),
                'timestamp': datetime.now(timezone.utc).isoformat()
            })

        await ws_manager.broadcast({
            'type': 'trade',
            'data': trade
        })

        return {"status": "ok"}

    @app.post("/api/sentiment/update")
    async def update_sentiment(sentiment: Dict[str, Any]):
        symbol = sentiment.get('symbol', 'XAUUSD')
        _store.update_sentiment(symbol, sentiment)

        tidb = _get_tidb()
        if tidb:
            tidb.log_sentiment(
                symbol=symbol,
                score=sentiment.get('score', 50),
                direction=sentiment.get('direction', 'NEUTRAL'),
                news_score=sentiment.get('news_score', 0),
                calendar_score=sentiment.get('calendar_score', 0),
                trend_score=sentiment.get('trend_score', 0),
                news_summary=sentiment.get('news_summary', ''),
                calendar_events=sentiment.get('calendar_events', [])
            )

        await ws_manager.broadcast({
            'type': 'sentiment',
            'data': sentiment
        })

        return {"status": "ok"}

    @app.post("/api/pipeline/log")
    async def log_pipeline_run(run: Dict[str, Any]):
        _store.add_pipeline_run(run)

        tidb = _get_tidb()
        if tidb:
            tidb.log_pipeline_run(
                symbol=run.get('symbol', ''),
                timeframe=run.get('timeframe', 'H1'),
                score=run.get('score', 0),
                decision=run.get('decision', 'BLOCK'),
                cb_state=run.get('cb_state', 'ACTIVE'),
                mtf_confirmed=run.get('mtf_confirmed', False),
                total_ms=run.get('total_ms', 0),
                step_times=run.get('step_times', {}),
                error=run.get('error', '')
            )

        return {"status": "ok"}

    @app.post("/api/sentiment/analyze")
    async def analyze_sentiment(request: Dict[str, Any]):
        symbol = request.get('symbol', 'XAUUSD')
        price = request.get('price', 0.0)
        bias = request.get('technical_bias', 'NEUTRAL')

        analyzer = _get_sentiment()
        if analyzer:
            result = analyzer.analyze(symbol, price, bias)
            sentiment_data = {
                'symbol': result.symbol,
                'score': result.score,
                'direction': result.direction.value,
                'news_score': result.news_score,
                'calendar_score': result.calendar_score,
                'trend_score': result.trend_score,
                'news_summary': result.news_summary,
                'calendar_events': result.calendar_events
            }
            _store.update_sentiment(symbol, sentiment_data)

            tidb = _get_tidb()
            if tidb:
                tidb.log_sentiment(
                    symbol=result.symbol, score=result.score,
                    direction=result.direction.value,
                    news_score=result.news_score,
                    calendar_score=result.calendar_score,
                    trend_score=result.trend_score,
                    news_summary=result.news_summary,
                    calendar_events=result.calendar_events
                )

            return sentiment_data
        else:
            return {"symbol": symbol, "score": 50, "direction": "NEUTRAL", "source": "no_analyzer"}

    @app.post("/api/positions/update")
    async def update_position(position: Dict[str, Any]):
        pd = PositionData(
            symbol=position.get('symbol', ''),
            direction=position.get('direction', ''),
            entry_price=position.get('entry_price', 0),
            current_price=position.get('current_price', 0),
            pnl=position.get('pnl', 0),
            pnl_pips=position.get('pnl_pips', 0),
            lot_size=position.get('lot_size', 0.1),
            open_time=position.get('open_time', ''),
            sl=position.get('sl', 0),
            tp=position.get('tp', 0)
        )
        _store.update_position(pd)

        await ws_manager.broadcast({
            'type': 'position',
            'data': asdict(pd)
        })

        return {"status": "ok"}

    @app.post("/api/order-blocks/add")
    async def add_order_block(ob: Dict[str, Any]):
        ob_data = OrderBlockData(
            symbol=ob.get('symbol', ''),
            direction=ob.get('direction', ''),
            price_high=ob.get('price_high', 0),
            price_low=ob.get('price_low', 0),
            timeframe=ob.get('timeframe', 'H1'),
            strength=ob.get('strength', 0)
        )
        _store.add_order_block(ob_data)

        await ws_manager.broadcast({
            'type': 'order_block',
            'data': asdict(ob_data)
        })

        return {"status": "ok"}

    # ── WebSocket ──────────────────────────────────────────────────────────

    @app.websocket("/ws/live")
    async def websocket_endpoint(websocket: WebSocket):
        await ws_manager.connect(websocket)
        try:
            while True:
                data = await websocket.receive_text()
                msg = json.loads(data)
                if msg.get('type') == 'ping':
                    await websocket.send_json({'type': 'pong', 'timestamp': datetime.now(timezone.utc).isoformat()})
                elif msg.get('type') == 'snapshot':
                    await websocket.send_json({
                        'type': 'snapshot',
                        'data': {
                            'signals': _store.get_signals(10),
                            'positions': _store.get_positions(),
                            'sentiment': _store.get_sentiment(),
                            'vitals': _store.get_vitals()
                        }
                    })
        except WebSocketDisconnect:
            ws_manager.disconnect(websocket)


# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE INTEGRATION BRIDGE
# ══════════════════════════════════════════════════════════════════════════════

class PipelineBridge:
    """
    Bridge between existing pipeline_orchestrator.py and the MCP Bridge server.
    Can be called from the pipeline to push data to the dashboard.
    """

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
# MAIN SERVER
# ══════════════════════════════════════════════════════════════════════════════

def create_app():
    """Create and configure the FastAPI app."""
    if not FASTAPI_AVAILABLE:
        log.error("FastAPI not installed. Run: pip install fastapi uvicorn")
        return None

    tidb = _get_tidb()
    if tidb:
        tidb.initialize()
        log.info("TiDB logger initialized")

    return app


def main():
    """Start the MCP Bridge server."""
    if not FASTAPI_AVAILABLE:
        print("ERROR: FastAPI not installed.")
        print("Run: pip install fastapi uvicorn")
        sys.exit(1)

    port = int(os.environ.get('MCP_BRIDGE_PORT', '8080'))

    server_app = create_app()
    if not server_app:
        sys.exit(1)

    log.info('=' * 60)
    log.info('OMNI BRAIN V2 - MCP BRIDGE SERVER')
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
    log.info(f'  WS   /ws/live')
    log.info('=' * 60)

    uvicorn.run(server_app, host="0.0.0.0", port=port, log_level="info")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    main()
