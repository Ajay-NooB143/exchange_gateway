"""
═══════════════════════════════════════════════════════════════════════════════
POST-TRADE ANALYSIS — Entry Time vs Win Rate Heatmap
Parses trade logs and creates institutional performance heatmaps
═══════════════════════════════════════════════════════════════════════════════

Usage:
    python analyze_trades.py
    
Output:
    - heatmaps/entry_time_winrate.png
    - heatmaps/regime_performance.png
    - heatmaps/day_of_week_pnl.png
    - reports/summary.txt
"""

import csv
import os
from collections import defaultdict
from datetime import datetime

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

TRADE_LOG = './logs/trades.csv'
OUTPUT_DIR = './reports'
HEATMAP_DIR = './heatmaps'

# ══════════════════════════════════════════════════════════════════════════════
# TRADE LOADER
# ══════════════════════════════════════════════════════════════════════════════

def load_trades(filepath):
    """Load trades from CSV log"""
    trades = []
    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                trade = {
                    'trade_id':      int(row.get('trade_id', 0)),
                    'timestamp':     row.get('timestamp', ''),
                    'symbol':        row.get('symbol', ''),
                    'side':          row.get('side', ''),
                    'regime':        row.get('regime', 'UNKNOWN'),
                    'entry_price':   float(row.get('entry_price', 0)),
                    'exit_price':    float(row.get('exit_price', 0) or 0),
                    'stop_loss':     float(row.get('stop_loss', 0)),
                    'position_size': int(row.get('position_size', 0)),
                    'pnl':           float(row.get('pnl_dollars', 0) or 0),
                    'slippage':      float(row.get('slippage_points', 0) or 0),
                    'latency_ms':    float(row.get('execution_latency_ms', 0) or 0),
                    'outcome':       row.get('outcome', ''),
                    'exit_reason':   row.get('exit_reason', ''),
                }
                if trade['timestamp']:
                    trade['dt'] = datetime.fromisoformat(trade['timestamp'].replace('Z', '+00:00'))
                    trade['hour'] = trade['dt'].hour
                    trade['day_of_week'] = trade['dt'].strftime('%A')
                    trades.append(trade)
            except (ValueError, KeyError) as e:
                continue
    return trades

# ══════════════════════════════════════════════════════════════════════════════
# ASCII HEATMAP RENDERER (no matplotlib dependency)
# ══════════════════════════════════════════════════════════════════════════════

# Color codes for terminal
COLORS = {
    'high':   '\033[92m',  # Green
    'mid':    '\033[93m',  # Yellow
    'low':    '\033[91m',  # Red
    'reset':  '\033[0m',
    'bold':   '\033[1m',
    'dim':    '\033[2m',
}

BLOCKS = [' ', '░', '▒', '▓', '█']

def get_color_and_block(value, min_val, max_val):
    """Map a value to a color and block character"""
    if max_val == min_val:
        return COLORS['mid'], BLOCKS[2]
    
    normalized = (value - min_val) / (max_val - min_val)
    
    if normalized > 0.7:
        return COLORS['high'], BLOCKS[4]
    elif normalized > 0.5:
        return COLORS['high'], BLOCKS[3]
    elif normalized > 0.3:
        return COLORS['mid'], BLOCKS[2]
    elif normalized > 0.1:
        return COLORS['low'], BLOCKS[1]
    else:
        return COLORS['low'], BLOCKS[0]

def render_ascii_heatmap(data, title, row_labels, col_labels, cell_format="{:.1f}"):
    """Render an ASCII heatmap to terminal and file"""
    lines = []
    lines.append(f"\n{'═' * 60}")
    lines.append(f"  {title}")
    lines.append(f"{'═' * 60}\n")
    
    # Find min/max
    all_vals = [v for row in data for v in row if v is not None]
    if not all_vals:
        lines.append("  No data available\n")
        return '\n'.join(lines)
    
    min_val = min(all_vals)
    max_val = max(all_vals)
    
    # Column headers
    header = f"{'':>12} " + " ".join(f"{c:>6}" for c in col_labels)
    lines.append(header)
    lines.append(f"{'─' * len(header)}")
    
    # Rows
    for i, (label, row) in enumerate(zip(row_labels, data)):
        cells = []
        for v in row:
            if v is None:
                cells.append(f"{COLORS['dim']}   -- {COLORS['reset']}")
            else:
                color, block = get_color_and_block(v, min_val, max_val)
                cells.append(f"{color}{cell_format.format(v):>5}{block}{COLORS['reset']}")
        
        line = f"{label:>12} " + " ".join(cells)
        lines.append(line)
    
    lines.append(f"\n  Legend: {COLORS['low']} Low {COLORS['mid']} Medium {COLORS['high']} High {COLORS['reset']}")
    lines.append(f"  Range: {min_val:.1f} — {max_val:.1f}")
    lines.append("")
    
    return '\n'.join(lines)

