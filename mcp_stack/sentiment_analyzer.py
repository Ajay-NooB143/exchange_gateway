"""
Market Sentiment Analyzer - OMNI BRAIN V2 MCP Stack
====================================================
Uses Perplexity MCP for real-time macro news and Firecrawl MCP
for economic calendar scraping to produce a market sentiment score.

Architecture:
  Perplexity MCP ──→ Macro News Query ──┐
                                         ├──→ Sentiment Score (0-100)
  Firecrawl MCP  ──→ Economic Calendar ─┘

Scoring:
  BULLISH: 60-100 (strong buy signal)
  NEUTRAL: 40-59  (no trade)
  BEARISH: 0-39   (strong sell signal)

Components:
  - News sentiment (40% weight): CPI, Fed, NFP, geopolitical
  - Calendar events (30% weight): upcoming high-impact events
  - Trend alignment (30% weight): macro vs technical alignment
"""

import os
import sys
import json
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum

log = logging.getLogger('SentimentAnalyzer')

LOG_DIR = Path(__file__).parent / 'logs'
LOG_DIR.mkdir(exist_ok=True)


class SentimentDirection(Enum):
    BULLISH = "BULLISH"
    NEUTRAL = "NEUTRAL"
    BEARISH = "BEARISH"


@dataclass
class SentimentResult:
    symbol: str
    score: int  # 0-100
    direction: SentimentDirection
    news_score: int = 0
    calendar_score: int = 0
    trend_score: int = 0
    news_summary: str = ""
    calendar_events: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: str = ""
    source: str = "perplexity+firecrawl"

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


# ══════════════════════════════════════════════════════════════════════════════
# PERPLEXITY INTEGRATION (Real-time Macro News)
# ══════════════════════════════════════════════════════════════════════════════

class PerplexityClient:
    """
    Query Perplexity API for real-time macroeconomic news.
    Uses the REST API directly (no MCP server dependency for Python).
    """

    API_URL = "https://api.perplexity.ai/chat/completions"

    def __init__(self):
        self.api_key = os.environ.get('PERPLEXITY_API_KEY', '')
        self.model = "sonar-pro"

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def query_macro_news(self, symbol: str = "XAUUSD") -> Dict[str, Any]:
        """
        Query Perplexity for latest macro news affecting the symbol.
        Returns sentiment analysis with score.
        """
        if not self.is_configured:
            return self._fallback_response(symbol)

        try:
            import urllib.request

            prompt = self._build_macro_prompt(symbol)

            payload = json.dumps({
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a financial analyst. Analyze the latest macroeconomic "
                            "news and provide a sentiment score for gold (XAUUSD). "
                            "Consider: Fed rate decisions, CPI data, NFP, geopolitical events, "
                            "USD strength, bond yields, and risk appetite. "
                            "Respond with JSON: {\"score\": 0-100, \"direction\": \"BULLISH|NEUTRAL|BEARISH\", "
                            "\"summary\": \"brief analysis\", \"factors\": [\"factor1\", \"factor2\"]}"
                        )
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "max_tokens": 500,
                "temperature": 0.2
            })

            req = urllib.request.Request(
                self.API_URL,
                data=payload.encode('utf-8'),
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {self.api_key}'
                }
            )

            resp = urllib.request.urlopen(req, timeout=15)
            result = json.loads(resp.read().decode())

            content = result.get('choices', [{}])[0].get('message', {}).get('content', '')

            return self._parse_response(content, symbol)

        except urllib.error.HTTPError as e:
            if e.code == 401:
                log.warning("Awaiting Perplexity API funding - bypassing sentiment analysis for now")
            else:
                log.error(f"Perplexity HTTP {e.code}: {e.reason}")
            return self._fallback_response(symbol, reason=f"HTTP {e.code}")

        except Exception as e:
            log.error(f"Perplexity query failed: {e}")
            return self._fallback_response(symbol, reason=str(e))

    def _build_macro_prompt(self, symbol: str) -> str:
        now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
        return (
            f"What is the current macroeconomic outlook for {symbol} as of {now}? "
            f"Analyze: 1) Federal Reserve policy direction, 2) Latest CPI/inflation data, "
            f"3) Non-Farm Payrolls impact, 4) USD index strength, 5) Geopolitical risks, "
            f"6) Bond yield movements, 7) Central bank decisions. "
            f"Provide a sentiment score from 0 (extremely bearish) to 100 (extremely bullish)."
        )

    def _parse_response(self, content: str, symbol: str) -> Dict[str, Any]:
        try:
            json_start = content.find('{')
            json_end = content.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                data = json.loads(content[json_start:json_end])
                return {
                    'score': max(0, min(100, int(data.get('score', 50)))),
                    'direction': data.get('direction', 'NEUTRAL'),
                    'summary': data.get('summary', content[:200]),
                    'factors': data.get('factors', []),
                    'source': 'perplexity'
                }
        except Exception:
            pass

        score = self._keyword_sentiment(content)
        return {
            'score': score,
            'direction': 'BULLISH' if score >= 60 else 'BEARISH' if score <= 40 else 'NEUTRAL',
            'summary': content[:300],
            'factors': [],
            'source': 'perplexity'
        }

    def _keyword_sentiment(self, text: str) -> int:
        text_lower = text.lower()
        bullish_kw = ['bullish', 'rally', 'surge', 'strong', 'buy', 'upward', 'gain', 'positive', 'hawkish pause', 'dovish']
        bearish_kw = ['bearish', 'decline', 'drop', 'weak', 'sell', 'downward', 'loss', 'negative', 'hawkish', 'rate hike']

        bull_count = sum(1 for kw in bullish_kw if kw in text_lower)
        bear_count = sum(1 for kw in bearish_kw if kw in text_lower)

        if bull_count > bear_count:
            return min(75, 50 + (bull_count - bear_count) * 10)
        elif bear_count > bull_count:
            return max(25, 50 - (bear_count - bull_count) * 10)
        return 50

    def _fallback_response(self, symbol: str, reason: str = "not configured") -> Dict[str, Any]:
        log.info(f"Perplexity fallback for {symbol}: {reason}")
        return {
            'score': 50,
            'direction': 'NEUTRAL',
            'summary': f'Using neutral sentiment ({reason}).',
            'factors': [f'Fallback: {reason}'],
            'source': 'fallback'
        }


