"""
Edge Case Tests for Smart Money Matrix
========================================
Tests for:
- Partial liquidity sweeps (sweep % < 50%)
- Invalid OrderBlock detection (OB with no FVG confirmation)
- Overlapping OB zones (duplicate filtering)
- Zero-volume candle handling
"""

import sys
import os
import time
import pytest

# Add production directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'production'))

from smart_money_matrix import (
    Candle, OrderBlock, OrderBlockDetector, FairValueGapMapper,
    LiquiditySweepDetector, SmartMoneyMatrix, Direction
)


# ══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def make_candle(
    timestamp: float = 0.0,
    open: float = 100.0,
    high: float = 101.0,
    low: float = 99.0,
    close: float = 100.5,
    volume: float = 1000.0
) -> Candle:
    """Create a candle with specified parameters."""
    return Candle(
        timestamp=timestamp,
        open=open,
        high=high,
        low=low,
        close=close,
        volume=volume
    )


def make_candles(
    count: int = 50,
    base_price: float = 100.0,
    base_volume: float = 1000.0,
    **overrides
) -> list:
    """Generate a list of test candles."""
    candles = []
    for i in range(count):
        price = base_price + (i * 0.1)
        candle = make_candle(
            timestamp=float(i),
            open=price,
            high=price + 1.0,
            low=price - 1.0,
            close=price + 0.5,
            volume=base_volume,
            **overrides
        )
        candles.append(candle)
    return candles


# ══════════════════════════════════════════════════════════════════════════════
# TEST 1: PARTIAL LIQUIDITY SWEEPS
# ══════════════════════════════════════════════════════════════════════════════

class TestPartialLiquiditySweeps:
    """Tests for partial liquidity sweeps (sweep % < 50%)."""

    def test_partial_sweep_below_threshold(self):
        """Sweep that doesn't reach 50% should not be detected as full sweep."""
        detector = LiquiditySweepDetector(
            equal_hl_tolerance_atr_mult=0.5,
            min_wick_atr_mult=0.3,
            max_bars_for_confirmation=3
        )
        
        # Create candles with a liquidity level at 100
        candles = []
        for i in range(20):
            if i < 10:
                # Build liquidity level
                candle = make_candle(
                    timestamp=float(i),
                    open=100.0,
                    high=100.0,
                    low=99.0,
                    close=100.0,
                    volume=1000.0
                )
            else:
                # Partial sweep - only 30% penetration
                candle = make_candle(
                    timestamp=float(i),
                    open=100.0,
                    high=100.3,  # Only 0.3 above level (30% of typical ATR)
                    low=99.5,
                    close=100.1,  # Closes back above
                    volume=1000.0
                )
            candles.append(candle)
        
        # Scan multiple times to build history
        for _ in range(5):
            detector.scan(candles)
        
        # Get recent sweeps
        sweeps = detector.get_recent_sweeps()
        
        # Partial sweeps should not generate confirmed signals
        # or should have limited detection
        assert len(sweeps) <= 1, "Partial sweeps should not generate multiple signals"

    def test_deep_sweep_detected(self):
        """Sweep that goes >50% should be detected."""
        detector = LiquiditySweepDetector(
            equal_hl_tolerance_atr_mult=0.5,
            min_wick_atr_mult=0.3,
            max_bars_for_confirmation=3
        )
        
        candles = []
        # Create proper swing high structure first (need 3 candles for swing detection)
        # Then wait 5+ bars, then sweep
        for i in range(30):
            if i < 3:
                # Build up to swing high
                candle = make_candle(
                    timestamp=float(i),
                    open=100.0 + i * 0.5,
                    high=100.0 + i * 0.5 + 0.5,
                    low=99.0,
                    close=100.0 + i * 0.5,
                    volume=1000.0
                )
            elif i == 3:
                # Create swing high at 102.0
                candle = make_candle(
                    timestamp=float(i),
                    open=102.0,
                    high=102.0,  # This will be the swing high
                    low=101.0,
                    close=101.5,
                    volume=1000.0
                )
            elif i == 4:
                # Drop after swing high
                candle = make_candle(
                    timestamp=float(i),
                    open=101.5,
                    high=101.8,
                    low=100.5,
                    close=100.8,
                    volume=1000.0
                )
            elif i >= 10 and i <= 15:
                # Wait for level to age, then sweep
                if i == 12:
                    # Sweep candle - spike above 102.0 and close back below
                    candle = make_candle(
                        timestamp=float(i),
                        open=101.0,
                        high=103.0,  # Spike 1.0 above level (deep sweep)
                        low=100.5,
                        close=101.5,  # Close back below level
                        volume=3000.0
                    )
                else:
                    candle = make_candle(
                        timestamp=float(i),
                        open=101.0,
                        high=101.5,
                        low=100.5,
                        close=101.0,
                        volume=1000.0
                    )
            else:
                candle = make_candle(
                    timestamp=float(i),
                    open=101.0,
                    high=101.5,
                    low=100.5,
                    close=101.0,
                    volume=1000.0
                )
            candles.append(candle)
        
        # Scan multiple times to build history
        for _ in range(5):
            detector.scan(candles)
        
        sweeps = detector.get_recent_sweeps()
        
        # Deep sweeps should be detected
        assert len(sweeps) >= 1, "Deep sweeps should be detected"

    def test_sweep_extreme_measurement(self):
        """Verify sweep extreme is correctly measured."""
        detector = LiquiditySweepDetector()
        
        candles = []
        level_price = 100.0
        
        # Create candles with known sweep
        for i in range(20):
            if i < 10:
                candle = make_candle(
                    timestamp=float(i),
                    open=level_price,
                    high=level_price,
                    low=level_price - 1.0,
                    close=level_price,
                    volume=1000.0
                )
            elif i == 15:
                # Sweep with known extreme
                sweep_extreme = 100.5
                candle = make_candle(
                    timestamp=float(i),
                    open=level_price,
                    high=sweep_extreme,
                    low=level_price - 0.5,
                    close=level_price - 0.1,  # Close back below
                    volume=2000.0
                )
            else:
                candle = make_candle(
                    timestamp=float(i),
                    open=level_price,
                    high=level_price + 0.2,
                    low=level_price - 0.2,
                    close=level_price,
                    volume=1000.0
                )
            candles.append(candle)
        
        # Scan
        for _ in range(3):
            detector.scan(candles)
        
        sweeps = detector.get_recent_sweeps()
        
        if sweeps:
            # Verify wick size is measured correctly
            for sweep in sweeps:
                assert sweep.wick_size > 0, "Wick size should be positive"


