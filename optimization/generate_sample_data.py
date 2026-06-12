"""
═══════════════════════════════════════════════════════════════════════════════
SAMPLE DATA GENERATOR — Creates realistic trade_logs.csv for testing
═══════════════════════════════════════════════════════════════════════════════
"""

import csv
import random
from datetime import datetime, timedelta

random.seed(42)

STEPS = ['htf_sweep', 'htf_mss', 'fvg_retest', 'm1_sweep', 'm1_displacement', 'm1_fvg']
REGIMES = ['TRENDING', 'RANGING', 'TRANSITIONING']
HOURS = list(range(13, 17))  # 13:00-16:00 GMT

def generate_trade(trade_id, start_time):
    """Generate a single realistic trade record"""
    
    # Each step has a probability of success
    # Realistic: earlier steps have higher pass rates, later steps filter more
    step_probs = {
        'htf_sweep':       0.85,
        'htf_mss':         0.70,
        'fvg_retest':      0.60,
        'm1_sweep':        0.55,
        'm1_displacement': 0.50,
        'm1_fvg':          0.45,
    }
    
    # Track which steps passed
    passed_steps = {}
    all_passed = True
    
    for step in STEPS:
        if all_passed:
            # Probability decreases as more steps pass (realistic pipeline)
            passed = random.random() < step_probs[step]
            passed_steps[f'{step}_success'] = 1 if passed else 0
            if not passed:
                all_passed = False
        else:
            passed_steps[f'{step}_success'] = 0
    
    # Regime affects win rate
    regime = random.choice(REGIMES)
    regime_win_bonus = {
        'TRENDING': 0.15,
        'RANGING': -0.10,
        'TRANSITIONING': 0.0
    }
    
    # Base win rate if all steps passed
    base_win_rate = 0.55 + regime_win_bonus[regime]
    
    # Calculate PnL
    if all_passed:
        # All steps passed — higher chance of win
        is_win = random.random() < base_win_rate
    else:
        # Partial pipeline — lower chance of win
        steps_passed = sum(1 for v in passed_steps.values() if v == 1)
        partial_win_rate = 0.30 + (steps_passed / len(STEPS)) * 0.25
        is_win = random.random() < partial_win_rate
    
    if is_win:
        pnl = random.uniform(50, 500)  # Win: $50-$500
    else:
        pnl = random.uniform(-300, -20)  # Loss: -$20-$300
    
    # Slippage (higher in ranging markets)
    base_slippage = 0.15
    if regime == 'RANGING':
        slippage = base_slippage + random.uniform(0.1, 0.4)
    else:
        slippage = base_slippage + random.uniform(0, 0.2)
    
    # Latency
    latency = random.uniform(20, 150)
    
    # Entry time
    entry_time = start_time + timedelta(
        days=random.randint(0, 30),
        hours=random.choice(HOURS),
        minutes=random.randint(0, 59),
        seconds=random.randint(0, 59)
    )
    
    # Entry/exit prices
    entry_price = 2300 + random.uniform(-50, 50)
    stop_distance = random.uniform(3, 8)
    
    if is_win:
        exit_price = entry_price + (stop_distance * random.uniform(1.0, 2.5))
    else:
        exit_price = entry_price - stop_distance
    
    return {
        'trade_id': trade_id,
        'timestamp': entry_time.isoformat(),
        'symbol': 'XAUUSD',
        'side': random.choice(['Long', 'Short']),
        'regime': regime,
        'entry_price': round(entry_price, 2),
        'exit_price': round(exit_price, 2),
        'stop_loss': round(entry_price - stop_distance if random.random() > 0.5 else entry_price + stop_distance, 2),
        'position_size': random.choice([1, 2, 3]),
        'net_pnl': round(pnl, 2),
        'slippage_points': round(slippage, 2),
        'execution_latency_ms': round(latency, 1),
        'outcome': 'WIN' if is_win else 'LOSS',
        'exit_reason': random.choice(['TP', 'SL', 'BE', 'TIME']),
        **passed_steps
    }

def main():
    trades = []
    start_time = datetime(2026, 5, 1)
    
    for i in range(1, 151):
        trades.append(generate_trade(i, start_time))
    
    # Write CSV
    fieldnames = list(trades[0].keys())
    with open('trade_logs.csv', 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(trades)
    
    # Summary
    total = len(trades)
    wins = sum(1 for t in trades if t['outcome'] == 'WIN')
    total_pnl = sum(t['net_pnl'] for t in trades)
    
    print(f"Generated {total} trades → trade_logs.csv")
    print(f"  Win Rate: {wins/total*100:.1f}%")
    print(f"  Total PnL: ${total_pnl:.2f}")
    print(f"  Steps tracked: {', '.join(STEPS)}")

if __name__ == '__main__':
    main()
