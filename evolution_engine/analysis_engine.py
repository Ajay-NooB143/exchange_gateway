"""
Alpha Agent Analysis Engine
============================
Continuous Self-Evolution Module 1: Log Ingestion & Analysis

Ingests execution logs, computes performance metrics, detects regime shifts,
and identifies structural bottlenecks for the evolution loop.

Architecture:
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ANALYSIS ENGINE                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                  │
│  │  Log Reader  │───▶│  Metrics     │───▶│  Regime      │                  │
│  │  (CSV/JSON)  │    │  Calculator  │    │  Detector    │                  │
│  └──────────────┘    └──────────────┘    └──────────────┘                  │
│         │                   │                   │                           │
│         ▼                   ▼                   ▼                           │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                  │
│  │  Slippage    │    │  Latency     │    │  Bottleneck  │                  │
│  │  Analyzer    │    │  Profiler    │    │  Identifier  │                  │
│  └──────────────┘    └──────────────┘    └──────────────┘                  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
"""

import csv
import json
import os
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from collections import deque
from enum import Enum
import statistics
import logging

log = logging.getLogger('AlphaAnalysis')


# ══════════════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ══════════════════════════════════════════════════════════════════════════════

class MarketRegime(Enum):
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    UNKNOWN = "unknown"


@dataclass
class TradeRecord:
    """Single trade record from execution log"""
    timestamp: str
    signal: str  # "long" or "short"
    entry: float
    sl: float
    tp: float
    exit_price: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    slippage_pips: float = 0.0
    execution_latency_ms: float = 0.0
    source: str = ""  # "sweep_return", "iob_mitigation"
    regime: str = ""
    atr: float = 0.0
    volume_pct: float = 0.0
    cvd_confirmed: bool = False
    status: str = "pending"  # "filled", "closed", "pending"


@dataclass
class PerformanceMetrics:
    """Aggregated performance metrics"""
    # Basic stats
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    
    # Ratios
    win_rate: float = 0.0
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    
    # P&L
    total_pnl: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    
    # Execution quality
    avg_slippage_pips: float = 0.0
    max_slippage_pips: float = 0.0
    avg_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    
    # Risk metrics
    avg_rr_ratio: float = 0.0
    expectancy: float = 0.0
    kelly_criterion: float = 0.0
    
    # Regime performance
    regime_win_rates: Dict[str, float] = field(default_factory=dict)
    source_win_rates: Dict[str, float] = field(default_factory=dict)
    
    # Time analysis
    avg_holding_time_s: float = 0.0
    trades_per_day: float = 0.0
    
    # Computed edge
    edge_score: float = 0.0  # 0-100 composite score


@dataclass
class RegimeAnalysis:
    """Market regime detection results"""
    current_regime: MarketRegime = MarketRegime.UNKNOWN
    regime_confidence: float = 0.0
    volatility_percentile: float = 50.0
    trend_strength: float = 0.0
    regime_duration_hours: float = 0.0
    recommended_adjustments: Dict[str, float] = field(default_factory=dict)


@dataclass
class Bottleneck:
    """Identified system bottleneck"""
    component: str
    metric_name: str
    current_value: float
    threshold: float
    severity: str  # "low", "medium", "high", "critical"
    recommendation: str


# ══════════════════════════════════════════════════════════════════════════════
# LOG READER
# ══════════════════════════════════════════════════════════════════════════════

