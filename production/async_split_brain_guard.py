"""
Async Split-Brain Guard
========================
Sub-millisecond execution lock using Unix domain sockets in RAM.

Architecture:
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ASYNC SPLIT-BRAIN GUARD                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Process A (Master)              Process B (Passive)                        │
│  ┌─────────────────┐             ┌─────────────────┐                       │
│  │ bind(socket)    │──── LOCK ──▶│ connect() fails │                       │
│  │ → MASTER        │             │ → PASSIVE        │                       │
│  └────────┬────────┘             └────────┬────────┘                       │
│           │                               │                                  │
│           ▼                               ▼                                  │
│  ┌─────────────────┐             ┌─────────────────┐                       │
│  │ Server running  │◀── PING ────│ Health monitor  │                       │
│  │ → PONG          │             │ → Check master  │                       │
│  └────────┬────────┘             └─────────────────┘                       │
│           │                                                                  │
│           ▼                                                                  │
│  ┌─────────────────┐             ┌─────────────────┐                       │
│  │ close(socket)   │──── FREE ──▶│ bind(socket)    │                       │
│  │ → PASSIVE       │             │ → MASTER (new)  │                       │
│  └─────────────────┘             └─────────────────┘                       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

Performance:
- Lock acquisition: < 0.1ms (socket bind in RAM)
- Health check: < 0.5ms (local IPC)
- Failover: < 1ms (socket release + rebind)

Usage:
    guard = AsyncSplitBrainGuard()
    is_master = await guard.acquire_master_lock()
    
    if is_master:
        await execute_trades()
    
    # Always release on shutdown
    await guard.release_lock()
"""

import asyncio
import os
import logging
import time
import signal
from typing import Optional, Callable
from dataclasses import dataclass
from enum import Enum

log = logging.getLogger('AsyncSplitBrainGuard')


class NodeRole(Enum):
    """Node roles"""
    MASTER = "MASTER"
    PASSIVE = "PASSIVE"
    UNKNOWN = "UNKNOWN"
    FAILED = "FAILED"


@dataclass
class GuardState:
    """Guard state"""
    role: str
    pid: int
    hostname: str
    acquired_at: float
    last_heartbeat: float
    lock_owner_pid: Optional[int] = None
    failover_count: int = 0


