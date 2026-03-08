# Built by Hamzy - ETS Montreal
# Market data service using yfinance + Alpha Vantage with Redis caching

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import redis
import yfinance as yf
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from app.models.schemas import (
    HistoryResponse,
    OHLCBar,
    OptionContract,
    OptionsChainResponse,
    QuoteResponse,
    ScreenerResponse,
    ScreenerStock,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
ALPHA_VANTAGE_KEY: str = os.getenv("ALPHA_VANTAGE_KEY", "")

QUOTE_CACHE_TTL: int = 30        # seconds
HISTORY_CACHE_TTL: int = 300     # 5 minutes
OPTIONS_CACHE_TTL: int = 60      # 1 minute
SCREENER_CACHE_TTL: int = 120    # 2 minutes

# Universe of 50 popular tickers used by the screener
SCREENER_UNIVERSE: List[str] = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK-B", "UNH", "JPM",
    "JNJ", "V", "XOM", "PG", "MA", "HD", "CVX", "MRK", "ABBV", "LLY",
    "PEP", "KO", "AVGO", "COST", "MCD", "TMO", "CSCO", "ACN", "ABT", "DHR",
    "NEE", "NKE", "ADBE", "TXN", "ORCL", "AMD", "QCOM", "HON", "PM", "IBM",
    "AMGN", "UNP", "LIN", "LOW", "SBUX", "INTU", "GS", "SPGI", "CAT", "BA",
]

PERIOD_MAP: Dict[str, Dict[str, str]] = {
    "1d":  {"period": "1d",  "interval": "5m"},
    "1w":  {"period": "5d",  "interval": "30m"},
    "1m":  {"period": "1mo", "interval": "1d"},
    "3m":  {"period": "3mo", "interval": "1d"},
    "1y":  {"period": "1y",  "interval": "1wk"},
}


# ---------------------------------------------------------------------------
# Redis helper
# ---------------------------------------------------------------------------

def _make_redis_client() -> Optional[redis.Redis]:
    """Attempt to connect to Redis; return None if unavailable."""
    try:
        client = redis.from_url(REDIS_URL, decode_responses=True, socket_connect_timeout=2)
        client.ping()
        logger.info("Redis connection established at {}", REDIS_URL)
        return client
    except Exception as exc:  # pragma: no cover
        logger.warning("Redis unavailable ({}). Running without cache.", exc)
        return None


# ---------------------------------------------------------------------------
# MarketDataService
# ---------------------------------------------------------------------------

