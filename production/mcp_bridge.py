"""
OMNI BRAIN V2 - MCP Bridge HTTP Server
=======================================
Pushes live signal data to dashboard via HTTP polling.
No external dependencies — uses only Python stdlib.

Architecture:
  HTTP POST /push  ← pipeline pushes signal data here
  HTTP GET  /data  → dashboard polls for latest state
  HTTP GET  /status → HTML status page
"""
import os
import json
import time
import logging
import threading
from datetime import datetime, timezone
from typing import Dict, Any
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

log = logging.getLogger('MCPBridge')

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


class MCPHTTPHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        log.info(f"{self.address_string()} - {format % args}")

    def _json_response(self, data, status=200):
        body = json.dumps(data, default=str).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == '/push':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            try:
                data = json.loads(body)
                store = BridgeDataStore()
                if data.get('type') == 'signal':
                    store.add_signal(data)
                elif data.get('type') == 'sentiment':
                    store.update_sentiment(data.get('symbol', ''), data)
                elif data.get('type') == 'status':
                    store.update_system_status(**data.get('data', {}))
                return self._json_response({'ok': True})
            except Exception as e:
                log.error(f"Push error: {e}")
                return self._json_response({'ok': False, 'error': str(e)}, 400)
        self._json_response({'error': 'Not found'}, 404)

    def do_GET(self):
        path = urlparse(self.path).path
        store = BridgeDataStore()

        if path in ('/health', '/data', '/api/data'):
            return self._json_response(store.get_payload())

        if path == '/status':
            payload = store.get_payload()
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
.card {{ background:#16161f; border:1px solid #2a2a3a; padding:20px; margin:10px auto; max-width:600px; }}
</style></head><body>
<h1>🧠 OMNI BRAIN V2</h1>
<div class="card">
<p>Status: <span class="ok">● ONLINE</span></p>
<p>Last Signal: {store.system_status.get('last_signal', 'N/A')}</p>
<p>Signals Today: {store.system_status.get('signals_today', 0)}</p>
<p>Uptime: {store.system_status.get('uptime', 0)}s</p>
<p>Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
</div>
</body></html>"""
            self.wfile.write(html.encode())
            return

        self._json_response({'error': 'Not found'}, 404)


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

    store = BridgeDataStore()
    store.update_system_status(status='ONLINE', feed='Twelve Data', telegram='ACTIVE')

    server = HTTPServer(('0.0.0.0', HTTP_PORT), MCPHTTPHandler)
    log.info(f"MCP Bridge HTTP: http://0.0.0.0:{HTTP_PORT}")
    log.info(f"  GET  /health, /data, /status")
    log.info(f"  POST /push")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        log.info("MCP Bridge stopped")


if __name__ == '__main__':
    main()