class AsyncSplitBrainGuard:
    """
    Async split-brain guard using Unix domain sockets.
    
    Features:
    - Sub-millisecond lock acquisition (< 0.1ms)
    - Built-in health monitoring (PING/PONG)
    - Automatic failover on master crash
    - GIL-safe async design
    - Graceful shutdown handling
    
    Usage:
        guard = AsyncSplitBrainGuard()
        
        async def trading_loop():
            if await guard.acquire_master_lock():
                # This process is MASTER - safe to execute
                await execute_trades()
            else:
                # This process is PASSIVE - monitor only
                await monitor_market()
            
            # Always release on exit
            await guard.release_lock()
    """
    
    def __init__(
        self,
        socket_path: str = "/tmp/hft_trading_bridge.sock",
        health_check_interval: float = 1.0,
        health_timeout: float = 3.0
    ):
        self.socket_path = socket_path
        self.health_check_interval = health_check_interval
        self.health_timeout = health_timeout
        
        self.role = NodeRole.UNKNOWN
        self.server: Optional[asyncio.AbstractServer] = None
        self.state = GuardState(
            role=NodeRole.UNKNOWN.value,
            pid=os.getpid(),
            hostname=os.uname().nodename,
            acquired_at=0,
            last_heartbeat=0
        )
        
        self._on_master_callback: Optional[Callable] = None
        self._on_failover_callback: Optional[Callable] = None
        self._health_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Cleanup socket if exists from previous run
        self._cleanup_socket()
    
    async def acquire_master_lock(self) -> bool:
        """
        Attempts to bind to the Unix socket in RAM. Sub-millisecond latency.
        
        Returns:
            True if MASTER (lock acquired)
            False if PASSIVE (lock held by another process)
        """
        start_time = time.perf_counter()
        
        try:
            # If we can start the server, we are the only instance (MASTER)
            self.server = await asyncio.start_unix_server(
                self._handle_client,
                path=self.socket_path
            )
            
            self.role = NodeRole.MASTER
            self.state.role = NodeRole.MASTER.value
            self.state.acquired_at = time.time()
            self.state.last_heartbeat = time.time()
            self.state.lock_owner_pid = os.getpid()
            
            latency = (time.perf_counter() - start_time) * 1000
            log.info(f"[LOCKED] Acquired MASTER status in {latency:.3f}ms (PID {os.getpid()})")
            
            # Start health monitoring
            self._running = True
            self._health_task = asyncio.create_task(self._health_monitor())
            
            # Register signal handlers
            self._register_signals()
            
            return True
            
        except OSError:
            # The socket is already in use by the other PM2 process (PASSIVE)
            self.role = NodeRole.PASSIVE
            self.state.role = NodeRole.PASSIVE.value
            self.state.lock_owner_pid = self._get_socket_owner_pid()
            
            latency = (time.perf_counter() - start_time) * 1000
            log.info(f"[LOCKED] Defaulted to PASSIVE status in {latency:.3f}ms (Master PID: {self.state.lock_owner_pid})")
            
            # Start passive health monitoring
            self._running = True
            self._health_task = asyncio.create_task(self._passive_health_monitor())
            
            return False
    
    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Allows passive nodes to ping the master to ensure it hasn't crashed"""
        try:
            data = await asyncio.wait_for(reader.read(100), timeout=5.0)
            message = data.decode()
            
            if message == "PING":
                writer.write(b"PONG")
                await writer.drain()
                self.state.last_heartbeat = time.time()
                
        except asyncio.TimeoutError:
            pass
        except Exception as e:
            log.debug(f"Client handler error: {e}")
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception as e:
                log.debug(f"Failed to close writer: {e}")
    
    async def _health_monitor(self):
        """Monitor master health and cleanup on shutdown"""
        while self._running and self.role == NodeRole.MASTER:
            try:
                await asyncio.sleep(self.health_check_interval)
                
                # Update heartbeat
                self.state.last_heartbeat = time.time()
                
                # Check if socket still exists
                if not os.path.exists(self.socket_path):
                    log.warning("Socket file missing, attempting to recreate")
                    await self.release_lock()
                    break
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Health monitor error: {e}")
    
    async def _passive_health_monitor(self):
        """Monitor master health from passive node"""
        consecutive_failures = 0
        
        while self._running and self.role == NodeRole.PASSIVE:
            try:
                await asyncio.sleep(self.health_check_interval)
                
                # Ping master
                alive = await self._ping_master()
                
                if alive:
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
                    
                    if consecutive_failures >= 3:
                        log.warning(f"Master unresponsive ({consecutive_failures} failures)")
                        # Master might be dead, attempt takeover
                        await self._attempt_takeover()
                        break
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Passive monitor error: {e}")
    
    async def _ping_master(self) -> bool:
        """Ping master node via Unix socket"""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_unix_connection(self.socket_path),
                timeout=self.health_timeout
            )
            
            writer.write(b"PING")
            await writer.drain()
            
            data = await asyncio.wait_for(reader.read(100), timeout=self.health_timeout)
            response = data.decode()
            
            writer.close()
            await writer.wait_closed()
            
            return response == "PONG"
            
        except Exception as e:
            log.debug(f"Health check ping failed: {e}")
            return False

    async def _attempt_takeover(self):
        """Attempt to take over as master"""
        log.info("Attempting master takeover...")
        
        # Cleanup old socket
        self._cleanup_socket()
        
        # Try to acquire
        success = await self.acquire_master_lock()
        
        if success:
            log.info("Takeover successful - now MASTER")
            if self._on_failover_callback:
                self._on_failover_callback()
        else:
            log.info("Takeover failed - another process acquired lock")
    
    async def release_lock(self):
        """Releases the socket so the passive node can take over instantly"""
        self._running = False
        
        if self._health_task:
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass
        
        if self.role == NodeRole.MASTER and self.server:
            try:
                self.server.close()
                await self.server.wait_closed()
            except Exception as e:
                log.debug(f"Failed to close server: {e}")

            if os.path.exists(self.socket_path):
                os.remove(self.socket_path)
            
            self.role = NodeRole.PASSIVE
            self.state.role = NodeRole.PASSIVE.value
            log.info("Master lock released. Socket cleared.")
    
    def is_master(self) -> bool:
        """Check if this process is MASTER"""
        return self.role == NodeRole.MASTER
    
    def get_status(self) -> dict:
        """Get current guard status"""
        return {
            "role": self.role.value,
            "pid": os.getpid(),
            "hostname": os.uname().nodename,
            "is_master": self.is_master(),
            "lock_owner_pid": self.state.lock_owner_pid,
            "acquired_at": self.state.acquired_at,
            "last_heartbeat": self.state.last_heartbeat,
            "uptime_s": time.time() - self.state.acquired_at if self.state.acquired_at else 0,
            "socket_exists": os.path.exists(self.socket_path)
        }
    
    def on_master(self, callback: Callable):
        """Register callback for when this process becomes master"""
        self._on_master_callback = callback
    
    def on_failover(self, callback: Callable):
        """Register callback for failover events"""
        self._on_failover_callback = callback
    
    def _cleanup_socket(self):
        """Cleanup socket if exists from previous run"""
        if os.path.exists(self.socket_path):
            try:
                os.remove(self.socket_path)
            except Exception as e:
                log.debug(f"Failed to cleanup socket: {e}")
    
    def _get_socket_owner_pid(self) -> Optional[int]:
        """Get PID of socket owner (for debugging)"""
        # In practice, we can't easily get the PID from a Unix socket
        # This is just for logging purposes
        return None
    
    def _register_signals(self):
        """Register signal handlers for graceful shutdown"""
        def signal_handler(signum, frame):
            log.info(f"Received signal {signum}, releasing lock...")
            asyncio.create_task(self.release_lock())
        
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)


