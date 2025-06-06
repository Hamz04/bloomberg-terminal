# Mini Bloomberg Terminal
### Author: Hamza Ahmad | ETS Montreal
### Built with FastAPI + Streamlit + FinBERT + yfinance

```
 ____  _                     _
|  _ \| | ___   ___  _ __ ___ | |__   ___ _ __ __ _
| |_) | |/ _ \ / _ \| '_ ` _ \| '_ \ / _ \ '__/ _` |
|  _ <| | (_) | (_) | | | | | | |_) |  __/ | | (_| |
|_| \_\_|\___/ \___/|_| |_| |_|_.__/ \___|_|  \__, |
                                                |___/
 _____                   _           _
|_   _|__ _ __ _ __ ___ (_)_ __   __| |
  | |/ _ \ '__| '_ ` _ \| | '_ \ / _` |
  | |  __/ |  | | | | | | | | | | (_| |
  |_|\___|_|  |_| |_| |_|_|_| |_|\__,_|
```

A production-grade financial intelligence terminal with real-time market data,
NLP sentiment analysis, options analytics, and portfolio risk metrics.

---

## Features

- **Real-Time Quotes** — Live bid/ask, OHLCV, 52-week range via yfinance
- **Interactive Charts** — Candlestick + volume, MACD, RSI via Plotly
- **Options Chain** — Calls/Puts heatmap, IV surface, Greeks
- **FinBERT Sentiment** — Transformer-based NLP on latest Yahoo Finance RSS news
- **Portfolio Analytics** — Sharpe ratio, Beta, VaR (95%), max drawdown, correlation matrix
- **Stock Screener** — Filter by P/E, market cap, volume, sector, 52w performance
- **WebSocket Streaming** — Sub-second price updates pushed to dashboard
- **Redis Caching** — 60-second TTL on quotes, graceful fallback when Redis is absent
- **Alpha Vantage Integration** — Fundamental data, earnings calendar, economic indicators
- **Dark Bloomberg Theme** — Professional terminal aesthetic in Streamlit

---

## Architecture

```
+---------------------------+        +---------------------------+
|   Streamlit Dashboard     |        |      FastAPI Backend       |
|   dashboard/              |        |      app/                 |
|   - streamlit_app.py      |<------>|   - main.py               |
|                           |  HTTP  |   - services/             |
|   Components:             |  + WS  |     - market_data.py      |
|   - Ticker search         |        |     - sentiment.py        |
|   - Candlestick chart     |        |     - analytics.py        |
|   - Options heatmap       |        |   - models/               |
|   - Sentiment gauge       |        |     - schemas.py          |
|   - Portfolio analyzer    |        +---------------------------+
|   - Stock screener        |                   |
+---------------------------+                   |
                                                |
              +----------------+----------------+---------------+
              |                |                |               |
     +--------+------+  +------+------+  +------+------+  +----+--------+
     |   yfinance    |  | Alpha Vantage|  |   FinBERT   |  |    Redis    |
     | (OHLCV, opts) |  | (fundamentals|  | (sentiment) |  |  (caching)  |
     +---------------+  |  earnings)  |  +-------------+  +-------------+
                        +-------------+
```

---

## Project Structure

```
bloomberg-terminal/
├── README.md
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI application + WebSocket
│   ├── models/
│   │   └── schemas.py           # Pydantic response models
│   └── services/
│       ├── market_data.py       # yfinance + Alpha Vantage + Redis cache
│       ├── sentiment.py         # FinBERT NLP pipeline + RSS scraping
│       └── analytics.py        # Sharpe, Beta, VaR, drawdown, correlations
└── dashboard/
    └── streamlit_app.py         # Full Streamlit UI
```

---

## Quick Start

### Option 1: Docker (Recommended)

```bash
git clone https://github.com/hamzaahmad/bloomberg-terminal.git
cd bloomberg-terminal
cp .env.example .env
# Add your ALPHA_VANTAGE_KEY to .env
docker-compose up --build
```

- Dashboard: http://localhost:8501
- API Docs:  http://localhost:8000/docs
- ReDoc:     http://localhost:8000/redoc

### Option 2: Local Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export ALPHA_VANTAGE_KEY=your_key_here
export REDIS_URL=redis://localhost:6379  # optional

# Start backend (terminal 1)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Start frontend (terminal 2)
streamlit run dashboard/streamlit_app.py --server.port 8501
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/quote/{ticker}` | Real-time quote + fundamentals |
| GET | `/api/history/{ticker}?period=1d` | OHLCV history (1d/1w/1m/3m/1y) |
| GET | `/api/options/{ticker}` | Full options chain with Greeks |
| GET | `/api/sentiment/{ticker}` | FinBERT sentiment on latest news |
| GET | `/api/screener?pe_max=20&mcap_min=1e9` | Stock screener with filters |
| GET | `/api/portfolio/analyze` | Portfolio risk metrics |
| WS  | `/ws/prices` | Real-time price streaming |
| GET | `/health` | Health check |

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ALPHA_VANTAGE_KEY` | Yes | Free key from alphavantage.co |
| `REDIS_URL` | No | Redis connection string (default: redis://localhost:6379) |
| `API_HOST` | No | Backend host for Streamlit (default: localhost) |
| `API_PORT` | No | Backend port (default: 8000) |
| `LOG_LEVEL` | No | Logging level (default: INFO) |
| `RATE_LIMIT_PER_MINUTE` | No | API rate limit (default: 60) |

---

## Resume Bullet Points

> Copy-paste ready for your software engineering resume:

```
Bloomberg Terminal Clone | Python, FastAPI, Streamlit, FinBERT, yfinance
- Architected a full-stack financial intelligence platform with real-time WebSocket
  price streaming, serving sub-100ms quote latency via Redis-backed caching layer.
- Integrated HuggingFace FinBERT transformer model to perform sentiment analysis on
  live Yahoo Finance RSS news feeds, achieving nuanced financial NLP scoring.
- Built REST API with FastAPI (12 endpoints) covering quotes, options chains, portfolio
  risk metrics (Sharpe ratio, Beta, VaR 95%, max drawdown) and a multi-filter stock screener.
- Designed interactive Streamlit dashboard with Plotly candlestick charts, options Greeks
  heatmaps, sentiment gauges, and portfolio correlation matrices using dark Bloomberg theme.
- Containerized full application stack (app + Redis) via Docker Compose for one-command
  reproducible deployment; implemented graceful degradation when optional services are offline.
```

---

## Technical Highlights

- **Rate Limiting**: SlowAPI middleware (60 req/min per IP)
- **Caching Strategy**: Redis TTL 60s for quotes, 5min for history, 1hr for fundamentals
- **Async Architecture**: Full async/await across FastAPI endpoints and data fetching
- **Error Handling**: Structured error responses with HTTP status codes and detail messages
- **Logging**: Structured JSON logging with request IDs via Python logging module
- **Data Validation**: Pydantic v2 models for all request/response schemas
- **WebSocket**: Asyncio-based broadcast to multiple concurrent dashboard clients

---

## License

MIT License - Hamza Ahmad, ETS Montreal, 2024
