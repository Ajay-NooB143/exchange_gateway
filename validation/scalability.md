# Scalability — Technical Limitations & Scaling Considerations

## 1. Broker API Rate Limits

| Broker Type | Typical Limit | Risk at Scale |
|-------------|---------------|---------------|
| REST API (most) | 10-60 requests/minute | Hit during rapid scalping |
| WebSocket streaming | 100+ connections | Fine for single strategy |
| FIX protocol | No limit | Institutional only |

**What to monitor:**
```
429 Too Many Requests  → You're exceeding rate limit
503 Service Unavailable → Broker is overloaded (common during NFP)
```

**Mitigation:** Implement exponential backoff. Never retry immediately.

## 2. Position Size Limitations

| Factor | Typical Limit | Impact |
|--------|--------------|--------|
| Max lot size per order | 10-50 lots (broker dependent) | Can't scale past this per trade |
| Max open positions | 50-200 | Multiple concurrent scalps |
| Max daily volume | Varies by broker/instrument | Limits total daily throughput |
| Margin requirements | Varies by leverage | Higher size = more margin needed |

**XAUUSD specific:**
- 1 lot = 100 oz of gold
- At $2350/oz, 1 lot = $235,000 notional
- With 1:100 leverage, margin = $2,350 per lot
- 10 lots = $23,500 margin required

## 3. Slippage Scaling

As position size increases, slippage increases non-linearly:

```
Size: 1 lot   → avg slippage: 0.1-0.3 pts
Size: 5 lots  → avg slippage: 0.3-0.8 pts
Size: 10 lots → avg slippage: 0.5-1.5 pts
Size: 50 lots → avg slippage: 2.0-5.0 pts (or rejected)
```

**This is the #1 hidden cost of scaling.** Your backtest assumes 0.2pt slippage. At 50 lots, actual slippage is 10x that.

## 4. Latency at Scale

```
Signal → Webhook → Node.js → Broker API → Exchange

Typical: 200-500ms
Under load: 1000-3000ms
During news: 5000ms+ (or timeout)
```

**For scalping, this matters.** A 1-second delay on XAUUSD can mean 5-10 points of difference.

## 5. Data Feed Limitations

| Source | Limitation |
|--------|-----------|
| TradingView alerts | 1-2 second delay from bar close |
| Yahoo Finance API | 15-minute delay (not suitable) |
| Broker WebSocket | Real-time, but 50-200ms latency |
| Co-located feeds | <1ms, institutional only |

**TradingView is not real-time.** Your alerts fire at bar close, which is already 1 minute old on a 1-min chart. At scale, consider moving to a direct data feed.

## 6. Scaling Roadmap

```
Phase 1: Paper Trading (current)
  - 1 lot, validate 100 trades
  - Measure actual slippage, latency, win rate
  - Prove the edge exists

Phase 2: Small Live
  - 1-2 lots, real money
  - Compare live vs paper performance
  - If live slippage > 2x paper slippage → problem

Phase 3: Scale Position Size
  - Increase by 50% increments, not 2x
  - Monitor slippage per trade
  - If slippage exceeds 1.5x average → stop scaling

Phase 4: Scale Frequency
  - Add more instruments (EURUSD, GBPUSD)
  - Each instrument needs its own validation
  - Don't assume one instrument's edge works on another

Phase 5: Infrastructure
  - Move to VPS near broker server (reduce latency)
  - Consider WebSocket for order management
  - Add redundancy (backup broker, backup server)
```

## 7. Red Flags When Scaling

| Warning Sign | Action |
|--------------|--------|
| Slippage doubles | Reduce size immediately |
| Win rate drops >5% | Re-validate the strategy |
| Latency >1s consistently | Move server closer to broker |
| Broker rejects orders | You're hitting their limits |
| Drawdown exceeds 2x backtest | Stop trading, re-optimize |

## 8. The Hard Truth

Most strategies that work at 1 lot fail at 10 lots. The edge doesn't scale linearly because:
1. You become a market-moving participant
2. Liquidity thins at your size
3. Slippage eats the edge
4. Broker behavior changes (they may hedge against you)

**The correct approach:** Validate at 1 lot for 100+ trades. Then increase by 50% increments, measuring slippage at each step. The maximum profitable size is where slippage cost exceeds the edge.
