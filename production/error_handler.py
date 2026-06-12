"""Centralized Error Handler - OMNI BRAIN V2

Error rate tracking, alert throttling (max 1 alert/5min per error type),
and error dashboard endpoint.
"""
import time
import logging
import traceback
from typing import Dict, Any, Optional, List
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger('ErrorHandler')

LOG_DIR = Path(__file__).parent / 'logs'
ERROR_LOG_FILE = LOG_DIR / 'errors.json'
LOG_DIR.mkdir(exist_ok=True)

ALERT_THROTTLE_SECONDS = 300
MAX_STORED_ERRORS = 100


class ErrorHandler:
    def __init__(self):
        self._error_counts: Dict[str, int] = defaultdict(int)
        self._last_alert_time: Dict[str, float] = {}
        self._errors: List[Dict[str, Any]] = []
        self._load()

    def _load(self):
        try:
            if ERROR_LOG_FILE.exists():
                data = ERROR_LOG_FILE.read_text()
                if data.strip():
                    self._errors = __import__('json').loads(data)[-MAX_STORED_ERRORS:]
        except Exception:
            pass

    def _save(self):
        try:
            ERROR_LOG_FILE.write_text(__import__('json').dumps(self._errors[-MAX_STORED_ERRORS:], indent=2))
        except Exception:
            pass

    def record(self, module: str, operation: str, error: Exception, severity: str = 'ERROR',
               exc_info: bool = False, send_alert: bool = False) -> Dict[str, Any]:
        error_type = f"{module}.{operation}"
        now = time.time()

        self._error_counts[error_type] += 1

        entry = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'module': module,
            'operation': operation,
            'error_type': type(error).__name__,
            'error': str(error),
            'severity': severity,
            'count': self._error_counts[error_type],
        }
        if exc_info:
            entry['traceback'] = traceback.format_exc()

        self._errors.append(entry)
        self._save()

        should_alert = False
        if send_alert and severity in ('CRITICAL', 'ERROR'):
            last = self._last_alert_time.get(error_type, 0)
            if now - last >= ALERT_THROTTLE_SECONDS:
                should_alert = True
                self._last_alert_time[error_type] = now

        entry['alerted'] = should_alert
        return entry

    def get_recent(self, limit: int = 100) -> List[Dict[str, Any]]:
        return list(self._errors[-limit:])

    def get_counts(self) -> Dict[str, int]:
        return dict(self._error_counts)

    def get_dashboard(self) -> Dict[str, Any]:
        return {
            'total_errors': len(self._errors),
            'unique_types': len(self._error_counts),
            'recent': self._errors[-10:],
            'counts': dict(sorted(self._error_counts.items(), key=lambda x: -x[1])[:20]),
        }

    def clear(self):
        self._errors.clear()
        self._error_counts.clear()
        self._save()


_handler: Optional[ErrorHandler] = None


def get_error_handler() -> ErrorHandler:
    global _handler
    if _handler is None:
        _handler = ErrorHandler()
    return _handler


def safe_call(module: str, operation: str, func, *args, severity: str = 'ERROR',
              send_alert: bool = False, default=None, **kwargs):
    """Wrap a call with error handling."""
    try:
        return func(*args, **kwargs)
    except Exception as e:
        handler = get_error_handler()
        handler.record(module, operation, e, severity=severity, exc_info=True, send_alert=send_alert)
        log.error(f"[{module}] {operation} failed: {e}")
        return default
