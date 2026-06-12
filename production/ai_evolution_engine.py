"""
AI Evolution Engine - OMNI BRAIN V2
====================================
Integrates with Claude API to analyze performance and suggest
prompt DNA evolutions. Requires human approval via Telegram.
"""

import os
import sys
import json
import logging
import threading
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from pathlib import Path

log = logging.getLogger('AIEvolutionEngine')

BASE_DIR = Path(__file__).parent
LOG_DIR = BASE_DIR / 'logs'
AI_SUGGESTIONS_FILE = LOG_DIR / 'ai_evolution_suggestions.json'

LOG_DIR.mkdir(parents=True, exist_ok=True)

PENDING_APPLY: Dict[str, Any] = {}
PENDING_LOCK = threading.Lock()


def _get_dna():
    sys.path.insert(0, str(BASE_DIR))
    from prompt_evolution import get_dna
    return get_dna()


def _get_mutation_engine():
    sys.path.insert(0, str(BASE_DIR))
    from prompt_evolution import get_mutation_engine
    return get_mutation_engine()


class AIEvolutionEngine:
    """Claude API integration for DNA evolution suggestions."""

    def __init__(self):
        self.client = None
        self._initialized = False

    def _ensure_client(self):
        if not self._initialized:
            try:
                from anthropic import Anthropic
                api_key = os.environ.get('ANTHROPIC_API_KEY', '')
                if api_key:
                    self.client = Anthropic(api_key=api_key)
                self._initialized = True
            except ImportError:
                log.debug("anthropic package not installed")
                self._initialized = True

    @property
    def available(self) -> bool:
        self._ensure_client()
        return self.client is not None

    def generate_suggestion(self, generation: int, fitness: float,
                            perf: Dict[str, Any], losses: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        self._ensure_client()
        if not self.client:
            return self._fallback_suggestion(generation, fitness, perf)

        system_prompt = (
            "You are an expert trading system optimizer. Analyze the performance "
            "data and suggest prompt DNA evolutions. Return ONLY valid JSON."
        )

        user_prompt = (
            f"Analyze this trading system performance and suggest evolution:\n\n"
            f"Generation: {generation}\n"
            f"Fitness: {fitness}\n"
            f"Performance: {json.dumps(perf, indent=2)}\n"
            f"Loss patterns: {json.dumps(losses, indent=2)}\n\n"
            f"Suggest in this JSON format:\n"
            f"{{\n"
            f'  "suggested_weights": {{"ob_weight": 20, "fvg_weight": 20, ...}},\n'
            f'  "suggested_threshold": 75,\n'
            f'  "rules_to_add": ["rule1", "rule2"],\n'
            f'  "rules_to_remove": ["rule3"],\n'
            f'  "asset_adjustments": {{"XAUUSD": "+5", "SP500": "-3"}},\n'
            f'  "reasoning": "Brief explanation..."\n'
            f"}}"
        )

        try:
            response = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1000,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}]
            )
            text = response.content[0].text if response.content else ""
            suggestion = self._parse_response(text)
            if suggestion:
                suggestion['generation'] = generation
                suggestion['timestamp'] = datetime.now(timezone.utc).isoformat()
                self._save_suggestion(suggestion)
                return suggestion
        except Exception as e:
            log.error(f"Claude API error: {e}")

        return self._fallback_suggestion(generation, fitness, perf)

    def _fallback_suggestion(self, generation: int, fitness: float,
                              perf: Dict[str, Any]) -> Dict[str, Any]:
        suggestion = {
            'generation': generation,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'source': 'fallback',
            'suggested_weights': {'ob_weight': 20, 'fvg_weight': 20, 'sweep_weight': 30},
            'suggested_threshold': 75,
            'rules_to_add': ['Monitor loss streaks'],
            'rules_to_remove': [],
            'asset_adjustments': {},
            'reasoning': 'Fallback suggestion (Claude API unavailable)'
        }
        if fitness < 0.65:
            suggestion['suggested_threshold'] = 78
            suggestion['rules_to_add'].append('Increase threshold after poor fitness')
        self._save_suggestion(suggestion)
        return suggestion

    def _parse_response(self, text: str) -> Optional[Dict[str, Any]]:
        try:
            start = text.index('{')
            end = text.rindex('}') + 1
            json_str = text[start:end]
            return json.loads(json_str)
        except (ValueError, json.JSONDecodeError) as e:
            log.error(f"Failed to parse Claude response: {e}")
            return None

    def _save_suggestion(self, suggestion: Dict[str, Any]):
        try:
            suggestions = []
            if AI_SUGGESTIONS_FILE.exists():
                with open(AI_SUGGESTIONS_FILE, 'r') as f:
                    data = json.load(f)
                    suggestions = data if isinstance(data, list) else [data]
            suggestions.append(suggestion)
            if len(suggestions) > 50:
                suggestions = suggestions[-50:]
            with open(AI_SUGGESTIONS_FILE, 'w') as f:
                json.dump(suggestions, f, indent=2, default=str)
        except Exception as e:
            log.error(f"Failed to save suggestion: {e}")

    def get_pending_suggestion(self) -> Optional[Dict[str, Any]]:
        with PENDING_LOCK:
            if PENDING_APPLY:
                return dict(PENDING_APPLY)
        try:
            if AI_SUGGESTIONS_FILE.exists():
                with open(AI_SUGGESTIONS_FILE, 'r') as f:
                    suggestions = json.load(f)
                if suggestions and isinstance(suggestions, list):
                    return suggestions[-1] if suggestions else None
        except Exception:
            pass
        return None

    def apply_suggestion(self, suggestion_id: str = None) -> Dict[str, bool]:
        suggestion = self.get_pending_suggestion()
        if not suggestion:
            return {'success': False, 'error': 'No pending suggestion'}
        results = {}
        try:
            dna = _get_dna()
            engine = _get_mutation_engine()
            weights = suggestion.get('suggested_weights', {})
            for comp_key, comp_data in dna.get_all().items():
                prompt = comp_data.get('prompt', {})
                changed = False
                for w_key, w_val in weights.items():
                    if w_key in prompt:
                        old = prompt[w_key]
                        prompt[w_key] = max(5, min(50, w_val))
                        if old != prompt[w_key]:
                            changed = True
                threshold = suggestion.get('suggested_threshold')
                if threshold and 'execute_threshold' in prompt:
                    old = prompt['execute_threshold']
                    prompt['execute_threshold'] = max(60, min(90, threshold))
                    if old != prompt['execute_threshold']:
                        changed = True
                if changed:
                    comp_data['generation'] += 1
                    comp_data['mutations'].append(f"AI_SUGGESTION: applied weights/threshold")
                    dna.update(comp_key, comp_data)
                    results[comp_key] = True
            for rule in suggestion.get('rules_to_add', []):
                for comp_key in dna.get_all():
                    engine._backup_before(comp_key)
                    data = dna.get(comp_key)
                    if data and 'prompt' in data:
                        rules = data['prompt'].setdefault('rules', [])
                        if rule not in rules:
                            rules.append(rule)
                            data['generation'] += 1
                            data['mutations'].append(f"AI_SUGGESTION: +{rule}")
                            dna.update(comp_key, data)
                            results[f'{comp_key}_add'] = True
            for rule in suggestion.get('rules_to_remove', []):
                for comp_key in dna.get_all():
                    data = dna.get(comp_key)
                    if data and 'prompt' in data:
                        rules = data['prompt'].get('rules', [])
                        if rule in rules and len(rules) > 5:
                            rules.remove(rule)
                            data['generation'] += 1
                            data['mutations'].append(f"AI_SUGGESTION: -{rule}")
                            dna.update(comp_key, data)
                            results[f'{comp_key}_remove'] = True
            with PENDING_LOCK:
                PENDING_APPLY.clear()
            results['success'] = True
        except Exception as e:
            results = {'success': False, 'error': str(e)}
        return results

    def reject_suggestion(self) -> bool:
        with PENDING_LOCK:
            PENDING_APPLY.clear()
        return True

    def get_full_reasoning(self) -> Optional[str]:
        suggestion = self.get_pending_suggestion()
        if suggestion:
            return suggestion.get('reasoning', 'No reasoning provided')
        return None