class MarketDataService:
    """Provides market data via yfinance with optional Redis caching."""

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
                logger.debug("Cache HIT for key={}", key)
                return json.loads(raw)
        except Exception as exc:
            logger.warning("Cache GET error: {}", exc)
        return None

    def _cache_set(self, key: str, value: Any, ttl: int) -> None:
        if self._redis is None:
            return
        try:
            self._redis.setex(key, ttl, json.dumps(value, default=str))
            logger.debug("Cache SET key={} ttl={}s", key, ttl)
        except Exception as exc:
            logger.warning("Cache SET error: {}", exc)

    # ------------------------------------------------------------------
    # Quote
    # ------------------------------------------------------------------

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def get_quote(self, ticker: str) -> QuoteResponse:
        """Fetch a real-time quote for *ticker*, caching results for 30 s."""
        ticker_upper = ticker.upper().strip()
        cache_key = f"quote:{ticker_upper}"

        cached = self._cache_get(cache_key)
        if cached:
            logger.info("Returning cached quote for {}", ticker_upper)
            return QuoteResponse(**cached)

        logger.info("Fetching live quote for {}", ticker_upper)
        yf_ticker = yf.Ticker(ticker_upper)
        info: Dict[str, Any] = yf_ticker.fast_info

        # fast_info attrs differ slightly from info; use both
        full_info: Dict[str, Any] = {}
        try:
            full_info = yf_ticker.info
        except Exception:
            pass

        price: float = float(info.get("last_price") or info.get("regularMarketPrice") or 0.0)
        prev_close: float = float(info.get("previous_close") or info.get("regularMarketPreviousClose") or price)
        open_price: float = float(info.get("open") or info.get("regularMarketOpen") or price)
        high: float = float(info.get("day_high") or info.get("regularMarketDayHigh") or price)
        low: float = float(info.get("day_low") or info.get("regularMarketDayLow") or price)
        volume: int = int(info.get("last_volume") or info.get("regularMarketVolume") or 0)
        avg_volume: int = int(full_info.get("averageVolume10days") or full_info.get("averageVolume") or 0)
        market_cap: Optional[float] = full_info.get("marketCap") or info.get("market_cap")
        pe_ratio: Optional[float] = full_info.get("trailingPE")
        week_52_high: Optional[float] = info.get("year_high") or full_info.get("fiftyTwoWeekHigh")
        week_52_low: Optional[float] = info.get("year_low") or full_info.get("fiftyTwoWeekLow")
        name: str = full_info.get("longName") or full_info.get("shortName") or ticker_upper

        change = round(price - prev_close, 4)
        change_pct = round((change / prev_close * 100) if prev_close else 0.0, 4)

        payload = {
            "ticker": ticker_upper,
            "name": name,
            "price": price,
            "open": open_price,
            "high": high,
            "low": low,
            "prev_close": prev_close,
            "change": change,
            "change_pct": change_pct,
            "volume": volume,
            "avg_volume": avg_volume,
            "market_cap": float(market_cap) if market_cap else None,
            "pe_ratio": float(pe_ratio) if pe_ratio else None,
            "week_52_high": float(week_52_high) if week_52_high else None,
            "week_52_low": float(week_52_low) if week_52_low else None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        self._cache_set(cache_key, payload, QUOTE_CACHE_TTL)
        logger.success("Quote fetched for {}: price={}", ticker_upper, price)
        return QuoteResponse(**payload)

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def get_history(self, ticker: str, period: str = "1m") -> HistoryResponse:
        """Fetch OHLCV history for *ticker* over *period*."""
        ticker_upper = ticker.upper().strip()
        period_lower = period.lower()
        cache_key = f"history:{ticker_upper}:{period_lower}"

        cached = self._cache_get(cache_key)
        if cached:
            logger.info("Returning cached history for {} period={}", ticker_upper, period_lower)
            return HistoryResponse(**cached)

        if period_lower not in PERIOD_MAP:
            raise ValueError(f"Invalid period '{period_lower}'. Valid: {list(PERIOD_MAP)}")

        params = PERIOD_MAP[period_lower]
        logger.info("Fetching history for {} period={} interval={}", ticker_upper, params["period"], params["interval"])

        df = yf.download(
            ticker_upper,
            period=params["period"],
            interval=params["interval"],
            auto_adjust=True,
            progress=False,
        )

        if df.empty:
            raise ValueError(f"No historical data returned for {ticker_upper}")

        # Flatten MultiIndex columns if present (yfinance >= 0.2.x)
        if isinstance(df.columns, type(df.columns)) and hasattr(df.columns, "levels"):
            df.columns = [col[0] if isinstance(col, tuple) else col for col in df.columns]

        bars: List[Dict[str, Any]] = []
        for ts, row in df.iterrows():
            bars.append({
                "timestamp": ts.isoformat(),
                "open": round(float(row["Open"]), 4),
                "high": round(float(row["High"]), 4),
                "low": round(float(row["Low"]), 4),
                "close": round(float(row["Close"]), 4),
                "volume": int(row["Volume"]),
            })

        payload = {"ticker": ticker_upper, "period": period_lower, "bars": bars}
        self._cache_set(cache_key, payload, HISTORY_CACHE_TTL)
        logger.success("History fetched for {}: {} bars", ticker_upper, len(bars))
        return HistoryResponse(**payload)

    # ------------------------------------------------------------------
    # Options Chain
    # ------------------------------------------------------------------

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def get_options_chain(self, ticker: str) -> OptionsChainResponse:
        """Fetch the full options chain for *ticker*."""
        ticker_upper = ticker.upper().strip()
        cache_key = f"options:{ticker_upper}"

        cached = self._cache_get(cache_key)
        if cached:
            logger.info("Returning cached options for {}", ticker_upper)
            return OptionsChainResponse(**cached)

        logger.info("Fetching options chain for {}", ticker_upper)
        yf_ticker = yf.Ticker(ticker_upper)
        expiry_dates: List[str] = list(yf_ticker.options or [])

        if not expiry_dates:
            raise ValueError(f"No options data available for {ticker_upper}")

        # Use the nearest expiry for call/put detail
        nearest_expiry = expiry_dates[0]
        chain = yf_ticker.option_chain(nearest_expiry)

        current_price: float = float(
            yf_ticker.fast_info.get("last_price")
            or yf_ticker.fast_info.get("regularMarketPrice")
            or 0.0
        )

        def _parse_contracts(df: Any, is_call: bool) -> List[Dict[str, Any]]:
            contracts: List[Dict[str, Any]] = []
            for _, row in df.iterrows():
                strike = float(row.get("strike", 0))
                itm = (current_price > strike) if is_call else (current_price < strike)
                contracts.append({
                    "strike": strike,
                    "expiry": nearest_expiry,
                    "bid": float(row.get("bid", 0)),
                    "ask": float(row.get("ask", 0)),
                    "last": float(row.get("lastPrice", 0)),
                    "volume": int(row.get("volume", 0) or 0),
                    "open_interest": int(row.get("openInterest", 0) or 0),
                    "implied_volatility": round(float(row.get("impliedVolatility", 0)), 4),
                    "delta": None,   # yfinance does not provide greeks natively
                    "gamma": None,
                    "theta": None,
                    "in_the_money": bool(row.get("inTheMoney", itm)),
                })
            return contracts

        calls = _parse_contracts(chain.calls, is_call=True)
        puts = _parse_contracts(chain.puts, is_call=False)

        payload = {
            "ticker": ticker_upper,
            "current_price": current_price,
            "expiry_dates": expiry_dates,
            "calls": calls,
            "puts": puts,
        }

        self._cache_set(cache_key, payload, OPTIONS_CACHE_TTL)
        logger.success(
            "Options chain fetched for {}: {} calls, {} puts, {} expiries",
            ticker_upper, len(calls), len(puts), len(expiry_dates),
        )
        return OptionsChainResponse(**payload)

    # ------------------------------------------------------------------
    # Screener
    # ------------------------------------------------------------------

    def get_screener(
        self,
        min_price: float = 0.0,
        max_price: float = 9_999.0,
        min_market_cap: float = 0.0,
        sector: Optional[str] = None,
    ) -> ScreenerResponse:
        """Screen stocks from the predefined universe using price / market-cap / sector filters."""
        cache_key = f"screener:{min_price}:{max_price}:{min_market_cap}:{sector or 'all'}"

        cached = self._cache_get(cache_key)
        if cached:
            logger.info("Returning cached screener results")
            return ScreenerResponse(**cached)

        logger.info(
            "Running screener min_price={} max_price={} min_market_cap={} sector={}",
            min_price, max_price, min_market_cap, sector,
        )

        results: List[Dict[str, Any]] = []

        # Batch download for efficiency
        tickers_str = " ".join(SCREENER_UNIVERSE)
        data = yf.download(tickers_str, period="2d", interval="1d", auto_adjust=True, progress=False, group_by="ticker")

        for sym in SCREENER_UNIVERSE:
            try:
                yf_ticker = yf.Ticker(sym)
                info: Dict[str, Any] = {}
                try:
                    info = yf_ticker.info
                except Exception:
                    pass

                # Extract price from downloaded data or info
                try:
                    closes = data[sym]["Close"].dropna()
                    price = float(closes.iloc[-1]) if not closes.empty else 0.0
                    prev_close = float(closes.iloc[-2]) if len(closes) >= 2 else price
                except Exception:
                    price = float(info.get("regularMarketPrice") or info.get("currentPrice") or 0.0)
                    prev_close = float(info.get("previousClose") or price)

                if price == 0.0:
                    continue

                change_pct = round(((price - prev_close) / prev_close * 100) if prev_close else 0.0, 2)
                market_cap = info.get("marketCap") or 0
                stock_sector = info.get("sector") or "Unknown"
                volume = int(info.get("regularMarketVolume") or info.get("volume") or 0)
                pe = info.get("trailingPE")
                name = info.get("longName") or info.get("shortName") or sym

                # Apply filters
                if price < min_price or price > max_price:
                    continue
                if market_cap and market_cap < min_market_cap:
                    continue
                if sector and sector.lower() not in ("all", "") and sector.lower() != stock_sector.lower():
                    continue

                results.append({
                    "ticker": sym,
                    "name": name,
                    "price": round(price, 2),
                    "change_pct": change_pct,
                    "market_cap": float(market_cap) if market_cap else None,
                    "pe_ratio": float(pe) if pe else None,
                    "volume": volume,
                    "sector": stock_sector,
                })
            except Exception as exc:
                logger.warning("Screener skipping {}: {}", sym, exc)
                continue

        payload = {"count": len(results), "stocks": results}
        self._cache_set(cache_key, payload, SCREENER_CACHE_TTL)
        logger.success("Screener complete: {} stocks matched", len(results))
        return ScreenerResponse(**payload)