# ══════════════════════════════════════════════════════════════════════════════
# FIRECRAWL INTEGRATION (Economic Calendar Scraping)
# ══════════════════════════════════════════════════════════════════════════════

class FirecrawlClient:
    """
    Scrape economic calendars using Firecrawl API.
    Extracts high-impact events that affect gold prices.
    """

    API_URL = "https://api.firecrawl.dev/v1/scrape"

    ECONOMIC_CALENDARS = [
        "https://www.forexfactory.com/calendar",
        "https://www.investing.com/economic-calendar/",
        "https://www.dailyfx.com/economic-calendar"
    ]

    def __init__(self):
        self.api_key = os.environ.get('FIRECRAWL_API_KEY', '')

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def scrape_calendar(self, days_ahead: int = 3) -> List[Dict[str, Any]]:
        """
        Scrape economic calendar for upcoming events.
        Returns list of events with impact level.
        """
        if not self.is_configured:
            return self._fallback_calendar()

        try:
            import urllib.request

            events = []
            for url in self.ECONOMIC_CALENDARS[:1]:
                result = self._scrape_url(url)
                if result:
                    events.extend(result)

            return self._filter_events(events, days_ahead)

        except Exception as e:
            log.error(f"Firecrawl scrape failed: {e}")
            return self._fallback_calendar()

    def _scrape_url(self, url: str) -> List[Dict[str, Any]]:
        try:
            import urllib.request

            payload = json.dumps({
                "url": url,
                "formats": ["markdown"],
                "onlyMainContent": True,
                "waitFor": 2000
            })

            req = urllib.request.Request(
                self.API_URL,
                data=payload.encode('utf-8'),
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {self.api_key}'
                }
            )

            resp = urllib.request.urlopen(req, timeout=30)
            result = json.loads(resp.read().decode())

            markdown = result.get('data', {}).get('markdown', '')
            return self._parse_calendar_markdown(markdown)

        except Exception as e:
            log.debug(f"Firecrawl scrape error for {url}: {e}")
            return []

    def _parse_calendar_markdown(self, markdown: str) -> List[Dict[str, Any]]:
        events = []
        lines = markdown.split('\n')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            impact = 'LOW'
            if 'high' in line.lower() or '🔴' in line or '3' in line:
                impact = 'HIGH'
            elif 'medium' in line.lower() or '🟡' in line or '2' in line:
                impact = 'MEDIUM'

            if impact in ('HIGH', 'MEDIUM'):
                events.append({
                    'event': line[:100],
                    'impact': impact,
                    'currency': self._detect_currency(line),
                    'scraped_at': datetime.now(timezone.utc).isoformat()
                })

        return events

    def _detect_currency(self, text: str) -> str:
        text_upper = text.upper()
        if 'USD' in text_upper or 'FED' in text_upper or 'NON-FARM' in text_upper:
            return 'USD'
        if 'EUR' in text_upper:
            return 'EUR'
        if 'GBP' in text_upper:
            return 'GBP'
        if 'JPY' in text_upper or 'BOJ' in text_upper:
            return 'JPY'
        if 'GOLD' in text_upper or 'XAU' in text_upper:
            return 'XAU'
        return 'USD'

    def _filter_events(self, events: List[Dict], days_ahead: int) -> List[Dict]:
        return [e for e in events if e.get('impact') in ('HIGH', 'MEDIUM')][:20]

    def _fallback_calendar(self) -> List[Dict]:
        now = datetime.now(timezone.utc)
        return [
            {
                'event': 'Fed Interest Rate Decision',
                'impact': 'HIGH',
                'currency': 'USD',
                'date': (now + timedelta(days=1)).strftime('%Y-%m-%d'),
                'source': 'fallback'
            },
            {
                'event': 'US CPI Inflation Data',
                'impact': 'HIGH',
                'currency': 'USD',
                'date': (now + timedelta(days=2)).strftime('%Y-%m-%d'),
                'source': 'fallback'
            },
            {
                'event': 'Non-Farm Payrolls',
                'impact': 'HIGH',
                'currency': 'USD',
                'date': (now + timedelta(days=5)).strftime('%Y-%m-%d'),
                'source': 'fallback'
            }
        ]


