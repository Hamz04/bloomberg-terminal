# Built by Hamzy - ETS Montreal
# Sentiment analysis service using FinBERT + Yahoo Finance RSS feed

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional, Tuple

import feedparser
import redis
from loguru import logger

from app.models.schemas import NewsArticle, SentimentResponse

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
SENTIMENT_CACHE_TTL: int = 300   # 5 minutes
MAX_ARTICLES: int = 20
FINBERT_MODEL: str = "ProsusAI/finbert"

# Yahoo Finance RSS template
YF_RSS_TEMPLATE = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"

# Simple financial lexicon used as fallback when model is not available
BULLISH_WORDS = {
    "surge", "surged", "rally", "rallied", "gain", "gains", "gained", "beat", "beats",
    "record", "high", "rise", "rises", "rose", "up", "bullish", "outperform", "upgrade",
    "profit", "profits", "revenue", "growth", "positive", "strong", "boost", "boosted",
    "exceed", "exceeded", "soar", "soared", "jump", "jumped", "buy", "breakout",
}
BEARISH_WORDS = {
    "fall", "falls", "fell", "drop", "drops", "dropped", "decline", "declines", "declined",
    "miss", "misses", "missed", "loss", "losses", "down", "bearish", "downgrade", "sell",
    "weak", "warning", "cut", "cuts", "slump", "slumped", "plunge", "plunged", "crash",
    "concern", "risk", "risks", "layoff", "layoffs", "lawsuit", "fraud", "debt", "recall",
}


# ---------------------------------------------------------------------------
# Redis helper (shared pattern — lightweight copy avoids circular imports)
# ---------------------------------------------------------------------------

def _make_redis_client() -> Optional[redis.Redis]:
    try:
        client = redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=2)
        client.ping()
        logger.info("SentimentService: Redis connected at {}", REDIS_URL)
        return client
    except Exception as exc:
        logger.warning("SentimentService: Redis unavailable ({}). No caching.", exc)
        return None


# ---------------------------------------------------------------------------
# FinBERT loader (lazy, singleton)
# ---------------------------------------------------------------------------

_finbert_pipeline: Optional[Any] = None
_finbert_loaded: bool = False


def _get_finbert() -> Optional[Any]:
    """Lazily load the FinBERT pipeline; return None if unavailable."""
    global _finbert_pipeline, _finbert_loaded
    if _finbert_loaded:
        return _finbert_pipeline

    _finbert_loaded = True
    try:
        from transformers import pipeline as hf_pipeline  # type: ignore
        logger.info("Loading FinBERT model {} …", FINBERT_MODEL)
        _finbert_pipeline = hf_pipeline(
            "text-classification",
            model=FINBERT_MODEL,
            tokenizer=FINBERT_MODEL,
            top_k=None,           # return all labels with scores
            truncation=True,
            max_length=512,
        )
        logger.success("FinBERT model loaded successfully.")
    except Exception as exc:
        logger.warning("FinBERT unavailable ({}). Falling back to lexicon.", exc)
        _finbert_pipeline = None

    return _finbert_pipeline


# ---------------------------------------------------------------------------
# Lexicon fallback
# ---------------------------------------------------------------------------

def _lexicon_sentiment(text: str) -> Tuple[str, float]:
    """Return (label, score) using a simple keyword lexicon."""
    words = set(re.findall(r"\b[a-z]+\b", text.lower()))
    bull_hits = len(words & BULLISH_WORDS)
    bear_hits = len(words & BEARISH_WORDS)

    if bull_hits == bear_hits == 0:
        return "neutral", 0.0

    total = bull_hits + bear_hits
    net = (bull_hits - bear_hits) / total   # in [-1, 1]

    if net > 0.1:
        return "bullish", round(net, 4)
    if net < -0.1:
        return "bearish", round(net, 4)
    return "neutral", round(net, 4)


# ---------------------------------------------------------------------------
# FinBERT scorer
# ---------------------------------------------------------------------------

def _finbert_sentiment(text: str, pipeline: Any) -> Tuple[str, float]:
    """Score *text* with FinBERT. Returns (label, score) where score ∈ [-1, 1]."""
    try:
        results: List[List[Dict[str, Any]]] = pipeline(text)
        # pipeline with top_k=None returns [[{label, score}, ...]]
        label_scores: Dict[str, float] = {}
        for item in results[0]:
            label_scores[item["label"].lower()] = item["score"]

        # FinBERT labels: positive / negative / neutral
        pos = label_scores.get("positive", 0.0)
        neg = label_scores.get("negative", 0.0)
        neu = label_scores.get("neutral", 0.0)

        # Map to our labels
        dominant = max(label_scores, key=lambda k: label_scores[k])
        if dominant == "positive":
            sentiment_label = "bullish"
            score = round(pos - neg, 4)
        elif dominant == "negative":
            sentiment_label = "bearish"
            score = round(neg - pos, 4) * -1  # keep sign: bearish = negative
        else:
            sentiment_label = "neutral"
            score = round(pos - neg, 4)

        return sentiment_label, score
    except Exception as exc:
        logger.warning("FinBERT inference error: {}. Falling back to lexicon.", exc)
        return _lexicon_sentiment(text)


# ---------------------------------------------------------------------------
# RSS fetcher
# ---------------------------------------------------------------------------

