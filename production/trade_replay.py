"""Trade Replay & Explainability Dashboard

Records every AI decision with full context, generates human-readable
explanations, and allows step-by-step replay of historical trades.
"""

import json
import time
import logging
import math
from typing import List, Dict, Optional, Any
from collections import deque
from pathlib import Path
from datetime import datetime, timezone

log = logging.getLogger(__name__)

REPLAY_DIR = Path(__file__).parent / 'trade_replays'
MAX_RECORDS = 1000


class TradeReplayDashboard:
    """Records AI decisions and generates explainable trade narratives."""

    def __init__(self):
        REPLAY_DIR.mkdir(parents=True, exist_ok=True)
        self._records: deque = deque(maxlen=MAX_RECORDS)
        self._load_recent()

    def record_decision(self, decision: Dict[str, Any]) -> str:
        record = {
            'trade_id': self._generate_id(decision),
            'timestamp': decision.get('timestamp', datetime.now(timezone.utc).isoformat()),
            'unix_time': time.time(),
            'symbol': decision.get('symbol', 'XAUUSD'),
            'action': decision.get('action', 'WAIT'),
            'price': decision.get('price', 0),
            'confidence': decision.get('confidence', 0),
            'calibrated_confidence': decision.get('calibrated_confidence',
                                                  decision.get('confidence', 0)),
            'consensus': decision.get('consensus', 50),
            'bias': decision.get('bias', 'NEUTRAL'),
            'session': decision.get('session', ''),
            'regime': decision.get('regime', ''),
            'macro_state': decision.get('macro_state', ''),
            'trap_probability': decision.get('trap_probability', 0),
            'orderflow': decision.get('orderflow', 'NEUTRAL'),
            'news_lock': decision.get('news_lock', False),
            'risk_tier': decision.get('risk_tier', ''),
            'portfolio_allocation': decision.get('portfolio_allocation', ''),
            'execution_score': decision.get('execution_score', 0),
            'expected_rr': decision.get('expected_rr', 0),
            'invalidity_level': decision.get('invalidity_level', 0),
            'sl': decision.get('sl', 0),
            'tp': decision.get('tp', 0),
            'reason': decision.get('reason', []),
            'components': decision.get('components', {}),
        }
        self._records.append(record)
        self._save_record(record)
        return record['trade_id']

    def record_outcome(self, trade_id: str, outcome: Dict[str, Any]) -> bool:
        for i, r in enumerate(self._records):
            if r.get('trade_id') == trade_id:
                updated = dict(r)
                updated['exit_price'] = outcome.get('exit_price', 0)
                updated['pnl'] = outcome.get('pnl', 0)
                updated['pnl_pips'] = outcome.get('pnl_pips', 0)
                updated['win'] = outcome.get('win', False)
                updated['rr_realized'] = outcome.get('rr', 0)
                updated['closed_at'] = outcome.get('timestamp',
                                                   datetime.now(timezone.utc).isoformat())
                self._records[i] = updated
                self._save_record(updated)
                return True
        return False

    def explain(self, trade_id: str) -> Optional[Dict[str, Any]]:
        record = None
        for r in self._records:
            if r.get('trade_id') == trade_id:
                record = r
                break
        if not record:
            return None
        return self._build_explanation(record)

    def replay(self, trade_id: str) -> Optional[Dict[str, Any]]:
        record = None
        for r in self._records:
            if r.get('trade_id') == trade_id:
                record = r
                break
        if not record:
            return None
        return self._build_replay(record)

    def get_recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        return list(self._records)[-limit:]

    def get_stats(self) -> Dict[str, Any]:
        if not self._records:
            return {'total': 0, 'buys': 0, 'sells': 0, 'waits': 0}
        total = len(self._records)
        actions = [r.get('action', 'WAIT') for r in self._records]
        decisions = [r for r in self._records if r.get('action') in ('BUY', 'SELL')]
        executed = len(decisions)
        return {
            'total_records': total,
            'executed_trades': executed,
            'buys': actions.count('BUY'),
            'sells': actions.count('SELL'),
            'waits': actions.count('WAIT'),
            'cancels': actions.count('CANCEL'),
            'avg_confidence': round(sum(r.get('confidence', 0) for r in self._records) / total, 1) if total else 0,
        }

    # ---- Internal ----

    def _generate_id(self, decision: Dict[str, Any]) -> str:
        ts = decision.get('timestamp', '')
        if isinstance(ts, str):
            try:
                ts_dt = datetime.fromisoformat(ts)
                ts = ts_dt.strftime('%Y%m%d_%H%M%S')
            except (ValueError, TypeError):
                ts = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        else:
            ts = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        symbol = decision.get('symbol', 'XAUUSD')
        action = decision.get('action', 'WAIT')
        seq = len(self._records) + 1
        return f"{symbol}_{action}_{ts}_{seq:04d}"

    def _build_explanation(self, record: Dict[str, Any]) -> Dict[str, Any]:
        reasons = []
        if record.get('action') in ('BUY', 'SELL'):
            action = record['action']
            reasons = [
                f"Action: {action}",
                f"Confidence: {record.get('confidence', 0)}% (calibrated: {record.get('calibrated_confidence', 0)}%)",
                f"Consensus: {record.get('consensus', 0)}%",
                f"Session: {record.get('session', 'N/A')}",
                f"Regime: {record.get('regime', 'N/A')}",
                f"Macro: {record.get('macro_state', 'NEUTRAL')}",
                f"Trap Probability: {record.get('trap_probability', 0)}%",
                f"Order Flow: {record.get('orderflow', 'NEUTRAL')}",
                f"Invalidity: {record.get('invalidity_level', 0)}%",
                f"Expected RR: {record.get('expected_rr', 0):.2f}",
                f"Execution Score: {record.get('execution_score', 0)}",
            ]

        if record.get('session'):
            reasons.append(f"\nSession Analysis:")
            reasons.append(f"  {record['session']}")

        if record.get('macro_state'):
            reasons.append(f"\nMacro State:")
            reasons.append(f"  {record['macro_state']}")

        custom_reasons = record.get('reason', [])
        if custom_reasons:
            reasons.append(f"\nAI Reasoning:")
            for r in custom_reasons[:5]:
                reasons.append(f"  \u2022 {r}")

        if record.get('action') == 'WAIT':
            reasons.append("\nNo trade: conditions not met")

        return {
            'trade_id': record['trade_id'],
            'explanation': '\n'.join(reasons),
            'summary': f"{record.get('action', 'WAIT')} "
                       f"{record.get('symbol', 'XAUUSD')} "
                       f"@ {record.get('price', 0)} "
                       f"(confidence {record.get('confidence', 0)}%)",
            'record': record,
        }

    def _build_replay(self, record: Dict[str, Any]) -> Dict[str, Any]:
        steps = []

        # Step 1: Market Data
        steps.append({
            'step': 1,
            'name': 'Market Data',
            'data': f"Symbol: {record.get('symbol')}, Price: {record.get('price')}",
        })

        # Step 2: Regime
        steps.append({
            'step': 2,
            'name': 'Regime Detection',
            'data': f"Regime: {record.get('regime', 'N/A')}",
        })

        # Step 3: Multi-Timeframe Consensus
        steps.append({
            'step': 3,
            'name': 'MTF Consensus',
            'data': f"Consensus: {record.get('consensus', 0)}%, Bias: {record.get('bias', 'NEUTRAL')}",
        })

        # Step 4: Liquidity Sweep
        sweep = record.get('components', {}).get('SWEEP', 'N/A')
        steps.append({
            'step': 4,
            'name': 'Liquidity Sweep',
            'data': f"Sweep score: {sweep}",
        })

        # Step 5: Trap Detection
        steps.append({
            'step': 5,
            'name': 'Trap Detection',
            'data': f"Trap probability: {record.get('trap_probability', 0)}%",
        })

        # Step 6: Order Flow
        steps.append({
            'step': 6,
            'name': 'Order Flow',
            'data': f"Flow: {record.get('orderflow', 'NEUTRAL')}",
        })

        # Step 7: Macro
        steps.append({
            'step': 7,
            'name': 'Macro Analysis',
            'data': f"Macro: {record.get('macro_state', 'NEUTRAL')}",
        })

        # Step 8: Session / Killzone
        steps.append({
            'step': 8,
            'name': 'Session / Killzone',
            'data': f"Session: {record.get('session', 'N/A')}",
        })

        # Step 9: Dynamic Session Volatility
        steps.append({
            'step': 9,
            'name': 'Dynamic Session Vol',
            'data': f"Risk tier: {record.get('risk_tier', 'N/A')}",
        })

        # Step 10: Adaptive Confidence
        steps.append({
            'step': 10,
            'name': 'Adaptive Confidence',
            'data': f"Raw: {record.get('confidence', 0)}% -> Calibrated: {record.get('calibrated_confidence', 0)}%",
        })

        # Step 11: News Lockout
        steps.append({
            'step': 11,
            'name': 'News Lockout',
            'data': f"Locked: {record.get('news_lock', False)}",
        })

        # Step 12: Portfolio Risk
        steps.append({
            'step': 12,
            'name': 'Portfolio Risk',
            'data': f"Allocation: {record.get('portfolio_allocation', 'N/A')}",
        })

        # Step 13: Execution Quality
        steps.append({
            'step': 13,
            'name': 'Execution Quality',
            'data': f"Score: {record.get('execution_score', 0)}",
        })

        # Step 14: Final Decision
        steps.append({
            'step': 14,
            'name': 'Master AI Decision',
            'data': f"Action: {record.get('action', 'WAIT')}, SL: {record.get('sl', 0)}, TP: {record.get('tp', 0)}",
        })

        # Step 15: Outcome (if closed)
        if record.get('closed_at'):
            steps.append({
                'step': 15,
                'name': 'Trade Outcome',
                'data': f"Exit: {record.get('exit_price', 0)}, "
                        f"P&L: {record.get('pnl', 0)}, "
                        f"Win: {record.get('win', False)}",
            })

        return {
            'trade_id': record['trade_id'],
            'steps': steps,
            'total_steps': len(steps),
            'record': record,
        }

    def _save_record(self, record: Dict[str, Any]) -> None:
        try:
            tid = record.get('trade_id', 'unknown')
            path = REPLAY_DIR / f"{tid}.json"
            path.write_text(json.dumps(record, indent=2, default=str))
        except Exception as e:
            log.debug(f"Could not save trade record: {e}")

    def _load_recent(self) -> None:
        try:
            files = sorted(REPLAY_DIR.glob('*.json'))
            for f in files[-MAX_RECORDS:]:
                try:
                    data = json.loads(f.read_text())
                    self._records.append(data)
                except Exception:
                    pass
        except Exception as e:
            log.debug(f"Could not load trade records: {e}")


