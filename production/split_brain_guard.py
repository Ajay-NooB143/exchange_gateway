"""
Split-Brain Guard - Production-Grade Execution Lock
====================================================
Prevents double-execution in distributed trading systems.

Architecture:
┌─────────────────────────────────────────────────────────────────┐
│                    SPLIT-BRAIN GUARD                            │
├─────────────────────────────────────────────────────────────────┤
│  Process A (Master)         Process B (Passive)                │
│  ┌─────────────────┐       ┌─────────────────┐                │
│  │ acquire_lock()  │──────▶│ waitForMaster() │                │
│  │ → LOCK_ACQUIRED │       │ → BLOCKED       │                │
│  │ → EXECUTE       │       │ → MONITOR       │                │
│  └─────────────────┘       └─────────────────┘                │
│           │                         │                          │
│           ▼                         ▼                          │
│  ┌─────────────────┐       ┌─────────────────┐                │
│  │ release_lock()  │◀──────│ takeOver()      │                │
│  │ → LOCK_RELEASED │       │ → NEW_MASTER    │                │
│  └─────────────────┘       └─────────────────┘                │
└─────────────────────────────────────────────────────────────────┘

Features:
- Atomic file-based locking with O_CREAT|O_EXCL
- Process PID tracking for owner verification
- Automatic stale lock detection (30s timeout)
- Heartbeat monitoring for failover
- Graceful shutdown with lock release
"""

import fcntl
import json
import os
import time
import signal
import atexit
import logging
from pathlib import Path
from typing import Optional, Callable
from dataclasses import dataclass, asdict
from enum import Enum

log = logging.getLogger('SplitBrainGuard')


class NodeRole(Enum):
    MASTER = "MASTER"
    PASSIVE = "PASSIVE"
    ACQUIRING = "ACQUIRING"
    FAILED = "FAILED"


@dataclass
class GuardState:
    role: str
    pid: int
    hostname: str
    acquired_at: float
    last_heartbeat: float
    lock_owner_pid: Optional[int] = None
    failover_count: int = 0