def _fetch_rss_articles(ticker: str) -> List[Dict[str, str]]:
    """Fetch up to MAX_ARTICLES news items from Yahoo Finance RSS for *ticker*."""
    url = YF_RSS_TEMPLATE.format(ticker=ticker.upper())
    logger.info("Fetching RSS feed for {}: {}", ticker, url)

    try:
        feed = feedparser.parse(url)
        articles: List[Dict[str, str]] = []

        for entry in feed.entries[:MAX_ARTICLES]:
            title: str = entry.get("title", "").strip()
            link: str = entry.get("link", "").strip()
            source: str = entry.get("source", {}).get("title", "Yahoo Finance")
            pub_raw: str = entry.get("published", "")

            # Parse published date
            try:
                published_dt = parsedate_to_datetime(pub_raw).astimezone(timezone.utc)
                published_iso = published_dt.isoformat()
            except Exception:
                published_iso = datetime.now(timezone.utc).isoformat()

            if title and link:
                articles.append({
                    "title": title,
                    "source": source,
                    "url": link,
                    "published": published_iso,
                })

        logger.info("Fetched {} articles for {}", len(articles), ticker)
        return articles

    except Exception as exc:
        logger.error("RSS fetch error for {}: {}", ticker, exc)
        return []


# ---------------------------------------------------------------------------
# SentimentService
# ---------------------------------------------------------------------------

class SentimentService:
    """Analyzes news sentiment for a stock ticker using FinBERT or lexicon fallback."""

    def __init__(self) -> None:
        self._redis: Optional[redis.Redis] = _make_redis_client()

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _cache_get(self, key: str) -> Optional[Any]:
        if self._redis is None:
            return None
        try:
            raw = self._redis.get(key)
            if raw:
                logger.debug("Sentiment cache HIT: {}", key)
                return json.loads(raw)
        except Exception as exc:
            logger.warning("Sentiment cache GET error: {}", exc)
        return None

    def _cache_set(self, key: str, value: Any, ttl: int) -> None:
        if self._redis is None:
            return
        try:
            self._redis.setex(key, ttl, json.dumps(value, default=str))
            logger.debug("Sentiment cache SET: {} ttl={}s", key, ttl)
        except Exception as exc:
            logger.warning("Sentiment cache SET error: {}", exc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, ticker: str) -> SentimentResponse:
        """
        Fetch news for *ticker* from Yahoo Finance RSS, score each article
        with FinBERT (or lexicon fallback), and return aggregated sentiment.
        Results are cached for SENTIMENT_CACHE_TTL seconds.
        """
        ticker_upper = ticker.upper().strip()
        cache_key = f"sentiment:{ticker_upper}"

        cached = self._cache_get(cache_key)
        if cached:
            logger.info("Returning cached sentiment for {}", ticker_upper)
            return SentimentResponse(**cached)

        logger.info("Analyzing sentiment for {}", ticker_upper)
        start = time.perf_counter()

        # Load model (lazy)
        pipeline = _get_finbert()

        # Fetch articles
        raw_articles = _fetch_rss_articles(ticker_upper)

        if not raw_articles:
            logger.warning("No articles found for {}. Returning neutral default.", ticker_upper)
            return self._neutral_response(ticker_upper)

        # Score each article
        scored_articles: List[Dict[str, Any]] = []
        for art in raw_articles:
            text = art["title"]
            if pipeline is not None:
                label, score = _finbert_sentiment(text, pipeline)
            else:
                label, score = _lexicon_sentiment(text)

            scored_articles.append({
                "title": art["title"],
                "source": art["source"],
                "url": art["url"],
                "published": art["published"],
                "sentiment": label,
                "sentiment_score": score,
            })

        # Aggregate
        n = len(scored_articles)
        bull_count = sum(1 for a in scored_articles if a["sentiment"] == "bullish")
        bear_count = sum(1 for a in scored_articles if a["sentiment"] == "bearish")
        neut_count = n - bull_count - bear_count

        bullish_pct = round(bull_count / n * 100, 2)
        bearish_pct = round(bear_count / n * 100, 2)
        neutral_pct = round(100.0 - bullish_pct - bearish_pct, 2)  # ensure sums to 100

        overall_score = round(
            sum(a["sentiment_score"] for a in scored_articles) / n, 4
        )

        if overall_score > 0.1:
            overall_sentiment = "bullish"
        elif overall_score < -0.1:
            overall_sentiment = "bearish"
        else:
            overall_sentiment = "neutral"

        elapsed = round(time.perf_counter() - start, 2)
        logger.success(
            "Sentiment for {}: {} (score={}) from {} articles in {}s",
            ticker_upper, overall_sentiment, overall_score, n, elapsed,
        )

        payload = {
            "ticker": ticker_upper,
            "overall_sentiment": overall_sentiment,
            "overall_score": overall_score,
            "articles_analyzed": n,
            "bullish_pct": bullish_pct,
            "bearish_pct": bearish_pct,
            "neutral_pct": neutral_pct,
            "articles": scored_articles,
        }

        self._cache_set(cache_key, payload, SENTIMENT_CACHE_TTL)
        return SentimentResponse(**payload)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _neutral_response(ticker: str) -> SentimentResponse:
        """Return a safe neutral SentimentResponse when no articles are available."""
        return SentimentResponse(
            ticker=ticker,
            overall_sentiment="neutral",
            overall_score=0.0,
            articles_analyzed=0,
            bullish_pct=0.0,
            bearish_pct=0.0,
            neutral_pct=100.0,
            articles=[],
        )
