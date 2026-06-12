"""
OMNI BRAIN V2 - MCP Bridge WebSocket Server
============================================
Pushes live signal data to the React dashboard via WebSocket.
Architecture:
  HTTP POST /push  ← pipeline pushes signal data here
  WebSocket /ws    → broadcasts to all connected dashboard clients
"""
import os
import sys
import json
import time
import asyncio
import logging
import threading
from datetime import datetime, timezone
from typing import Set, Dict, Any, Optional
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

log = logging.getLogger('MCPBridge')

WS_PORT = int(os.environ.get('MCP_WS_PORT', '3002'))
HTTP_PORT = int(os.environ.get('MCP_HTTP_PORT', '3001'))

class BridgeDataStore:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance.signals = []
                    cls._instance.latest_signal = None
                    cls._instance.sentiment = {}
                    cls._instance.system_status = {
                        'status': 'INITIALIZING',
                        'uptime': 0,
                        'signals_today': 0,
                        'last_signal': None,
                        'feed': 'UNKNOWN',
                        'telegram': 'UNKNOWN',
                        'ws_clients': 0
                    }
                    cls._instance._start_time = time.time()
        return cls._instance

    def add_signal(self, data: Dict[str, Any]):
        self.signals.append(data)
        if len(self.signals) > 100:
            self.signals = self.signals[-100:]
        self.latest_signal = data
        self.system_status['last_signal'] = f"{data.get('symbol', '?')} {data.get('score', 0)}/100 {data.get('decision', '?')}"
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        self.system_status['signals_today'] = sum(
            1 for s in self.signals
            if s.get('timestamp', '').startswith(today)
        )

    def update_sentiment(self, symbol: str, data: Dict[str, Any]):
        self.sentiment[symbol] = data

    def update_system_status(self, **kwargs):
        self.system_status.update(kwargs)
        self.system_status['uptime'] = int(time.time() - self._start_time)

    def get_payload(self) -> Dict[str, Any]:
        return {
            'signals': self.signals[-20:],
            'latest_signal': self.latest_signal,
            'sentiment': self.sentiment,
            'system': self.system_status,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }


class WebSocketHandler:
    def __init__(self):
        self.clients: Set[asyncio.Queue] = set()
        self.store = BridgeDataStore()

    async def broadcast(self, data: Dict[str, Any]):
        message = json.dumps(data)
        dead = set()
        for q in self.clients:
            try:
                await asyncio.wait_for(q.put(message), timeout=1.0)
            except (asyncio.TimeoutError, Exception):
                dead.add(q)
        self.clients -= dead
        self.store.system_status['ws_clients'] = len(self.clients)

    async def handle_client(self, websocket):
        q = asyncio.Queue()
        self.clients.add(q)
        log.info(f"WS client connected ({len(self.clients)} total)")
        self.store.system_status['ws_clients'] = len(self.clients)

        try:
            initial = self.store.get_payload()
            await websocket.send(json.dumps(initial))

            while True:
                try:
                    message = await asyncio.wait_for(q.get(), timeout=30)
                    await websocket.send(message)
                except asyncio.TimeoutError:
                    await websocket.send(json.dumps({'type': 'ping', 'timestamp': datetime.now(timezone.utc).isoformat()}))
        except Exception:
            pass
        finally:
            self.clients.discard(q)
            log.info(f"WS client disconnected ({len(self.clients)} remaining)")
            self.store.system_status['ws_clients'] = len(self.clients)


_ws_handler: Optional[WebSocketHandler] = None
_loop: Optional[asyncio.AbstractEventLoop] = None


class PushHTTPHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        path = urlparse(self.path).path
        if path == '/push':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            try:
                data = json.loads(body)
                store = BridgeDataStore()
                if data.get('type') == 'signal':
                    store.add_signal(data)
                elif data.get('type') == 'sentiment':
                    store.update_sentiment(data.get('symbol', ''), data)
                elif data.get('type') == 'status':
                    store.update_system_status(**data.get('data', {}))

                if _ws_handler and _loop and not _loop.is_closed():
                    asyncio.run_coroutine_threadsafe(
                        _ws_handler.broadcast(store.get_payload()),
                        _loop
                    )

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'ok': True}).encode())
            except Exception as e:
                log.error(f"Push error: {e}")
                self.send_response(400)
                self.end_headers()
                self.wfile.write(json.dumps({'ok': False, 'error': str(e)}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/health':
            store = BridgeDataStore()
            payload = store.get_payload()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode())
        elif path == '/status':
            store = BridgeDataStore()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            html = f"""<!DOCTYPE html>
<html><head><title>OMNI BRAIN V2 - Status</title>
<meta http-equiv="refresh" content="30">
<style>
body {{ background:#0a0a0f; color:#00ffff; font-family:monospace; text-align:center; padding:40px; }}
h1 {{ color:#00ffff; text-shadow:0 0 20px #00ffff; }}
.ok {{ color:#00ff88; }}
.warn {{ color:#ffaa00; }}
.err {{ color:#ff3355; }}
.card {{ background:#16161f; border:1px solid #2a2a3a; padding:20px; margin:10px auto; max-width:600px; }}
</style></head><body>
<h1>🧠 OMNI BRAIN V2</h1>
<div class="card">
<p>Status: <span class="ok">● ONLINE</span></p>
<p>Last Signal: {store.system_status.get('last_signal', 'N/A')}</p>
<p>Signals Today: {store.system_status.get('signals_today', 0)}</p>
<p>Uptime: {store.system_status.get('uptime', 0)}s</p>
<p>WebSocket Clients: {store.system_status.get('ws_clients', 0)}</p>
<p>Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
</div>
</body></html>"""
            self.wfile.write(html.encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


async def ws_server():
    global _ws_handler, _loop
    _loop = asyncio.get_running_loop()
    _ws_handler = WebSocketHandler()
    store = BridgeDataStore()
    store.update_system_status(status='ONLINE', feed='Twelve Data', telegram='ACTIVE')
    log.info(f"WS server ready on port {WS_PORT}")

    import websockets
    async with websockets.serve(_ws_handler.handle_client, '0.0.0.0', WS_PORT):
        log.info(f"MCP Bridge WebSocket: ws://0.0.0.0:{WS_PORT}")
        await asyncio.Future()


def run_http_server():
    httpd = HTTPServer(('0.0.0.0', HTTP_PORT), PushHTTPHandler)
    log.info(f"MCP Bridge HTTP push: http://0.0.0.0:{HTTP_PORT}/push")
    httpd.serve_forever()


def push_signal(symbol: str, score: int, decision: str, **kwargs):
    import urllib.request
    data = {
        'type': 'signal',
        'symbol': symbol,
        'score': score,
        'decision': decision,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        **kwargs
    }
    payload = json.dumps(data).encode()
    req = urllib.request.Request(
        f'http://127.0.0.1:{HTTP_PORT}/push',
        data=payload,
        headers={'Content-Type': 'application/json'}
    )
    try:
        urllib.request.urlopen(req, timeout=2)
        return True
    except Exception:
        return False


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] [%(levelname)s] %(message)s')

    import signal as sig
    stop_event = threading.Event()

    def shutdown(signum, frame):
        log.info("Shutting down MCP Bridge...")
        stop_event.set()

    sig.signal(sig.SIGINT, shutdown)
    sig.signal(sig.SIGTERM, shutdown)

    http_thread = threading.Thread(target=run_http_server, daemon=True)
    http_thread.start()

    try:
        asyncio.run(ws_server())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        log.error(f"WS server error: {e}")


if __name__ == '__main__':
    main()
