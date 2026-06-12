"""
═══════════════════════════════════════════════════════════════════════════════
BOTTLENECK ANALYZER — Institutional Strategy Pipeline Diagnostics
Identifies exactly where your edge degrades through the confluence chain
═══════════════════════════════════════════════════════════════════════════════
"""

import pandas as pd
import numpy as np
from collections import defaultdict
import os

# ══════════════════════════════════════════════════════════════════════════════
# COLOR OUTPUT
# ══════════════════════════════════════════════════════════════════════════════

class C:
    GREEN  = '\033[92m'
    YELLOW = '\033[93m'
    RED    = '\033[91m'
    CYAN   = '\033[96m'
    BOLD   = '\033[1m'
    DIM    = '\033[2m'
    RESET  = '\033[0m'

BLOCKS = [' ', '░', '▒', '▓', '█']

def color_block(value, min_val, max_val):
    if max_val == min_val:
        return C.YELLOW, BLOCKS[2]
    norm = (value - min_val) / (max_val - min_val)
    if norm > 0.7:   return C.GREEN, BLOCKS[4]
    if norm > 0.5:   return C.GREEN, BLOCKS[3]
    if norm > 0.3:   return C.YELLOW, BLOCKS[2]
    if norm > 0.1:   return C.RED, BLOCKS[1]
    return C.RED, BLOCKS[0]

# ══════════════════════════════════════════════════════════════════════════════
# DATA LOADER
# ══════════════════════════════════════════════════════════════════════════════

def load_trades(filepath):
    """Load trade log with flexible column detection"""
    df = pd.read_csv(filepath)
    
    # Normalize column names
    df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')
    
    # Auto-detect PnL column
    pnl_cols = [c for c in df.columns if 'pnl' in c or 'profit' in c]
    if pnl_cols:
        df['net_pnl'] = pd.to_numeric(df[pnl_cols[0]], errors='coerce').fillna(0)
    
    # Auto-detect outcome column
    if 'outcome' not in df.columns:
        df['outcome'] = df['net_pnl'].apply(lambda x: 'WIN' if x > 0 else 'LOSS' if x < 0 else 'BE')
    
    return df

# ══════════════════════════════════════════════════════════════════════════════
# CORE: PIPELINE BOTTLENECK ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

def analyze_bottleneck(df, steps=None):
    """
    Analyze win rate degradation through the confluence pipeline.
    Returns metrics for each step: win rate, count, avg PnL, drop-off from previous step.
    """
    if steps is None:
        # Auto-detect success columns
        steps = [c.replace('_success', '') for c in df.columns if c.endswith('_success')]
        if not steps:
            # Fallback: use common institutional structure steps
            steps = ['htf_sweep', 'htf_mss', 'fvg_retest', 'm1_sweep', 'm1_displacement', 'm1_fvg']
    
    results = []
    prev_winrate = None
    
    for step in steps:
        col = f'{step}_success'
        
        if col not in df.columns:
            results.append({
                'step': step,
                'win_rate': None,
                'count': 0,
                'avg_pnl': None,
                'total_pnl': None,
                'drop_off': None,
                'status': 'MISSING'
            })
            continue
        
        subset = df[df[col] == 1]
        count = len(subset)
        
        if count == 0:
            results.append({
                'step': step,
                'win_rate': 0,
                'count': 0,
                'avg_pnl': 0,
                'total_pnl': 0,
                'drop_off': None,
                'status': 'NO_DATA'
            })
            continue
        
        winrate = (subset['net_pnl'] > 0).mean() * 100
        avg_pnl = subset['net_pnl'].mean()
        total_pnl = subset['net_pnl'].sum()
        
        drop_off = None
        if prev_winrate is not None and prev_winrate > 0:
            drop_off = winrate - prev_winrate
        
        results.append({
            'step': step,
            'win_rate': winrate,
            'count': count,
            'avg_pnl': avg_pnl,
            'total_pnl': total_pnl,
            'drop_off': drop_off,
            'status': 'OK'
        })
        
        prev_winrate = winrate
    
    return pd.DataFrame(results)