class LogReader:
    """Reads and parses execution logs from various formats"""
    
    def __init__(self, log_dir: str = "/opt/trading-bridge/data"):
        self.log_dir = log_dir
        self.trade_log = os.path.join(log_dir, "trade_log.csv")
        self.execution_log = os.path.join(log_dir, "execution_log.csv")
        self.state_file = os.path.join(log_dir, "production_state.json")
    
    def read_trades(self, days: int = 7) -> List[TradeRecord]:
        """Read trade records from CSV"""
        trades = []
        
        for log_file in [self.trade_log, self.execution_log]:
            if not os.path.exists(log_file):
                continue
            
            try:
                with open(log_file, 'r') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        trade = self._parse_trade_row(row)
                        if trade and self._is_within_days(trade.timestamp, days):
                            trades.append(trade)
            except Exception as e:
                log.error(f"Error reading {log_file}: {e}")
        
        return sorted(trades, key=lambda t: t.timestamp)
    
    def read_state(self) -> Dict:
        """Read current production state"""
        if not os.path.exists(self.state_file):
            return {}
        
        try:
            with open(self.state_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            log.error(f"Error reading state: {e}")
            return {}
    
    def _parse_trade_row(self, row: Dict) -> Optional[TradeRecord]:
        """Parse a CSV row into TradeRecord"""
        try:
            return TradeRecord(
                timestamp=row.get('timestamp', ''),
                signal=row.get('signal', row.get('side', '')),
                entry=float(row.get('entry', row.get('entry_price', 0))),
                sl=float(row.get('sl', row.get('stop_loss', 0))),
                tp=float(row.get('tp', row.get('take_profit', 0))),
                exit_price=float(row.get('exit_price', row.get('fill_price', 0))),
                pnl=float(row.get('pnl', 0)),
                pnl_pct=float(row.get('pnl_pct', 0)),
                slippage_pips=float(row.get('slippage_pips', 0)),
                execution_latency_ms=float(row.get('execution_latency_ms', row.get('latency_ms', 0))),
                source=row.get('type', row.get('source', '')),
                regime=row.get('regime', ''),
                atr=float(row.get('atr', 0)),
                volume_pct=float(row.get('volume_pct', 0)),
                cvd_confirmed=row.get('cvd_confirmed', '').lower() == 'true',
                status=row.get('status', 'closed')
            )
        except Exception as e:
            log.debug(f"Error parsing row: {e}")
            return None
    
    def _is_within_days(self, timestamp_str: str, days: int) -> bool:
        """Check if timestamp is within N days"""
        try:
            if not timestamp_str:
                return True  # Include if no timestamp
            
            # Try multiple formats
            for fmt in ['%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d']:
                try:
                    trade_time = datetime.strptime(timestamp_str[:19], fmt)
                    cutoff = datetime.now() - timedelta(days=days)
                    return trade_time >= cutoff
                except ValueError:
                    continue
            
            return True  # Include if can't parse
        except Exception as e:
            log.debug(f"Failed to parse date filter: {e}")
            return True


# ══════════════════════════════════════════════════════════════════════════════
# METRICS CALCULATOR
# ══════════════════════════════════════════════════════════════════════════════

class MetricsCalculator:
    """Computes performance metrics from trade records"""
    
    def calculate(self, trades: List[TradeRecord]) -> PerformanceMetrics:
        """Calculate comprehensive performance metrics"""
        metrics = PerformanceMetrics()
        
        if not trades:
            return metrics
        
        # Filter closed trades
        closed_trades = [t for t in trades if t.status in ('closed', 'filled')]
        metrics.total_trades = len(closed_trades)
        
        if metrics.total_trades == 0:
            return metrics
        
        # Win/Loss split
        winners = [t for t in closed_trades if t.pnl > 0]
        losers = [t for t in closed_trades if t.pnl <= 0]
        
        metrics.winning_trades = len(winners)
        metrics.losing_trades = len(losers)
        metrics.win_rate = len(winners) / len(closed_trades) if closed_trades else 0
        
        # P&L metrics
        pnls = [t.pnl for t in closed_trades]
        metrics.total_pnl = sum(pnls)
        metrics.avg_win = statistics.mean([t.pnl for t in winners]) if winners else 0
        metrics.avg_loss = statistics.mean([t.pnl for t in losers]) if losers else 0
        metrics.largest_win = max(pnls) if pnls else 0
        metrics.largest_loss = min(pnls) if pnls else 0
        
        # Profit Factor
        gross_profit = sum(t.pnl for t in winners)
        gross_loss = abs(sum(t.pnl for t in losers))
        metrics.profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        # Sharpe Ratio (simplified)
        if len(pnls) > 1:
            avg_pnl = statistics.mean(pnls)
            std_pnl = statistics.stdev(pnls)
            metrics.sharpe_ratio = (avg_pnl / std_pnl) * (252 ** 0.5) if std_pnl > 0 else 0
        
        # Max Drawdown
        metrics.max_drawdown_pct = self._calculate_max_drawdown(closed_trades)
        
        # Execution quality
        slippages = [t.slippage_pips for t in closed_trades if t.slippage_pips > 0]
        latencies = [t.execution_latency_ms for t in closed_trades if t.execution_latency_ms > 0]
        
        metrics.avg_slippage_pips = statistics.mean(slippages) if slippages else 0
        metrics.max_slippage_pips = max(slippages) if slippages else 0
        metrics.avg_latency_ms = statistics.mean(latencies) if latencies else 0
        metrics.max_latency_ms = max(latencies) if latencies else 0
        
        # R:R metrics
        rr_ratios = []
        for t in closed_trades:
            if t.sl > 0 and t.tp > 0:
                risk = abs(t.entry - t.sl)
                reward = abs(t.tp - t.entry)
                if risk > 0:
                    rr_ratios.append(reward / risk)
        
        metrics.avg_rr_ratio = statistics.mean(rr_ratios) if rr_ratios else 0
        
        # Expectancy
        metrics.expectancy = (
            (metrics.win_rate * metrics.avg_win) - 
            ((1 - metrics.win_rate) * abs(metrics.avg_loss))
        )
        
        # Kelly Criterion
        if metrics.avg_loss != 0:
            metrics.kelly_criterion = (
                (metrics.win_rate * metrics.avg_win - (1 - metrics.win_rate) * abs(metrics.avg_loss)) /
                metrics.avg_win if metrics.avg_win > 0 else 0
            )
        
        # Regime performance
        metrics.regime_win_rates = self._calculate_regime_win_rates(closed_trades)
        metrics.source_win_rates = self._calculate_source_win_rates(closed_trades)
        
        # Edge Score (composite)
        metrics.edge_score = self._calculate_edge_score(metrics)
        
        return metrics
    
    def _calculate_max_drawdown(self, trades: List[TradeRecord]) -> float:
        """Calculate maximum drawdown percentage"""
        if not trades:
            return 0.0
        
        cumulative = 0
        peak = 0
        max_dd = 0
        
        for trade in trades:
            cumulative += trade.pnl
            if cumulative > peak:
                peak = cumulative
            dd = (peak - cumulative) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)
        
        return max_dd * 100
    
    def _calculate_regime_win_rates(self, trades: List[TradeRecord]) -> Dict[str, float]:
        """Calculate win rate by market regime"""
        regime_trades = {}
        
        for trade in trades:
            regime = trade.regime or "unknown"
            if regime not in regime_trades:
                regime_trades[regime] = {'wins': 0, 'total': 0}
            regime_trades[regime]['total'] += 1
            if trade.pnl > 0:
                regime_trades[regime]['wins'] += 1
        
        return {
            regime: data['wins'] / data['total'] if data['total'] > 0 else 0
            for regime, data in regime_trades.items()
        }
    
    def _calculate_source_win_rates(self, trades: List[TradeRecord]) -> Dict[str, float]:
        """Calculate win rate by signal source"""
        source_trades = {}
        
        for trade in trades:
            source = trade.source or "unknown"
            if source not in source_trades:
                source_trades[source] = {'wins': 0, 'total': 0}
            source_trades[source]['total'] += 1
            if trade.pnl > 0:
                source_trades[source]['wins'] += 1
        
        return {
            source: data['wins'] / data['total'] if data['total'] > 0 else 0
            for source, data in source_trades.items()
        }
    
    def _calculate_edge_score(self, metrics: PerformanceMetrics) -> float:
        """
        Calculate composite edge score (0-100)
        
        Components:
        - Profit Factor (25%)
        - Win Rate (25%)
        - Sharpe Ratio (25%)
        - Max Drawdown (25%)
        """
        score = 0
        
        # Profit Factor (0-25)
        if metrics.profit_factor >= 2.0:
            score += 25
        elif metrics.profit_factor >= 1.5:
            score += 20
        elif metrics.profit_factor >= 1.2:
            score += 15
        elif metrics.profit_factor >= 1.0:
            score += 10
        
        # Win Rate (0-25)
        if metrics.win_rate >= 0.6:
            score += 25
        elif metrics.win_rate >= 0.55:
            score += 20
        elif metrics.win_rate >= 0.5:
            score += 15
        elif metrics.win_rate >= 0.45:
            score += 10
        
        # Sharpe Ratio (0-25)
        if metrics.sharpe_ratio >= 2.0:
            score += 25
        elif metrics.sharpe_ratio >= 1.5:
            score += 20
        elif metrics.sharpe_ratio >= 1.0:
            score += 15
        elif metrics.sharpe_ratio >= 0.5:
            score += 10
        
        # Max Drawdown (0-25)
        if metrics.max_drawdown_pct <= 3:
            score += 25
        elif metrics.max_drawdown_pct <= 5:
            score += 20
        elif metrics.max_drawdown_pct <= 8:
            score += 15
        elif metrics.max_drawdown_pct <= 12:
            score += 10
        
        return score