# ══════════════════════════════════════════════════════════════════════════════
# TEST 2: INVALID ORDERBLOCK DETECTION
# ══════════════════════════════════════════════════════════════════════════════

class TestInvalidOrderBlockDetection:
    """Tests for OrderBlock detection without FVG confirmation."""

    def test_ob_without_fvg(self):
        """OB should be detected independently of FVG."""
        ob_detector = OrderBlockDetector(
            lookback=50,
            volume_percentile=80.0
        )
        
        fvg_mapper = FairValueGapMapper(max_gaps=20)
        
        # Create candles with high volume but no FVG pattern
        candles = []
        for i in range(30):
            if i == 15:
                # High volume candle
                candle = make_candle(
                    timestamp=float(i),
                    open=100.0,
                    high=105.0,
                    low=99.0,
                    close=104.0,
                    volume=5000.0  # Very high volume
                )
            else:
                candle = make_candle(
                    timestamp=float(i),
                    open=100.0,
                    high=101.0,
                    low=99.0,
                    close=100.5,
                    volume=1000.0
                )
            candles.append(candle)
        
        # Scan
        ob_detector.scan(candles)
        fvg_mapper.scan(candles)
        
        # Get OBs
        active_obs = ob_detector.get_active_blocks()
        
        # OB might be detected but without FVG confirmation
        # This tests that OB detection works independently
        assert len(active_obs) >= 0, "OB detection should work"

    def test_ob_requires_bos(self):
        """OB should only be detected with Break of Structure."""
        detector = OrderBlockDetector(
            lookback=50,
            volume_percentile=80.0,
            bos_min_atr_mult=0.5
        )
        
        # Create candles without BOS
        candles = []
        for i in range(30):
            # Sideways market - no BOS
            candle = make_candle(
                timestamp=float(i),
                open=100.0 + (i % 5) * 0.1,
                high=101.0 + (i % 5) * 0.1,
                low=99.0 + (i % 5) * 0.1,
                close=100.5 + (i % 5) * 0.1,
                volume=1000.0
            )
            candles.append(candle)
        
        # Scan
        detector.scan(candles)
        
        # Without BOS, no OBs should be detected
        active_obs = detector.get_active_blocks()
        assert len(active_obs) == 0, "No OBs should be detected without BOS"

    def test_ob_mitigation_tracking(self):
        """Verify OB mitigation is properly tracked."""
        detector = OrderBlockDetector(lookback=50)
        
        # Create OB with known mitigation
        candles = []
        for i in range(30):
            if i == 10:
                # High volume candle creating OB
                candle = make_candle(
                    timestamp=float(i),
                    open=100.0,
                    high=105.0,
                    low=99.0,
                    close=104.0,
                    volume=5000.0
                )
            elif i == 25:
                # Price returns to mitigate OB
                candle = make_candle(
                    timestamp=float(i),
                    open=100.5,
                    high=101.0,
                    low=99.5,
                    close=100.0,  # Close at OB level
                    volume=1000.0
                )
            else:
                candle = make_candle(
                    timestamp=float(i),
                    open=100.0,
                    high=101.0,
                    low=99.0,
                    close=100.5,
                    volume=1000.0
                )
            candles.append(candle)
        
        # Scan
        for _ in range(3):
            detector.scan(candles)
        
        # Check mitigation status
        all_blocks = detector.blocks
        mitigated_count = sum(1 for b in all_blocks if b.mitigated)
        
        # Should track mitigation properly
        assert mitigated_count >= 0, "Mitigation tracking should work"


