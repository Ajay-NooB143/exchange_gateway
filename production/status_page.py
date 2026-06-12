#!/usr/bin/env python3
"""Simple status page for PM2 health check."""
import http.server, json, time, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

class StatusHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps({
            'status': 'healthy',
            'service': 'omni-status',
            'timestamp': time.time()
        }).encode())
    def log_message(self, *a): pass

if __name__ == '__main__':
    port = int(__import__('os').environ.get('STATUS_PORT', '8089'))
    server = http.server.HTTPServer(('0.0.0.0', port), StatusHandler)
    server.serve_forever()