_engine_instance = None


def get_ai_evolution_engine() -> AIEvolutionEngine:
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = AIEvolutionEngine()
    return _engine_instance


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='AI Evolution Engine')
    parser.add_argument('--test', action='store_true', help='Run self-test')
    parser.add_argument('--suggest', action='store_true', help='Generate suggestion')
    parser.add_argument('--apply', action='store_true', help='Apply pending suggestion')
    parser.add_argument('--reject', action='store_true', help='Reject pending suggestion')
    args = parser.parse_args()

    engine = get_ai_evolution_engine()

    if args.test:
        if engine.available:
            print("Claude API: Available")
        else:
            print("Claude API: Not available (no API key or package)")
        print(f"Pending: {engine.get_pending_suggestion() is not None}")

    if args.suggest:
        suggestion = engine.generate_suggestion(
            generation=1,
            fitness=0.71,
            perf={'win_rate': 0.71, 'total_signals': 147, 'avg_score': 68.4},
            losses=[{'reason': 'SL hit', 'asset': 'XAUUSD', 'score': 82}]
        )
        print(json.dumps(suggestion, indent=2))

    if args.apply:
        results = engine.apply_suggestion()
        print(json.dumps(results, indent=2))

    if args.reject:
        engine.reject_suggestion()
        print("Suggestion rejected")
