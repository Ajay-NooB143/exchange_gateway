"""
Memory Profiler Integration Test
=================================
Tests memory usage of critical components:
1. Smart Money Matrix (OrderBlockDetector, FairValueGapMapper, LiquiditySweepDetector)
2. HFT Liquidity Chase Engine
3. Split-Brain Guard
4. Pipeline Orchestrator

Usage:
    python -m memory_profiler memory_integration_test.py
    # or
    python memory_integration_test.py
"""

import sys
import os
import time
import random
import tracemalloc

# Add parent directories to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '/home/userland/opencode-dev/Vibe-Trading/agent')


def print_separator(title: str):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def get_memory_usage() -> float:
    """Get current memory usage in MB"""
    current, peak = tracemalloc.get_traced_memory()
    return current / 1024 / 1024


# ══════════════════════════════════════════════════════════════════════════════
# TEST 1: SMART MONEY MATRIX
# ══════════════════════════════════════════════════════════════════════════════

def test_smart_money_matrix():
    """Test memory usage of Smart Money Matrix components"""
    print_separator("TEST 1: SMART MONEY MATRIX")
    
    from production.smart_money_matrix import (
        SmartMoneyMatrix, OrderBlockDetector, FairValueGapMapper,
        LiquiditySweepDetector, Candle, Direction
    )
    
    # Generate test data
    print("\nGenerating 10,000 test candles...")
    candles = []
    base_price = 2350.0
    
    for i in range(10000):
        price = base_price + random.uniform(-10, 10)
        candle = Candle(
            timestamp=time.time() - (10000 - i) * 60,
            open=price,
            high=price + random.uniform(0.5, 5),
            low=price - random.uniform(0.5, 5),
            close=price + random.uniform(-3, 3),
            volume=random.uniform(100, 2000)
        )
        candles.append(candle)
    
    mem_before = get_memory_usage()
    print(f"Memory before: {mem_before:.2f} MB")
    
    # Test OrderBlockDetector
    print("\n--- OrderBlockDetector ---")
    ob_detector = OrderBlockDetector(lookback=100, max_blocks=50)
    
    start = time.time()
    for i in range(0, len(candles), 50):
        batch = candles[i:i+50]
        blocks = ob_detector.scan(batch, i)
    ob_time = time.time() - start
    
    mem_after = get_memory_usage()
    print(f"Memory after: {mem_after:.2f} MB")
    print(f"Memory delta: {mem_after - mem_before:.2f} MB")
    print(f"Scan time: {ob_time:.3f}s")
    print(f"Blocks found: {len(ob_detector.blocks)}")
    print(f"Active blocks: {len(ob_detector.get_active_blocks())}")
    
    # Test FairValueGapMapper
    print("\n--- FairValueGapMapper ---")
    fvg_mapper = FairValueGapMapper(max_gaps=30)
    
    start = time.time()
    for i in range(0, len(candles), 50):
        batch = candles[i:i+50]
        gaps = fvg_mapper.scan(batch, i)
    fvg_time = time.time() - start
    
    mem_after = get_memory_usage()
    print(f"Memory after: {mem_after:.2f} MB")
    print(f"Memory delta: {mem_after - mem_before:.2f} MB")
    print(f"Scan time: {fvg_time:.3f}s")
    print(f"Gaps found: {len(fvg_mapper.gaps)}")
    print(f"Active gaps: {len(fvg_mapper.get_active_gaps())}")
    
    # Test LiquiditySweepDetector
    print("\n--- LiquiditySweepDetector ---")
    sweep_detector = LiquiditySweepDetector(max_levels=100)
    
    start = time.time()
    for i in range(0, len(candles), 50):
        batch = candles[i:i+50]
        sweeps = sweep_detector.scan(batch, i)
    sweep_time = time.time() - start
    
    mem_after = get_memory_usage()
    print(f"Memory after: {mem_after:.2f} MB")
    print(f"Memory delta: {mem_after - mem_before:.2f} MB")
    print(f"Scan time: {sweep_time:.3f}s")
    print(f"Sweeps found: {len(sweep_detector.sweep_events)}")
    print(f"Liquidity levels: {len(sweep_detector.liquidity_levels)}")
    
    # Test combined SmartMoneyMatrix
    print("\n--- SmartMoneyMatrix (Combined) ---")
    matrix = SmartMoneyMatrix()
    
    start = time.time()
    for i in range(0, len(candles), 50):
        batch = candles[i:i+50]
        results = matrix.scan(batch, i)
    matrix_time = time.time() - start
    
    mem_after = get_memory_usage()
    print(f"Memory after: {mem_after:.2f} MB")
    print(f"Memory delta: {mem_after - mem_before:.2f} MB")
    print(f"Total scan time: {matrix_time:.3f}s")
    print(f"Status: {matrix.get_status()}")
    
    return {
        'smart_money_matrix': {
            'memory_delta_mb': mem_after - mem_before,
            'scan_time_s': matrix_time,
            'blocks': len(ob_detector.blocks),
            'gaps': len(fvg_mapper.gaps),
            'sweeps': len(sweep_detector.sweep_events)
        }
    }


