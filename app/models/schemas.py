# Built by Hamza Ahmad - ETS Montreal
# Pydantic v2 schemas for Bloomberg Terminal API

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Market Data Schemas
# ---------------------------------------------------------------------------

class QuoteResponse(BaseModel):
    """Real-time quote snapshot for a single ticker."""

    ticker: str = Field(..., description="Stock ticker symbol (e.g. AAPL)")
    name: str = Field(..., description="Full company name")
    price: float = Field(..., description="Last trade price")
    open: float = Field(..., description="Session open price")
    high: float = Field(..., description="Session high price")
    low: float = Field(..., description="Session low price")
    prev_close: float = Field(..., description="Previous session close price")
    change: float = Field(..., description="Absolute price change from prev_close")
    change_pct: float = Field(..., description="Percentage price change from prev_close")
    volume: int = Field(..., description="Current session volume")
    avg_volume: int = Field(..., description="10-day average volume")
    market_cap: Optional[float] = Field(None, description="Market capitalisation in USD")
    pe_ratio: Optional[float] = Field(None, description="Trailing price-to-earnings ratio")
    week_52_high: Optional[float] = Field(None, description="52-week high price")
    week_52_low: Optional[float] = Field(None, description="52-week low price")
    timestamp: datetime = Field(..., description="UTC timestamp of the quote")

    model_config = {"json_schema_extra": {"example": {
        "ticker": "AAPL",
        "name": "Apple Inc.",
        "price": 189.30,
        "open": 188.00,
        "high": 190.50,
        "low": 187.20,
        "prev_close": 187.15,
        "change": 2.15,
        "change_pct": 1.15,
        "volume": 55_000_000,
        "avg_volume": 60_000_000,
        "market_cap": 2_950_000_000_000.0,
        "pe_ratio": 30.5,
        "week_52_high": 199.62,
        "week_52_low": 124.17,
        "timestamp": "2024-01-15T20:00:00Z",
    }}}


class OHLCBar(BaseModel):
    """A single OHLCV candlestick bar."""

    timestamp: datetime = Field(..., description="Bar open timestamp (UTC)")
    open: float = Field(..., description="Open price")
    high: float = Field(..., description="High price")
    low: float = Field(..., description="Low price")
    close: float = Field(..., description="Close price")
    volume: int = Field(..., description="Volume traded during the bar")


class HistoryResponse(BaseModel):
    """Historical OHLCV data for a ticker."""

    ticker: str = Field(..., description="Stock ticker symbol")
    period: str = Field(..., description="Requested period (1d, 1w, 1m, 3m, 1y)")
    bars: List[OHLCBar] = Field(..., description="List of OHLCV bars, oldest first")

    @field_validator("period")
    @classmethod
    def validate_period(cls, v: str) -> str:
        allowed = {"1d", "1w", "1m", "3m", "1y"}
        if v not in allowed:
            raise ValueError(f"period must be one of {allowed}")
        return v


# ---------------------------------------------------------------------------
# Options Schemas
# ---------------------------------------------------------------------------

class OptionContract(BaseModel):
    """A single option contract (call or put)."""

    strike: float = Field(..., description="Strike price")
    expiry: str = Field(..., description="Expiry date (YYYY-MM-DD)")
    bid: float = Field(..., description="Bid price")
    ask: float = Field(..., description="Ask price")
    last: float = Field(..., description="Last trade price")
    volume: int = Field(..., description="Contracts traded today")
    open_interest: int = Field(..., description="Open interest")
    implied_volatility: float = Field(..., description="Implied volatility (decimal, e.g. 0.35 = 35%)")
    delta: Optional[float] = Field(None, description="Option delta (-1 to 1)")
    gamma: Optional[float] = Field(None, description="Option gamma")
    theta: Optional[float] = Field(None, description="Option theta (daily decay)")
    in_the_money: bool = Field(..., description="True if the contract is in-the-money")


class OptionsChainResponse(BaseModel):
    """Full options chain for a ticker."""

    ticker: str = Field(..., description="Underlying ticker symbol")
    current_price: float = Field(..., description="Current underlying price")
    expiry_dates: List[str] = Field(..., description="Available expiry dates (YYYY-MM-DD)")
    calls: List[OptionContract] = Field(..., description="Call contracts for selected expiry")
    puts: List[OptionContract] = Field(..., description="Put contracts for selected expiry")


# ---------------------------------------------------------------------------
# Sentiment Schemas
# ---------------------------------------------------------------------------

class NewsArticle(BaseModel):
    """A single news article with sentiment annotation."""

    title: str = Field(..., description="Article headline")
    source: str = Field(..., description="News source name")
    url: str = Field(..., description="Full article URL")
    published: datetime = Field(..., description="Publication timestamp (UTC)")
    sentiment: str = Field(..., description="Sentiment label: bullish | bearish | neutral")
    sentiment_score: float = Field(
        ...,
        ge=-1.0,
        le=1.0,
        description="Sentiment score: -1 (very bearish) to +1 (very bullish)",
    )

    @field_validator("sentiment")
    @classmethod
    def validate_sentiment(cls, v: str) -> str:
        allowed = {"bullish", "bearish", "neutral"}
        if v not in allowed:
            raise ValueError(f"sentiment must be one of {allowed}")
        return v


