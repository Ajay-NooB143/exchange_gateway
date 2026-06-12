"""
OMNI BRAIN V2 - Pipeline Integration Test
Tests: TwelveData → Pipeline → Sentiment → Telegram → MCP Bridge
"""
import os
import sys
import json
import time
import logging
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger('PipelineTest')

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'production'))

os.environ.setdefault('TZ', 'UTC')
time.tzset()


def load_env():
    env_file = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, _, value = line.partition('=')
                    os.environ[key.strip()] = value.strip().strip('"\'')


def check_keys():
    required = {
        'LIVE_DATA_API_KEY': 'Twelve Data',
        'TELEGRAM_BOT_TOKEN': 'Telegram',
    }
    optional = {
        'TELEGRAM_CHAT_ID': 'Telegram Chat ID',
        'PERPLEXITY_API_KEY': 'Perplexity',
        'FIRECRAWL_API_KEY': 'Firecrawl',
    }
    log.info("=== ENVIRONMENT CHECK ===")
    all_ok = True
    for key, name in required.items():
        val = os.getenv(key, '')
        if val and val != 'your_bot_token_here' and val != 'your_chat_id_here':
            log.info(f"  {name}: {'SET' if len(val) > 3 else 'INVALID'}")
        else:
            log.warning(f"  {name}: MISSING - skipping relevant tests")
            all_ok = False
    for key, name in optional.items():
        val = os.getenv(key, '')
        if val and len(val) > 3:
            log.info(f"  {name}: SET")
    return all_ok


def test_twelvedata():
    log.info("\n=== 1. TWELVEDATA PRICE CHECK ===")
    try:
        from live_feed_scanner import LiveFeedScanner
        scanner = LiveFeedScanner()
        if not scanner.api_key:
            log.warning("  SKIP: No Twelve Data API key")
            return None, None
        candles = scanner.fetch_candles('XAUUSD', 'H1')
        if not candles:
            log.warning("  SKIP: No candles returned (rate limited?)")
            return None, None
        price = candles[-1].close
        log.info(f"  XAUUSD Price: {price}")
        log.info(f"  Candles: {len(candles)} H1 bars")
        return price, [c.to_dict() for c in candles[-100:]]
    except Exception as e:
        log.error(f"  FAILED: {e}")
        return None, None