# ══════════════════════════════════════════════════════════════════════════════
# TEST 2: HFT LIQUIDITY CHASE ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def test_hft_engine():
    """Test memory usage of HFT Liquidity Chase Engine"""
    print_separator("TEST 2: HFT LIQUIDITY CHASE ENGINE")
    
    from hft_liquidity_chase.engine import (
        Config, OBICalculator, TapeReader, RiskManager,
        DOMSnapshot, DOMLevel, TapeEvent, Side
    )
    
    mem_before = get_memory_usage()
    print(f"\nMemory before: {mem_before:.2f} MB")
    
    config = Config()
    
    # Test OBICalculator
    print("\n--- OBICalculator ---")
    obi_calc = OBICalculator(config)
    
    start = time.time()
    for i in range(1000):
        # Generate random DOM
        bids = [DOMLevel(2350 - i*0.1, random.uniform(10, 100)) for i in range(20)]
        asks = [DOMLevel(2351 + i*0.1, random.uniform(10, 100)) for i in range(20)]
        dom = DOMSnapshot(bids=bids, asks=asks, timestamp=time.time())
        obi = obi_calc.calculate(dom)
    obi_time = time.time() - start
    
    mem_after = get_memory_usage()
    print(f"Memory after: {mem_after:.2f} MB")
    print(f"Memory delta: {mem_after - mem_before:.2f} MB")
    print(f"Calculation time: {obi_time:.3f}s")
    print(f"History size: {len(obi_calc.history)}")
    
    # Test TapeReader
    print("\n--- TapeReader ---")
    tape_reader = TapeReader(config)
    
    start = time.time()
    for i in range(10000):
        trade = {
            'price': 2350 + random.uniform(-2, 2),
            'size': random.uniform(1, 50),
            'side': random.choice(['BUY', 'SELL']),
            'timestamp': time.time(),
            'is_aggressive': random.random() < 0.3
        }
        tape_reader.ingest(trade)
    tape_time = time.time() - start
    
    mem_after = get_memory_usage()
    print(f"Memory after: {mem_after:.2f} MB")
    print(f"Memory delta: {mem_after - mem_before:.2f} MB")
    print(f"Ingest time: {tape_time:.3f}s")
    print(f"Tape size: {len(tape_reader.tape)}")
    print(f"Aggressive window: {len(tape_reader.aggressive_window)}")
    
    # Test RiskManager
    print("\n--- RiskManager ---")
    risk_manager = RiskManager(config)
    
    start = time.time()
    for i in range(100):
        pos = risk_manager.open_position(
            Side.LONG if random.random() > 0.5 else Side.SHORT,
            2350 + random.uniform(-5, 5),
            DOMSnapshot()
        )
        risk_manager.close_position(pos, 2350 + random.uniform(-10, 10), "TEST")
    risk_time = time.time() - start
    
    mem_after = get_memory_usage()
    print(f"Memory after: {mem_after:.2f} MB")
    print(f"Memory delta: {mem_after - mem_before:.2f} MB")
    print(f"Risk check time: {risk_time:.3f}s")
    print(f"Daily PnL: ${risk_manager.daily_pnl:.2f}")
    
    return {
        'hft_engine': {
            'memory_delta_mb': mem_after - mem_before,
            'obi_time_s': obi_time,
            'tape_time_s': tape_time,
            'risk_time_s': risk_time,
            'tape_size': len(tape_reader.tape)
        }
    }


# ══════════════════════════════════════════════════════════════════════════════
# TEST 3: SPLIT-BRAIN GUARD
# ══════════════════════════════════════════════════════════════════════════════

