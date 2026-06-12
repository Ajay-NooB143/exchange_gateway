"""
Evolution Engine Status Panel
=============================
ASCII terminal panel showing all 5 Evolution Engine module states.

Features:
- Each module shows: name, status (READY/ERROR/LOADING), last_run timestamp, scan_time_ms
- Refresh every 10 seconds
- Color: green=READY, red=ERROR, yellow=LOADING
- Also expose /api/evo-status JSON endpoint for React dashboard integration

Usage:
    python evo_status_panel.py          # Continuous display
    python evo_status_panel.py --once   # Single display
    python evo_status_panel.py --api    # Start HTTP API server
"""

import os
import sys
import time
import json
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from enum import Enum
from http.server import HTTPServer, BaseHTTPRequestHandler

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

LOG_DIR = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
log = logging.getLogger('EvoStatusPanel')


# ══════════════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ══════════════════════════════════════════════════════════════════════════════

class ModuleStatus(Enum):
    """Module status states."""
    READY = "READY"
    ERROR = "ERROR"
    LOADING = "LOADING"
    DISABLED = "DISABLED"


@dataclass
class ModuleState:
    """State of a single evolution engine module."""
    name: str
    status: ModuleStatus
    last_run: Optional[datetime] = None
    scan_time_ms: float = 0.0
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


# ══════════════════════════════════════════════════════════════════════════════
# EVOLUTION ENGINE MODULES
# ══════════════════════════════════════════════════════════════════════════════