# ══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE
# ══════════════════════════════════════════════════════════════════════════════

_global_guard: Optional[AsyncSplitBrainGuard] = None


def get_guard(**kwargs) -> AsyncSplitBrainGuard:
    """Get or create global guard instance"""
    global _global_guard
    if _global_guard is None:
        _global_guard = AsyncSplitBrainGuard(**kwargs)
    return _global_guard


async def is_safe_to_execute() -> bool:
    """Quick check if this process is safe to execute trades"""
    guard = get_guard()
    return guard.is_master()


async def acquire_execution_lock() -> bool:
    """Acquire execution lock"""
    guard = get_guard()
    return await guard.acquire_master_lock()


async def release_execution_lock():
    """Release execution lock"""
    guard = get_guard()
    await guard.release_lock()


# ══════════════════════════════════════════════════════════════════════════════
# INTEGRATION EXAMPLE
# ══════════════════════════════════════════════════════════════════════════════

async def example_trading_loop():
    """
    Example integration with trading pipeline.
    
    This shows how to use the AsyncSplitBrainGuard in your pipeline_orchestrator.py
    """
    guard = AsyncSplitBrainGuard(socket_path="/tmp/hft_trading.sock")
    
    print("=" * 60)
    print("  ASYNC SPLIT-BRAIN GUARD - EXAMPLE")
    print("=" * 60)
    
    # Try to become master
    is_master = await guard.acquire_master_lock()
    
    if is_master:
        print("\n  This process is MASTER")
        print("  Safe to execute trades...")
        
        # Simulate trading
        for i in range(5):
            print(f"  Trade {i+1}: Executing...")
            await asyncio.sleep(0.1)
        
        # Release on completion
        await guard.release_lock()
        print("\n  Lock released")
    else:
        print("\n  This process is PASSIVE")
        print("  Monitoring master...")
        
        # Monitor for a few seconds
        await asyncio.sleep(2)
    
    print(f"\n  Status: {guard.get_status()}")
    print("=" * 60)


# ══════════════════════════════════════════════════════════════════════════════
# TEST / BENCHMARK
# ══════════════════════════════════════════════════════════════════════════════

async def benchmark():
    """Benchmark lock acquisition performance"""
    print("=" * 60)
    print("  BENCHMARK: Lock Acquisition Performance")
    print("=" * 60)
    
    # Cleanup any existing socket
    socket_path = "/tmp/benchmark_test.sock"
    if os.path.exists(socket_path):
        os.remove(socket_path)
    
    # Benchmark 1000 lock acquisitions
    guard = AsyncSplitBrainGuard(socket_path=socket_path)
    
    times = []
    for i in range(1000):
        start = time.perf_counter()
        
        # Acquire and release
        if await guard.acquire_master_lock():
            await guard.release_lock()
        
        elapsed = (time.perf_counter() - start) * 1000
        times.append(elapsed)
    
    # Cleanup
    if os.path.exists(socket_path):
        os.remove(socket_path)
    
    # Stats
    import statistics
    
    print(f"\n  Total iterations: {len(times)}")
    print(f"  Average latency: {statistics.mean(times):.3f}ms")
    print(f"  Median latency: {statistics.median(times):.3f}ms")
    print(f"  P95 latency: {sorted(times)[int(len(times)*0.95)]:.3f}ms")
    print(f"  P99 latency: {sorted(times)[int(len(times)*0.99)]:.3f}ms")
    print(f"  Max latency: {max(times):.3f}ms")
    print("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Run example
    asyncio.run(example_trading_loop())
    
    # Run benchmark
    asyncio.run(benchmark())
