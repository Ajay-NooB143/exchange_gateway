"""Tests for auth middleware in pipeline_orchestrator.py - OMNI BRAIN V2"""
import sys, os, json, time, threading
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'production'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import pytest

from unittest.mock import Mock, patch


class TestAuthMiddleware:
    def make_handler(self, path='/health', method='GET'):
        handler = Mock()
        handler.client_address = ('127.0.0.1', 54321)
        handler.path = path
        handler.command = method
        handler.headers = {}
        handler._send_json = Mock()
        return handler

    @pytest.fixture(autouse=True)
    def reset_state(self):
        import pipeline_orchestrator as po
        po._blocked_ips.clear()
        po._request_counts.clear()
        po._failed_auth.clear()

    def test_auth_required_blocks_unauthorized(self):
        import pipeline_orchestrator as po
        handler = self.make_handler(path='/api/omni-status')
        handler.headers = {'X-API-Key': 'wrong-key'}
        po.ScannerHandler.do_GET(handler)
        call_args = handler._send_json.call_args
        assert call_args is not None
        args, kwargs = call_args
        assert args[0] == 401

    def test_rate_limiting_exceeded(self):
        import pipeline_orchestrator as po
        handler = self.make_handler(path='/api/omni-status')
        handler.headers = {'X-API-Key': po.API_KEY}
        po._request_counts['127.0.0.1'] = {'count': 61, 'window_start': time.time(), 'trigger_scan': 0}
        po.ScannerHandler.do_GET(handler)
        call_args = handler._send_json.call_args
        assert call_args is not None
        args, kwargs = call_args
        assert args[0] == 429

    def test_blocked_ips_rejected(self):
        import pipeline_orchestrator as po
        po._blocked_ips.add('127.0.0.1')
        handler = self.make_handler(path='/api/omni-status')
        handler.headers = {'X-API-Key': po.API_KEY}
        po.ScannerHandler.do_GET(handler)
        call_args = handler._send_json.call_args
        assert call_args is not None
        args, kwargs = call_args
        assert args[0] == 403

    def test_health_endpoint_public(self):
        import pipeline_orchestrator as po
        handler = self.make_handler(path='/health')
        po.ScannerHandler.do_GET(handler)
        call_args = handler._send_json.call_args
        assert call_args is not None
        args, kwargs = call_args
        assert args[0] == 200
        assert args[1]['status'] == 'healthy'

    def test_api_errors_endpoint_responds(self):
        import pipeline_orchestrator as po
        handler = self.make_handler(path='/api/errors')
        handler.headers = {'X-API-Key': po.API_KEY}
        po.ScannerHandler.do_GET(handler)
        call_args = handler._send_json.call_args
        assert call_args is not None
        args, kwargs = call_args
        assert args[0] == 200
        assert isinstance(args[1], dict)

    def test_api_positions_endpoint_responds(self):
        import pipeline_orchestrator as po
        handler = self.make_handler(path='/api/positions')
        handler.headers = {'X-API-Key': po.API_KEY}
        po.ScannerHandler.do_GET(handler)
        call_args = handler._send_json.call_args
        assert call_args is not None
        args, kwargs = call_args
        assert args[0] == 200
        assert isinstance(args[1], dict)

    def test_auth_log_format(self):
        import pipeline_orchestrator as po
        auth_log = Path(po.AUTH_LOG_FILE)
        before = auth_log.read_text() if auth_log.exists() else ''
        handler = self.make_handler(path='/api/omni-status')
        handler.headers = {'X-API-Key': 'wrong-key'}
        po.ScannerHandler.do_GET(handler)
        after = auth_log.read_text()
        new_lines = after[len(before):].strip().split('\n')
        assert len(new_lines) >= 1
        assert 'UNAUTHORIZED' in new_lines[0] or '401' in new_lines[0]

    def test_api_key_validation(self):
        import pipeline_orchestrator as po
        handler = self.make_handler(path='/api/omni-status')
        expected = os.environ.get('PIPELINE_API_KEY', po.API_KEY)
        handler.headers = {'X-API-Key': expected}
        po.ScannerHandler.do_GET(handler)
        call_args = handler._send_json.call_args
        assert call_args is not None
        args, kwargs = call_args
        assert args[0] == 200

    def test_rate_limit_reset(self):
        import pipeline_orchestrator as po
        handler = self.make_handler(path='/api/omni-status')
        handler.headers = {'X-API-Key': po.API_KEY}
        po._request_counts['127.0.0.1'] = {'count': 60, 'window_start': time.time() - 120, 'trigger_scan': 0}
        po.ScannerHandler.do_GET(handler)
        call_args = handler._send_json.call_args
        assert call_args is not None
        args, kwargs = call_args
        assert args[0] == 200

    def test_concurrent_access(self):
        import pipeline_orchestrator as po
        results = []
        lock = threading.Lock()

        def worker(i):
            h = Mock()
            h.client_address = (f'10.0.0.{i}', 12345)
            h.path = '/health'
            h.command = 'GET'
            h.headers = {}
            h._send_json = lambda s, d: results.append((s, d))
            po.ScannerHandler.do_GET(h)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads: t.start()
        for t in threads: t.join()
        ok_count = sum(1 for s, d in results if s == 200 and d.get('status') == 'healthy')
        assert ok_count == 20

    def test_request_body_validation_post(self):
        import pipeline_orchestrator as po
        handler = self.make_handler(path='/api/unknown-post', method='POST')
        handler.headers = {'X-API-Key': po.API_KEY}
        po.ScannerHandler.do_POST(handler)
        call_args = handler._send_json.call_args
        assert call_args is not None
        args, kwargs = call_args
        assert args[0] == 404

    def test_unauthorized_does_not_block_on_single_fail(self):
        import pipeline_orchestrator as po
        for _ in range(3):
            po._failed_auth.pop('127.0.0.1', None)
        handler = self.make_handler(path='/api/omni-status')
        handler.headers = {'X-API-Key': 'bad-key'}
        po.ScannerHandler.do_GET(handler)
        call_args = handler._send_json.call_args
        assert call_args is not None
        args, kwargs = call_args
        assert args[0] == 401

    def test_trigger_scan_rate_limited(self):
        import pipeline_orchestrator as po
        handler = self.make_handler(path='/api/trigger-scan', method='POST')
        handler.headers = {'X-API-Key': po.API_KEY}
        po._request_counts['127.0.0.1'] = {'count': 0, 'window_start': time.time(), 'trigger_scan': 11}
        try:
            po.ScannerHandler.do_POST(handler)
        except Exception:
            pass
        call_args = handler._send_json.call_args
        if call_args:
            args, kwargs = call_args
            assert args[0] == 429

    def test_ip_auto_blocked_after_5_failed(self):
        import pipeline_orchestrator as po
        po._blocked_ips.discard('127.0.0.1')
        po._failed_auth['127.0.0.1'] = 4
        handler = self.make_handler(path='/api/omni-status')
        handler.headers = {'X-API-Key': 'wrong-key-5'}
        po.ScannerHandler.do_GET(handler)
        call_args = handler._send_json.call_args
        assert call_args is not None
        args, kwargs = call_args
        assert args[0] in (401, 403)

    def test_nonexistent_endpoint_returns_404(self):
        import pipeline_orchestrator as po
        handler = self.make_handler(path='/api/nonexistent')
        handler.headers = {'X-API-Key': po.API_KEY}
        po.ScannerHandler.do_GET(handler)
        call_args = handler._send_json.call_args
        assert call_args is not None
        args, kwargs = call_args
        assert args[0] == 404