# ══════════════════════════════════════════════════════════════════════════════
# CORE: LEAKAGE ANALYSIS (Trades that passed but still lost)
# ══════════════════════════════════════════════════════════════════════════════

def analyze_leakage(df, steps):
    """
    Find trades that passed ALL filters but still lost money.
    These are 'false positives' — the system thinks they're valid but they aren't.
    """
    # Build filter for trades that passed all steps
    all_pass = pd.Series(True, index=df.index)
    for step in steps:
        col = f'{step}_success'
        if col in df.columns:
            all_pass &= (df[col] == 1)
    
    passed = df[all_pass]
    lost = passed[passed['net_pnl'] <= 0]
    
    if len(lost) == 0:
        return None
    
    # Analyze what's different about losing trades that passed all filters
    analysis = {
        'total_passed': len(passed),
        'lost_after_pass': len(lost),
        'leakage_rate': (len(lost) / len(passed) * 100) if len(passed) > 0 else 0,
        'avg_loss': lost['net_pnl'].mean(),
        'max_loss': lost['net_pnl'].min(),
    }
    
    # If regime data available, check if losses cluster in specific regimes
    if 'regime' in df.columns:
        regime_loss = lost.groupby('regime')['net_pnl'].agg(['count', 'mean', 'sum'])
        analysis['regime_breakdown'] = regime_loss
    
    # If time data available, check if losses cluster at specific hours
    if 'hour' in df.columns:
        hour_loss = lost.groupby('hour')['net_pnl'].agg(['count', 'mean'])
        analysis['hour_breakdown'] = hour_loss
    
    return analysis

# ══════════════════════════════════════════════════════════════════════════════
# CORE: CONDITIONAL WIN RATE MATRIX
# ══════════════════════════════════════════════════════════════════════════════

def conditional_matrix(df, steps):
    """
    Build a matrix showing win rate for every combination of conditions.
    Answers: "What happens when Step A is true but Step B is false?"
    """
    results = []
    
    for i, step_a in enumerate(steps):
        for j, step_b in enumerate(steps):
            if i >= j:
                continue
            
            col_a = f'{step_a}_success'
            col_b = f'{step_b}_success'
            
            if col_a not in df.columns or col_b not in df.columns:
                continue
            
            # A=true, B=true
            both = df[(df[col_a] == 1) & (df[col_b] == 1)]
            # A=true, B=false
            a_only = df[(df[col_a] == 1) & (df[col_b] == 0)]
            # A=false, B=true
            b_only = df[(df[col_a] == 0) & (df[col_b] == 1)]
            
            for label, subset in [('A+B', both), ('A only', a_only), ('B only', b_only)]:
                if len(subset) > 0:
                    wr = (subset['net_pnl'] > 0).mean() * 100
                    avg = subset['net_pnl'].mean()
                else:
                    wr = None
                    avg = None
                
                results.append({
                    'condition_a': step_a,
                    'condition_b': step_b,
                    'combination': label,
                    'count': len(subset),
                    'win_rate': wr,
                    'avg_pnl': avg
                })
    
    return pd.DataFrame(results)

# ══════════════════════════════════════════════════════════════════════════════
# RENDERERS
# ══════════════════════════════════════════════════════════════════════════════

