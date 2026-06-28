"""
LTE BLACK BOX <-> OmniRoute Gateway Integration
=================================================
Connects the OmniSignalApexV35 terminal to the OmniRoute AI gateway
running on localhost:20128.

Architecture:
    LTE Terminal (signal generation)
        -> Integration Bridge (this module)
            -> OmniRoute Gateway (LLM enrichment at localhost:20128)
                -> Enriched signal output (dashboard, Telegram, logging)

Usage:
    # As a module
    from lte_omniroute_bridge import LTEOmniRouteBridge

    bridge = LTEOmniRouteBridge()
    signal = terminal.process_candle(ohlcv, "XAUUSD")
    if signal:
        enriched = bridge.enrich_signal(signal)
        bridge.send_to_dashboard(enriched)

    # Standalone
    python lte_omniroute_bridge.py --symbols XAUUSD EURUSD --interval 60
"""

import os
import json
import time
import logging
import hashlib
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from enum import Enum

import httpx

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OMNIROUTE_BASE_URL = os.getenv("OMNIROUTE_BASE_URL", "http://localhost:20128")
OMNIROUTE_API_KEY = os.getenv("OMNIROUTE_API_KEY", "")
OMNIROUTE_MODEL = os.getenv("OMNIROUTE_MODEL", "auto")

BRIDGE_HOST = os.getenv("BRIDGE_HOST", "0.0.0.0")
BRIDGE_PORT = int(os.getenv("BRIDGE_PORT", "8090"))
BRIDGE_API_KEY = os.getenv("BRIDGE_API_KEY", "")

LOG_DIR = os.getenv("LOG_DIR", "logs/omniroute")
SIGNAL_LOG = os.getenv("SIGNAL_LOG", "logs/signal_log_enriched.csv")

