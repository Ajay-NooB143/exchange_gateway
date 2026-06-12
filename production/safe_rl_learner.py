"""Safe Online Reinforcement Learning

Continuous learning from closed trades with safety mechanisms:
shadow model, paper validation, walk-forward validation,
rollback capability, model versioning, automatic rejection if degraded.
"""

import time
import json
import logging
import copy
import math
from typing import List, Dict, Optional, Any
from collections import deque
from pathlib import Path
from datetime import datetime, timezone

log = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).parent / 'rl_models'
MAX_HISTORY = 500
VALIDATION_SPLIT = 0.8
MIN_TRAIN_SAMPLES = 30
MAX_VERSIONS = 10


class SafeRLLearner:
    """Safe online reinforcement learning with shadow model validation."""

    def __init__(self):
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        self._trade_history: deque = deque(maxlen=MAX_HISTORY)
        self._current_model: Dict[str, Any] = self._default_model()
        self._shadow_model: Optional[Dict[str, Any]] = None
        self._version_history: List[Dict[str, Any]] = []
        self._last_train_result: Optional[Dict[str, Any]] = None
        self._total_trades = 0
        self._load_latest()

    def record_trade(self, trade: Dict[str, Any]) -> None:
        record = {
            'symbol': trade.get('symbol', 'XAUUSD'),
            'direction': trade.get('direction', ''),
            'win': trade.get('win', False),
            'rr': trade.get('rr', 0),
            'pattern': trade.get('pattern', ''),
            'regime': trade.get('regime', ''),
            'session': trade.get('session', ''),
            'liquidity_quality': trade.get('liquidity_quality', 50),
            'trap_detected': trade.get('trap_detected', False),
            'confidence': trade.get('confidence', 50),
            'entry': trade.get('entry', 0),
            'exit': trade.get('exit', 0),
            'atr': trade.get('atr', 5.0),
            'timestamp': trade.get('timestamp', time.time()),
        }
        self._trade_history.append(record)
        self._total_trades += 1

    def train(self) -> Dict[str, Any]:
        result = {
            'trained': False,
            'accepted': False,
            'samples': 0,
            'performance_before': {},
            'performance_after': {},
            'improvement': 0,
            'rejection_reason': '',
            'version': 0,
        }
        try:
            trades = list(self._trade_history)
            if len(trades) < MIN_TRAIN_SAMPLES:
                result['rejection_reason'] = (f'Insufficient samples: '
                                              f'{len(trades)} < {MIN_TRAIN_SAMPLES}')
                return result

            split_idx = int(len(trades) * VALIDATION_SPLIT)
            train_set = trades[:split_idx]
            val_set = trades[split_idx:]

            # -- Evaluate current model --
            current_perf = self._evaluate_model(self._current_model, val_set)

            # -- Train shadow model --
            self._shadow_model = self._train_model(train_set)
            shadow_perf = self._evaluate_model(self._shadow_model, val_set)

            # -- Walk-forward validation --
            wf_result = self._walk_forward_validation(trades)
            result['walk_forward'] = wf_result

            # -- Compare --
            current_score = current_perf.get('composite', 0)
            shadow_score = shadow_perf.get('composite', 0)
            improvement = shadow_score - current_score

            result['samples'] = len(trades)
            result['performance_before'] = current_perf
            result['performance_after'] = shadow_perf
            result['improvement'] = round(improvement, 2)

            # -- Accept or reject --
            if improvement > 0 and wf_result.get('net_improvement', 0) > 0:
                self._promote_shadow()
                result['trained'] = True
                result['accepted'] = True
                result['version'] = self._current_model.get('version', 0)

                # Save model
                self._save_model(self._current_model)
                self._prune_versions()
                result['model_path'] = str(self._model_path(
                    self._current_model.get('version', 0)))
            else:
                reasons = []
                if improvement <= 0:
                    reasons.append(f'Shadow underperforms by {abs(improvement):.2f}')
                if wf_result.get('net_improvement', 0) <= 0:
                    reasons.append('Walk-forward shows no improvement')
                result['rejection_reason'] = '; '.join(reasons)
                self._shadow_model = None

            self._last_train_result = result

        except Exception as e:
            log.warning(f"SafeRLLearner.train error: {e}")
            result['error'] = str(e)
            self._shadow_model = None

        return result

    def get_adjustments(self) -> Dict[str, Any]:
        model = self._shadow_model or self._current_model
        return {
            'pattern_weights': model.get('pattern_weights', {}),
            'regime_weights': model.get('regime_weights', {}),
            'session_weights': model.get('session_weights', {}),
            'confidence_bias': model.get('confidence_bias', 0),
            'rr_factor': model.get('rr_factor', 1.0),
            'model_version': model.get('version', 0),
            'model_active': self._shadow_model is None,
        }

    def rollback(self, version: Optional[int] = None) -> bool:
        if version is not None:
            target = next((v for v in self._version_history
                          if v.get('version') == version), None)
            if target:
                self._current_model = dict(target['model'])
                self._save_model(self._current_model)
                self._shadow_model = None
                return True
            return False
        if len(self._version_history) >= 2:
            prev = self._version_history[-2]
            self._current_model = dict(prev['model'])
            self._save_model(self._current_model)
            self._shadow_model = None
            return True
        return False

    def get_version_history(self) -> List[Dict[str, Any]]:
        return list(self._version_history)

    def get_stats(self) -> Dict[str, Any]:
        return {
            'total_trades': self._total_trades,
            'history_size': len(self._trade_history),
            'current_version': self._current_model.get('version', 0),
            'shadow_active': self._shadow_model is not None,
            'versions_available': len(self._version_history),
        }

    # ---- Internal ----

    def _default_model(self) -> Dict[str, Any]:
        return {
            'version': 0,
            'pattern_weights': {},
            'regime_weights': {
                'EXPANSION': 1.0,
                'COMPRESSION': 1.0,
                'TRAP': 0.5,
                'VOLATILITY': 0.7,
            },
            'session_weights': {
                'ASIAN': 0.6,
                'LONDON': 1.0,
                'NY': 0.9,
            },
            'confidence_bias': 0,
            'rr_factor': 1.0,
            'created': datetime.now(timezone.utc).isoformat(),
        }

    def _train_model(self, trades: List[Dict]) -> Dict[str, Any]:
        model = copy.deepcopy(self._current_model)
        model['version'] = self._current_model.get('version', 0) + 1
        model['created'] = datetime.now(timezone.utc).isoformat()

        if not trades:
            return model

        total = len(trades)
        wins = [t for t in trades if t.get('win')]

        # Pattern weights
        pattern_trades: Dict[str, List] = {}
        for t in trades:
            p = t.get('pattern', 'unknown')
            if p not in pattern_trades:
                pattern_trades[p] = []
            pattern_trades[p].append(t)

        pattern_weights = {}
        for pattern, pts in pattern_trades.items():
            if len(pts) >= 3:
                wr = sum(1 for pt in pts if pt.get('win')) / len(pts)
                avg_rr = sum(pt.get('rr', 0) for pt in pts) / len(pts)
                pattern_weights[pattern] = round(0.5 + (wr - 0.5) + (avg_rr - 1.0) * 0.2, 3)
            else:
                pattern_weights[pattern] = 1.0
        model['pattern_weights'] = pattern_weights

        # Regime weights
        regime_trades: Dict[str, List] = {}
        for t in trades:
            r = t.get('regime', 'UNKNOWN')
            if r not in regime_trades:
                regime_trades[r] = []
            regime_trades[r].append(t)

        regime_weights = {}
        for regime, rt in regime_trades.items():
            if len(rt) >= 5:
                wr = sum(1 for r in rt if r.get('win')) / len(rt)
                regime_weights[regime] = round(0.5 + (wr - 0.5) * 2, 3)
            else:
                regime_weights[regime] = 1.0
        model['regime_weights'] = regime_weights

        # Session weights
        session_trades: Dict[str, List] = {}
        for t in trades:
            s = t.get('session', 'UNKNOWN')
            if s not in session_trades:
                session_trades[s] = []
            session_trades[s].append(t)

        session_weights = {}
        for session, st in session_trades.items():
            if len(st) >= 5:
                wr = sum(1 for s in st if s.get('win')) / len(st)
                session_weights[session] = round(0.5 + (wr - 0.5) * 2, 3)
            else:
                session_weights[session] = 1.0
        model['session_weights'] = session_weights

        # Confidence bias
        if wins:
            avg_conf_winners = sum(w.get('confidence', 50) for w in wins) / len(wins)
            avg_conf = sum(t.get('confidence', 50) for t in trades) / total
            model['confidence_bias'] = round((avg_conf_winners - avg_conf) * 0.1, 3)

        # RR factor
        if wins:
            avg_rr = sum(w.get('rr', 0) for w in wins) / len(wins)
            expected_rr = 1.5
            model['rr_factor'] = round(max(0.5, min(2.0, avg_rr / expected_rr)), 3)

        return model

    def _evaluate_model(self, model: Dict[str, Any],
                        val_set: List[Dict]) -> Dict[str, Any]:
        if not val_set:
            return {'composite': 0, 'win_rate': 0, 'avg_rr': 0, 'samples': 0}

        simulated = []
        for t in val_set:
            expected = self._simulate_trade(model, t)
            simulated.append({'actual': t.get('win', False), 'predicted': expected})

        correct = sum(1 for s in simulated if s['actual'] == s['predicted'])
        accuracy = correct / len(simulated)

        wins = sum(1 for s in simulated if s['actual'])
        wr = wins / len(simulated)

        rr_sum = sum(t.get('rr', 0) for t in val_set)
        avg_rr = rr_sum / len(val_set)

        composite = accuracy * 50 + wr * 30 + min(avg_rr, 3) / 3 * 20
        return {
            'composite': round(composite, 1),
            'accuracy': round(accuracy * 100, 1),
            'win_rate': round(wr * 100, 1),
            'avg_rr': round(avg_rr, 2),
            'samples': len(val_set),
        }

    def _simulate_trade(self, model: Dict[str, Any],
                        trade: Dict[str, Any]) -> bool:
        score = 50
        pattern_w = model.get('pattern_weights', {}).get(trade.get('pattern', ''), 1.0)
        regime_w = model.get('regime_weights', {}).get(trade.get('regime', ''), 1.0)
        session_w = model.get('session_weights', {}).get(trade.get('session', ''), 1.0)
        bias = model.get('confidence_bias', 0)
        score *= pattern_w * regime_w * session_w
        score += bias * 100
        return score > 50

    def _walk_forward_validation(self, trades: List[Dict]) -> Dict[str, Any]:
        if len(trades) < 20:
            return {'net_improvement': 0, 'windows': 0}

        window_size = max(10, len(trades) // 5)
        improvements = []
        for i in range(0, len(trades) - window_size, window_size // 2):
            train = trades[:i + window_size] if i + window_size < len(trades) else trades[:-window_size]
            val = trades[i + window_size:i + 2 * window_size]
            if len(train) < 5 or len(val) < 3:
                continue
            shadow = self._train_model(train)
            current = self._current_model
            shadow_perf = self._evaluate_model(shadow, val)
            current_perf = self._evaluate_model(current, val)
            improvements.append(shadow_perf.get('composite', 0) - current_perf.get('composite', 0))

        if not improvements:
            return {'net_improvement': 0, 'windows': 0}
        return {
            'net_improvement': round(sum(improvements) / len(improvements), 2),
            'windows': len(improvements),
            'positive_windows': sum(1 for i in improvements if i > 0),
        }

    def _promote_shadow(self) -> None:
        if self._shadow_model is None:
            return
        self._version_history.append({
            'version': self._current_model.get('version', 0),
            'model': copy.deepcopy(self._current_model),
            'promoted': datetime.now(timezone.utc).isoformat(),
        })
        self._current_model = self._shadow_model
        self._shadow_model = None

    def _model_path(self, version: int) -> Path:
        return MODEL_DIR / f'model_v{version}.json'

    def _save_model(self, model: Dict[str, Any]) -> None:
        try:
            path = self._model_path(model.get('version', 0))
            path.write_text(json.dumps(model, indent=2, default=str))
        except Exception as e:
            log.warning(f"Could not save model: {e}")

    def _load_latest(self) -> None:
        try:
            versions = sorted(MODEL_DIR.glob('model_v*.json'))
            if versions:
                latest = versions[-1]
                data = json.loads(latest.read_text())
                self._current_model = data
                log.info(f"Loaded RL model v{data.get('version', 0)}")
        except Exception as e:
            log.debug(f"No saved RL model found: {e}")

    def _prune_versions(self) -> None:
        versions = sorted(MODEL_DIR.glob('model_v*.json'))
        while len(versions) > MAX_VERSIONS:
            oldest = versions[0]
            try:
                oldest.unlink()
            except Exception:
                pass
            versions = sorted(MODEL_DIR.glob('model_v*.json'))


_learner: Optional[SafeRLLearner] = None


def get_rl_learner() -> SafeRLLearner:
    global _learner
    if _learner is None:
        _learner = SafeRLLearner()
    return _learner


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    rl = get_rl_learner()
    import random
    for i in range(100):
        rl.record_trade({
            'symbol': 'XAUUSD', 'direction': random.choice(['BUY', 'SELL']),
            'win': random.random() > 0.4,
            'rr': random.uniform(0.5, 3.0),
            'pattern': random.choice(['FVG', 'OB', 'MSS', 'BOS', '']),
            'regime': random.choice(['EXPANSION', 'COMPRESSION', 'TRAP']),
            'session': random.choice(['ASIAN', 'LONDON', 'NY']),
            'liquidity_quality': random.randint(30, 90),
            'trap_detected': random.random() > 0.8,
            'confidence': random.uniform(50, 90),
            'entry': 2000, 'exit': 2010, 'atr': 5.0,
        })
    result = rl.train()
    print(f"Trained: {result['trained']}, Accepted: {result['accepted']}")
    print(f"Samples: {result['samples']}, Improvement: {result['improvement']}")
    print(f"Rejection: {result['rejection_reason']}")