# ══════════════════════════════════════════════════════════════════════════════
# REGIME DETECTOR
# ══════════════════════════════════════════════════════════════════════════════

class RegimeDetector:
    """Detects market regime shifts from trade data"""
    
    def __init__(self, lookback_trades: int = 50):
        self.lookback = lookback_trades
        self.regime_history: deque = deque(maxlen=100)
    
    def analyze(self, trades: List[TradeRecord]) -> RegimeAnalysis:
        """Analyze current market regime"""
        analysis = RegimeAnalysis()
        
        if len(trades) < 10:
            return analysis
        
        recent_trades = trades[-self.lookback:]
        
        # Volatility analysis (based on ATR)
        atrs = [t.atr for t in recent_trades if t.atr > 0]
        if atrs:
            current_atr = atrs[-1]
            avg_atr = statistics.mean(atrs)
            analysis.volatility_percentile = (
                sum(1 for a in atrs if a <= current_atr) / len(atrs) * 100
            )
            
            if analysis.volatility_percentile > 80:
                analysis.current_regime = MarketRegime.HIGH_VOLATILITY
            elif analysis.volatility_percentile < 20:
                analysis.current_regime = MarketRegime.LOW_VOLATILITY
        
        # Trend analysis (based on consecutive wins/losses and P&L direction)
        pnls = [t.pnl for t in recent_trades[-20:]]
        if len(pnls) >= 10:
            # Check for trend in P&L
            positive_runs = self._count_consecutive(pnls, positive=True)
            negative_runs = self._count_consecutive(pnls, positive=False)
            
            if positive_runs >= 5:
                analysis.current_regime = MarketRegime.TRENDING_UP
                analysis.trend_strength = positive_runs / 10
            elif negative_runs >= 5:
                analysis.current_regime = MarketRegime.TRENDING_DOWN
                analysis.trend_strength = negative_runs / 10
            else:
                analysis.current_regime = MarketRegime.RANGING
        
        # Calculate confidence
        analysis.regime_confidence = self._calculate_confidence(recent_trades, analysis)
        
        # Generate recommended adjustments
        analysis.recommended_adjustments = self._get_adjustments(analysis)
        
        return analysis
    
    def _count_consecutive(self, values: List[float], positive: bool = True) -> int:
        """Count consecutive positive/negative values"""
        count = 0
        for v in reversed(values):
            if (positive and v > 0) or (not positive and v < 0):
                count += 1
            else:
                break
        return count
    
    def _calculate_confidence(self, trades: List[TradeRecord], analysis: RegimeAnalysis) -> float:
        """Calculate regime detection confidence"""
        # Simplified confidence based on data consistency
        return 0.7  # Placeholder - implement proper confidence
    
    def _get_adjustments(self, analysis: RegimeAnalysis) -> Dict[str, float]:
        """Get recommended parameter adjustments for regime"""
        adjustments = {}
        
        if analysis.current_regime == MarketRegime.HIGH_VOLATILITY:
            adjustments['atr_sl_mult'] = 1.5  # Wider stops
            adjustments['atr_tp_mult'] = 2.5  # Wider targets
            adjustments['position_size_mult'] = 0.7  # Smaller size
            adjustments['obi_threshold'] = 2.0  # Higher threshold
            
        elif analysis.current_regime == MarketRegime.LOW_VOLATILITY:
            adjustments['atr_sl_mult'] = 0.8  # Tighter stops
            adjustments['atr_tp_mult'] = 1.2  # Tighter targets
            adjustments['position_size_mult'] = 1.2  # Larger size
            adjustments['obi_threshold'] = 1.2  # Lower threshold
            
        elif analysis.current_regime == MarketRegime.TRENDING_UP:
            adjustments['atr_sl_mult'] = 1.2
            adjustments['atr_tp_mult'] = 2.0
            adjustments['position_size_mult'] = 1.0
            adjustments['volume_ma_period'] = 20  # Longer MA
            
        elif analysis.current_regime == MarketRegime.TRENDING_DOWN:
            adjustments['atr_sl_mult'] = 1.2
            adjustments['atr_tp_mult'] = 2.0
            adjustments['position_size_mult'] = 0.8  # Smaller in downtrend
            
        elif analysis.current_regime == MarketRegime.RANGING:
            adjustments['atr_sl_mult'] = 0.7
            adjustments['atr_tp_mult'] = 1.0
            adjustments['position_size_mult'] = 1.0
            adjustments['max_daily_trades'] = 5  # More trades in range
        
        return adjustments