LOGGING_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(
    level=getattr(logging, LOGGING_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("lte_omniroute_bridge")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass
class OHLCV:
    timestamp: float
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class Signal:
    symbol: str
    direction: Direction
    score: int
    strength: float
    source: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=lambda: time.time())


@dataclass
class EnrichedSignal:
    """Signal enriched with LLM analysis from OmniRoute."""
    signal: Signal
    llm_analysis: str = ""
    llm_confidence: float = 0.0
    llm_recommendation: str = ""
    risk_assessment: str = ""
    suggested_sl: Optional[float] = None
    suggested_tp: Optional[float] = None
    enriched_at: float = field(default_factory=lambda: time.time())
    latency_ms: float = 0.0
    model_used: str = ""


# ---------------------------------------------------------------------------
# OmniRoute API Client
# ---------------------------------------------------------------------------

class OmniRouteClient:
    """HTTP client for the OmniRoute AI gateway at localhost:20128."""

    def __init__(
        self,
        base_url: str = OMNIROUTE_BASE_URL,
        api_key: str = OMNIROUTE_API_KEY,
        model: str = OMNIROUTE_MODEL,
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self._client: Optional[httpx.Client] = None

    def _get_client(self) -> httpx.Client:
        if self._client is None or self._client.is_closed:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._client = httpx.Client(
                base_url=self.base_url,
                headers=headers,
                timeout=self.timeout,
            )
        return self._client

    def health_check(self) -> bool:
        """Check if OmniRoute gateway is reachable."""
        try:
            client = self._get_client()
            resp = client.get("/v1/models")
            return resp.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException):
            return False

    def list_models(self) -> List[Dict[str, Any]]:
        """List available models from OmniRoute."""
        try:
            client = self._get_client()
            resp = client.get("/v1/models")
            resp.raise_for_status()
            return resp.json().get("data", [])
        except Exception as e:
            logger.error("Failed to list models: %s", e)
            return []

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 512,
    ) -> Optional[Dict[str, Any]]:
        """Send a chat completion request to OmniRoute."""
        try:
            client = self._get_client()
            payload = {
                "model": model or self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            resp = client.post("/v1/chat/completions", json=payload)
            resp.raise_for_status()
            return resp.json()
        except httpx.ConnectError:
            logger.warning("OmniRoute gateway not reachable at %s", self.base_url)
            return None
        except httpx.TimeoutException:
            logger.warning("OmniRoute request timed out")
            return None
        except Exception as e:
            logger.error("OmniRoute chat completion failed: %s", e)
            return None

    def close(self):
        if self._client and not self._client.is_closed:
            self._client.close()


# ---------------------------------------------------------------------------
# Signal Enrichment Prompt Templates
# ---------------------------------------------------------------------------

ENRICHMENT_SYSTEM_PROMPT = """You are an expert forex/crypto trading analyst integrated into an automated signal pipeline.

Your role: Analyze trading signals from a multi-module confluence scoring system and provide:
1. Confidence assessment (0-100)
2. Risk evaluation
3. Entry/exit recommendations
4. Market context

Be concise. Respond in valid JSON only."""

ENRICHMENT_USER_TEMPLATE = """Analyze this trading signal:

Symbol: {symbol}
Direction: {direction}
Confluence Score: {score}/10
Signal Strength: {strength}
Source Modules: {source}

Module Details:
{metadata}

Provide analysis as JSON:
{{
  "confidence": <0-100>,
  "recommendation": "EXECUTE" | "WAIT" | "SKIP",
  "risk_level": "LOW" | "MEDIUM" | "HIGH",
  "risk_assessment": "<brief risk notes>",
  "suggested_sl_pips": <number or null>,
  "suggested_tp_pips": <number or null>,
  "market_context": "<brief market context>",
  "reasoning": "<1-2 sentence reasoning>"
}}"""


# ---------------------------------------------------------------------------
# Main Bridge
# ---------------------------------------------------------------------------

class LTEOmniRouteBridge:
    """
    Bridge between LTE BLACK BOX terminal and OmniRoute AI gateway.

    Flow:
        1. Receive Signal from terminal
        2. Build enrichment prompt
        3. Send to OmniRoute (localhost:20128)
        4. Parse LLM response
        5. Return EnrichedSignal
    """

    def __init__(
        self,
        omniroute_url: str = OMNIROUTE_BASE_URL,
        omniroute_api_key: str = OMNIROUTE_API_KEY,
        model: str = OMNIROUTE_MODEL,
    ):
        self.client = OmniRouteClient(
            base_url=omniroute_url,
            api_key=omniroute_api_key,
            model=model,
        )
        self._signal_count = 0
        self._enrichment_cache: Dict[str, EnrichedSignal] = {}

        # Ensure log directory exists
        os.makedirs(LOG_DIR, exist_ok=True)

        logger.info(
            "Bridge initialized: OmniRoute=%s, model=%s",
            omniroute_url,
            model,
        )

    def _cache_key(self, signal: Signal) -> str:
        """Generate cache key for deduplication."""
        raw = f"{signal.symbol}:{signal.direction}:{signal.score}:{signal.timestamp}"
        return hashlib.md5(raw.encode()).hexdigest()

    def _build_prompt(self, signal: Signal) -> str:
        """Build the enrichment prompt from a signal."""
        metadata_str = "\n".join(
            f"  - {k}: {v}" for k, v in signal.metadata.items()
        )
        return ENRICHMENT_USER_TEMPLATE.format(
            symbol=signal.symbol,
            direction=signal.direction.value,
            score=signal.score,
            strength=f"{signal.strength:.2f}",
            source=signal.source,
            metadata=metadata_str or "  (no module details)",
        )

    def _parse_llm_response(self, raw: str) -> Dict[str, Any]:
        """Parse LLM JSON response, handling markdown fences."""
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM response as JSON: %s", raw[:200])
            return {}

    def enrich_signal(self, signal: Signal) -> EnrichedSignal:
        """
        Send a signal to OmniRoute for LLM enrichment.

        Returns EnrichedSignal with analysis, confidence, and recommendations.
        """
        start = time.monotonic()

        # Check cache (skip duplicate signals within 60s)
        key = self._cache_key(signal)
        if key in self._enrichment_cache:
            cached = self._enrichment_cache[key]
            if time.time() - cached.enriched_at < 60:
                logger.debug("Cache hit for %s %s", signal.symbol, signal.direction)
                return cached

        # Build prompt
        user_prompt = self._build_prompt(signal)
        messages = [
            {"role": "system", "content": ENRICHMENT_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        # Call OmniRoute
        response = self.client.chat_completion(messages)
        latency_ms = (time.time() - start) * 1000

        # Parse response
        llm_analysis = ""
        confidence = 0.0
        recommendation = "WAIT"
        risk_assessment = ""
        suggested_sl = None
        suggested_tp = None
        model_used = ""

        if response:
            model_used = response.get("model", self.client.model)
            choices = response.get("choices", [])
            if choices:
                content = choices[0].get("message", {}).get("content", "")
                llm_analysis = content
                parsed = self._parse_llm_response(content)
                if parsed:
                    confidence = parsed.get("confidence", 0) / 100.0
                    recommendation = parsed.get("recommendation", "WAIT")
                    risk_assessment = parsed.get("risk_assessment", "")
                    suggested_sl = parsed.get("suggested_sl_pips")
                    suggested_tp = parsed.get("suggested_tp_pips")

        enriched = EnrichedSignal(
            signal=signal,
            llm_analysis=llm_analysis,
            llm_confidence=confidence,
            llm_recommendation=recommendation,
            risk_assessment=risk_assessment,
            suggested_sl=suggested_sl,
            suggested_tp=suggested_tp,
            latency_ms=latency_ms,
            model_used=model_used,
        )

        # Cache and log
        self._enrichment_cache[key] = enriched
        self._signal_count += 1
        self._log_enriched(enriched)

        logger.info(
            "Enriched %s %s: score=%d -> confidence=%.0f%% rec=%s (%.0fms)",
            signal.symbol,
            signal.direction.value,
            signal.score,
            confidence * 100,
            recommendation,
            latency_ms,
        )

        return enriched

    def _log_enriched(self, enriched: EnrichedSignal):
        """Append enriched signal to CSV log."""
        try:
            import csv

            write_header = not os.path.exists(SIGNAL_LOG)
            with open(SIGNAL_LOG, "a", newline="") as f:
                writer = csv.writer(f)
                if write_header:
                    writer.writerow([
                        "timestamp", "symbol", "direction", "score",
                        "confidence", "recommendation", "risk",
                        "sl_pips", "tp_pips", "latency_ms", "model",
                    ])
                writer.writerow([
                    datetime.fromtimestamp(enriched.signal.timestamp, tz=timezone.utc).isoformat(),
                    enriched.signal.symbol,
                    enriched.signal.direction.value,
                    enriched.signal.score,
                    f"{enriched.llm_confidence:.0%}",
                    enriched.llm_recommendation,
                    enriched.risk_assessment,
                    enriched.suggested_sl or "",
                    enriched.suggested_tp or "",
                    f"{enriched.latency_ms:.0f}",
                    enriched.model_used,
                ])
        except Exception as e:
            logger.error("Failed to log enriched signal: %s", e)

    def should_execute(self, enriched: EnrichedSignal) -> bool:
        """
        Decision function: should we execute this signal?

        Logic:
        - LLM recommendation must be EXECUTE
        - Confidence must be >= 60%
        - Signal score must be >= 3 (terminal threshold)
        """
        if enriched.llm_recommendation != "EXECUTE":
            return False
        if enriched.llm_confidence < 0.60:
            return False
        if abs(enriched.signal.score) < 3:
            return False
        return True

    def format_telegram(self, enriched: EnrichedSignal) -> str:
        """Format enriched signal for Telegram notification."""
        s = enriched.signal
        emoji = "🟢" if s.direction == Direction.LONG else "🔴"
        execute = "✅ EXECUTE" if self.should_execute(enriched) else "⚠️ WAIT"

        lines = [
            f"{emoji} *{s.symbol}* {s.direction.value}",
            f"",
            f"📊 Score: {s.score}/10",
            f"🤖 AI Confidence: {enriched.llm_confidence:.0%}",
            f"📋 Recommendation: {enriched.llm_recommendation}",
            f"⚡ Decision: {execute}",
            f"",
            f"💡 {enriched.risk_assessment}",
        ]

        if enriched.suggested_sl:
            lines.append(f"🛑 SL: {enriched.suggested_sl} pips")
        if enriched.suggested_tp:
            lines.append(f"🎯 TP: {enriched.suggested_tp} pips")

        lines.extend([
            f"",
            f"🧠 {enriched.llm_analysis[:200]}",
            f"",
            f"⏱️ {enriched.latency_ms:.0f}ms via {enriched.model_used}",
        ])

        return "\n".join(lines)

    def get_stats(self) -> Dict[str, Any]:
        """Return bridge statistics."""
        return {
            "signals_enriched": self._signal_count,
            "cache_size": len(self._enrichment_cache),
            "omniroute_connected": self.client.health_check(),
            "model": self.client.model,
            "base_url": self.client.base_url,
        }

    def close(self):
        """Clean up resources."""
        self.client.close()


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------

def main():
    """Run the bridge in standalone mode with mock data for testing."""
    import argparse

    parser = argparse.ArgumentParser(description="LTE <-> OmniRoute Bridge")
    parser.add_argument("--symbols", nargs="+", default=["XAUUSD", "EURUSD"])
    parser.add_argument("--interval", type=int, default=60, help="Scan interval (seconds)")
    parser.add_argument("--omniroute-url", default=OMNIROUTE_BASE_URL)
    parser.add_argument("--model", default=OMNIROUTE_MODEL)
    args = parser.parse_args()

    bridge = LTEOmniRouteBridge(
        omniroute_url=args.omniroute_url,
        model=args.model,
    )

    # Check connectivity
    if not bridge.client.health_check():
        logger.error(
            "Cannot reach OmniRoute at %s. "
            "Start OmniRoute: npm install -g omniroute && omniroute",
            args.omniroute_url,
        )
        return

    logger.info("Connected to OmniRoute. Starting bridge loop...")
    logger.info("Symbols: %s, Interval: %ds", args.symbols, args.interval)

    try:
        while True:
            for symbol in args.symbols:
                # Generate mock OHLCV for testing
                import random
                base = 2000 if symbol == "XAUUSD" else 1.1
               ohlcv = OHLCV(
                    timestamp=time.time(),
                    open=base + random.uniform(-0.5, 0.5),
                    high=base + random.uniform(0, 1),
                    low=base - random.uniform(0, 1),
                    close=base + random.uniform(-0.3, 0.3),
                    volume=random.uniform(100, 1000),
                )

                # Create mock signal
                signal = Signal(
                    symbol=symbol,
                    direction=random.choice([Direction.LONG, Direction.SHORT]),
                    score=random.randint(2, 8),
                    strength=random.uniform(0.5, 1.0),
                    source="test",
                    metadata={"test": True},
                )

                # Enrich
                enriched = bridge.enrich_signal(signal)
                print(bridge.format_telegram(enriched))
                print("---")

            time.sleep(args.interval)

    except KeyboardInterrupt:
        logger.info("Shutting down bridge...")
    finally:
        bridge.close()


if __name__ == "__main__":
    main()