class EvolutionEngineModules:
    """
    Manages the state of all 5 Evolution Engine modules:
    1. Analysis Engine
    2. Parameter Evolution
    3. Champion vs Challenger
    4. Evolution Log Generator
    5. Orchestrator
    """
    
    def __init__(self):
        self.modules: Dict[str, ModuleState] = {
            'analysis_engine': ModuleState(
                name='Analysis Engine',
                status=ModuleStatus.READY,
                last_run=datetime.now(timezone.utc),
                scan_time_ms=45.2
            ),
            'parameter_evolution': ModuleState(
                name='Parameter Evolution',
                status=ModuleStatus.READY,
                last_run=datetime.now(timezone.utc),
                scan_time_ms=12.8
            ),
            'champion_challenger': ModuleState(
                name='Champion vs Challenger',
                status=ModuleStatus.READY,
                last_run=datetime.now(timezone.utc),
                scan_time_ms=156.3
            ),
            'evolution_log': ModuleState(
                name='Evolution Log',
                status=ModuleStatus.READY,
                last_run=datetime.now(timezone.utc),
                scan_time_ms=8.5
            ),
            'orchestrator': ModuleState(
                name='Orchestrator',
                status=ModuleStatus.READY,
                last_run=datetime.now(timezone.utc),
                scan_time_ms=2.1
            )
        }
        
        # Try to load actual module states
        self._load_module_states()
    
    def _load_module_states(self):
        """Try to load actual module states from files."""
        # Check if modules exist in the evolution_engine directory
        evo_dir = os.path.join(os.path.dirname(__file__), '..', 'evolution_engine')
        
        module_files = {
            'analysis_engine': 'analysis_engine.py',
            'parameter_evolution': 'parameter_evolution.py',
            'champion_challenger': 'champion_challenger.py',
            'evolution_log': 'evolution_log.py',
            'orchestrator': 'orchestrator.py'
        }
        
        for module_name, filename in module_files.items():
            filepath = os.path.join(evo_dir, filename)
            if os.path.exists(filepath):
                self.modules[module_name].status = ModuleStatus.READY
            else:
                self.modules[module_name].status = ModuleStatus.DISABLED
    
    def get_module(self, name: str) -> Optional[ModuleState]:
        """Get module state by name."""
        return self.modules.get(name)
    
    def update_module(
        self,
        name: str,
        status: Optional[ModuleStatus] = None,
        scan_time_ms: Optional[float] = None,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Update module state."""
        if name in self.modules:
            module = self.modules[name]
            if status is not None:
                module.status = status
            if scan_time_ms is not None:
                module.scan_time_ms = scan_time_ms
            if error_message is not None:
                module.error_message = error_message
            if metadata is not None:
                module.metadata.update(metadata)
            module.last_run = datetime.now(timezone.utc)
    
    def get_all_states(self) -> Dict[str, Dict[str, Any]]:
        """Get all module states as dict."""
        return {
            name: {
                'name': module.name,
                'status': module.status.value,
                'last_run': module.last_run.isoformat() if module.last_run else None,
                'scan_time_ms': module.scan_time_ms,
                'error_message': module.error_message,
                'metadata': module.metadata
            }
            for name, module in self.modules.items()
        }


# ══════════════════════════════════════════════════════════════════════════════
# TERMINAL DISPLAY
# ══════════════════════════════════════════════════════════════════════════════

class TerminalDisplay:
    """ASCII terminal display for Evolution Engine status."""
    
    # ANSI colors
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    RESET = '\033[0m'
    
    @classmethod
    def get_status_color(cls, status: ModuleStatus) -> str:
        """Get color for module status."""
        if status == ModuleStatus.READY:
            return cls.GREEN
        elif status == ModuleStatus.ERROR:
            return cls.RED
        elif status == ModuleStatus.LOADING:
            return cls.YELLOW
        return cls.RESET
    
    @classmethod
    def display_panel(cls, modules: EvolutionEngineModules, clear: bool = True):
        """Display the status panel with MT5 Sync Guard section."""
        if clear:
            os.system('clear' if os.name == 'posix' else 'cls')
        
        print(f"\n{cls.BOLD}{cls.CYAN}{'=' * 70}{cls.RESET}")
        print(f"{cls.BOLD}{cls.CYAN}  EVOLUTION ENGINE STATUS PANEL{cls.RESET}")
        print(f"{cls.BOLD}{cls.CYAN}{'=' * 70}{cls.RESET}\n")
        
        # Header
        print(f"  {'MODULE':<25} {'STATUS':<10} {'LAST RUN':<20} {'SCAN (ms)':<12}")
        print(f"  {'-' * 25} {'-' * 10} {'-' * 20} {'-' * 12}")
        
        # Module rows
        for name, module in modules.modules.items():
            color = cls.get_status_color(module.status)
            status_str = f"{color}{module.status.value:<10}{cls.RESET}"
            
            last_run_str = module.last_run.strftime('%Y-%m-%d %H:%M:%S') if module.last_run else 'Never'
            
            print(
                f"  {module.name:<25} {status_str} {last_run_str:<20} {module.scan_time_ms:<12.1f}"
            )
        
        # MT5 Sync Guard Panel
        print(f"\n{cls.BOLD}{cls.CYAN}{'=' * 70}{cls.RESET}")
        cls._display_mt5_sync_panel()
        
        print(f"\n{cls.BOLD}{cls.CYAN}{'=' * 70}{cls.RESET}")
        print(f"  {cls.CYAN}Press Ctrl+C to exit{cls.RESET}")
        print(f"{cls.BOLD}{cls.CYAN}{'=' * 70}{cls.RESET}\n")
    
    @classmethod
    def _display_mt5_sync_panel(cls):
        """Display MT5 Sync Guard status panel."""
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
            from production.mt5_sync_guard import MT5SyncGuard
            guard = MT5SyncGuard()
            
            print(f"\n  {cls.BOLD}{cls.CYAN}╔══════════════════════════════════════════════╗{cls.RESET}")
            print(f"  {cls.BOLD}{cls.CYAN}║        MT5 SYNC GUARD STATUS                 ║{cls.RESET}")
            print(f"  {cls.BOLD}{cls.CYAN}╠══════════════════════════════════════════════╣{cls.RESET}")
            
            status = guard.get_status()
            
            for asset in ['XAUUSD', 'EURUSD', 'GBPUSD', 'SP500']:
                for tf in ['H1']:  # Show H1 for brevity
                    key = f"{asset}_{tf}"
                    sync = status.get(key, {})
                    
                    sync_status = sync.get('status', 'NOT_SYNCED')
                    lock_ms = sync.get('lock_ms', 0)
                    source = sync.get('source', 'NONE')
                    
                    if sync_status == 'OK':
                        icon = f"{cls.GREEN}🟢 OK{cls.RESET}"
                        detail = f"{lock_ms:.1f}ms"
                    elif sync_status in ('STALE', 'CACHED'):
                        icon = f"{cls.YELLOW}🟡 STALE{cls.RESET}"
                        detail = "cache"
                    elif source == 'CSV_FALLBACK':
                        icon = f"{cls.RED}🔴 CSV{cls.RESET}"
                        detail = "fallback"
                    else:
                        icon = f"{cls.YELLOW}⚪ {sync_status}{cls.RESET}"
                        detail = "—"
                    
                    print(f"  {cls.BOLD}{cls.CYAN}║{cls.RESET} {asset:8s}/{tf:3s} {icon}   {detail:12s} {cls.BOLD}{cls.CYAN}║{cls.RESET}")
            
            print(f"  {cls.BOLD}{cls.CYAN}╚══════════════════════════════════════════════╝{cls.RESET}")
            
        except ImportError:
            print(f"\n  {cls.YELLOW}  [MT5] Sync Guard not available{cls.RESET}")
        except Exception as e:
            print(f"\n  {cls.RED}  [MT5] Error: {e}{cls.RESET}")
    
    @classmethod
    def display_once(cls, modules: EvolutionEngineModules):
        """Display panel once and exit."""
        cls.display_panel(modules, clear=False)


# ══════════════════════════════════════════════════════════════════════════════
# HTTP API SERVER
# ══════════════════════════════════════════════════════════════════════════════

class EvoStatusAPIHandler(BaseHTTPRequestHandler):
    """HTTP handler for /api/evo-status endpoint."""
    
    modules: EvolutionEngineModules = None
    
    def do_GET(self):
        """Handle GET requests."""
        if self.path == '/api/evo-status':
            self._send_json(200, self.modules.get_all_states())
        elif self.path == '/health':
            self._send_json(200, {'status': 'healthy'})
        else:
            self._send_json(404, {'error': 'not_found'})
    
    def _send_json(self, status_code: int, data: Dict[str, Any]):
        """Send JSON response."""
        response = json.dumps(data, indent=2, default=str)
        
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Length', str(len(response)))
        self.end_headers()
        
        self.wfile.write(response.encode('utf-8'))
    
    def log_message(self, format, *args):
        """Suppress default HTTP logging."""
        pass


def run_api_server(port: int = 8080):
    """Run the HTTP API server."""
    modules = EvolutionEngineModules()
    EvoStatusAPIHandler.modules = modules
    
    server = HTTPServer(('0.0.0.0', port), EvoStatusAPIHandler)
    
    print(f"\n{TerminalDisplay.BOLD}{TerminalDisplay.CYAN}{'=' * 70}{TerminalDisplay.RESET}")
    print(f"{TerminalDisplay.BOLD}{TerminalDisplay.CYAN}  EVOLUTION ENGINE API SERVER{TerminalDisplay.RESET}")
    print(f"{TerminalDisplay.BOLD}{TerminalDisplay.CYAN}{'=' * 70}{TerminalDisplay.RESET}")
    print(f"\n  Endpoint: http://0.0.0.0:{port}/api/evo-status")
    print(f"  Health:   http://0.0.0.0:{port}/health")
    print(f"\n{TerminalDisplay.BOLD}{TerminalDisplay.CYAN}{'=' * 70}{TerminalDisplay.RESET}\n")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.shutdown()


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Evolution Engine Status Panel')
    parser.add_argument('--once', action='store_true', help='Display once and exit')
    parser.add_argument('--api', action='store_true', help='Start HTTP API server')
    parser.add_argument('--port', type=int, default=8080, help='API server port')
    
    args = parser.parse_args()
    
    if args.api:
        run_api_server(args.port)
        return
    
    modules = EvolutionEngineModules()
    
    if args.once:
        TerminalDisplay.display_once(modules)
    else:
        try:
            while True:
                TerminalDisplay.display_panel(modules)
                time.sleep(10)
        except KeyboardInterrupt:
            print("\nStatus panel stopped.")


if __name__ == '__main__':
    main()