# ══════════════════════════════════════════════════════════════════════════════
# BOTTLENECK IDENTIFIER
# ══════════════════════════════════════════════════════════════════════════════

class BottleneckIdentifier:
    """Identifies structural bottlenecks in the trading system"""
    
    def __init__(self):
        self.thresholds = {
            'execution_latency_ms': 100,  # > 100ms is slow
            'smart_money_matrix_ms': 1000,  # > 1s is critical
            'slippage_pips': 2.0,  # > 2 pips slippage
            'win_rate': 0.45,  # < 45% win rate
            'profit_factor': 1.2,  # < 1.2 PF
            'max_drawdown_pct': 8.0,  # > 8% drawdown
            'kelly_criterion': 0.1,  # < 10% Kelly
        }
    
    def identify(
        self, 
        metrics: PerformanceMetrics, 
        regime: RegimeAnalysis,
        latencies: List[float] = None
    ) -> List[Bottleneck]:
        """Identify bottlenecks from metrics"""
        bottlenecks = []
        
        # Execution latency bottleneck
        if metrics.avg_latency_ms > self.thresholds['execution_latency_ms']:
            severity = "critical" if metrics.avg_latency_ms > 500 else "high"
            bottlenecks.append(Bottleneck(
                component="Execution Engine",
                metric_name="avg_latency_ms",
                current_value=metrics.avg_latency_ms,
                threshold=self.thresholds['execution_latency_ms'],
                severity=severity,
                recommendation="Optimize order submission pipeline, consider async batch processing"
            ))
        
        # Slippage bottleneck
        if metrics.avg_slippage_pips > self.thresholds['slippage_pips']:
            bottlenecks.append(Bottleneck(
                component="Order Execution",
                metric_name="avg_slippage_pips",
                current_value=metrics.avg_slippage_pips,
                threshold=self.thresholds['slippage_pips'],
                severity="medium",
                recommendation="Use limit orders instead of market, adjust entry timing"
            ))
        
        # Win rate bottleneck
        if metrics.win_rate < self.thresholds['win_rate']:
            bottlenecks.append(Bottleneck(
                component="Signal Generation",
                metric_name="win_rate",
                current_value=metrics.win_rate,
                threshold=self.thresholds['win_rate'],
                severity="high",
                recommendation="Tighten entry filters, add confluence requirements"
            ))
        
        # Profit factor bottleneck
        if metrics.profit_factor < self.thresholds['profit_factor']:
            bottlenecks.append(Bottleneck(
                component="Risk Management",
                metric_name="profit_factor",
                current_value=metrics.profit_factor,
                threshold=self.thresholds['profit_factor'],
                severity="high",
                recommendation="Adjust R:R ratio, optimize take profit levels"
            ))
        
        # Drawdown bottleneck
        if metrics.max_drawdown_pct > self.thresholds['max_drawdown_pct']:
            bottlenecks.append(Bottleneck(
                component="Risk Management",
                metric_name="max_drawdown_pct",
                current_value=metrics.max_drawdown_pct,
                threshold=self.thresholds['max_drawdown_pct'],
                severity="critical",
                recommendation="Reduce position size, tighten daily loss limits"
            ))
        
        # Regime-specific bottlenecks
        if regime.current_regime == MarketRegime.HIGH_VOLATILITY:
            bottlenecks.append(Bottleneck(
                component="Regime Adaptation",
                metric_name="volatility_percentile",
                current_value=regime.volatility_percentile,
                threshold=80,
                severity="medium",
                recommendation="Switch to wider stops, reduce position size"
            ))
        
        # Smart Money Matrix bottleneck (if available)
        if latencies and len(latencies) > 0:
            avg_matrix_time = statistics.mean(latencies)
            if avg_matrix_time > self.thresholds['smart_money_matrix_ms']:
                bottlenecks.append(Bottleneck(
                    component="Smart Money Matrix",
                    metric_name="avg_computation_ms",
                    current_value=avg_matrix_time,
                    threshold=self.thresholds['smart_money_matrix_ms'],
                    severity="critical",
                    recommendation="Refactor with Numba/Cython, optimize array operations"
                ))
        
        return bottlenecks