def test_split_brain_guard():
    """Test memory usage of Split-Brain Guard"""
    print_separator("TEST 3: SPLIT-BRAIN GUARD")
    
    from production.split_brain_guard import SplitBrainGuard
    
    mem_before = get_memory_usage()
    print(f"\nMemory before: {mem_before:.2f} MB")
    
    # Create guard
    guard = SplitBrainGuard(data_dir="/tmp/sb_test")
    
    # Test lock acquisition
    start = time.time()
    for i in range(100):
        if guard.acquire_lock():
            guard.release_lock()
    lock_time = time.time() - start
    
    mem_after = get_memory_usage()
    print(f"Memory after: {mem_after:.2f} MB")
    print(f"Memory delta: {mem_after - mem_before:.2f} MB")
    print(f"Lock cycle time: {lock_time:.3f}s")
    print(f"Status: {guard.get_status()}")
    
    # Cleanup
    guard.release_lock()
    
    return {
        'split_brain_guard': {
            'memory_delta_mb': mem_after - mem_before,
            'lock_cycle_time_s': lock_time
        }
    }


# ══════════════════════════════════════════════════════════════════════════════
# TEST 4: PIPELINE ORCHESTRATOR (Basic)
# ══════════════════════════════════════════════════════════════════════════════

def test_pipeline_orchestrator():
    """Test memory usage of Pipeline Orchestrator"""
    print_separator("TEST 4: PIPELINE ORCHESTRATOR")
    
    mem_before = get_memory_usage()
    print(f"\nMemory before: {mem_before:.2f} MB")
    
    # Import (without running)
    start = time.time()
    from opencode_dev.pipeline_orchestrator import AIGoldTerminal
    import_time = time.time() - start
    
    mem_after = get_memory_usage()
    print(f"Memory after import: {mem_after:.2f} MB")
    print(f"Import time: {import_time:.3f}s")
    
    # Create instance
    terminal = AIGoldTerminal()
    
    mem_after = get_memory_usage()
    print(f"Memory after instantiation: {mem_after:.2f} MB")
    print(f"Memory delta: {mem_after - mem_before:.2f} MB")
    
    return {
        'pipeline_orchestrator': {
            'memory_delta_mb': mem_after - mem_before,
            'import_time_s': import_time
        }
    }


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print_separator("MEMORY PROFILER INTEGRATION TEST")
    
    # Enable tracemalloc
    tracemalloc.start()
    
    results = {}
    
    try:
        # Run tests
        results.update(test_smart_money_matrix())
        results.update(test_hft_engine())
        results.update(test_split_brain_guard())
        results.update(test_pipeline_orchestrator())
        
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
    
    # Summary
    print_separator("TEST SUMMARY")
    
    total_memory = 0
    for module, data in results.items():
        if isinstance(data, dict) and 'memory_delta_mb' in data:
            delta = data['memory_delta_mb']
            total_memory += delta
            status = "✓ PASS" if delta < 10 else "⚠ HIGH"
            print(f"  {module}: {delta:.2f} MB {status}")
    
    print(f"\n  Total Memory Delta: {total_memory:.2f} MB")
    
    # Memory assessment
    if total_memory < 50:
        print("\n  ✓ MEMORY USAGE: EXCELLENT (< 50 MB)")
    elif total_memory < 100:
        print("\n  ✓ MEMORY USAGE: GOOD (< 100 MB)")
    elif total_memory < 200:
        print("\n  ⚠ MEMORY USAGE: ACCEPTABLE (< 200 MB)")
    else:
        print("\n  ✗ MEMORY USAGE: HIGH (> 200 MB) - OPTIMIZATION NEEDED")
    
    # Recommendations
    print_separator("RECOMMENDATIONS")
    
    for module, data in results.items():
        if isinstance(data, dict):
            if data.get('memory_delta_mb', 0) > 50:
                print(f"  - {module}: Consider reducing buffer sizes")
            if data.get('scan_time_s', 0) > 1:
                print(f"  - {module}: Scan time > 1s, optimize algorithms")
            if data.get('tape_size', 0) > 5000:
                print(f"  - {module}: Tape size > 5000, add cleanup")
    
    print("\n" + "=" * 70)
    print("  TEST COMPLETE")
    print("=" * 70)
    
    return results


if __name__ == "__main__":
    main()
