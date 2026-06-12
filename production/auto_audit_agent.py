"""
Auto-Audit Agent — Layer 2 Self-Tuning Module
==============================================
Autonomous performance auditor that reads metrics, detects underperformance,
and auto-tunes strategy parameters within safe bounds.

Read-only constraints:
    - Only reads metrics_db.json (never writes to it)
    - Only writes to audit_log.txt (append-only)
    - Parameter adjustments are advisory (passed to pipeline, not forced)

Audit triggers:
    - win_rate < 50% → reduce volume_multiplier (more selective entries)
    - profit_factor < 1.5 → tighten trail_activation (lock profits faster)

Parameter bounds (safety rails):
    - volume_multiplier: [1.0, 2.5] (default 1.5)
    - trail_activation_pips: [30.0, 80.0] (default 50.0)
"""

import os
import json
import time
import logging
from typing import Dict, Any, Optional, Tuple
from pathlib import Path
from datetime import datetime, timezone

log = logging.getLogger('AutoAuditAgent')

METRICS_DB = Path(__file__).parent.parent / 'logs' / 'metrics_db.json'
AUDIT_LOG = Path(__file__).parent.parent / 'logs' / 'audit_log.txt'

# Safety bounds
PARAM_BOUNDS = {
    'volume_multiplier': {'min': 1.0, 'max': 2.5, 'step': 0.1, 'default': 1.5},
    'trail_activation_pips': {'min': 30.0, 'max': 80.0, 'step': 5.0, 'default': 50.0},
}

# Audit thresholds
AUDIT_THRESHOLDS = {
    'min_trades': 5,           # Minimum trades before audit
    'win_rate_floor': 50.0,    # Below this → tune volume_multiplier
    'profit_factor_floor': 1.5, # Below this → tune trail_activation
}


