"""
Self-Writing Prompt Generator - OMNI BRAIN V2
==============================================
Generates human-readable prompts after each evolution cycle.
Produces signal detection, entry rules, risk rules, and per-asset prompts.
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from pathlib import Path

log = logging.getLogger('PromptWriter')

BASE_DIR = Path(__file__).parent
LOG_DIR = BASE_DIR / 'logs'
EVOLVED_DIR = LOG_DIR / 'evolved_prompts'
EVOLVED_DIR.mkdir(parents=True, exist_ok=True)

ASSETS = ['XAUUSD', 'EURUSD', 'GBPUSD', 'SP500', 'BTCUSD']

COMPONENT_LABELS = {
    'confidence_scorer': 'Confidence Scorer',
    'pattern_engine': 'Pattern Engine',
    'mtf_confirmation': 'MTF Confirmation',
    'signal_filter': 'Signal Filter',
    'entry_rules': 'Entry Rules',
    'risk_rules': 'Risk Rules',
}


def _format_rule_set(rules: list) -> str:
    if not rules:
        return '  (none)'
    return '\n'.join(f'  {i+1}. {r}' for i, r in enumerate(rules))


def _format_weights(data: dict, skip_keys: set = None) -> str:
    skip = skip_keys or {'rules', 'execute_threshold', 'wait_threshold'}
    items = []
    for k, v in sorted(data.items()):
        if k not in skip and isinstance(v, (int, float)):
            items.append(f'  {k}: {v}')
    return '\n'.join(items) if items else '  (none)'


class PromptWriter:
    """Generates evolved prompts from DNA data."""

    def __init__(self, dna_instance=None):
        if dna_instance is not None:
            self.dna = dna_instance
        else:
            sys.path.insert(0, str(BASE_DIR))
            from prompt_evolution import get_dna
            self.dna = get_dna()

    def generate_signal_detection_prompt(self, generation: int = None) -> str:
        cs = self.dna.get('confidence_scorer') or {}
        pe = self.dna.get('pattern_engine') or {}
        mtf = self.dna.get('mtf_confirmation') or {}
        gen = generation or (cs.get('generation', 1) if cs else 1)
        p = cs.get('prompt', {})
        p_pe = pe.get('prompt', {})
        p_mtf = mtf.get('prompt', {})

        text = (
            f"=== SIGNAL DETECTION PROMPT (Generation {gen}) ===\n\n"
            f"Confidence Scoring Weights:\n"
            f"  OB Weight: {p.get('ob_weight', 20)}\n"
            f"  FVG Weight: {p.get('fvg_weight', 20)}\n"
            f"  Sweep Weight: {p.get('sweep_weight', 30)}\n"
            f"  VWAP Weight: {p.get('vwap_weight', 15)}\n"
            f"  Session Weight: {p.get('session_weight', 15)}\n\n"
            f"Thresholds:\n"
            f"  Execute: >= {p.get('execute_threshold', 75)}/100\n"
            f"  Wait: {p.get('wait_threshold', 50)}-{p.get('execute_threshold', 75)-1}/100\n"
            f"  Block: < {p.get('wait_threshold', 50)}/100\n\n"
            f"Pattern Engine:\n"
            f"  Min Candles: {p_pe.get('min_candles', 12)}\n"
            f"  Min Volume Ratio: {p_pe.get('min_volume_ratio', 1.5)}\n"
            f"  Propulsion Score: {p_pe.get('propulsion_score', 7)}\n"
            f"  Rejection Score: {p_pe.get('rejection_score', 5)}\n\n"
            f"MTF Confirmation:\n"
            f"  M15 Weight: {p_mtf.get('m15_weight', 15)}\n"
            f"  H1 Weight: {p_mtf.get('h1_weight', 30)}\n"
            f"  H4 Weight: {p_mtf.get('h4_weight', 35)}\n"
            f"  D1 Weight: {p_mtf.get('d1_weight', 20)}\n"
            f"  Alignment Bonus: +{p_mtf.get('alignment_bonus', 20)}\n"
            f"  Conflict Penalty: {p_mtf.get('conflict_penalty', -15)}\n\n"
            f"Active Rules:\n"
            f"{_format_rule_set(p.get('rules', []))}\n\n"
            f"Pattern Rules:\n"
            f"{_format_rule_set(p_pe.get('rules', []))}\n\n"
            f"MTF Rules:\n"
            f"{_format_rule_set(p_mtf.get('rules', []))}\n\n"
            f"Fitness: {cs.get('fitness_score', 0.71):.2f} | "
            f"Win Rate: {cs.get('performance', {}).get('win_rate', 0):.0%}\n"
            f"Generated: {datetime.now(timezone.utc).isoformat()}"
        )
        return text

    def generate_entry_rules_prompt(self, generation: int = None) -> str:
        er = self.dna.get('entry_rules') or {}
        gen = generation or (er.get('generation', 1) if er else 1)
        p = er.get('prompt', {})

        text = (
            f"=== ENTRY RULES PROMPT (Generation {gen}) ===\n\n"
            f"Position Management:\n"
            f"  Max Concurrent: {p.get('max_concurrent_trades', 3)}\n"
            f"  Max Daily: {p.get('max_daily_trades', 10)}\n"
            f"  Min Time Between: {p.get('min_time_between_trades', 300)}s\n"
            f"  Max Per Pair: {p.get('max_trades_per_pair', 3)}\n\n"
            f"Entry Rules:\n"
            f"{_format_rule_set(p.get('rules', []))}\n\n"
            f"Performance:\n"
            f"  Fitness: {er.get('fitness_score', 0.70):.2f}\n"
            f"  Win Rate: {er.get('performance', {}).get('win_rate', 0):.0%}\n"
            f"Generated: {datetime.now(timezone.utc).isoformat()}"
        )
        return text

    def generate_risk_rules_prompt(self, generation: int = None) -> str:
        rr = self.dna.get('risk_rules') or {}
        gen = generation or (rr.get('generation', 1) if rr else 1)
        p = rr.get('prompt', {})

        text = (
            f"=== RISK RULES PROMPT (Generation {gen}) ===\n\n"
            f"Risk Parameters:\n"
            f"  Risk Per Trade: {p.get('risk_per_trade_pct', 1.0)}%\n"
            f"  Max Daily Risk: {p.get('max_daily_risk_pct', 3.0)}%\n"
            f"  Max Drawdown: {p.get('max_drawdown_pct', 5.0)}%\n"
            f"  Max Spread: {p.get('max_spread_pips', 3.0)} pips\n\n"
            f"Risk Rules:\n"
            f"{_format_rule_set(p.get('rules', []))}\n\n"
            f"Performance:\n"
            f"  Fitness: {rr.get('fitness_score', 0.75):.2f}\n"
            f"  Win Rate: {rr.get('performance', {}).get('win_rate', 0):.0%}\n"
            f"Generated: {datetime.now(timezone.utc).isoformat()}"
        )
        return text

    def generate_asset_prompt(self, asset: str, generation: int = None) -> str:
        cs = self.dna.get('confidence_scorer') or {}
        rr = self.dna.get('risk_rules') or {}
        gen = generation or cs.get('generation', 1)

        p_cs = cs.get('prompt', {})
        p_rr = rr.get('prompt', {})

        text = (
            f"=== {asset} TRADING PROMPT (Generation {gen}) ===\n\n"
            f"Asset-Specific Configuration:\n\n"
            f"Confidence Weights:\n"
            f"  OB: {p_cs.get('ob_weight', 20)} | "
            f"FVG: {p_cs.get('fvg_weight', 20)} | "
            f"Sweep: {p_cs.get('sweep_weight', 30)}\n"
            f"  VWAP: {p_cs.get('vwap_weight', 15)} | "
            f"Session: {p_cs.get('session_weight', 15)}\n\n"
            f"Thresholds:\n"
            f"  Execute: >= {p_cs.get('execute_threshold', 75)}/100\n"
            f"  Wait: >= {p_cs.get('wait_threshold', 50)}/100\n"
            f"  Block: < {p_cs.get('wait_threshold', 50)}/100\n\n"
            f"Risk:\n"
            f"  Risk Per Trade: {p_rr.get('risk_per_trade_pct', 1.0)}%\n"
            f"  Max Spread: {p_rr.get('max_spread_pips', 3.0)} pips\n\n"
            f"Active Rules:\n"
            f"{_format_rule_set(p_cs.get('rules', []))}\n\n"
            f"Risk Rules:\n"
            f"{_format_rule_set(p_rr.get('rules', []))}\n\n"
            f"Generated: {datetime.now(timezone.utc).isoformat()}"
        )
        return text

    def generate_all(self, generation: int = None) -> Dict[str, str]:
        return {
            'signal_detection': self.generate_signal_detection_prompt(generation),
            'entry_rules': self.generate_entry_rules_prompt(generation),
            'risk_rules': self.generate_risk_rules_prompt(generation),
        }

    def save_all(self, generation: int = None) -> Dict[str, str]:
        prompts = self.generate_all(generation)
        gen = generation or self.dna.get_generation()
        paths = {}
        for name, text in prompts.items():
            path = EVOLVED_DIR / f'{name}_gen{gen}.txt'
            path.write_text(text)
            paths[name] = str(path)
            log.info(f"Saved {name} prompt to {path}")
        for asset in ASSETS:
            text = self.generate_asset_prompt(asset, gen)
            path = EVOLVED_DIR / f'{asset}_gen{gen}.txt'
            path.write_text(text)
            paths[asset] = str(path)
            log.info(f"Saved {asset} prompt to {path}")
        return paths


_writer_instance = None


def get_prompt_writer() -> PromptWriter:
    global _writer_instance
    if _writer_instance is None:
        _writer_instance = PromptWriter()
    return _writer_instance


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Prompt Writer')
    parser.add_argument('--generate', action='store_true', help='Generate all prompts')
    parser.add_argument('--generation', type=int, help='Generation number')
    args = parser.parse_args()

    writer = get_prompt_writer()

    if args.generate:
        gen = args.generation
        paths = writer.save_all(gen)
        print(f"Generated prompts for generation {gen or writer.dna.get_generation()}:")
        for name, path in paths.items():
            print(f"  {name}: {path}")