def render_pipeline(bottleneck_df):
    """Render the pipeline waterfall"""
    print(f"\n{'═' * 70}")
    print(f"  {C.BOLD}CONFLUENCE PIPELINE — Win Rate Waterfall{C.RESET}")
    print(f"{'═' * 70}\n")
    
    print(f"  {'Step':<20} {'Win Rate':>10} {'Count':>8} {'Avg PnL':>10} {'Drop':>8} {'Status':>10}")
    print(f"  {'─' * 70}")
    
    max_wr = bottleneck_df['win_rate'].max() if not bottleneck_df['win_rate'].isna().all() else 100
    min_wr = bottleneck_df['win_rate'].min() if not bottleneck_df['win_rate'].isna().all() else 0
    
    for _, row in bottleneck_df.iterrows():
        step = row['step']
        wr = row['win_rate']
        count = row['count']
        avg_pnl = row['avg_pnl']
        drop = row['drop_off']
        status = row['status']
        
        if status == 'MISSING':
            print(f"  {C.DIM}{step:<20} {'—':>10} {'—':>8} {'—':>10} {'—':>8} {C.YELLOW}MISSING{C.RESET}")
            continue
        
        if count == 0:
            print(f"  {C.DIM}{step:<20} {'0%':>10} {'0':>8} {'—':>10} {'—':>8} {C.RED}NO DATA{C.RESET}")
            continue
        
        # Color win rate
        if wr >= 60:
            wr_color = C.GREEN
        elif wr >= 45:
            wr_color = C.YELLOW
        else:
            wr_color = C.RED
        
        # Color drop-off
        drop_str = '—'
        drop_color = C.DIM
        if drop is not None:
            if drop < -10:
                drop_color = C.RED
                drop_str = f'{C.RED}{drop:+.1f}%{C.RESET}'
            elif drop < 0:
                drop_color = C.YELLOW
                drop_str = f'{C.YELLOW}{drop:+.1f}%{C.RESET}'
            else:
                drop_color = C.GREEN
                drop_str = f'{C.GREEN}{drop:+.1f}%{C.RESET}'
        
        # Color PnL
        pnl_color = C.GREEN if avg_pnl > 0 else C.RED if avg_pnl < 0 else C.DIM
        
        # Visual bar
        color, block = color_block(wr, min_wr, max_wr)
        bar = f'{color}{block * int(wr / 5)}{C.RESET}'
        
        print(f"  {step:<20} {wr_color}{wr:>9.1f}%{C.RESET} {count:>8} {pnl_color}${avg_pnl:>8.2f}{C.RESET} {drop_str:>20} {bar}")
    
    # Identify biggest drop
    drops = bottleneck_df[bottleneck_df['drop_off'].notna()]
    if not drops.empty:
        worst = drops.loc[drops['drop_off'].idxmin()]
        print(f"\n  {C.RED}{C.BOLD}⚠ BIGGEST DROP: {worst['step']} ({worst['drop_off']:+.1f}%){C.RESET}")
        print(f"  {C.DIM}This is your weakest link. Focus optimization here.{C.RESET}")

def render_leakage(leakage):
    """Render leakage analysis"""
    if leakage is None:
        print(f"\n  {C.GREEN}✔ No leakage detected — all trades that passed filters were profitable{C.RESET}")
        return
    
    print(f"\n{'═' * 70}")
    print(f"  {C.BOLD}LEAKAGE ANALYSIS — False Positives{C.RESET}")
    print(f"{'═' * 70}\n")
    
    print(f"  Trades that passed ALL filters:  {leakage['total_passed']}")
    print(f"  But still lost money:            {leakage['lost_after_pass']} {C.RED}({leakage['leakage_rate']:.1f}%){C.RESET}")
    print(f"  Average loss when leaking:       {C.RED}${leakage['avg_loss']:.2f}{C.RESET}")
    print(f"  Maximum single loss:             {C.RED}${leakage['max_loss']:.2f}{C.RESET}")
    
    if 'regime_breakdown' in leakage:
        print(f"\n  Regime Breakdown of Leaking Trades:")
        for regime, row in leakage['regime_breakdown'].iterrows():
            print(f"    {regime:<15} Count: {int(row['count']):>5}  Avg Loss: ${row['mean']:>8.2f}")
    
    if 'hour_breakdown' in leakage:
        print(f"\n  Hour Breakdown of Leaking Trades:")
        for hour, row in leakage['hour_breakdown'].iterrows():
            print(f"    {int(hour):02d}:00          Count: {int(row['count']):>5}  Avg Loss: ${row['mean']:>8.2f}")