def test_pipeline(price, candles):
    log.info("\n=== 2. PIPELINE EXECUTION ===")
    if not candles:
        log.warning("  SKIP: No candle data")
        return None
    try:
        from pipeline_orchestrator import get_pipeline
        pipeline = get_pipeline()
        payload = {
            'symbol': 'XAUUSD',
            'direction': 'LONG' if price else 'LONG',
            'timeframe': 'H1',
            'price': price or 2350.0,
            'candles': candles
        }
        start = time.time()
        result = pipeline.run_pipeline(payload)
        elapsed = time.time() - start
        log.info(f"  Decision: {result.get('decision', 'N/A')}")
        log.info(f"  Score: {result.get('score', 0)}/100")
        log.info(f"  Time: {elapsed*1000:.0f}ms")
        log.info(f"  Steps: {json.dumps(result.get('steps', {}), indent=4)}")
        return result
    except Exception as e:
        log.error(f"  FAILED: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_sentiment():
    log.info("\n=== 3. SENTIMENT ANALYSIS ===")
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'mcp_stack'))
        from sentiment_analyzer import get_sentiment_analyzer
        analyzer = get_sentiment_analyzer()
        pp_configured = analyzer.perplexity.is_configured
        fc_configured = analyzer.firecrawl.is_configured
        log.info(f"  Perplexity key: {'SET' if pp_configured else 'NOT SET'}")
        log.info(f"  Firecrawl key:  {'SET' if fc_configured else 'NOT SET'}")
        result = analyzer.analyze("XAUUSD", 2350.0, "BULLISH")
        log.info(f"  Score: {result.score}/100 ({result.direction.value})")
        log.info(f"  News: {result.news_score}, Calendar: {result.calendar_score}, Trend: {result.trend_score}")
        log.info(f"  Summary: {result.news_summary[:120]}")
        return result
    except Exception as e:
        log.error(f"  FAILED: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_telegram(decision, score, price):
    log.info("\n=== 4. TELEGRAM ALERT ===")
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN', '')
    chat_id = os.getenv('TELEGRAM_CHAT_ID', '')
    if not bot_token or not chat_id or 'your' in bot_token:
        log.warning("  SKIP: Telegram not configured")
        return False
    try:
        from telegram_signals import send_signal_alert
        sent = send_signal_alert(
            symbol='XAUUSD',
            tf='H1',
            decision=decision or 'WAIT',
            score=score or 50,
            components={'OB': 20, 'FVG': 15, 'SWEEP': 30, 'VWAP': 10, 'SESSION': 5},
            mtf_data={'M15': 'BULLISH', 'H1': 'BULLISH', 'H4': 'NEUTRAL', 'D1': 'BULLISH'},
            threshold=75,
            cb_state='ACTIVE',
            price=price or 2350.0,
            atr=5.0
        )
        log.info(f"  Result: {'SENT' if sent else 'FAILED (rate limited?)'}")
        return sent
    except Exception as e:
        log.error(f"  FAILED: {e}")
        return False


def test_mcp_bridge(price, result, sentiment):
    log.info("\n=== 5. MCP BRIDGE PUSH ===")
    try:
        from mcp_bridge_server import PipelineBridge
        bridge = PipelineBridge()
        # Signal
        sig_ok = bridge.push_signal({
            'symbol': 'XAUUSD',
            'direction': 'LONG',
            'score': (result or {}).get('score', 50),
            'decision': (result or {}).get('decision', 'WAIT'),
            'entry_price': price or 2350.0,
            'timeframe': 'H1',
            'sentiment_score': sentiment.score if sentiment else 50,
            'components': {'OB': 20, 'FVG': 15, 'SWEEP': 30, 'VWAP': 10, 'SESSION': 5}
        })
        log.info(f"  Signal push: {'OK' if sig_ok else 'FAILED'}")

        # Sentiment
        if sentiment:
            sent_ok = bridge.push_sentiment({
                'symbol': 'XAUUSD',
                'score': sentiment.score,
                'direction': sentiment.direction.value,
                'news_score': sentiment.news_score,
                'calendar_score': sentiment.calendar_score,
                'trend_score': sentiment.trend_score,
                'news_summary': sentiment.news_summary
            })
            log.info(f"  Sentiment push: {'OK' if sent_ok else 'FAILED'}")

        # Position
        pos_ok = bridge.push_position({
            'symbol': 'XAUUSD',
            'direction': 'LONG',
            'entry_price': price or 2350.0,
            'current_price': (price or 2350.0) + 5.0,
            'pnl': 5.0,
            'pnl_pips': 50,
            'lot_size': 0.1,
            'open_time': datetime.now(timezone.utc).isoformat()
        })
        log.info(f"  Position push: {'OK' if pos_ok else 'FAILED'}")

        return sig_ok
    except Exception as e:
        log.error(f"  FAILED: {e}")
        return False


def test_pipeline_run(price, result):
    log.info("\n=== 6. PIPELINE RUN LOG ===")
    try:
        from mcp_bridge_server import PipelineBridge
        bridge = PipelineBridge()
        steps = (result or {}).get('steps', {})
        run_ok = bridge.push_pipeline_run({
            'symbol': 'XAUUSD',
            'timeframe': 'H1',
            'score': (result or {}).get('score', 0),
            'decision': (result or {}).get('decision', 'ERROR'),
            'cb_state': 'ACTIVE',
            'mtf_confirmed': True,
            'total_ms': 250.0,
            'step_times': {
                'scanner': 120.0,
                'cb': 0.5,
                'mtf': 0.1,
                'confidence': 50.0,
                'threshold': 0.2,
                'execute': 5.0
            },
            'error': ''
        })
        log.info(f"  Pipeline run log: {'OK' if run_ok else 'FAILED'}")
        return run_ok
    except Exception as e:
        log.error(f"  FAILED: {e}")
        return False


def summary(results):
    log.info("\n" + "=" * 56)
    log.info("  PIPELINE INTEGRATION TEST - SUMMARY")
    log.info("=" * 56)
    passed = sum(1 for r in results if r)
    total = len(results)
    log.info(f"  Passed: {passed}/{total}")
    log.info(f"  Time:   {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}")
    if passed < total:
        log.warning(f"  Failed: {total - passed}")
    log.info("=" * 56)


if __name__ == '__main__':
    load_env()
    has_keys = check_keys()

    price, candles = test_twelvedata()
    result = test_pipeline(price, candles)
    sentiment = test_sentiment()
    telegram_ok = test_telegram(
        (result or {}).get('decision'),
        (result or {}).get('score'),
        price
    )
    bridge_ok = test_mcp_bridge(price, result, sentiment)
    run_ok = test_pipeline_run(price, result)

    summary([price is not None, result is not None, sentiment is not None,
             telegram_ok, bridge_ok, run_ok])
