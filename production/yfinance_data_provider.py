"""
YFinance Data Provider — OMNI BRAIN V2
======================================
Free market data via yfinance (no API key required).

Supports:
  - Forex: XAUUSD, EURUSD, GBPUSD
  - Indices: SP500
  - Crypto: BTCUSD, ETHUSD, BNBUSD, SOLUSD, XRPUSD

Timeframes:
  M15 → 15m, H1 → 60m, H4 → resampled from 60m, D1 → 1d

Limitations:
  - Intraday data limited to 60 days max
  - H4 must be resampled from hourly candles
  - Weekend/holiday gaps possible
"""

import time
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger('YFinanceProvider')

# ══════════════════════════════════════════════════════════════════════════════
# SYMBOL MAPPING
# ══════════════════════════════════════════════════════════════════════════════

YF_SYMBOL_MAP = {
    'XAUUSD': 'GC=F',      # Gold futures
    'EURUSD': 'EURUSD=X',
    'GBPUSD': 'GBPUSD=X',
    'SP500': '^GSPC',       # S&P 500 index
    'BTCUSD': 'BTC-USD',
    'ETHUSD': 'ETH-USD',
    'BNBUSD': 'BNB-USD',
    'SOLUSD': 'SOL-USD',
    'XRPUSD': 'XRP-USD',
}

# yfinance interval mapping
TF_YF_MAP = {
    'M15': '15m',
    'H1': '60m',
    'H4': '60m',  # Will be resampled
    'D1': '1d',
}

# Max candles per fetch
MAX_CANDLES = 200


def fetch_yf_candles(symbol: str, timeframe: str, limit: int = 100) -> List[Dict[str, Any]]:
    """
    Fetch OHLCV candles from yfinance.

    Returns list of dicts:
        [{'timestamp': int, 'open': float, 'high': float,
          'low': float, 'close': float, 'volume': float}, ...]

    Candles are returned in chronological order (oldest first).
    """
    yf_symbol = YF_SYMBOL_MAP.get(symbol)
    if not yf_symbol:
        log.warning("[YF] Unknown symbol: %s", symbol)
        return []

    yf_interval = TF_YF_MAP.get(timeframe)
    if not yf_interval:
        log.warning("[YF] Unknown timeframe: %s", timeframe)
        return []

    try:
        import yfinance as yf
        import pandas as pd

        # Determine period based on timeframe
        # yfinance limits: intraday max 60 days, daily unlimited
        if timeframe in ('M15', 'H1', 'H4'):
            period = '60d'
        elif timeframe == 'D1':
            period = '1y'
        else:
            period = '60d'

        ticker = yf.Ticker(yf_symbol)

        # For H4, fetch hourly and resample
        if timeframe == 'H4':
            df = ticker.history(period=period, interval='60m')
            if df.empty:
                log.warning("[YF] No hourly data for %s", symbol)
                return []

            # Resample to 4-hour candles
            df.index = pd.to_datetime(df.index, utc=True)
            df_resampled = df.resample('4h').agg({
                'Open': 'first',
                'High': 'max',
                'Low': 'min',
                'Close': 'last',
                'Volume': 'sum'
            }).dropna()

            df = df_resampled
        else:
            df = ticker.history(period=period, interval=yf_interval)

        if df.empty:
            log.warning("[YF] No data for %s %s", symbol, timeframe)
            return []

        # Convert to our format
        candles = []
        for idx, row in df.iterrows():
            try:
                ts = int(idx.timestamp())
                candle = {
                    'timestamp': ts,
                    'open': round(float(row['Open']), 6),
                    'high': round(float(row['High']), 6),
                    'low': round(float(row['Low']), 6),
                    'close': round(float(row['Close']), 6),
                    'volume': round(float(row['Volume']), 0),
                }
                candles.append(candle)
            except Exception:
                continue

        # Take last `limit` candles
        if len(candles) > limit:
            candles = candles[-limit:]

        log.info("[YF] Fetched %s %s — %d candles", symbol, timeframe, len(candles))
        return candles

    except ImportError:
        log.error("[YF] yfinance not installed: pip install yfinance")
        return []
    except Exception as e:
        log.error("[YF] Error fetching %s %s: %s", symbol, timeframe, e)
        return []


def validate_yf_candles(candles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Validate yfinance candle data, reject bad entries."""
    validated = []
    for c in candles:
        if c.get('open', 0) <= 0 or c.get('close', 0) <= 0:
            continue
        if c.get('high', 0) < c.get('low', 0):
            continue
        validated.append(c)
    return validated


def is_available() -> bool:
    """Check if yfinance is importable."""
    try:
        import yfinance
        return True
    except ImportError:
        return False