# ══════════════════════════════════════════════════════════════════════════════
# RECOMMENDATIONS ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def generate_recommendations(bottleneck_df, leakage=None):
    """Generate actionable recommendations based on analysis"""
    print(f"\n{'═' * 70}")
    print(f"  {C.BOLD}RECOMMENDATIONS{C.RESET}")
    print(f"{'═' * 70}\n")
    
    recs = []
    
    # 1. Biggest drop-off
    drops = bottleneck_df[bottleneck_df['drop_off'].notna()]
    if not drops.empty:
        worst = drops.loc[drops['drop_off'].idxmin()]
        recs.append({
            'priority': 'HIGH',
            'area': worst['step'],
            'issue': f"Win rate drops {worst['drop_off']:.1f}% at this step",
            'action': f"Investigate why {worst['step']} is degrading signals. Consider tightening the filter or adding a secondary confirmation."
        })
    
    # 2. Steps with low win rate
    low_wr = bottleneck_df[(bottleneck_df['win_rate'].notna()) & (bottleneck_df['win_rate'] < 45)]
    for _, row in low_wr.iterrows():
        recs.append({
            'priority': 'HIGH',
            'area': row['step'],
            'issue': f"Win rate is only {row['win_rate']:.1f}% (below 45%)",
            'action': f"The {row['step']} filter is letting through too many losing trades. Tighten parameters or add volume/ATR confirmation."
        })
    
    # 3. Steps with zero data
    missing = bottleneck_df[bottleneck_df['status'] == 'MISSING']
    for _, row in missing.iterrows():
        recs.append({
            'priority': 'MEDIUM',
            'area': row['step'],
            'issue': f"No data column found for {row['step']}_success",
            'action': f"Add '{row['step']}_success' column to your trade log to enable full pipeline tracking."
        })
    
    # 4. Leakage
    if leakage and leakage['leakage_rate'] > 20:
        recs.append({
            'priority': 'HIGH',
            'area': 'PIPELINE',
            'issue': f"{leakage['leakage_rate']:.1f}% of trades pass all filters but still lose",
            'action': "Your filters are not discriminative enough. Add a regime filter or news filter to reduce false positives."
        })
    
    # 5. Print recommendations
    for i, rec in enumerate(recs, 1):
        priority_color = C.RED if rec['priority'] == 'HIGH' else C.YELLOW
        print(f"  {priority_color}[{rec['priority']}]{C.RESET} {rec['area']}")
        print(f"    Issue:   {rec['issue']}")
        print(f"    Action:  {C.CYAN}{rec['action']}{C.RESET}")
        print()
    
    if not recs:
        print(f"  {C.GREEN}✔ No critical issues found. Pipeline looks healthy.{C.RESET}")

# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main(filepath='trade_logs.csv'):
    print(f"\n{'═' * 70}")
    print(f"  {C.BOLD}INSTITUTIONAL STRATEGY — BOTTLENECK DIAGNOSTICS{C.RESET}")
    print(f"{'═' * 70}\n")
    
    if not os.path.exists(filepath):
        print(f"  {C.RED}[ERROR] File not found: {filepath}{C.RESET}")
        print(f"  Generate trade logs with your validation bridge first.")
        return
    
    df = load_trades(filepath)
    print(f"  Loaded {len(df)} trades from {filepath}")
    
    # Auto-detect steps from columns
    success_cols = [c for c in df.columns if c.endswith('_success')]
    if success_cols:
        steps = [c.replace('_success', '') for c in success_cols]
        print(f"  Detected pipeline steps: {', '.join(steps)}")
    else:
        steps = ['htf_sweep', 'htf_mss', 'fvg_retest', 'm1_sweep', 'm1_displacement', 'm1_fvg']
        print(f"  Using default steps: {', '.join(steps)}")
    
    # 1. Pipeline bottleneck analysis
    bottleneck_df = analyze_bottleneck(df, steps)
    render_pipeline(bottleneck_df)
    
    # 2. Leakage analysis
    leakage = analyze_leakage(df, steps)
    render_leakage(leakage)
    
    # 3. Recommendations
    generate_recommendations(bottleneck_df, leakage)
    
    # 4. Export
    os.makedirs('./reports', exist_ok=True)
    bottleneck_df.to_csv('./reports/bottleneck_analysis.csv', index=False)
    print(f"\n  {C.DIM}Report exported to ./reports/bottleneck_analysis.csv{C.RESET}")
    print(f"{'═' * 70}\n")

if __name__ == '__main__':
    import sys
    filepath = sys.argv[1] if len(sys.argv) > 1 else 'trade_logs.csv'
    main(filepath)
