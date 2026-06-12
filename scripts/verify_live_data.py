#!/usr/bin/env python3
"""
OMNI BRAIN V2 — Live Data Verification Script
==============================================
Runs a comprehensive check of all data pipeline components.
"""

import os
import sys
import json
import time
import urllib.request
import urllib.error
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

passed = 0
failed = 0
skipped = 0
errors = []


def check(label, condition, detail=''):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✅ {label}")
    else:
        failed += 1
        errors.append(f"{label}: {detail}")
        print(f"  ❌ {label}" + (f" — {detail}" if detail else ""))


def check_env_vars(vars):
    print("\n[CHECK 1] .env variables")
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ.setdefault(k.strip(), v.strip())
        print("  📄 .env loaded")
    else:
        print("  ⚠️  No .env file found")

    for var in vars:
        val = os.environ.get(var, '')
        check(f"{var} set", bool(val), 'missing from .env')
        if val:
            print(f"     {var}={val[:8]}...{val[-4:] if len(val) > 12 else val}")


def test_twelvedata_connection():
    print("\n[CHECK 2] TwelveData API connection")
    api_key = os.environ.get('LIVE_DATA_API_KEY', '')
    if not api_key:
        print("  ⏭️  Skipped — no API key")
        global skipped
        skipped += 1
        return False

    try:
        url = f"https://api.twelvedata.com/price?symbol=XAU/USD&apikey={api_key}"
        resp = urllib.request.urlopen(url, timeout=10)
        data = json.loads(resp.read().decode())
        check("GET price returns data", 'price' in data, str(data))
        return True
    except urllib.error.HTTPError as e:
        check(f"TwelveData HTTP {e.code}", False, str(e.reason))
        return False
    except Exception as e:
        check("TwelveData connection", False, str(e))
        return False


def fetch_sample_candle(symbol):
    print(f"\n[CHECK 3] Sample candle fetch: {symbol}")
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'production'))
        from live_feed_scanner import generate_mock_candles, LiveFeedScanner
        from live_feed_scanner import USE_MOCK_DATA

        if USE_MOCK_DATA or not os.environ.get('LIVE_DATA_API_KEY'):
            candles = generate_mock_candles(symbol, 'H1', 10)
            check(f"Mock candles for {symbol}", len(candles) > 0, f"got {len(candles)}")
            if candles:
                print(f"     Last close: {candles[-1].close}")
            return candles

        scanner = LiveFeedScanner()
        candles = scanner.fetch_candles(symbol, 'H1')
        check(f"Real candles for {symbol}", len(candles) > 0, f"got {len(candles)}")
        if candles:
            print(f"     Last close: {candles[-1].close}")
        return candles
    except Exception as e:
        check(f"Candle fetch for {symbol}", False, str(e))
        return []


def run_mock_pipeline_scan():
    print("\n[CHECK 4] Pipeline test scan")
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        from pipeline_orchestrator import PipelineEngine
        from live_feed_scanner import generate_mock_candles

        engine = PipelineEngine()
        mock = generate_mock_candles('XAUUSD', 'H1', 100)
        candles_dicts = [c.to_dict() for c in mock]
        payload = {
            'symbol': 'XAUUSD',
            'direction': 'LONG',
            'timeframe': 'H1',
            'price': mock[-1].close if mock else 2000.0,
            'candles': candles_dicts,
            'candles_data': {'H1': candles_dicts},
        }
        result = engine.run_pipeline(payload, 'verify')
        score = result.get('score', 0)
        decision = result.get('decision', 'BLOCK')
        check(f"Pipeline complete score={score} decision={decision}", True)
        if score == 0:
            print("     ⚠️  Score is 0 — components may be inactive")
        else:
            print(f"     ✅ Non-zero score: {score}")
        return result
    except Exception as e:
        check("Pipeline execution", False, str(e))
        import traceback
        traceback.print_exc()
        return {}


def print_score_trace(result):
    print("\n[CHECK 5] Score trace")
    if not result:
        print("  ⏭️  No result to trace")
        return
    steps = result.get('steps', {})
    conf = steps.get('confidence', {})
    components = conf.get('components', {})
    if components:
        print(f"  Score: {result.get('score', 0)} | Decision: {result.get('decision', 'N/A')}")
        for k, v in sorted(components.items()):
            if v != 0:
                bar = '█' * (int(v) // 5)
                print(f"    {k:12}: {v:3} {bar}")
    else:
        print("  ⚠️  No components found in result")


def send_test_message(text):
    print(f"\n[CHECK 6] Telegram test message")
    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID', '')
    if not bot_token or not chat_id:
        print("  ⏭️  Skipped — Telegram not configured")
        global skipped
        skipped += 1
        return

    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = json.dumps({'chat_id': chat_id, 'text': text}).encode()
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read().decode())
        check("Telegram message sent", result.get('ok', False), str(result))
    except Exception as e:
        check("Telegram send", False, str(e))


def test_all_imports():
    print("\n[CHECK 7] Module imports")
    modules = [
        'live_feed_scanner', 'confidence_scorer', 'health_heartbeat',
        'memory_monitor', 'smart_money_matrix', 'pattern_engine',
        'mtf_confirmation', 'circuit_breaker', 'risk_manager',
        'sentiment_engine', 'forex_factory_news', 'treasury_monitor',
        'correlation_engine', 'session_detector', 'divergence_scanner',
        'adaptive_threshold', 'regime_detector', 'ai_decision_engine',
    ]
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'production'))
    for mod in modules:
        try:
            __import__(mod)
            check(f"{mod} imports OK", True)
        except Exception as e:
            check(f"{mod} import", False, str(e))


def print_verification_summary():
    global passed, failed, skipped
    total = passed + failed + skipped
    print("\n" + "=" * 60)
    print("  VERIFICATION SUMMARY")
    print("=" * 60)
    print(f"  Passed:  {passed}/{total}")
    print(f"  Failed:  {failed}/{total}")
    print(f"  Skipped: {skipped}/{total}")
    if errors:
        print("\n  Issues found:")
        for e in errors:
            print(f"    • {e}")
    if failed == 0:
        print("\n  ✅ All checks passed — system is healthy")
    else:
        print(f"\n  ❌ {failed} check(s) failed — review issues above")
    print("=" * 60)


def main():
    print("=" * 60)
    print("  OMNI BRAIN V2 — DATA VERIFICATION")
    print("=" * 60)

    check_env_vars(['LIVE_DATA_API_KEY', 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID'])
    test_twelvedata_connection()
    fetch_sample_candle('XAUUSD')
    fetch_sample_candle('EURUSD')
    result = run_mock_pipeline_scan()
    print_score_trace(result)
    send_test_message("🔧 OMNI BRAIN verification test")
    test_all_imports()
    print_verification_summary()

    return 1 if failed > 0 else 0


if __name__ == '__main__':
    sys.exit(main())