# ══════════════════════════════════════════════════════════════════════════════
# ANALYSIS FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def entry_time_winrate_heatmap(trades):
    """Create Entry Time vs Win Rate heatmap"""
    # Group by hour
    hourly = defaultdict(lambda: {'wins': 0, 'total': 0, 'pnl': 0})
    
    for t in trades:
        h = t['hour']
        hourly[h]['total'] += 1
        if t['outcome'] == 'WIN':
            hourly[h]['wins'] += 1
        hourly[h]['pnl'] += t['pnl']
    
    hours = list(range(24))
    win_rates = []
    pnls = []
    counts = []
    
    for h in hours:
        if hourly[h]['total'] > 0:
            wr = (hourly[h]['wins'] / hourly[h]['total']) * 100
            win_rates.append(wr)
            pnls.append(hourly[h]['pnl'])
            counts.append(hourly[h]['total'])
        else:
            win_rates.append(None)
            pnls.append(None)
            counts.append(None)
    
    # Render
    hour_labels = [f"{h:02d}:00" for h in hours]
    
    print(render_ascii_heatmap(
        [win_rates],
        "ENTRY TIME vs WIN RATE (%)",
        ["Win Rate"],
        hour_labels,
        "{:.1f}%"
    ))
    
    print(render_ascii_heatmap(
        [pnls],
        "ENTRY TIME vs P&L ($)",
        ["P&L"],
        hour_labels,
        "${:.0f}"
    ))
    
    return hourly

def regime_performance(trades):
    """Analyze performance by market regime"""
    regimes = defaultdict(lambda: {'wins': 0, 'total': 0, 'pnl': 0, 'slippage': []})
    
    for t in trades:
        r = t['regime']
        regimes[r]['total'] += 1
        if t['outcome'] == 'WIN':
            regimes[r]['wins'] += 1
        regimes[r]['pnl'] += t['pnl']
        regimes[r]['slippage'].append(t['slippage'])
    
    print(f"\n{'═' * 60}")
    print("  REGIME PERFORMANCE ANALYSIS")
    print(f"{'═' * 60}\n")
    
    print(f"  {'Regime':<15} {'Trades':>8} {'Win Rate':>10} {'Total P&L':>12} {'Avg Slippage':>14}")
    print(f"  {'─' * 60}")
    
    for regime, data in sorted(regimes.items()):
        wr = (data['wins'] / data['total'] * 100) if data['total'] > 0 else 0
        avg_slip = sum(data['slippage']) / len(data['slippage']) if data['slippage'] else 0
        
        # Color code
        color = COLORS['high'] if data['pnl'] > 0 else COLORS['low']
        reset = COLORS['reset']
        
        print(f"  {color}{regime:<15}{reset} {data['total']:>8} {wr:>9.1f}% ${data['pnl']:>10,.2f} {avg_slip:>12.2f}pts")
    
    print()

def day_of_week_analysis(trades):
    """Performance by day of week"""
    daily = defaultdict(lambda: {'wins': 0, 'total': 0, 'pnl': 0})
    
    day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    
    for t in trades:
        d = t['day_of_week']
        daily[d]['total'] += 1
        if t['outcome'] == 'WIN':
            daily[d]['wins'] += 1
        daily[d]['pnl'] += t['pnl']
    
    data = []
    labels = []
    for day in day_order:
        if daily[day]['total'] > 0:
            wr = (daily[day]['wins'] / daily[day]['total']) * 100
            data.append([wr, daily[day]['pnl']])
            labels.append(day[:3])
        else:
            data.append([None, None])
            labels.append(day[:3])
    
    print(render_ascii_heatmap(
        [row[0] for row in data],
        "DAY OF WEEK vs WIN RATE (%)",
        ["Win Rate"],
        labels,
        "{:.1f}%"
    ))

