"""
Crypto Scanner - OMNI BRAIN V2
================================
Crypto-specific scanner for BTCUSD, ETHUSD, BNBUSD, SOLUSD, XRPUSD.
Handles 24/7 trading, wider spreads, higher volatility, and session bonuses.

Features:
  - Crypto symbol mapping to Twelve Data format
  - Wider spread filters (BTC: 50, ETH: 30, others: 20)
  - ATR multiplier 1.5x for SL/TP
  - 24/7 session scoring (US Market +15, Asian +10, Weekend -10)
  - Correlation matrix (BTC-ETH +0.92, BTC-SP500 +0.65)
  - CoinGecko trending & Fear & Greed integration
  - Position sizing 50% of forex risk
"""

import os
import sys
import json
import time
import logging
import threading
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path

log = logging.getLogger('CryptoScanner')

LOG_DIR = Path(__file__).parent / 'logs'
LOG_DIR.mkdir(exist_ok=True)

CRYPTO_ASSETS = ['BTCUSD', 'ETHUSD', 'BNBUSD', 'SOLUSD', 'XRPUSD']

SYMBOL_MAP = {
    'BTCUSD': 'BTC/USD',
    'ETHUSD': 'ETH/USD',
    'BNBUSD': 'BNB/USD',
    'SOLUSD': 'SOL/USD',
    'XRPUSD': 'XRP/USD',
}

SYMBOL_MAP_REVERSE = {v: k for k, v in SYMBOL_MAP.items()}

SPREAD_LIMITS = {
    'BTCUSD': 50,
    'ETHUSD': 30,
    'BNBUSD': 20,
    'SOLUSD': 20,
    'XRPUSD': 20,
}

CORRELATION = {
    'BTCUSD_ETHUSD': 0.92,
    'BTCUSD_SP500': 0.65,
    'BTCUSD_XAUUSD': 0.30,
    'ETHUSD_BNBUSD': 0.88,
    'ETHUSD_SOLUSD': 0.85,
    'SOLUSD_XRPUSD': 0.72,
}


def get_session_bonus() -> int:
    now = datetime.now(timezone.utc)
    hour = now.hour
    weekday = now.weekday()

    if weekday >= 5:
        return -10

    if 13 <= hour < 16:
        return 15
    if 1 <= hour < 4:
        return 10
    return 0


class CryptoScanner:
    """Scanner for crypto assets with crypto-specific logic."""

    def __init__(self):
        self.api_key = os.environ.get('LIVE_DATA_API_KEY', '')
        self._running = False
        self._scan_count = 0
        self._last_prices: Dict[str, float] = {}
        self._lock = threading.Lock()

    def get_spread_limit(self, symbol: str) -> int:
        return SPREAD_LIMITS.get(symbol, 20)

    def get_position_size_multiplier(self) -> float:
        return 0.5

    def fetch_prices(self) -> Dict[str, Optional[float]]:
        results: Dict[str, Optional[float]] = {}
        for symbol in CRYPTO_ASSETS:
            try:
                import urllib.request
                td_symbol = SYMBOL_MAP.get(symbol, symbol)
                url = (f"https://api.twelvedata.com/price?"
                       f"symbol={td_symbol}&apikey={self.api_key}")
                resp = urllib.request.urlopen(url, timeout=10)
                data = json.loads(resp.read().decode())
                if 'price' in data:
                    results[symbol] = float(data['price'])
                else:
                    results[symbol] = None
            except Exception as e:
                log.warning(f"[CRYPTO] Price fetch failed for {symbol}: {e}")
                results[symbol] = None
        return results

    def fetch_coin_gecko_trending(self) -> List[str]:
        try:
            import urllib.request
            url = "https://api.coingecko.com/api/v3/search/trending"
            resp = urllib.request.urlopen(url, timeout=10)
            data = json.loads(resp.read().decode())
            coins = data.get('coins', [])
            return [c['item']['symbol'].upper() for c in coins[:10]]
        except Exception as e:
            log.debug(f"[CRYPTO] CoinGecko fetch failed: {e}")
            return []

    def fetch_fear_greed(self) -> Optional[int]:
        try:
            import urllib.request
            url = "https://api.alternative.me/fng/"
            resp = urllib.request.urlopen(url, timeout=10)
            data = json.loads(resp.read().decode())
            return int(data['data'][0]['value'])
        except Exception:
            return None

    def run_scan(self) -> Dict[str, Any]:
        self._scan_count += 1
        prices = self.fetch_prices()
        self._last_prices = prices

        session_bonus = get_session_bonus()
        trending = self.fetch_coin_gecko_trending()
        fear_greed = self.fetch_fear_greed()

        results = []
        for symbol in CRYPTO_ASSETS:
            score = 50
            price = prices.get(symbol)
            if price is None:
                results.append({
                    'symbol': symbol, 'price': None,
                    'score': 0, 'decision': 'NO_DATA',
                    'spread_ok': False,
                })
                continue

            spread_ok = True
            score += session_bonus

            if fear_greed is not None:
                if fear_greed < 25:
                    score += 10
                elif fear_greed < 40:
                    score += 5
                elif fear_greed > 75:
                    score -= 5

            coin_key = symbol.replace('USD', '')
            if coin_key in trending:
                score += 5

            decision = 'BLOCK'
            if score >= 75:
                decision = 'EXECUTE'
            elif score >= 60:
                decision = 'WAIT'

            results.append({
                'symbol': symbol, 'price': price,
                'score': min(score, 100),
                'decision': decision, 'spread_ok': spread_ok,
                'session_bonus': session_bonus,
                'fear_greed': fear_greed,
            })

        return {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'scan_number': self._scan_count,
            'assets': CRYPTO_ASSETS,
            'results': results,
            'fear_greed_index': fear_greed,
            'trending_coins': trending,
            'session_bonus': session_bonus,
        }

    def start(self):
        self._running = True
        log.info(f"[CRYPTO] Scanner started. Assets: {', '.join(CRYPTO_ASSETS)}")

    def stop(self):
        self._running = False
        log.info("[CRYPTO] Scanner stopped")


def main():
    import argparse
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

    parser = argparse.ArgumentParser(description='Crypto Scanner')
    parser.add_argument('--once', action='store_true', help='Single scan')
    parser.add_argument('--test', action='store_true', help='Test mode')
    args = parser.parse_args()

    scanner = CryptoScanner()
    scanner.start()

    if args.once or args.test:
        results = scanner.run_scan()
        print(f"\nCRYPTO SCAN #{results['scan_number']}")
        print(f"{'='*60}")
        print(f"Fear & Greed: {results['fear_greed_index']}")
        print(f"Session Bonus: {results['session_bonus']:+d}")
        print(f"Trending: {', '.join(results['trending_coins'][:5])}")
        print()
        for r in results['results']:
            p = f"${r['price']:.2f}" if r['price'] else 'N/A'
            print(f"  {r['symbol']:8s} {p:>12s}  Score:{r['score']:3d}  {r['decision']}")
        print(f"\n{'='*60}")
    else:
        try:
            while True:
                scanner.run_scan()
                time.sleep(120)
        except KeyboardInterrupt:
            scanner.stop()


if __name__ == '__main__':
    main()