# ══════════════════════════════════════════════════════════════════════════════
# MAIN ANALYSIS ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class AlphaAnalysisEngine:
    """
    Main analysis engine orchestrating all components.
    
    Usage:
        engine = AlphaAnalysisEngine()
        report = engine.analyze(days=7)
        print(report['metrics'].edge_score)
    """
    
    def __init__(self, log_dir: str = "/opt/trading-bridge/data"):
        self.log_reader = LogReader(log_dir)
        self.metrics_calc = MetricsCalculator()
        self.regime_detector = RegimeDetector()
        self.bottleneck_identifier = BottleneckIdentifier()
    
    def analyze(self, days: int = 7) -> Dict:
        """
        Run full analysis on recent trading data.
        
        Returns:
            Dict with metrics, regime, bottlenecks, and recommendations
        """
        log.info(f"Starting analysis for last {days} days...")
        
        # Read trades
        trades = self.log_reader.read_trades(days=days)
        state = self.log_reader.read_state()
        
        log.info(f"Loaded {len(trades)} trades")
        
        # Calculate metrics
        metrics = self.metrics_calc.calculate(trades)
        
        # Detect regime
        regime = self.regime_detector.analyze(trades)
        
        # Identify bottlenecks
        bottlenecks = self.bottleneck_identifier.identify(metrics, regime)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(metrics, regime, bottlenecks)
        
        # Build report
        report = {
            'timestamp': datetime.now().isoformat(),
            'analysis_period_days': days,
            'total_trades': metrics.total_trades,
            'metrics': metrics,
            'regime': regime,
            'bottlenecks': bottlenecks,
            'recommendations': recommendations,
            'current_state': state,
            'evolution_candidates': self._identify_evolution_candidates(metrics, regime)
        }
        
        log.info(f"Analysis complete. Edge score: {metrics.edge_score:.1f}/100")
        
        return report
    
    def _generate_recommendations(
        self, 
        metrics: PerformanceMetrics, 
        regime: RegimeAnalysis,
        bottlenecks: List[Bottleneck]
    ) -> List[str]:
        """Generate actionable recommendations"""
        recommendations = []
        
        # Based on win rate
        if metrics.win_rate < 0.5:
            recommendations.append(
                "WIN RATE BELOW 50%: Consider adding additional confluence filters "
                "before signal generation"
            )
        
        # Based on profit factor
        if metrics.profit_factor < 1.5:
            recommendations.append(
                "PROFIT FACTOR LOW: Optimize take profit targets, consider trailing stops"
            )
        
        # Based on drawdown
        if metrics.max_drawdown_pct > 5:
            recommendations.append(
                "HIGH DRAWDOWN: Reduce position size, implement tighter daily loss limits"
            )
        
        # Based on regime
        if regime.current_regime == MarketRegime.HIGH_VOLATILITY:
            recommendations.append(
                "HIGH VOLATILITY REGIME: Widen stops by 1.5x ATR, reduce position size 30%"
            )
        elif regime.current_regime == MarketRegime.RANGING:
            recommendations.append(
                "RANGING MARKET: Use range-bound strategy, tighter TP/SL"
            )
        
        # Based on bottlenecks
        critical_bottlenecks = [b for b in bottlenecks if b.severity == "critical"]
        if critical_bottlenecks:
            recommendations.append(
                f"CRITICAL BOTTLENECKS DETECTED: {len(critical_bottlenecks)} issues require immediate attention"
            )
        
        # Based on latency
        if metrics.avg_latency_ms > 100:
            recommendations.append(
                "HIGH LATENCY: Optimize execution pipeline, consider Numba/Cython for matrix operations"
            )
        
        return recommendations
    
    def _identify_evolution_candidates(
        self, 
        metrics: PerformanceMetrics,
        regime: RegimeAnalysis
    ) -> List[Dict]:
        """Identify parameters that could benefit from evolution"""
        candidates = []
        
        # ATR multipliers
        candidates.append({
            'parameter': 'atr_sl_mult',
            'current_value': 1.0,
            'evolution_range': (0.5, 2.0),
            'reason': f"Current regime: {regime.current_regime.value}"
        })
        
        # OBI threshold
        candidates.append({
            'parameter': 'obi_threshold',
            'current_value': 1.5,
            'evolution_range': (1.0, 2.5),
            'reason': f"Win rate: {metrics.win_rate:.1%}"
        })
        
        # Volume MA period
        candidates.append({
            'parameter': 'volume_ma_period',
            'current_value': 20,
            'evolution_range': (10, 50),
            'reason': 'Optimize volume filter sensitivity'
        })
        
        # TP multiplier
        candidates.append({
            'parameter': 'tp_rr_ratio',
            'current_value': 2.0,
            'evolution_range': (1.5, 3.0),
            'reason': f"Current PF: {metrics.profit_factor:.2f}"
        })
        
        return candidates


