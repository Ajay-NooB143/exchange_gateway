"""
Exchange Gateway — Central Configuration Manager
=================================================
Securely loads API credentials, manages exchange-specific IP whitelists,
and enforces distinct rate limit policies (Binance weight-based vs Bybit linear).

Usage:
    from config_manager import ExchangeConfig
    cfg = ExchangeConfig.from_env()
    binance_creds = cfg.get_credentials('binance')
"""

import os
import json
import logging
import ipaddress
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

log = logging.getLogger("ExchangeConfig")

# ── defaults ───────────────────────────────────────────────────────────

CONFIG_DIR = Path(__file__).parent
PROJECT_ROOT = CONFIG_DIR.parent

# Binance: weight-based rate limit (1200 weight/min)
BINANCE_RATE_LIMITS = {
    "requests_per_minute": 1200,
    "order_weight": 1,
    "query_weight": 1,
    "market_data_weight": 2,
}

# Bybit: linear rate limit (120 req/min)
BYBIT_RATE_LIMITS = {
    "requests_per_minute": 120,
    "order_weight": 1,
    "query_weight": 1,
    "market_data_weight": 1,
}

EXCHANGE_RATE_LIMITS: Dict[str, Dict[str, int]] = {
    "binance": BINANCE_RATE_LIMITS,
    "bybit": BYBIT_RATE_LIMITS,
}

# ── data classes ───────────────────────────────────────────────────────

@dataclass
class ExchangeCredentials:
    """Encapsulates a single exchange's API credentials."""
    exchange: str
    api_key: str
    api_secret: str
    testnet: bool = False
    ip_whitelist: List[str] = field(default_factory=list)

    def validate(self) -> bool:
        """Return True if credentials look non-empty and well-formed."""
        if not self.api_key or not self.api_secret:
            log.warning("[CONFIG] %s: api_key or api_secret is empty", self.exchange)
            return False
        if self.testnet:
            log.info("[CONFIG] %s: testnet mode enabled", self.exchange)
        return True


@dataclass
class RateLimitConfig:
    """Rate limit policy for a single exchange."""
    requests_per_minute: int
    order_weight: int
    query_weight: int
    market_data_weight: int

    @classmethod
    def from_dict(cls, d: Dict[str, int]) -> "RateLimitConfig":
        return cls(
            requests_per_minute=d["requests_per_minute"],
            order_weight=d["order_weight"],
            query_weight=d["query_weight"],
            market_data_weight=d["market_data_weight"],
        )


# ── config manager ─────────────────────────────────────────────────────

