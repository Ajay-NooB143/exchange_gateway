"""
Layer 0 — Pipeline Contract
===========================
Pure interface for the data processing pipeline.
No business logic. No imports from Layers 1-4.
"""

from typing import Protocol, Any, Dict, Optional


class PipelineProtocol(Protocol):
    """Protocol for the signal processing pipeline."""

    def run_pipeline(
        self,
        symbol: str,
        timeframe: str,
        candle_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute the full signal pipeline for a symbol.

        Args:
            symbol: Trading pair (e.g. "XAUUSD", "EURUSD").
            timeframe: Candle timeframe (e.g. "M15", "H1", "H4", "D1").
            candle_data: Optional raw candle data to process.

        Returns:
            Dict with at least:
                - action: "EXECUTE" | "WAIT" | "BLOCK"
                - confidence: int (0-100)
                - symbol: str
                - timeframe: str
        """
        ...