# ══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE
# ══════════════════════════════════════════════════════════════════════════════

def run_analysis(days: int = 7, log_dir: str = "/opt/trading-bridge/data") -> Dict:
    """Quick analysis run"""
    engine = AlphaAnalysisEngine(log_dir)
    return engine.analyze(days)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 70)
    print("  ALPHA AGENT ANALYSIS ENGINE")
    print("=" * 70)
    
    report = run_analysis(days=7)
    
    print(f"\n  Total Trades: {report['total_trades']}")
    print(f"  Edge Score: {report['metrics'].edge_score:.1f}/100")
    print(f"  Win Rate: {report['metrics'].win_rate:.1%}")
    print(f"  Profit Factor: {report['metrics'].profit_factor:.2f}")
    print(f"  Sharpe Ratio: {report['metrics'].sharpe_ratio:.2f}")
    print(f"  Max Drawdown: {report['metrics'].max_drawdown_pct:.1f}%")
    print(f"  Current Regime: {report['regime'].current_regime.value}")
    
    print(f"\n  Bottlenecks: {len(report['bottlenecks'])}")
    for b in report['bottlenecks']:
        print(f"    [{b.severity.upper()}] {b.component}: {b.recommendation}")
    
    print(f"\n  Recommendations:")
    for r in report['recommendations']:
        print(f"    • {r}")
    
    print("=" * 70)