class SplitBrainGuard:
    """
    Production-grade split-brain prevention using file-based locking.
    
    Usage:
        guard = SplitBrainGuard()
        
        if guard.acquire_lock():
            # This process is MASTER - safe to execute
            execute_trade()
        else:
            # This process is PASSIVE - monitor only
            monitor_market()
        
        # Always release on exit
        guard.release_lock()
    """
    
    def __init__(
        self,
        data_dir: str = "/opt/trading-bridge/data",
        lock_timeout_ms: int = 100,
        stale_timeout_s: float = 30.0,
        heartbeat_interval_s: float = 5.0
    ):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.lock_file = self.data_dir / "execution.lock"
        self.state_file = self.data_dir / "split_brain_state.json"
        self.heartbeat_file = self.data_dir / "heartbeat.json"
        
        self.lock_timeout_ms = lock_timeout_ms
        self.stale_timeout_s = stale_timeout_s
        self.heartbeat_interval_s = heartbeat_interval_s
        
        self._lock_fd: Optional[int] = None
        self._role = NodeRole.PASSIVE
        self._state = GuardState(
            role=NodeRole.PASSIVE.value,
            pid=os.getpid(),
            hostname=os.uname().nodename,
            acquired_at=0,
            last_heartbeat=0
        )
        self._heartbeat_running = False
        self._on_master_callback: Optional[Callable] = None
        self._on_failover_callback: Optional[Callable] = None
        
        # Register cleanup handlers
        atexit.register(self._cleanup)
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
    
    def acquire_lock(self) -> bool:
        """
        Attempt to acquire execution lock.
        
        Returns:
            True if lock acquired (this process is MASTER)
            False if lock held by another process (this process is PASSIVE)
        """
        self._role = NodeRole.ACQUIRING
        
        # Check for stale lock first
        if self._is_lock_stale():
            log.warning("Detected stale lock, attempting cleanup")
            self._cleanup_stale_lock()
        
        try:
            # Atomic lock creation
            self._lock_fd = os.open(
                str(self.lock_file),
                os.O_CREAT | os.O_EXCL | os.O_WRONLY
            )
            
            # Get exclusive lock (non-blocking)
            fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            
            # Write lock owner info
            owner_info = {
                "pid": os.getpid(),
                "hostname": os.uname().nodename,
                "acquired_at": time.time(),
                "ppid": os.getppid()
            }
            os.write(self._lock_fd, json.dumps(owner_info).encode())
            os.fsync(self._lock_fd)
            
            # Update state
            self._state = GuardState(
                role=NodeRole.MASTER.value,
                pid=os.getpid(),
                hostname=os.uname().nodename,
                acquired_at=time.time(),
                last_heartbeat=time.time(),
                lock_owner_pid=os.getpid()
            )
            self._write_state()
            
            self._role = NodeRole.MASTER
            log.info(f"Lock acquired - PID {os.getpid()} is MASTER")
            
            # Start heartbeat
            self._start_heartbeat()
            
            return True
            
        except FileExistsError:
            # Lock file exists - another process is master
            self._role = NodeRole.PASSIVE
            self._state.role = NodeRole.PASSIVE.value
            self._state.lock_owner_pid = self._get_lock_owner_pid()
            self._write_state()
            
            log.info(f"Lock held by PID {self._state.lock_owner_pid} - this process is PASSIVE")
            return False
            
        except BlockingIOError:
            # Another process is acquiring - wait and retry
            log.warning("Lock acquisition in progress by another process")
            self._role = NodeRole.PASSIVE
            return False
            
        except Exception as e:
            log.error(f"Failed to acquire lock: {e}")
            self._role = NodeRole.FAILED
            return False
    
    def release_lock(self):
        """Release the execution lock and update state."""
        if self._lock_fd is not None:
            try:
                fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
                os.close(self._lock_fd)
            except Exception as e:
                log.debug(f"Failed to release lock fd: {e}")
            self._lock_fd = None

        try:
            self.lock_file.unlink(missing_ok=True)
        except Exception as e:
            log.debug(f"Failed to unlink lock file: {e}")

        # Update state
        self._state.role = NodeRole.PASSIVE.value
        self._state.lock_owner_pid = None
        self._state.last_heartbeat = 0
        self._write_state()
        
        self._role = NodeRole.PASSIVE
        log.info("Lock released - this process is now PASSIVE")
    
    def is_master(self) -> bool:
        """Check if this process is currently the master."""
        if self._role != NodeRole.MASTER:
            return False
        
        # Verify lock is still held
        if not self.lock_file.exists():
            self._role = NodeRole.PASSIVE
            return False
        
        # Verify we still own the lock
        owner_pid = self._get_lock_owner_pid()
        if owner_pid != os.getpid():
            self._role = NodeRole.PASSIVE
            return False
        
        return True
    
    def wait_for_master(self, timeout_s: float = 60.0) -> bool:
        """
        Wait until this process becomes master (failover).
        
        Returns:
            True if became master within timeout
            False if timeout
        """
        start = time.time()
        
        while time.time() - start < timeout_s:
            if self.acquire_lock():
                return True
            time.sleep(1.0)
        
        return False
    
    def force_takeover(self) -> bool:
        """
        Force takeover by removing existing lock.
        USE WITH EXTREME CAUTION - can cause double execution.
        """
        log.warning("FORCE TAKEOVER INITIATED")
        
        # Read current owner
        owner_pid = self._get_lock_owner_pid()
        if owner_pid:
            log.warning(f"Killing existing master PID {owner_pid}")
            try:
                os.kill(owner_pid, signal.SIGTERM)
                time.sleep(0.5)  # Give time for cleanup
            except ProcessLookupError:
                pass  # Process already dead
            except PermissionError:
                log.error(f"No permission to kill PID {owner_pid}")
                return False
        
        # Cleanup and acquire
        self._cleanup_stale_lock()
        return self.acquire_lock()
    
    def get_status(self) -> dict:
        """Get current guard status."""
        return {
            "role": self._role.value,
            "pid": os.getpid(),
            "hostname": os.uname().nodename,
            "is_master": self.is_master(),
            "lock_owner_pid": self._state.lock_owner_pid,
            "acquired_at": self._state.acquired_at,
            "uptime_s": time.time() - self._state.acquired_at if self._state.acquired_at else 0,
            "failover_count": self._state.failover_count,
            "lock_file_exists": self.lock_file.exists()
        }
    
    def on_master(self, callback: Callable):
        """Register callback for when this process becomes master."""
        self._on_master_callback = callback
    
    def on_failover(self, callback: Callable):
        """Register callback for failover events."""
        self._on_failover_callback = callback
    
    # ─────────────────────────────────────────────────────────────────────
    # PRIVATE METHODS
    # ─────────────────────────────────────────────────────────────────────
    
    def _is_lock_stale(self) -> bool:
        """Check if existing lock is stale (no heartbeat)."""
        if not self.lock_file.exists():
            return False
        
        if not self.heartbeat_file.exists():
            try:
                lock_age = time.time() - self.lock_file.stat().st_mtime
                return lock_age > self.stale_timeout_s
            except Exception as e:
                log.debug(f"Failed to check lock age: {e}")
                return True

        try:
            with open(self.heartbeat_file, 'r') as f:
                heartbeat = json.load(f)
            last_heartbeat = heartbeat.get("timestamp", 0)
            return time.time() - last_heartbeat > self.stale_timeout_s
        except Exception as e:
            log.debug(f"Failed to read heartbeat: {e}")
            return True

    def _cleanup_stale_lock(self):
        """Remove stale lock files."""
        log.info("Cleaning up stale lock")
        try:
            self.lock_file.unlink(missing_ok=True)
            self.heartbeat_file.unlink(missing_ok=True)
        except Exception as e:
            log.debug(f"Failed to cleanup stale lock: {e}")

    def _get_lock_owner_pid(self) -> Optional[int]:
        """Get PID of current lock owner."""
        if not self.lock_file.exists():
            return None

        try:
            with open(self.lock_file, 'r') as f:
                owner = json.load(f)
            return owner.get("pid")
        except Exception as e:
            log.debug(f"Failed to get lock owner PID: {e}")
            return None
    
    def _write_state(self):
        """Write current state to file."""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(asdict(self._state), f, indent=2)
        except Exception as e:
            log.error(f"Failed to write state: {e}")
    
    def _start_heartbeat(self):
        """Start heartbeat thread for lock keepalive."""
        self._heartbeat_running = True
        
        def heartbeat_loop():
            while self._heartbeat_running and self._role == NodeRole.MASTER:
                try:
                    heartbeat = {
                        "pid": os.getpid(),
                        "hostname": os.uname().nodename,
                        "timestamp": time.time(),
                        "role": self._role.value
                    }
                    with open(self.heartbeat_file, 'w') as f:
                        json.dump(heartbeat, f)
                    
                    self._state.last_heartbeat = time.time()
                    self._write_state()
                except Exception as e:
                    log.debug(f"Heartbeat write failed: {e}")

                time.sleep(self.heartbeat_interval_s)
        
        import threading
        thread = threading.Thread(target=heartbeat_loop, daemon=True)
        thread.start()
    
    def _cleanup(self):
        """Cleanup on exit."""
        self._heartbeat_running = False
        if self._role == NodeRole.MASTER:
            self.release_lock()
    
    def _signal_handler(self, signum, frame):
        """Handle signals for graceful shutdown."""
        log.info(f"Received signal {signum}")
        self._cleanup()
        raise SystemExit(0)