_replay: Optional[TradeReplayDashboard] = None


def get_trade_replay() -> TradeReplayDashboard:
    global _replay
    if _replay is None:
        _replay = TradeReplayDashboard()
    return _replay


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    tr = get_trade_replay()
    tid = tr.record_decision({
        'symbol': 'XAUUSD', 'action': 'BUY', 'price': 2010.5,
        'confidence': 84, 'calibrated_confidence': 72,
        'consensus': 89, 'bias': 'BULLISH',
        'session': 'LONDON_OPEN', 'regime': 'EXPANSION',
        'macro_state': 'BULLISH', 'trap_probability': 11,
        'orderflow': 'Strong Buy', 'news_lock': False,
        'risk_tier': 'Medium', 'portfolio_allocation': '22%',
        'execution_score': 94,
        'expected_rr': 2.5, 'invalidity_level': 15,
        'sl': 2005.0, 'tp': 2025.0,
        'reason': ['Liquidity Sweep', 'Bullish Order Flow',
                    'Macro Alignment', 'London Killzone'],
    })
    print(f"Trade ID: {tid}")
    expl = tr.explain(tid)
    print("\n--- Explanation ---")
    print(expl['explanation'])
    replay = tr.replay(tid)
    print("\n--- Replay Steps ---")
    for step in replay['steps']:
        print(f"  [{step['step']}] {step['name']}: {step['data']}")