class ExchangeConfig:
    """
    Central configuration manager.

    Sources (in priority order):
      1. Environment variables (EXCHANGE_GATEWAY_*)
      2. config/exchanges.json
      3. Hardcoded defaults
    """

    ENV_PREFIX = "EXCHANGE_GATEWAY_"

    def __init__(self):
        self._credentials: Dict[str, ExchangeCredentials] = {}
        self._rate_limits: Dict[str, RateLimitConfig] = {}
        self._load_from_json()
        self._load_from_env()

    # ── public API ─────────────────────────────────────────────────────

    @classmethod
    def from_env(cls) -> "ExchangeConfig":
        """Create config from environment + JSON file."""
        return cls()

    def get_credentials(self, exchange: str) -> ExchangeCredentials:
        """Return credentials for *exchange*, raising KeyError if missing."""
        if exchange not in self._credentials:
            raise KeyError(f"No credentials configured for exchange '{exchange}'")
        return self._credentials[exchange]

    def get_rate_limits(self, exchange: str) -> RateLimitConfig:
        """Return rate-limit policy for *exchange*."""
        if exchange not in self._rate_limits:
            raise KeyError(f"No rate limits configured for exchange '{exchange}'")
        return self._rate_limits[exchange]

    def list_exchanges(self) -> List[str]:
        """Return names of all configured exchanges."""
        return list(self._credentials.keys())

    def validate_ip(self, exchange: str, ip: str) -> bool:
        """Check if *ip* is in the whitelist for *exchange*.

        Returns True if the whitelist is empty (no restriction).
        """
        creds = self.get_credentials(exchange)
        if not creds.ip_whitelist:
            return True
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            log.error("[CONFIG] Invalid IP address: %s", ip)
            return False
        for allowed in creds.ip_whitelist:
            if "/" in allowed:
                if addr in ipaddress.ip_network(allowed, strict=False):
                    return True
            elif ip == allowed:
                return True
        log.warning("[CONFIG] %s: IP %s not in whitelist", exchange, ip)
        return False

    def as_dict(self) -> Dict[str, Any]:
        """Serialize config (secrets redacted) for logging/debug."""
        out: Dict[str, Any] = {}
        for name, creds in self._credentials.items():
            out[name] = {
                "api_key": creds.api_key[:8] + "..." if len(creds.api_key) > 8 else "***",
                "testnet": creds.testnet,
                "ip_whitelist": creds.ip_whitelist,
                "rate_limits": {
                    "rpm": self._rate_limits[name].requests_per_minute
                },
            }
        return out

    # ── private loaders ────────────────────────────────────────────────

    def _load_from_json(self):
        """Load from config/exchanges.json if it exists."""
        path = CONFIG_DIR / "exchanges.json"
        if not path.exists():
            log.debug("[CONFIG] No %s found — using env/defaults", path)
            return
        try:
            with open(path) as f:
                data = json.load(f)
        except Exception as e:
            log.error("[CONFIG] Failed to parse %s: %s", path, e)
            return

        for exchange, block in data.get("exchanges", {}).items():
            ip_wl = block.get("ip_whitelist", [])
            self._credentials[exchange] = ExchangeCredentials(
                exchange=exchange,
                api_key=block.get("api_key", ""),
                api_secret=block.get("api_secret", ""),
                testnet=block.get("testnet", False),
                ip_whitelist=ip_wl,
            )
            rl = EXCHANGE_RATE_LIMITS.get(exchange, BINANCE_RATE_LIMITS)
            rl.update(block.get("rate_limits", {}))
            self._rate_limits[exchange] = RateLimitConfig.from_dict(rl)

    def _load_from_env(self):
        """Overlay env vars: EXCHANGE_GATEWAY_BINANCE_API_KEY, etc."""
        env_map = {
            "API_KEY": "api_key",
            "API_SECRET": "api_secret",
            "TESTNET": "testnet",
        }
        for exchange in EXCHANGE_RATE_LIMITS:
            prefix = f"{self.ENV_PREFIX}{exchange.upper()}_"
            has_key = os.environ.get(f"{prefix}API_KEY")
            if not has_key:
                continue
            api_key = os.environ.get(f"{prefix}API_KEY", "")
            api_secret = os.environ.get(f"{prefix}API_SECRET", "")
            testnet = os.environ.get(f"{prefix}TESTNET", "").lower() in ("1", "true", "yes")
            ip_wl_raw = os.environ.get(f"{prefix}IP_WHITELIST", "")
            ip_wl = [ip.strip() for ip in ip_wl_raw.split(",") if ip.strip()]

            self._credentials[exchange] = ExchangeCredentials(
                exchange=exchange,
                api_key=api_key,
                api_secret=api_secret,
                testnet=testnet,
                ip_whitelist=ip_wl,
            )
            if exchange not in self._rate_limits:
                self._rate_limits[exchange] = RateLimitConfig.from_dict(
                    EXCHANGE_RATE_LIMITS[exchange]
                )

        # Also support a generic EXCHANGE_GATEWAY_API_KEY / _SECRET for single-exchange setups
        generic_key = os.environ.get(f"{self.ENV_PREFIX}API_KEY", "")
        if generic_key and not self._credentials:
            generic_secret = os.environ.get(f"{self.ENV_PREFIX}API_SECRET", "")
            self._credentials["binance"] = ExchangeCredentials(
                exchange="binance",
                api_key=generic_key,
                api_secret=generic_secret,
            )
            self._rate_limits["binance"] = RateLimitConfig.from_dict(BINANCE_RATE_LIMITS)