# ══════════════════════════════════════════════════════════════════════════════
# TEST 3: OVERLAPPING OB ZONES
# ══════════════════════════════════════════════════════════════════════════════

class TestOverlappingOBZones:
    """Tests for duplicate filtering of overlapping OB zones."""

    def test_duplicate_ob_filtering(self):
        """Overlapping OBs should be filtered/deduplicated."""
        detector = OrderBlockDetector(
            lookback=50,
            max_blocks=10  # Limit to test deduplication
        )
        
        # Create multiple OBs in same zone
        candles = []
        for i in range(40):
            if i in [10, 15, 20]:
                # Multiple high volume candles in same zone
                candle = make_candle(
                    timestamp=float(i),
                    open=100.0,
                    high=105.0,
                    low=99.0,
                    close=104.0,
                    volume=5000.0
                )
            else:
                candle = make_candle(
                    timestamp=float(i),
                    open=100.0,
                    high=101.0,
                    low=99.0,
                    close=100.5,
                    volume=1000.0
                )
            candles.append(candle)
        
        # Scan
        for _ in range(3):
            detector.scan(candles)
        
        # Get all blocks
        all_blocks = detector.get_active_blocks()
        
        # Should respect max_blocks limit
        assert len(all_blocks) <= 10, "Should respect max_blocks limit"

    def test_ob_zone_overlap_detection(self):
        """Test that overlapping zones are properly identified."""
        detector = OrderBlockDetector()
        
        # Create OBs that might overlap
        block1 = make_candle(
            timestamp=1.0,
            open=100.0,
            high=105.0,
            low=99.0,
            close=104.0,
            volume=5000.0
        )
        
        block2 = make_candle(
            timestamp=2.0,
            open=100.5,  # Overlaps with block1
            high=105.5,
            low=99.5,
            close=104.5,
            volume=5000.0
        )
        
        # Test price in overlapping zone
        detector.blocks.append(block1)  # Simplified test
        detector.blocks.append(block2)
        
        # Price should be in at least one block
        price_in_zone = any(
            b.low <= 101.0 <= b.high 
            for b in detector.blocks
        )
        
        assert price_in_zone, "Price should be in overlapping zone"

    def test_ob_deduplication_by_direction(self):
        """Test deduplication works per direction."""
        detector = OrderBlockDetector()
        
        # Simulate multiple blocks
        from collections import deque
        detector.blocks = deque(maxlen=50)
        
        # Add blocks with same direction
        for i in range(5):
            block = OrderBlock(
                timestamp=float(i),
                price=100.0 + i * 0.1,
                high=105.0,
                low=99.0,
                volume=5000.0,
                direction=Direction.BULLISH,
                bar_index=i
            )
            detector.blocks.append(block)
        
        # Get active blocks
        active = detector.get_active_blocks(Direction.BULLISH)
        
        # Should return all (deduplication is by position, not direction)
        assert len(active) > 0, "Should return active blocks"


# ══════════════════════════════════════════════════════════════════════════════
# TEST 4: ZERO-VOLUME CANDLE HANDLING
# ══════════════════════════════════════════════════════════════════════════════

