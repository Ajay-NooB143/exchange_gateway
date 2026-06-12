"""
App Wiring — Composition Root (Layer 4)
========================================
The ONLY file allowed to instantiate concrete implementations
and wire them together. No file may ever import this module.

Usage:
    python app_wiring.py              # run forever
    python app_wiring.py --once       # single scan
    python app_wiring.py --test       # single scan (alias)
"""

import os
import sys
import signal
import time
import logging
import logging.handlers
import threading
import argparse
from pathlib import Path
from typing import Optional

# ── ensure project root is importable ──────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "production"))

# ── logging ────────────────────────────────────────────────────────────

LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


def _setup_logging():
    """Configure root logger with console + rotating file handlers."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    if root.handlers:
        return  # already configured

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s — %(message)s")

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    console.setLevel(logging.INFO)

    file_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "orchestrator.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
    )
    file_handler.setFormatter(fmt)
    file_handler.setLevel(logging.DEBUG)

    root.setLevel(logging.DEBUG)
    root.addHandler(console)
    root.addHandler(file_handler)


log = logging.getLogger("AppWiring")


# ══════════════════════════════════════════════════════════════════════════════
# WIRING — Build the dependency graph
# ══════════════════════════════════════════════════════════════════════════════
#
#   Layer 0:  AlertSender (Protocol)     ← implemented by TelegramSignalService
#   Layer 0:  PipelineProtocol (Protocol)← implemented by PipelineEngine
#   Layer 1:  LiveFeedScanner            ← consumes PipelineProtocol
#   Layer 2:  PipelineEngine             ← consumes AlertSender
#   Layer 3:  TelegramSignalService      ← implements AlertSender
#   Layer 4:  This file                  ← wires everything
#

def _create_alert_sender():
    """
    Instantiate the concrete Telegram alert sender (Layer 3).
    Returns None if the module is unavailable.
    """
    try:
        from production.telegram_signals import TelegramSignalService
        svc = TelegramSignalService()
        log.info("AlertSender (TelegramSignalService) created")
        return svc
    except Exception as exc:
        log.warning("TelegramSignalService unavailable: %s", exc)
        return None


def _create_pipeline(alert_sender):
    """
    Instantiate the pipeline engine (Layer 2), injecting the alert sender.
    """
    from pipeline_orchestrator import get_pipeline
    engine = get_pipeline(alert_sender=alert_sender)
    log.info("PipelineEngine created (alert_sender=%s)",
             type(alert_sender).__name__ if alert_sender else "None")
    return engine


def _create_scanner(pipeline):
    """
    Instantiate the live-feed scanner (Layer 1), injecting the pipeline.
    """
    from production.live_feed_scanner import LiveFeedScanner
    scanner = LiveFeedScanner(pipeline=pipeline)
    log.info("LiveFeedScanner created (mock=%s, pipeline=%s)",
             scanner.mock_mode, type(pipeline).__name__)
    return scanner


def _create_audit_agent():
    """
    Instantiate the auto-audit agent (Layer 2).
    Returns None if the module is unavailable.
    """
    try:
        from production.auto_audit_agent import get_auto_audit_agent
        agent = get_auto_audit_agent()
        log.info("AutoAuditAgent created")
        return agent
    except Exception as exc:
        log.warning("AutoAuditAgent unavailable: %s", exc)
        return None


def _create_exchange_gateway():
    """
    Instantiate the exchange gateway (Layer 2) — ccxt unified.
    Returns None if ccxt is unavailable.
    """
    try:
        from production.exchange_gateway import get_exchange_gateway
        gw = get_exchange_gateway()
        log.info("ExchangeGateway created (paper=%s, exchanges=%s)",
                 os.environ.get('PAPER_MODE', 'true').lower() != 'false',
                 gw.list_exchanges())
        return gw
    except Exception as exc:
        log.warning("ExchangeGateway unavailable: %s", exc)
        return None


def _create_ws_scanner():
    """
    Instantiate the async WebSocket scanner (Layer 1) — Binance/Bybit.
    Returns None if websockets is unavailable.
    """
    try:
        from production.async_ws_scanner import get_ws_scanner
        exchange = os.environ.get('WS_EXCHANGE', 'binance')
        scanner = get_ws_scanner(exchange=exchange)
        log.info("AsyncWSScanner created (exchange=%s)", exchange)
        return scanner
    except Exception as exc:
        log.warning("AsyncWSScanner unavailable: %s", exc)
        return None


# ══════════════════════════════════════════════════════════════════════════════
# CONTAINER — Lazy singleton wiring
# ══════════════════════════════════════════════════════════════════════════════

class Container:
    """
    Dependency injection container with lazy singletons.

    Build order (enforced):
        alert_sender → pipeline → scanner → audit_agent
        exchange_gateway → ws_scanner (independent, optional)
    """

    def __init__(self):
        self._alert_sender = None
        self._pipeline = None
        self._scanner = None
        self._audit_agent = None
        self._exchange_gateway = None
        self._ws_scanner = None
        self._lock = threading.Lock()

    @property
    def alert_sender(self):
        if self._alert_sender is None:
            with self._lock:
                if self._alert_sender is None:
                    self._alert_sender = _create_alert_sender()
        return self._alert_sender

    @property
    def pipeline(self):
        if self._pipeline is None:
            with self._lock:
                if self._pipeline is None:
                    self._pipeline = _create_pipeline(self.alert_sender)
        return self._pipeline

    @property
    def scanner(self):
        if self._scanner is None:
            with self._lock:
                if self._scanner is None:
                    self._scanner = _create_scanner(self.pipeline)
        return self._scanner

    @property
    def audit_agent(self):
        if self._audit_agent is None:
            with self._lock:
                if self._audit_agent is None:
                    self._audit_agent = _create_audit_agent()
        return self._audit_agent

    @property
    def exchange_gateway(self):
        if self._exchange_gateway is None:
            with self._lock:
                if self._exchange_gateway is None:
                    self._exchange_gateway = _create_exchange_gateway()
        return self._exchange_gateway

    @property
    def ws_scanner(self):
        if self._ws_scanner is None:
            with self._lock:
                if self._ws_scanner is None:
                    self._ws_scanner = _create_ws_scanner()
        return self._ws_scanner

    def reset(self):
        """Tear down all singletons. Safe to call multiple times."""
        with self._lock:
            self._alert_sender = None
            self._pipeline = None
            self._scanner = None
            self._audit_agent = None
            self._exchange_gateway = None
            self._ws_scanner = None
        log.debug("Container singletons reset")


# ── module-level singleton ─────────────────────────────────────────────

_container: Optional[Container] = None


def get_container() -> Container:
    """Return the global Container singleton (created on first call)."""
    global _container
    if _container is None:
        _container = Container()
    return _container


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINTS
# ══════════════════════════════════════════════════════════════════════════════

def start_bridge():
    """
    Main entry point — wires and starts the full OMNI BRAIN pipeline.

    Sequence:
        1. Initialize logging
        2. Create alert_sender (Layer 3 → Layer 0 contract)
        3. Create pipeline with alert_sender (Layer 2 → Layer 0 contract)
        4. Create scanner with pipeline (Layer 1 → Layer 0 contract)
        5. Create exchange gateway (Layer 2 — ccxt)
        6. Create WS scanner (Layer 1 — real-time feeds)
        7. Start scanner loop
    """
    _setup_logging()
    log.info("=" * 60)
    log.info("OMNI BRAIN V2 — COMPOSITION ROOT (Layer 4)")
    log.info("=" * 60)

    # 1. Alert sender (Layer 3 concrete → Layer 0 protocol)
    log.info("[1/6] Creating AlertSender …")
    alert_sender = get_container().alert_sender
    if alert_sender:
        log.info("[1/6] ✓ AlertSender ready (%s)", type(alert_sender).__name__)
    else:
        log.warning("[1/6] ⚠ AlertSender unavailable — alerts disabled")

    # 2. Pipeline (Layer 2 → Layer 0 contract)
    log.info("[2/6] Creating PipelineEngine …")
    pipeline = get_container().pipeline
    log.info("[2/6] ✓ PipelineEngine ready")

    # 3. Scanner (Layer 1 → Layer 0 contract)
    log.info("[3/6] Creating LiveFeedScanner …")
    scanner = get_container().scanner
    log.info("[3/6] ✓ LiveFeedScanner ready (mock=%s)", scanner.mock_mode)

    # 4. Exchange Gateway (Layer 2 — ccxt)
    log.info("[4/6] Creating ExchangeGateway …")
    exchange_gateway = get_container().exchange_gateway
    if exchange_gateway:
        log.info("[4/6] ✓ ExchangeGateway ready (exchanges=%s)", exchange_gateway.list_exchanges())
    else:
        log.warning("[4/6] ⚠ ExchangeGateway unavailable — no exchange execution")

    # 5. WS Scanner (Layer 1 — real-time feeds)
    log.info("[5/6] Creating AsyncWSScanner …")
    ws_scanner = get_container().ws_scanner
    if ws_scanner:
        log.info("[5/6] ✓ AsyncWSScanner ready (exchange=%s)", ws_scanner.exchange)
    else:
        log.warning("[5/6] ⚠ AsyncWSScanner unavailable — using REST polling only")

    # 6. Start scanner
    log.info("[6/6] Starting scanner …")
    scanner.start()
    log.info("=" * 60)
    log.info("OMNI BRAIN V2 — ORCHESTRATOR ONLINE")
    log.info("=" * 60)

    return scanner


# ── main loop with signal handling ─────────────────────────────────────

_shutdown_requested = False


def _handle_signal(signum, _frame):
    """Handle SIGTERM / SIGINT for clean PM2 shutdowns."""
    global _shutdown_requested
    name = signal.Signals(signum).name
    log.info("Received %s — initiating graceful shutdown", name)
    _shutdown_requested = True


def run_forever(interval: int = 60):
    """
    Main orchestrator loop.

    - Runs the scanner on *interval* second cadence.
    - Runs auto-audit in background every hour.
    - Handles SIGTERM/SIGINT for graceful PM2 stop/restart.
    """
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    scanner = start_bridge()

    # Start background audit thread
    audit_agent = get_container().audit_agent
    if audit_agent:
        def _audit_loop():
            while not _shutdown_requested:
                try:
                    time.sleep(3600)  # Run audit every hour
                    if not _shutdown_requested:
                        audit_agent.audit()
                except Exception as e:
                    log.error("Audit error: %s", e)
        audit_thread = threading.Thread(target=_audit_loop, daemon=True)
        audit_thread.start()
        log.info("Background audit thread started (interval=3600s)")

    log.info("Scan interval: %ds", interval)

    scan_count = 0
    while not _shutdown_requested:
        try:
            scan_count += 1
            log.info("── scan #%d ──", scan_count)
            results = scanner.run_scan()
            log.info(
                "Scan #%d complete: exec=%s wait=%s block=%s err=%s",
                scan_count,
                results["summary"]["executed"],
                results["summary"]["waited"],
                results["summary"]["blocked"],
                results["summary"]["errors"],
            )
        except Exception as exc:
            log.error("Scan cycle error: %s", exc, exc_info=True)

        # Sleep in small increments so SIGTERM is responsive
        waited = 0
        while waited < interval and not _shutdown_requested:
            time.sleep(min(1, interval - waited))
            waited += 1

    # ── graceful teardown ──────────────────────────────────────────────
    log.info("Shutting down orchestrator …")
    try:
        scanner.stop()
    except Exception:
        pass

    # Shutdown exchange gateway
    try:
        from production.exchange_gateway import shutdown_gateway
        shutdown_gateway()
    except Exception:
        pass

    # Shutdown WS scanner
    try:
        from production.async_ws_scanner import shutdown_ws_scanner
        shutdown_ws_scanner()
    except Exception:
        pass

    container = get_container()
    if container.alert_sender is not None:
        try:
            container.alert_sender.send_shutdown_message()
            container.alert_sender.stop()
        except Exception:
            pass

    log.info("Orchestrator stopped cleanly")


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

def main():
    """Entry point when run directly."""
    _setup_logging()

    parser = argparse.ArgumentParser(description="OMNI BRAIN Orchestrator")
    parser.add_argument("--once", action="store_true", help="Single scan then exit")
    parser.add_argument("--test", action="store_true", help="Single scan then exit")
    parser.add_argument("--interval", type=int, default=60, help="Scan interval in seconds")
    args = parser.parse_args()

    if args.once or args.test:
        scanner = start_bridge()
        results = scanner.run_scan()
        log.info(
            "Result: exec=%s wait=%s block=%s",
            results["summary"]["executed"],
            results["summary"]["waited"],
            results["summary"]["blocked"],
        )
        scanner.stop()
        return

    run_forever(interval=args.interval)


if __name__ == "__main__":
    main()
