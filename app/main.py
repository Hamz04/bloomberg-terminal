# Built by Hamzy - ETS Montreal
# FastAPI Bloomberg Terminal backend — full production application

from __future__ import annotations

import asyncio
import sys
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator, List, Optional

import uvicorn
from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.models.schemas import (
    HistoryResponse,
    OptionsChainResponse,
    PortfolioMetrics,
    QuoteResponse,
    ScreenerResponse,
    SentimentResponse,
    WSPriceMessage,
)
from app.services.analytics import AnalyticsService
from app.services.market_data import MarketDataService
from app.services.sentiment import SentimentService

# ---------------------------------------------------------------------------
# Logging configuration (Loguru)
# ---------------------------------------------------------------------------

logger.remove()
logger.add(
    sys.stderr,
    format=(
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> — "
        "<level>{message}</level>"
    ),
    level="INFO",
    colorize=True,
)
logger.add(
    "logs/bloomberg_terminal.log",
    rotation="50 MB",
    retention="14 days",
    compression="gz",
    level="DEBUG",
    enqueue=True,
)

# ---------------------------------------------------------------------------
# Rate limiter (SlowAPI)
# ---------------------------------------------------------------------------

limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])

# ---------------------------------------------------------------------------
# Service singletons
# ---------------------------------------------------------------------------

_market_svc: Optional[MarketDataService] = None
_sentiment_svc: Optional[SentimentService] = None
_analytics_svc: Optional[AnalyticsService] = None


def get_market_service() -> MarketDataService:
    if _market_svc is None:
        raise RuntimeError("MarketDataService not initialised")
    return _market_svc


def get_sentiment_service() -> SentimentService:
    if _sentiment_svc is None:
        raise RuntimeError("SentimentService not initialised")
    return _sentiment_svc


def get_analytics_service() -> AnalyticsService:
    if _analytics_svc is None:
        raise RuntimeError("AnalyticsService not initialised")
    return _analytics_svc


# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global _market_svc, _sentiment_svc, _analytics_svc

    logger.info("Bloomberg Terminal API starting up …")
    _market_svc = MarketDataService()
    _sentiment_svc = SentimentService()
    _analytics_svc = AnalyticsService()
    logger.success("All services initialised. API ready.")

    yield

    logger.info("Bloomberg Terminal API shutting down …")
    # Graceful shutdown: close Redis connections if open
    for svc in (_market_svc, _sentiment_svc):
        redis_client = getattr(svc, "_redis", None)
        if redis_client is not None:
            try:
                redis_client.close()
            except Exception:
                pass
    logger.info("Shutdown complete.")


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Bloomberg Terminal API",
    description=(
        "Production-grade financial data API providing real-time quotes, "
        "options chains, news sentiment, portfolio analytics, and stock screening.\n\n"
        "**Built by Hamzy — ETS Montreal**"
    ),
    version="1.0.0",
    contact={
        "name": "Hamzy",
        "email": "hhhyh178@gmail.com",
    },
    license_info={"name": "MIT"},
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Attach rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # tighten in production to specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Built-By", "X-Response-Time"],
)

# ---------------------------------------------------------------------------
# Request timing + author middleware
# ---------------------------------------------------------------------------

@app.middleware("http")
async def timing_and_author_middleware(request: Request, call_next: Any) -> Response:
    t0 = time.perf_counter()
    response: Response = await call_next(request)
    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
    response.headers["X-Response-Time"] = f"{elapsed_ms}ms"
    response.headers["X-Built-By"] = "Hamzy"
    logger.info(
        "{method} {path} → {status} ({elapsed}ms)",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        elapsed=elapsed_ms,
    )
    return response


# We need Any for the middleware type hint without importing it at top level
from typing import Any  # noqa: E402 (placed here intentionally after middleware def)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get(
    "/health",
    tags=["System"],
    summary="Health check",
    response_description="API health status",
)
async def health_check() -> JSONResponse:
    """Returns a simple liveness probe response."""
    return JSONResponse(
        content={
            "status": "ok",
            "service": "Bloomberg Terminal API",
            "author": "Hamzy - ETS Montreal",
            "version": "1.0.0",
        }
    )


