"""
Metrics Monitor — Layer 2 CLI Dashboard
========================================
Read-only CLI tool that displays aggregated performance metrics
from the MetricsCollector singleton.

Usage:
    python3 production/metrics_monitor.py          # one-shot print
    python3 production/metrics_monitor.py --watch   # refresh every 30s
"""

import sys
import os
import time
import argparse
from typing import Dict, Any

# Add parent directory to path for production imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from production.metrics_collector import get_metrics_collector


def format_table(metrics: Dict[str, Any]) -> str:
    """Format metrics dict into a clean ASCII table."""
    lines = []
    lines.append("╔══════════════════════════════════════════════════════╗")
    lines.append("║        OMNI BRAIN V35 — PERFORMANCE METRICS        ║")
    lines.append("╠══════════════════════════════════════════════════════╣")

    # ── Trade Summary ────────────────────────────────────────────────
    lines.append("║  TRADE SUMMARY                                      ║")
    lines.append("║  ─────────────────────────────────────────────────  ║")
    lines.append(f"║  Total Trades:     {metrics.get('total_trades', 0):>10}                      ║")
    lines.append(f"║  Open Trades:      {metrics.get('open_trades', 0):>10}                      ║")
    lines.append(f"║  Wins:             {metrics.get('wins', 0):>10}                      ║")
    lines.append(f"║  Losses:           {metrics.get('losses', 0):>10}                      ║")
    lines.append(f"║  Win Rate:         {metrics.get('win_rate_pct', 0):>9.2f}%                     ║")

    lines.append("╠══════════════════════════════════════════════════════╣")

    # ── Risk Metrics ─────────────────────────────────────────────────
    lines.append("║  RISK METRICS                                        ║")
    lines.append("║  ─────────────────────────────────────────────────  ║")
    lines.append(f"║  Avg R:R:          {metrics.get('avg_rr', 0):>10.2f}                      ║")
    lines.append(f"║  Avg Win:          {metrics.get('avg_win_pips', 0):>9.2f} pips                ║")
    lines.append(f"║  Avg Loss:         {metrics.get('avg_loss_pips', 0):>9.2f} pips                ║")
    lines.append(f"║  Profit Factor:    {metrics.get('profit_factor', 0):>10.2f}                      ║")
    lines.append(f"║  Max Drawdown:     {metrics.get('max_drawdown_pct', 0):>9.2f}%                     ║")

    lines.append("╠══════════════════════════════════════════════════════╣")

    # ── P&L ──────────────────────────────────────────────────────────
    total_pnl = metrics.get('total_pnl_pips', 0)
    pnl_icon = "+" if total_pnl >= 0 else ""
    lines.append("║  PROFIT & LOSS                                        ║")
    lines.append("║  ─────────────────────────────────────────────────  ║")
    lines.append(f"║  Total P&L:        {pnl_icon}{total_pnl:>8.2f} pips                ║")
    lines.append(f"║  Equity Current:   ${metrics.get('equity_current', 10000):>10.2f}                   ║")
    lines.append(f"║  Equity Peak:      ${metrics.get('equity_peak', 10000):>10.2f}                   ║")

    lines.append("╠══════════════════════════════════════════════════════╣")

    # ── Sniper ───────────────────────────────────────────────────────
    lines.append("║  SNIPER PERFORMANCE                                   ║")
    lines.append("║  ─────────────────────────────────────────────────  ║")
    lines.append(f"║  Signals Generated: {metrics.get('sniper_signals', 0):>8}                      ║")
    lines.append(f"║  Executed:          {metrics.get('sniper_executions', 0):>8}                      ║")
    lines.append(f"║  Hit Rate:          {metrics.get('sniper_hit_rate_pct', 0):>7.2f}%                     ║")

    lines.append("╠══════════════════════════════════════════════════════╣")

    # ── Footer ───────────────────────────────────────────────────────
    last_updated = metrics.get('last_updated', 'N/A')
    if len(last_updated) > 45:
        last_updated = last_updated[:42] + "..."
    lines.append(f"║  Last Updated: {last_updated:<40} ║")
    lines.append("╚══════════════════════════════════════════════════════╝")

    return "\n".join(lines)


def print_empty_state():
    """Print a message when no data is available."""
    print()
    print("╔══════════════════════════════════════════════════════╗")
    print("║        OMNI BRAIN V35 — PERFORMANCE METRICS        ║")
    print("╠══════════════════════════════════════════════════════╣")
    print("║                                                      ║")
    print("║  No trade data yet.                                  ║")
    print("║                                                      ║")
    print("║  The system is in stress-test mode.                  ║")
    print("║  Metrics will appear after the first trades execute. ║")
    print("║                                                      ║")
    print("╚══════════════════════════════════════════════════════╝")
    print()


def main():
    """Entry point for metrics monitor CLI."""
    parser = argparse.ArgumentParser(description="OMNI BRAIN V35 Metrics Monitor")
    parser.add_argument("--watch", action="store_true", help="Refresh every 30 seconds")
    parser.add_argument("--interval", type=int, default=30, help="Refresh interval in seconds")
    args = parser.parse_args()

    try:
        mc = get_metrics_collector()
    except Exception as e:
        print(f"Error initializing MetricsCollector: {e}")
        sys.exit(1)

    if args.watch:
        print("Watching metrics (Ctrl+C to stop)...\n")
        try:
            while True:
                metrics = mc.get_metrics()
                if metrics.get('total_trades', 0) == 0:
                    print_empty_state()
                else:
                    print("\033[2J\033[H")  # Clear screen
                    print(format_table(metrics))
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nMonitor stopped.")
    else:
        metrics = mc.get_metrics()
        if metrics.get('total_trades', 0) == 0:
            print_empty_state()
        else:
            print(format_table(metrics))


if __name__ == "__main__":
    main()