class SentimentResponse(BaseModel):
    """Aggregated sentiment analysis for a ticker."""

    ticker: str = Field(..., description="Stock ticker symbol")
    overall_sentiment: str = Field(..., description="Dominant sentiment: bullish | bearish | neutral")
    overall_score: float = Field(
        ...,
        ge=-1.0,
        le=1.0,
        description="Weighted average sentiment score across all articles",
    )
    articles_analyzed: int = Field(..., description="Number of articles analyzed")
    bullish_pct: float = Field(..., ge=0.0, le=100.0, description="Percentage of bullish articles")
    bearish_pct: float = Field(..., ge=0.0, le=100.0, description="Percentage of bearish articles")
    neutral_pct: float = Field(..., ge=0.0, le=100.0, description="Percentage of neutral articles")
    articles: List[NewsArticle] = Field(..., description="Individual article sentiment scores")

    @model_validator(mode="after")
    def percentages_sum_to_100(self) -> "SentimentResponse":
        total = self.bullish_pct + self.bearish_pct + self.neutral_pct
        if abs(total - 100.0) > 0.5:  # allow minor float rounding
            raise ValueError(f"bullish_pct + bearish_pct + neutral_pct must equal 100, got {total}")
        return self


# ---------------------------------------------------------------------------
# Screener Schemas
# ---------------------------------------------------------------------------

class ScreenerStock(BaseModel):
    """A stock result returned by the screener."""

    ticker: str = Field(..., description="Ticker symbol")
    name: str = Field(..., description="Company name")
    price: float = Field(..., description="Current price")
    change_pct: float = Field(..., description="Daily percentage change")
    market_cap: Optional[float] = Field(None, description="Market cap in USD")
    pe_ratio: Optional[float] = Field(None, description="Trailing P/E ratio")
    volume: int = Field(..., description="Today's volume")
    sector: Optional[str] = Field(None, description="GICS sector")


class ScreenerResponse(BaseModel):
    """Screener results."""

    count: int = Field(..., description="Number of stocks returned")
    stocks: List[ScreenerStock] = Field(..., description="Matched stocks")

    @model_validator(mode="after")
    def count_matches_stocks(self) -> "ScreenerResponse":
        if self.count != len(self.stocks):
            self.count = len(self.stocks)
        return self


# ---------------------------------------------------------------------------
# Portfolio / Analytics Schemas
# ---------------------------------------------------------------------------

class PortfolioMetrics(BaseModel):
    """Risk/return metrics for a multi-asset portfolio."""

    tickers: List[str] = Field(..., description="Portfolio tickers")
    weights: List[float] = Field(..., description="Portfolio weights (must sum to 1.0)")
    total_return_pct: float = Field(..., description="Total return over the analysis period (%)")
    annualized_return_pct: float = Field(..., description="Annualized return (%)")
    sharpe_ratio: float = Field(..., description="Sharpe ratio (risk-free = 5.25%)")
    beta: float = Field(..., description="Portfolio beta vs SPY")
    max_drawdown_pct: float = Field(..., description="Maximum drawdown (%)")
    var_95_pct: float = Field(..., description="95% historical Value-at-Risk (%)")
    volatility_annualized: float = Field(..., description="Annualized portfolio volatility (%)")
    correlation_matrix: Dict[str, Dict[str, float]] = Field(
        ..., description="Pairwise correlation matrix between all tickers"
    )
    benchmark: str = Field(default="SPY", description="Benchmark ticker used for beta calculation")

    @field_validator("weights")
    @classmethod
    def weights_sum_to_one(cls, v: List[float]) -> List[float]:
        if abs(sum(v) - 1.0) > 0.01:
            raise ValueError(f"Weights must sum to 1.0, got {sum(v):.4f}")
        return v

    @model_validator(mode="after")
    def tickers_weights_same_length(self) -> "PortfolioMetrics":
        if len(self.tickers) != len(self.weights):
            raise ValueError("tickers and weights must have the same length")
        return self


# ---------------------------------------------------------------------------
# WebSocket Schemas
# ---------------------------------------------------------------------------

class WSPriceMessage(BaseModel):
    """WebSocket price update message pushed to clients every 5 seconds."""

    type: str = Field(default="price_update", description="Message type identifier")
    ticker: str = Field(..., description="Ticker symbol")
    price: float = Field(..., description="Current price")
    change: float = Field(..., description="Absolute change from previous close")
    change_pct: float = Field(..., description="Percentage change from previous close")
    timestamp: datetime = Field(..., description="UTC timestamp of this price snapshot")

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v != "price_update":
            raise ValueError("type must be 'price_update'")
        return v
