"""
Layer 0 — Alert Contract
========================
Pure interface for alert/signal delivery.
No business logic. No imports from Layers 1-4.
"""

from typing import Protocol, Any, Dict, Optional


class AlertSender(Protocol):
    """Protocol for sending trading signals and alerts."""

    def send_signal(
        self,
        symbol: str,
        action: str,
        confidence: float,
        details: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Send a trading signal alert.

        Args:
            symbol: Trading pair (e.g. "BTCUSDT").
            action: Signal action (e.g. "BUY", "SELL", "WAIT", "BLOCK").
            confidence: Confidence score 0-100.
            details: Optional extra payload (entry, SL, TP, etc.).

        Returns:
            True if sent successfully, False otherwise.
        """
        ...