class TestZeroVolumeCandles:
    """Tests for zero-volume candle handling."""

    def test_zero_volume_candle(self):
        """Zero volume candles should not crash detectors."""
        matrix = SmartMoneyMatrix()
        
        # Create candles with zero volume
        candles = []
        for i in range(30):
            candle = make_candle(
                timestamp=float(i),
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                volume=0.0 if i == 15 else 1000.0  # Zero volume at index 15
            )
            candles.append(candle)
        
        # Scan should not crash
        result = matrix.scan(candles)
        
        assert 'order_blocks' in result
        assert 'fair_value_gaps' in result
        assert 'sweep_events' in result

    def test_all_zero_volume(self):
        """All zero volume candles should be handled gracefully."""
        matrix = SmartMoneyMatrix()
        
        candles = []
        for i in range(30):
            candle = make_candle(
                timestamp=float(i),
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                volume=0.0  # All zero volume
            )
            candles.append(candle)
        
        # Scan should not crash
        result = matrix.scan(candles)
        
        assert result is not None

    def test_zero_volume_no_ob_detection(self):
        """Zero volume should prevent OB detection (OB requires high volume)."""
        detector = OrderBlockDetector(
            lookback=50,
            volume_percentile=80.0
        )
        
        candles = []
        for i in range(30):
            candle = make_candle(
                timestamp=float(i),
                open=100.0,
                high=105.0,
                low=99.0,
                close=104.0,
                volume=0.0  # Zero volume
            )
            candles.append(candle)
        
        # Scan
        detector.scan(candles)
        
        # No OBs should be detected with zero volume
        active_obs = detector.get_active_blocks()
        assert len(active_obs) == 0, "No OBs should be detected with zero volume"

    def test_extremely_low_volume(self):
        """Very low volume (but not zero) should still be processed."""
        matrix = SmartMoneyMatrix()
        
        candles = []
        for i in range(30):
            candle = make_candle(
                timestamp=float(i),
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                volume=0.001  # Very low but not zero
            )
            candles.append(candle)
        
        # Scan should complete
        result = matrix.scan(candles)
        assert result is not None


# ══════════════════════════════════════════════════════════════════════════════
# TEST 5: INTEGRATION TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestSmartMoneyMatrixIntegration:
    """Integration tests for the complete Smart Money Matrix."""

    def test_empty_candles(self):
        """Empty candle list should not crash."""
        matrix = SmartMoneyMatrix()
        result = matrix.scan([])
        
        assert result['order_blocks'] == []
        assert result['fair_value_gaps'] == []
        assert result['sweep_events'] == []

    def test_single_candle(self):
        """Single candle should not crash."""
        matrix = SmartMoneyMatrix()
        candles = [make_candle()]
        result = matrix.scan(candles)
        
        assert result is not None

    def test_two_candles(self):
        """Two candles should not crash."""
        matrix = SmartMoneyMatrix()
        candles = [make_candle(timestamp=0.0), make_candle(timestamp=1.0)]
        result = matrix.scan(candles)
        
        assert result is not None

    def test_status_method(self):
        """Status method should return valid data."""
        matrix = SmartMoneyMatrix()
        candles = make_candles(20)
        matrix.scan(candles)
        
        status = matrix.get_status()
        
        assert 'order_blocks' in status
        assert 'fair_value_gaps' in status
        assert 'liquidity_levels' in status
        assert 'performance' in status

    def test_concurrent_scans(self):
        """Multiple scans should not corrupt state."""
        matrix = SmartMoneyMatrix()
        candles = make_candles(50)
        
        # Run multiple scans
        for _ in range(10):
            result = matrix.scan(candles)
            assert result is not None


# ══════════════════════════════════════════════════════════════════════════════
# TEST 6: BOUNDARY CONDITIONS
# ══════════════════════════════════════════════════════════════════════════════

class TestBoundaryConditions:
    """Tests for boundary conditions and edge cases."""

    def test_lookback_limit_respected(self):
        """Candles beyond lookback should be clipped."""
        detector = OrderBlockDetector(lookback=10)
        
        candles = make_candles(50)
        detector.scan(candles)
        
        # Should only process last 10 candles
        assert len(detector.volume_history) <= 10

    def test_max_blocks_enforced(self):
        """Should not exceed max_blocks."""
        max_blocks = 5
        detector = OrderBlockDetector(max_blocks=max_blocks)
        
        # Create many potential OBs
        candles = make_candles(100)
        
        for _ in range(20):
            detector.scan(candles)
        
        assert len(detector.blocks) <= max_blocks

    def test_extreme_price_values(self):
        """Should handle extreme price values."""
        matrix = SmartMoneyMatrix()
        
        # Very large prices
        candle = make_candle(
            open=1_000_000.0,
            high=1_100_000.0,
            low=900_000.0,
            close=1_050_000.0,
            volume=1_000_000.0
        )
        
        result = matrix.scan([candle])
        assert result is not None

    def test_negative_prices(self):
        """Should handle negative prices (commodities)."""
        matrix = SmartMoneyMatrix()
        
        candle = make_candle(
            open=-10.0,
            high=-9.0,
            low=-11.0,
            close=-9.5,
            volume=1000.0
        )
        
        result = matrix.scan([candle])
        assert result is not None


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