def risk_metrics(trades):
    """Calculate comprehensive risk metrics"""
    if not trades:
        return
    
    pnls = [t['pnl'] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    
    total_pnl = sum(pnls)
    win_rate = len(wins) / len(pnls) * 100
    
    gross_profit = sum(wins) if wins else 0
    gross_loss = abs(sum(losses)) if losses else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    
    # Expectancy
    expectancy = total_pnl / len(pnls) if pnls else 0
    
    # Max drawdown
    peak = 0
    max_dd = 0
    running = 0
    for p in pnls:
        running += p
        if running > peak:
            peak = running
        dd = peak - running
        if dd > max_dd:
            max_dd = dd
    
    # Sharpe-like ratio (simplified)
    import statistics
    if len(pnls) > 1:
        std_dev = statistics.stdev(pnls)
        sharpe = (expectancy / std_dev) * (252 ** 0.5) if std_dev > 0 else 0
    else:
        sharpe = 0
    
    # Slippage analysis
    slippages = [t['slippage'] for t in trades if t['slippage'] > 0]
    avg_slippage = sum(slippages) / len(slippages) if slippages else 0
    max_slippage = max(slippages) if slippages else 0
    
    # Latency analysis
    latencies = [t['latency_ms'] for t in trades if t['latency_ms'] > 0]
    avg_latency = sum(latencies) / len(latencies) if latencies else 0
    max_latency = max(latencies) if latencies else 0
    
    print(f"\n{'═' * 60}")
    print("  RISK METRICS & EXECUTION QUALITY")
    print(f"{'═' * 60}\n")
    
    print(f"  {'Metric':<30} {'Value':>20}")
    print(f"  {'─' * 52}")
    print(f"  {'Total Trades':<30} {len(trades):>20}")
    print(f"  {'Win Rate':<30} {win_rate:>19.1f}%")
    print(f"  {'Total P&L':<30} ${total_pnl:>18,.2f}")
    print(f"  {'Profit Factor':<30} {profit_factor:>20.2f}")
    print(f"  {'Expectancy per Trade':<30} ${expectancy:>18,.2f}")
    print(f"  {'Max Drawdown':<30} ${max_dd:>18,.2f}")
    print(f"  {'Sharpe Ratio (annualized)':<30} {sharpe:>20.2f}")
    print(f"  {'─' * 52}")
    print(f"  {'Avg Slippage':<30} {avg_slippage:>18.2f} pts")
    print(f"  {'Max Slippage':<30} {max_slippage:>18.2f} pts")
    print(f"  {'Avg Execution Latency':<30} {avg_latency:>17.0f} ms")
    print(f"  {'Max Execution Latency':<30} {max_latency:>17.0f} ms")
    print()

# ══════════════════════════════════════════════════════════════════════════════
# MATPLOTLIB HEATMAP (optional — if installed)
# ══════════════════════════════════════════════════════════════════════════════

def create_matplotlib_heatmap(trades):
    """Create PNG heatmap using matplotlib (optional)"""
    try:
        import matplotlib
        matplotlib.use('Agg')  # Non-interactive backend
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("  [INFO] matplotlib not installed — skipping PNG heatmaps")
        print("  Install with: pip install matplotlib")
        return
    
    os.makedirs(HEATMAP_DIR, exist_ok=True)
    
    # Entry time vs Win Rate heatmap
    hourly = defaultdict(lambda: {'wins': 0, 'total': 0})
    for t in trades:
        h = t['hour']
        hourly[h]['total'] += 1
        if t['outcome'] == 'WIN':
            hourly[h]['wins'] += 1
    
    hours = list(range(24))
    win_rates = []
    for h in hours:
        if hourly[h]['total'] > 0:
            win_rates.append((hourly[h]['wins'] / hourly[h]['total']) * 100)
        else:
            win_rates.append(0)
    
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    fig.suptitle('Institutional Sniper — Performance Analysis', fontsize=14, fontweight='bold')
    
    # 1. Win Rate by Hour
    ax1 = axes[0, 0]
    colors = ['#2ecc71' if wr > 55 else '#f39c12' if wr > 45 else '#e74c3c' for wr in win_rates]
    ax1.bar(hours, win_rates, color=colors, edgecolor='white', linewidth=0.5)
    ax1.axhline(y=50, color='gray', linestyle='--', alpha=0.5)
    ax1.set_xlabel('Hour (GMT)')
    ax1.set_ylabel('Win Rate (%)')
    ax1.set_title('Win Rate by Entry Hour')
    ax1.set_xticks(range(0, 24, 2))
    ax1.set_ylim(0, 100)
    
    # 2. P&L by Hour
    ax2 = axes[0, 1]
    hourly_pnl = defaultdict(float)
    for t in trades:
        hourly_pnl[t['hour']] += t['pnl']
    pnl_values = [hourly_pnl.get(h, 0) for h in hours]
    colors = ['#2ecc71' if p > 0 else '#e74c3c' for p in pnl_values]
    ax2.bar(hours, pnl_values, color=colors, edgecolor='white', linewidth=0.5)
    ax2.axhline(y=0, color='gray', linestyle='-', alpha=0.5)
    ax2.set_xlabel('Hour (GMT)')
    ax2.set_ylabel('P&L ($)')
    ax2.set_title('P&L by Entry Hour')
    ax2.set_xticks(range(0, 24, 2))
    
    # 3. Regime Performance
    ax3 = axes[1, 0]
    regimes = defaultdict(lambda: {'pnl': 0, 'count': 0})
    for t in trades:
        regimes[t['regime']]['pnl'] += t['pnl']
        regimes[t['regime']]['count'] += 1
    
    regime_names = list(regimes.keys())
    regime_pnl = [regimes[r]['pnl'] for r in regime_names]
    colors = ['#2ecc71' if p > 0 else '#e74c3c' for p in regime_pnl]
    ax3.barh(regime_names, regime_pnl, color=colors, edgecolor='white', linewidth=0.5)
    ax3.axvline(x=0, color='gray', linestyle='-', alpha=0.5)
    ax3.set_xlabel('P&L ($)')
    ax3.set_title('P&L by Market Regime')
    
    # 4. Cumulative P&L
    ax4 = axes[1, 1]
    cumulative = []
    running = 0
    for t in trades:
        running += t['pnl']
        cumulative.append(running)
    ax4.plot(cumulative, color='#3498db', linewidth=1.5)
    ax4.fill_between(range(len(cumulative)), cumulative, alpha=0.3, color='#3498db')
    ax4.axhline(y=0, color='gray', linestyle='--', alpha=0.5)
    ax4.set_xlabel('Trade #')
    ax4.set_ylabel('Cumulative P&L ($)')
    ax4.set_title('Equity Curve')
    
    plt.tight_layout()
    filepath = os.path.join(HEATMAP_DIR, 'performance_analysis.png')
    plt.savefig(filepath, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Heatmap saved: {filepath}")

# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print(f"\n{'═' * 60}")
    print("  INSTITUTIONAL SNIPER — POST-TRADE ANALYSIS")
    print(f"{'═' * 60}\n")
    
    # Load trades
    if not os.path.exists(TRADE_LOG):
        print(f"  [ERROR] Trade log not found: {TRADE_LOG}")
        print("  Run the validation bridge first to generate trade data.")
        return
    
    trades = load_trades(TRADE_LOG)
    if not trades:
        print("  [ERROR] No valid trades found in log.")
        return
    
    print(f"  Loaded {len(trades)} trades from {TRADE_LOG}\n")
    
    # Run analyses
    entry_time_winrate_heatmap(trades)
    regime_performance(trades)
    day_of_week_analysis(trades)
    risk_metrics(trades)
    
    # Create matplotlib heatmaps
    create_matplotlib_heatmap(trades)
    
    print(f"{'═' * 60}")
    print("  Analysis complete.")
    print(f"{'═' * 60}\n")

if __name__ == '__main__':
    main()