# ══════════════════════════════════════════════════════════════════════════════
# SENTIMENT SCORING ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class SentimentAnalyzer:
    """
    Combine Perplexity news + Firecrawl calendar into a single
    market sentiment score (0-100).

    Weights:
      News sentiment:  40%
      Calendar events: 30%
      Trend alignment: 30%
    """

    NEWS_WEIGHT = 0.40
    CALENDAR_WEIGHT = 0.30
    TREND_WEIGHT = 0.30

    HIGH_IMPACT_PENALTY = -15  # High-impact event upcoming = uncertainty
    USD_WEAK_GOLD_BULL = 10   # Weak USD = bullish gold

    def __init__(self):
        self.perplexity = PerplexityClient()
        self.firecrawl = FirecrawlClient()
        self.history: List[SentimentResult] = []

    def analyze(
        self,
        symbol: str = "XAUUSD",
        current_price: float = 0.0,
        technical_bias: str = "NEUTRAL"
    ) -> SentimentResult:
        """
        Full sentiment analysis combining news + calendar + technicals.

        Args:
            symbol: Trading pair
            current_price: Current market price
            technical_bias: Technical analysis direction (BULLISH/NEUTRAL/BEARISH)
        """
        news_data = self.perplexity.query_macro_news(symbol)
        calendar_events = self.firecrawl.scrape_calendar()

        news_score = news_data.get('score', 50)
        calendar_score = self._score_calendar(calendar_events)
        trend_score = self._score_trend_alignment(technical_bias, news_score)

        raw_score = (
            news_score * self.NEWS_WEIGHT +
            calendar_score * self.CALENDAR_WEIGHT +
            trend_score * self.TREND_WEIGHT
        )

        final_score = max(0, min(100, int(raw_score)))

        if final_score >= 60:
            direction = SentimentDirection.BULLISH
        elif final_score <= 40:
            direction = SentimentDirection.BEARISH
        else:
            direction = SentimentDirection.NEUTRAL

        result = SentimentResult(
            symbol=symbol,
            score=final_score,
            direction=direction,
            news_score=news_score,
            calendar_score=calendar_score,
            trend_score=trend_score,
            news_summary=news_data.get('summary', ''),
            calendar_events=calendar_events[:5]
        )

        self.history.append(result)
        self._save_result(result)

        log.info(
            f"[SENTIMENT] {symbol} Score:{final_score} ({direction.value}) "
            f"News:{news_score} Cal:{calendar_score} Trend:{trend_score}"
        )

        return result

    def _score_calendar(self, events: List[Dict]) -> int:
        if not events:
            return 50

        high_impact = sum(1 for e in events if e.get('impact') == 'HIGH')
        medium_impact = sum(1 for e in events if e.get('impact') == 'MEDIUM')

        score = 50

        if high_impact > 0:
            score += self.HIGH_IMPACT_PENALTY * min(high_impact, 3)

        if medium_impact > 2:
            score -= 5

        usd_events = sum(1 for e in events if e.get('currency') == 'USD')
        if usd_events > 3:
            score -= 10

        return max(0, min(100, score))

    def _score_trend_alignment(self, technical_bias: str, news_score: int) -> int:
        if technical_bias == 'BULLISH' and news_score >= 60:
            return 80
        elif technical_bias == 'BEARISH' and news_score <= 40:
            return 80
        elif technical_bias == 'NEUTRAL':
            return 50
        else:
            return 30

    def _save_result(self, result: SentimentResult) -> None:
        try:
            filepath = LOG_DIR / 'sentiment_log.jsonl'
            entry = {
                'symbol': result.symbol,
                'score': result.score,
                'direction': result.direction.value,
                'news_score': result.news_score,
                'calendar_score': result.calendar_score,
                'trend_score': result.trend_score,
                'timestamp': result.timestamp
            }
            with open(filepath, 'a') as f:
                f.write(json.dumps(entry) + '\n')
        except Exception as e:
            log.debug(f"Failed to save sentiment: {e}")

    def get_history(self, symbol: str = None, limit: int = 50) -> List[SentimentResult]:
        if symbol:
            return [r for r in self.history if r.symbol == symbol][-limit:]
        return self.history[-limit:]

    def should_allow_trade(
        self,
        symbol: str,
        technical_score: int,
        sentiment: SentimentResult
    ) -> Tuple[bool, str]:
        """
        Final gate: should we allow the trade?

        Rules:
          - Technical score >= 75 AND sentiment >= 50 → EXECUTE
          - Technical score >= 75 AND sentiment < 40 → BLOCK (conflict)
          - Sentiment >= 70 → Boost technical by +5
          - Sentiment <= 30 → Reduce technical by -10
        """
        adj_score = technical_score

        if sentiment.score >= 70:
            adj_score += 5
            log.info(f"[SENTIMENT] {symbol} Boost: +5 (strong bullish sentiment)")
        elif sentiment.score <= 30:
            adj_score -= 10
            log.info(f"[SENTIMENT] {symbol} Penalty: -10 (strong bearish sentiment)")

        if adj_score >= 75 and sentiment.score >= 50:
            return True, f"EXECUTE (tech:{technical_score} adj:{adj_score} sent:{sentiment.score})"
        elif adj_score >= 75 and sentiment.score < 40:
            return False, f"BLOCKED (conflict: tech bullish but sentiment bearish {sentiment.score})"
        elif adj_score < 50:
            return False, f"BLOCKED (low score: {adj_score})"
        else:
            return True, f"WAIT (adj:{adj_score} sent:{sentiment.score})"