# ══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

_global_guard: Optional[SplitBrainGuard] = None


def get_guard(**kwargs) -> SplitBrainGuard:
    """Get or create global split-brain guard instance."""
    global _global_guard
    if _global_guard is None:
        _global_guard = SplitBrainGuard(**kwargs)
    return _global_guard


def is_safe_to_execute() -> bool:
    """Quick check if this process is safe to execute trades."""
    guard = get_guard()
    return guard.is_master()


def acquire_execution_lock() -> bool:
    """Acquire execution lock."""
    guard = get_guard()
    return guard.acquire_lock()


def release_execution_lock():
    """Release execution lock."""
    guard = get_guard()
    guard.release_lock()


# ══════════════════════════════════════════════════════════════════════════════
# TEST / DEMO
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 60)
    print("SPLIT-BRAIN GUARD TEST")
    print("=" * 60)
    
    guard = SplitBrainGuard(data_dir="/tmp/split_brain_test")
    
    print(f"\nTrying to acquire lock...")
    if guard.acquire_lock():
        print(f"✓ LOCK ACQUIRED - I am MASTER (PID {os.getpid()})")
        
        print(f"\nStatus: {guard.get_status()}")
        
        print(f"\nSimulating work for 3 seconds...")
        time.sleep(3)
        
        print(f"\nReleasing lock...")
        guard.release_lock()
        print(f"✓ LOCK RELEASED")
    else:
        print(f"✗ LOCK NOT ACQUIRED - I am PASSIVE")
        print(f"Status: {guard.get_status()}")
    
    print(f"\nFinal status: {guard.get_status()}")
    print("=" * 60)
