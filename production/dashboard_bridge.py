"""
Dashboard Bridge - Multi-Asset Heatmap & AI Insight Engine
===========================================================
Compiles a unified JSON payload of all system state for the trading
dashboard. Generates AI Insight prompts for async LLM reasoning calls.

Output structure:
  {
    "timestamp": "...",
    "assets": {
      "XAUUSD": { "regime": "EXPANSION", "score": 85, "decision": "EXECUTE", ... },
      "EURUSD": { ... },
      "GBPUSD": { ... },
      "SP500":  { ... }
    },
    "health": { "cpu": "...", "memory": "...", "pm2_status": "online" },
    "insight_prompt": "..."
  }
"""

import logging
import json
import math
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from pathlib import Path

log = logging.getLogger('DashboardBridge')

SUPPORTED_ASSETS = ['XAUUSD', 'EURUSD', 'GBPUSD', 'SP500']

# Default empty signal for missing assets
_EMPTY_SIGNAL = {
    'score': 0,
    'decision': 'NONE',
    'regime': 'UNKNOWN',
    'signal_strength': '0%',
    'liquidity_tier': 'LOW',
    'execution_grade': 'N/A',
    'direction': 'NEUTRAL',
}


class DashboardBridge:
    """
    Compiles multi-asset system state into a single JSON payload.
    Formats AI insight prompts for LLM reasoning.
    """

    def __init__(self):
        self._cache: Dict[str, Any] = {}
        self._last_update: float = 0

    def build_state(
        self,
        asset_signals: Dict[str, Dict[str, Any]],
        system_health: Optional[Dict[str, str]] = None,
        execution_log: Optional[List[Dict]] = None,
        weekly_stats: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Build unified system state dict.

        Args:
            asset_signals: Dict mapping symbol -> signal data (score, decision, etc.)
            system_health: Dict with 'cpu', 'memory', 'pm2_status' keys
            execution_log: Recent execution records
            weekly_stats: Weekly performance stats

        Returns:
            Complete state dict ready for JSON serialization.
        """
        now = datetime.now(timezone.utc)

        # Merge with defaults for all supported assets
        assets = {}
        for sym in SUPPORTED_ASSETS:
            signal = asset_signals.get(sym, {})
            assets[sym] = {
                'score': signal.get('score', 0),
                'decision': signal.get('decision', 'NONE'),
                'regime': signal.get('regime', 'UNKNOWN'),
                'direction': signal.get('direction', 'NEUTRAL'),
                'signal_strength': signal.get('signal_strength', '0%'),
                'liquidity_tier': signal.get('liquidity_tier', 'LOW'),
                'execution_grade': signal.get('execution_grade', 'N/A'),
                'timestamp': now.isoformat(),
            }

        state = {
            'timestamp': now.isoformat(),
            'epoch_sec': int(time.time()),
            'assets': assets,
            'health': {
                'cpu': (system_health or {}).get('cpu', 'N/A'),
                'memory': (system_health or {}).get('memory', 'N/A'),
                'disk': (system_health or {}).get('disk', 'N/A'),
                'pm2_status': (system_health or {}).get('pm2_status', 'unknown'),
                'uptime_hours': (system_health or {}).get('uptime_hours', 0),
                'last_heartbeat': (system_health or {}).get('last_heartbeat', now.isoformat()),
            },
            'execution': (execution_log or [])[-10:],
            'weekly_stats': weekly_stats or {},
            'insight_prompt': self._build_insight_prompt(assets, weekly_stats),
        }

        self._cache = state
        self._last_update = time.time()
        return state

    def _build_insight_prompt(
        self,
        assets: Dict[str, Dict],
        weekly_stats: Optional[Dict] = None,
    ) -> str:
        """
        Build an AI Insight reasoning prompt from current system state.
        Designed to be sent to an LLM for analysis.
        """
        lines = [
            "# OMNI BRAIN V2 - Market Insight Request",
            f"## Timestamp: {datetime.now(timezone.utc).isoformat()}",
            "",
            "### Multi-Asset State",
            "",
        ]

        for sym, data in assets.items():
            regime = data.get('regime', '?')
            score = data.get('score', 0)
            decision = data.get('decision', '?')
            direction = data.get('direction', '?')
            liq_tier = data.get('liquidity_tier', '?')
            exec_grade = data.get('execution_grade', 'N/A')
            strength = data.get('signal_strength', '?')

            lines.append(f"**{sym}**:")
            lines.append(f"- Regime: {regime} | Score: {score}/100 | Decision: {decision}")
            lines.append(f"- Direction: {direction} | Signal Strength: {strength}")
            lines.append(f"- Liquidity: {liq_tier} | Execution Grade: {exec_grade}")
            lines.append("")

        if weekly_stats:
            lines.append("### Weekly Performance")
            lines.append(f"- Win Rate: {weekly_stats.get('win_rate', 'N/A')}")
            lines.append(f"- Total PnL: {weekly_stats.get('total_pnl', 'N/A')}")
            lines.append(f"- Best Trade: {weekly_stats.get('best_trade', 'N/A')}")
            lines.append(f"- Worst Trade: {weekly_stats.get('worst_trade', 'N/A')}")
            lines.append(f"- Max Drawdown: {weekly_stats.get('max_drawdown', 'N/A')}")
            lines.append("")

        lines.append("### Analysis Request")
        lines.append("Based on the above market state:")
        lines.append("1. What is the dominant market theme across assets?")
        lines.append("2. Are there any regime divergences worth noting?")
        lines.append("3. Which asset presents the highest-probability setup right now?")
        lines.append("4. Any warnings or risk management adjustments needed?")
        lines.append("5. Recommended bias for the next 4-8 hours.")

        return '\n'.join(lines)

    def get_signal_map(self, state: Dict[str, Any] = None) -> Dict[str, str]:
        """
        Generate a heatmap-friendly signal map.
        Returns emoji-coded state per asset.
        """
        data = state or self._cache
        assets = data.get('assets', {})
        signal_map = {}

        for sym, info in assets.items():
            decision = info.get('decision', 'NONE')
            regime = info.get('regime', '?')

            if decision == 'EXECUTE':
                if regime in ('EXPANSION', 'VOLATILITY'):
                    emoji = '🟢🔥'
                else:
                    emoji = '🟢'
            elif decision == 'WAIT':
                emoji = '🟡'
            elif decision == 'BLOCK':
                emoji = '🔴'
            else:
                emoji = '⚪'

            signal_map[sym] = f"{emoji} {regime[:4]} {info.get('score', 0)}"

        return signal_map

    def to_json(self, state: Dict[str, Any] = None) -> str:
        """Serialize state to JSON string."""
        data = state or self._cache
        if not data:
            return json.dumps({'error': 'No state data'})
        try:
            return json.dumps(data, indent=2, default=str)
        except (TypeError, ValueError) as e:
            return json.dumps({'error': f'Serialization failed: {e}'})

    def get_insight_prompt(self) -> str:
        """Get the cached insight prompt."""
        return self._cache.get('insight_prompt', '')


# ══════════════════════════════════════════════════════════════════════════════
# GLOBAL INSTANCE
# ══════════════════════════════════════════════════════════════════════════════

_bridge: Optional[DashboardBridge] = None


def get_bridge() -> DashboardBridge:
    global _bridge
    if _bridge is None:
        _bridge = DashboardBridge()
    return _bridge


# ══════════════════════════════════════════════════════════════════════════════
# CLI TEST
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.INFO, format='%(message)s')

    if '--test' in sys.argv:
        bridge = get_bridge()

        test_signals = {
            'XAUUSD': {
                'score': 85, 'decision': 'EXECUTE', 'regime': 'EXPANSION',
                'direction': 'BUY', 'signal_strength': '94%',
                'liquidity_tier': 'INSTITUTIONAL', 'execution_grade': 'A⁺',
            },
            'EURUSD': {
                'score': 45, 'decision': 'BLOCK', 'regime': 'COMPRESSION',
                'direction': 'SELL', 'signal_strength': '30%',
                'liquidity_tier': 'LOW', 'execution_grade': 'N/A',
            },
        }

        health = {
            'cpu': '23%', 'memory': '42%', 'disk': '67%',
            'pm2_status': 'online', 'uptime_hours': 48,
            'last_heartbeat': datetime.now(timezone.utc).isoformat(),
        }

        weekly = {
            'win_rate': '68%', 'total_pnl': '+342 pips',
            'best_trade': '+85 pips XAUUSD',
            'worst_trade': '-32 pips EURUSD',
            'max_drawdown': '8.5%',
        }

        state = bridge.build_state(test_signals, health, [], weekly)
        print("=== STATE JSON ===")
        print(bridge.to_json(state))

        print("\n=== SIGNAL MAP ===")
        for sym, label in bridge.get_signal_map(state).items():
            print(f"  {sym}: {label}")

        print("\n=== INSIGHT PROMPT ===")
        print(bridge.get_insight_prompt())

        print("\nDashboardBridge OK")