# ══════════════════════════════════════════════════════════════════════════════
# GLOBAL INSTANCE
# ══════════════════════════════════════════════════════════════════════════════

_analyzer: Optional[SentimentAnalyzer] = None


def get_sentiment_analyzer() -> SentimentAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = SentimentAnalyzer()
    return _analyzer


def analyze_sentiment(
    symbol: str = "XAUUSD",
    current_price: float = 0.0,
    technical_bias: str = "NEUTRAL"
) -> SentimentResult:
    return get_sentiment_analyzer().analyze(symbol, current_price, technical_bias)


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import sys

    logging.basicConfig(level=logging.INFO, format='%(message)s')

    if '--test' in sys.argv:
        print("=" * 60)
        print("  SENTIMENT ANALYZER - TEST")
        print("=" * 60)

        analyzer = SentimentAnalyzer()

        print(f"\n  Perplexity configured: {analyzer.perplexity.is_configured}")
        print(f"  Firecrawl configured: {analyzer.firecrawl.is_configured}")

        print("\n--- Analyzing XAUUSD sentiment ---")
        result = analyzer.analyze("XAUUSD", 2350.0, "BULLISH")

        print(f"\n  Symbol:    {result.symbol}")
        print(f"  Score:     {result.score}/100")
        print(f"  Direction: {result.direction.value}")
        print(f"  News:      {result.news_score}")
        print(f"  Calendar:  {result.calendar_score}")
        print(f"  Trend:     {result.trend_score}")
        print(f"  Summary:   {result.news_summary[:100]}...")
        print(f"  Events:    {len(result.calendar_events)} upcoming")

        print("\n--- Trade Gate Check ---")
        allowed, reason = analyzer.should_allow_trade("XAUUSD", 80, result)
        print(f"  Allowed: {allowed}")
        print(f"  Reason:  {reason}")

        print("\n--- Fallback Calendar ---")
        fallback = analyzer.firecrawl._fallback_calendar()
        for event in fallback:
            print(f"  [{event['impact']}] {event['event']} ({event['currency']})")

        print("\n" + "=" * 60)
    else:
        print("Usage: python sentiment_analyzer.py --test")
