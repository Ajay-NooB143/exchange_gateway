# Liquidity Chase — HFT Micro-Scalping Engine

## Architecture

```
WebSocket Feed → DOM Engine → Strategy → Executor
     │               │            │           │
  Level II        OBI Calc     Liquidity    Market
  Bids/Asks       + Spoof      Chase        Orders
                  Filter       + Tape        + Risk
```

## Quick Start

```bash
cd hft_liquidity_chase
python3 engine.py
```

## Configuration

Edit `Config` class in `engine.py`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `symbol` | GC | Futures symbol |
| `tick_size` | 0.10 | Minimum price increment |
| `tick_value` | 10.0 | Dollar value per tick |
| `obi_depth_ticks` | 10 | Price range for OBI calculation |
| `obi_threshold` | 1.5 | Ratio for bullish/bearish signal |
| `min_order_age_ms` | 500 | Spoofing filter (ms) |
| `chase_volume_threshold` | 50.0 | Min size for liquidity wall |
| `tp_ticks` | 4 | Take profit in ticks |
| `sl_ticks` | 3 | Stop loss in ticks |
| `max_hold_seconds` | 180 | Time-stop (3 min) |

## How It Works

### 1. Order Book Imbalance (OBI)

```python
ratio = bid_volume / ask_volume

if ratio > 1.5:   # More bids than asks
    → BULLISH     # Price drawn up to consume liquidity
elif ratio < 0.67: # More asks than bids
    → BEARISH     # Price drawn down to consume liquidity
```

### 2. Liquidity Chase Detection

**LONG signal:**
- Dense resting bids (wall) above current price
- Aggressive market buying (hitting asks)
- OBI ratio > 1.5

**SHORT signal:**
- Dense resting asks (wall) below current price
- Aggressive market selling (hitting bids)
- OBI ratio < 0.67

### 3. Spoofing Filter

```python
# Orders must persist for ≥ 500ms to be considered "real"
if order_age < 500ms:
    → DISCARD (likely spoofed)
```

### 4. Risk Management

| Rule | Value | Action |
|------|-------|--------|
| Time-Stop | 180s | Force exit at 3 min |
| Take Profit | +4 ticks | Exit at profit target |
| Stop Loss | -3 ticks | Exit at loss limit |
| Wall-Pull | Immediate | Exit if wall disappears |

## Connecting to Real Exchange

### CME Futures (via CQG)

```python
# Replace WebSocketFeed.connect() with:
import websockets

async def connect(self):
    async with websockets.connect("wss://feed.cqg.com/ws") as ws:
        await ws.send(json.dumps({
            "type": "subscribe",
            "symbols": ["GC"]
        }))
        async for message in ws:
            data = json.loads(message)
            dom = parse_cme_dom(data)
            await self.on_dom_update(dom)
```

### Crypto Futures (Binance)

```python
async def connect(self):
    stream = f"wss://fstream.binance.com/ws/{self.config.symbol.lower()}@depth20@100ms"
    async with websockets.connect(stream) as ws:
        async for message in ws:
            data = json.loads(message)
            dom = parse_binance_dom(data)
            await self.on_dom_update(dom)
```

## Performance Targets

| Metric | Target |
|--------|--------|
| DOM processing | < 1ms |
| OBI calculation | < 0.5ms |
| Strategy decision | < 0.5ms |
| Order submission | < 1ms |
| End-to-end latency | < 3ms |

## Risk Warnings

- This is for educational purposes
- HFT requires colocated servers near exchange
- Paper trade extensively before live trading
- Futures trading involves substantial risk of loss