# ---------------------------------------------------------------------------
# Quote endpoint
# ---------------------------------------------------------------------------

@app.get(
    "/api/quote/{ticker}",
    response_model=QuoteResponse,
    tags=["Market Data"],
    summary="Real-time stock quote",
)
@limiter.limit("100/minute")
async def get_quote(
    request: Request,
    ticker: str,
    svc: MarketDataService = Depends(get_market_service),
) -> QuoteResponse:
    """
    Returns a real-time quote snapshot for the requested ticker.
    Results are cached for **30 seconds**.

    - **ticker**: Stock symbol (e.g. `AAPL`, `MSFT`, `TSLA`)
    """
    try:
        return svc.get_quote(ticker)
    except Exception as exc:
        logger.error("Quote error for {}: {}", ticker, exc)
        raise HTTPException(status_code=404, detail=str(exc))


# ---------------------------------------------------------------------------
# History endpoint
# ---------------------------------------------------------------------------

@app.get(
    "/api/history/{ticker}",
    response_model=HistoryResponse,
    tags=["Market Data"],
    summary="OHLCV price history",
)
@limiter.limit("60/minute")
async def get_history(
    request: Request,
    ticker: str,
    period: str = Query(
        default="1m",
        description="Time period: `1d`, `1w`, `1m`, `3m`, `1y`",
        pattern="^(1d|1w|1m|3m|1y)$",
    ),
    svc: MarketDataService = Depends(get_market_service),
) -> HistoryResponse:
    """
    Returns OHLCV candlestick bars for the requested ticker and period.
    Results are cached for **5 minutes**.
    """
    try:
        return svc.get_history(ticker, period)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("History error for {} period={}: {}", ticker, period, exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Options chain endpoint
# ---------------------------------------------------------------------------

@app.get(
    "/api/options/{ticker}",
    response_model=OptionsChainResponse,
    tags=["Options"],
    summary="Full options chain",
)
@limiter.limit("30/minute")
async def get_options_chain(
    request: Request,
    ticker: str,
    svc: MarketDataService = Depends(get_market_service),
) -> OptionsChainResponse:
    """
    Returns calls and puts for the nearest expiry date of *ticker*.
    Results are cached for **60 seconds**.
    """
    try:
        return svc.get_options_chain(ticker)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error("Options error for {}: {}", ticker, exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Sentiment endpoint
# ---------------------------------------------------------------------------

@app.get(
    "/api/sentiment/{ticker}",
    response_model=SentimentResponse,
    tags=["Sentiment"],
    summary="News sentiment analysis",
)
@limiter.limit("20/minute")
async def get_sentiment(
    request: Request,
    ticker: str,
    svc: SentimentService = Depends(get_sentiment_service),
) -> SentimentResponse:
    """
    Fetches latest news from Yahoo Finance RSS and scores each article
    using **FinBERT** (ProsusAI/finbert). Falls back to a keyword lexicon
    if the model is unavailable. Results are cached for **5 minutes**.
    """
    try:
        return svc.analyze(ticker)
    except Exception as exc:
        logger.error("Sentiment error for {}: {}", ticker, exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Screener endpoint
# ---------------------------------------------------------------------------

@app.get(
    "/api/screener",
    response_model=ScreenerResponse,
    tags=["Screener"],
    summary="Filter stocks from a 50-ticker universe",
)
@limiter.limit("20/minute")
async def get_screener(
    request: Request,
    min_price: float = Query(default=0.0, ge=0, description="Minimum stock price (USD)"),
    max_price: float = Query(default=9999.0, ge=0, description="Maximum stock price (USD)"),
    min_market_cap: float = Query(default=0.0, ge=0, description="Minimum market cap (USD)"),
    sector: str = Query(default="all", description="Sector filter (e.g. Technology, Healthcare, or 'all')"),
    svc: MarketDataService = Depends(get_market_service),
) -> ScreenerResponse:
    """
    Screens the pre-defined universe of **50 popular tickers** using
    price, market cap, and sector filters. Results are cached for **2 minutes**.
    """
    try:
        return svc.get_screener(
            min_price=min_price,
            max_price=max_price,
            min_market_cap=min_market_cap,
            sector=None if sector.lower() == "all" else sector,
        )
    except Exception as exc:
        logger.error("Screener error: {}", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Portfolio analytics endpoint
# ---------------------------------------------------------------------------

@app.get(
    "/api/portfolio/analyze",
    response_model=PortfolioMetrics,
    tags=["Portfolio"],
    summary="Portfolio risk/return analytics",
)
@limiter.limit("10/minute")
async def analyze_portfolio(
    request: Request,
    tickers: str = Query(
        ...,
        description="Comma-separated tickers (e.g. `AAPL,MSFT,GOOGL`)",
        example="AAPL,MSFT,GOOGL",
    ),
    weights: str = Query(
        ...,
        description="Comma-separated weights summing to 1.0 (e.g. `0.4,0.35,0.25`)",
        example="0.4,0.35,0.25",
    ),
    svc: AnalyticsService = Depends(get_analytics_service),
) -> PortfolioMetrics:
    """
    Computes the following metrics over a **1-year** look-back period:

    | Metric | Description |
    |---|---|
    | `annualized_return_pct` | Geometric annualised return |
    | `sharpe_ratio` | Sharpe ratio (RF = 5.25 %) |
    | `beta` | Portfolio beta vs SPY |
    | `max_drawdown_pct` | Peak-to-trough maximum drawdown |
    | `var_95_pct` | Historical 95 % Value-at-Risk (1-day) |
    | `volatility_annualized` | Annualised portfolio volatility |
    | `correlation_matrix` | Pairwise ticker correlations |
    """
    try:
        ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
        weight_list = [float(w.strip()) for w in weights.split(",") if w.strip()]

        if len(ticker_list) == 0:
            raise ValueError("At least one ticker is required.")
        if len(ticker_list) != len(weight_list):
            raise ValueError(
                f"Number of tickers ({len(ticker_list)}) must match number of weights ({len(weight_list)})."
            )

        return svc.calculate_portfolio_metrics(ticker_list, weight_list)

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("Portfolio analytics error: {}", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# WebSocket — live price stream
# ---------------------------------------------------------------------------

@app.websocket("/ws/prices/{ticker}")
async def websocket_price_stream(websocket: WebSocket, ticker: str) -> None:
    """
    WebSocket endpoint that pushes a price update every **5 seconds**.

    Message format (JSON):
    ```json
    {
      "type": "price_update",
      "ticker": "AAPL",
      "price": 189.30,
      "change": 2.15,
      "change_pct": 1.15,
      "timestamp": "2024-01-15T20:00:00+00:00"
    }
    ```
    """
    await websocket.accept()
    ticker_upper = ticker.upper().strip()
    svc: MarketDataService = get_market_service()

    logger.info("WebSocket opened for ticker={} client={}", ticker_upper, websocket.client)

    try:
        while True:
            try:
                quote = svc.get_quote(ticker_upper)
                msg = WSPriceMessage(
                    type="price_update",
                    ticker=quote.ticker,
                    price=quote.price,
                    change=quote.change,
                    change_pct=quote.change_pct,
                    timestamp=quote.timestamp,
                )
                await websocket.send_text(msg.model_dump_json())
                logger.debug("WS push {} price={}", ticker_upper, quote.price)
            except Exception as exc:
                logger.warning("WS price fetch error for {}: {}", ticker_upper, exc)
                error_payload = {
                    "type": "error",
                    "ticker": ticker_upper,
                    "message": str(exc),
                }
                import json
                await websocket.send_text(json.dumps(error_payload))

            await asyncio.sleep(5)

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for ticker={}", ticker_upper)
    except Exception as exc:
        logger.error("WebSocket fatal error for {}: {}", ticker_upper, exc)
        try:
            await websocket.close(code=1011)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------

@app.exception_handler(404)
async def not_found_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={
            "error": "Not found",
            "path": str(request.url.path),
            "detail": str(exc),
        },
    )


@app.exception_handler(500)
async def server_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled server error on {}: {}", request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": "An unexpected error occurred. Please try again later.",
        },
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
        access_log=False,   # handled by our custom middleware
    )