class AutoAuditAgent:
    """
    Layer 2: Self-Tuning Performance Auditor

    Reads metrics, detects underperformance, and adjusts strategy parameters.
    """

    def __init__(self):
        self._last_audit_time: float = 0
        self._audit_interval: float = 3600  # Run audit every hour
        self._current_params: Dict[str, float] = {
            'volume_multiplier': PARAM_BOUNDS['volume_multiplier']['default'],
            'trail_activation_pips': PARAM_BOUNDS['trail_activation_pips']['default'],
        }
        self._audit_history: list = []
        self._load_state()

    def _load_state(self):
        """Load persisted audit state."""
        state_file = Path(__file__).parent.parent / 'logs' / 'audit_state.json'
        try:
            if state_file.exists():
                with open(state_file, 'r') as f:
                    state = json.load(f)
                    self._current_params = state.get('params', self._current_params)
                    self._audit_history = state.get('history', [])
                    self._last_audit_time = state.get('last_audit_time', 0)
        except Exception as e:
            log.warning(f"[AUDIT] Failed to load state: {e}")

    def _save_state(self):
        """Persist audit state."""
        state_file = Path(__file__).parent.parent / 'logs' / 'audit_state.json'
        try:
            state = {
                'params': self._current_params,
                'history': self._audit_history[-100:],  # Keep last 100 audits
                'last_audit_time': self._last_audit_time,
            }
            tmp = str(state_file) + '.tmp'
            with open(tmp, 'w') as f:
                json.dump(state, f, indent=2)
            os.replace(tmp, str(state_file))
        except Exception as e:
            log.warning(f"[AUDIT] Failed to save state: {e}")

    def _load_metrics(self) -> Dict[str, Any]:
        """Read metrics from metrics_db.json (read-only)."""
        try:
            if METRICS_DB.exists():
                with open(METRICS_DB, 'r') as f:
                    return json.load(f)
        except Exception as e:
            log.warning(f"[AUDIT] Failed to load metrics: {e}")
        return {}

    def _log_audit(self, report: str):
        """Append audit report to audit_log.txt."""
        try:
            AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
            with open(AUDIT_LOG, 'a') as f:
                f.write(report + '\n')
        except Exception as e:
            log.warning(f"[AUDIT] Failed to write audit log: {e}")

    def _compute_metrics(self, db: Dict[str, Any]) -> Dict[str, Any]:
        """Compute aggregated metrics from raw trade data."""
        trades = db.get('trades', [])
        closed = [t for t in trades if t.get('result') in ('WIN', 'LOSS')]

        if not closed:
            return {
                'total_trades': 0,
                'win_rate': 0.0,
                'profit_factor': 0.0,
                'avg_rr': 0.0,
                'total_pnl': 0.0,
            }

        wins = [t for t in closed if t['result'] == 'WIN']
        losses = [t for t in closed if t['result'] == 'LOSS']

        win_rate = (len(wins) / len(closed)) * 100 if closed else 0

        gross_profit = sum(t.get('pnl_pips', 0) or 0 for t in wins)
        gross_loss = abs(sum(t.get('pnl_pips', 0) or 0 for t in losses))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float('inf') if gross_profit > 0 else 0

        r_r_values = [t.get('r_r_ratio', 0) for t in closed if t.get('r_r_ratio') is not None]
        avg_rr = (sum(r_r_values) / len(r_r_values)) if r_r_values else 0

        total_pnl = sum(t.get('pnl_pips', 0) or 0 for t in closed)

        return {
            'total_trades': len(closed),
            'win_rate': round(win_rate, 2),
            'profit_factor': round(profit_factor, 2),
            'avg_rr': round(avg_rr, 2),
            'total_pnl': round(total_pnl, 2),
        }

    def audit(self) -> Dict[str, Any]:
        """
        Run a full audit cycle.

        Returns:
            {
                'timestamp': str,
                'metrics': dict,
                'issues': list[str],
                'adjustments': dict,
                'params': dict,
            }
        """
        now = time.time()

        # Rate limit audits
        if now - self._last_audit_time < self._audit_interval:
            return {'status': 'skipped', 'reason': 'audit_interval_not_reached'}

        self._last_audit_time = now

        # Load and compute metrics
        db = self._load_metrics()
        metrics = self._compute_metrics(db)

        issues = []
        adjustments = {}

        # ── Audit: Win Rate ──────────────────────────────────────────
        if metrics['total_trades'] >= AUDIT_THRESHOLDS['min_trades']:
            if metrics['win_rate'] < AUDIT_THRESHOLDS['win_rate_floor']:
                issues.append(
                    f"Win rate {metrics['win_rate']:.1f}% < {AUDIT_THRESHOLDS['win_rate_floor']}%"
                )
                # Reduce volume_multiplier (more selective entries)
                old_val = self._current_params['volume_multiplier']
                new_val = max(
                    PARAM_BOUNDS['volume_multiplier']['min'],
                    old_val - PARAM_BOUNDS['volume_multiplier']['step']
                )
                if new_val != old_val:
                    self._current_params['volume_multiplier'] = round(new_val, 2)
                    adjustments['volume_multiplier'] = {
                        'old': old_val,
                        'new': new_val,
                        'reason': 'win_rate_below_threshold',
                    }

            # ── Audit: Profit Factor ─────────────────────────────────
            if metrics['profit_factor'] < AUDIT_THRESHOLDS['profit_factor_floor']:
                issues.append(
                    f"Profit factor {metrics['profit_factor']:.2f} < {AUDIT_THRESHOLDS['profit_factor_floor']}"
                )
                # Reduce trail_activation_pips (lock profits faster)
                old_val = self._current_params['trail_activation_pips']
                new_val = max(
                    PARAM_BOUNDS['trail_activation_pips']['min'],
                    old_val - PARAM_BOUNDS['trail_activation_pips']['step']
                )
                if new_val != old_val:
                    self._current_params['trail_activation_pips'] = round(new_val, 1)
                    adjustments['trail_activation_pips'] = {
                        'old': old_val,
                        'new': new_val,
                        'reason': 'profit_factor_below_threshold',
                    }

            # ── Audit: Positive Performance → loosen params ──────────
            if metrics['win_rate'] >= 60 and metrics['profit_factor'] >= 2.0:
                # Performance is good, can afford wider trail
                old_val = self._current_params['trail_activation_pips']
                new_val = min(
                    PARAM_BOUNDS['trail_activation_pips']['max'],
                    old_val + PARAM_BOUNDS['trail_activation_pips']['step']
                )
                if new_val != old_val:
                    self._current_params['trail_activation_pips'] = round(new_val, 1)
                    adjustments['trail_activation_pips'] = {
                        'old': old_val,
                        'new': new_val,
                        'reason': 'performance_strong_loosening',
                    }

        # ── Generate Report ──────────────────────────────────────────
        timestamp = datetime.now(timezone.utc).isoformat()
        report_lines = [
            f"\n{'='*60}",
            f"AUDIT REPORT — {timestamp}",
            f"{'='*60}",
            f"Trades:      {metrics['total_trades']}",
            f"Win Rate:    {metrics['win_rate']:.2f}%",
            f"Profit Factor: {metrics['profit_factor']:.2f}",
            f"Avg R:R:     {metrics['avg_rr']:.2f}",
            f"Total P&L:   {metrics['total_pnl']:.2f} pips",
            f"",
            f"Current Parameters:",
            f"  volume_multiplier:     {self._current_params['volume_multiplier']:.2f}",
            f"  trail_activation_pips: {self._current_params['trail_activation_pips']:.1f}",
        ]

        if issues:
            report_lines.append(f"\nIssues Detected ({len(issues)}):")
            for issue in issues:
                report_lines.append(f"  ⚠ {issue}")
        else:
            report_lines.append("\nNo issues detected.")

        if adjustments:
            report_lines.append(f"\nAdjustments Made ({len(adjustments)}):")
            for param, adj in adjustments.items():
                report_lines.append(f"  → {param}: {adj['old']} → {adj['new']} ({adj['reason']})")
        else:
            report_lines.append("\nNo adjustments needed.")

        report_lines.append(f"{'='*60}\n")
        report = "\n".join(report_lines)

        # Log to file
        self._log_audit(report)
        log.info(f"[AUDIT] Completed — {len(issues)} issues, {len(adjustments)} adjustments")

        # Save state
        self._audit_history.append({
            'timestamp': timestamp,
            'metrics': metrics,
            'issues': issues,
            'adjustments': adjustments,
        })
        self._save_state()

        return {
            'timestamp': timestamp,
            'metrics': metrics,
            'issues': issues,
            'adjustments': adjustments,
            'params': self._current_params.copy(),
        }

    def get_params(self) -> Dict[str, float]:
        """Get current tuned parameters."""
        return self._current_params.copy()

    def get_history(self, limit: int = 10) -> list:
        """Get recent audit history."""
        return self._audit_history[-limit:]


# Module-level singleton
_agent: Optional[AutoAuditAgent] = None


def get_auto_audit_agent() -> AutoAuditAgent:
    """Get the global AutoAuditAgent singleton."""
    global _agent
    if _agent is None:
        _agent = AutoAuditAgent()
    return _agent
