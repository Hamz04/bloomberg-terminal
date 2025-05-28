# Built by Hamza Ahmad - ETS Montreal
# Streamlit Bloomberg Terminal Dashboard — full dark-theme, 5-page application

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st
from plotly.subplots import make_subplots

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_URL: str = os.getenv("API_URL", "http://localhost:8000")
AUTO_REFRESH_INTERVAL: int = 30  # seconds (market overview page)

# Bloomberg-inspired colour palette
BLOOMBERG_BG = "#0a0a0a"
BLOOMBERG_SURFACE = "#111111"
BLOOMBERG_PANEL = "#1a1a1a"
BLOOMBERG_BORDER = "#2a2a2a"
BLOOMBERG_ORANGE = "#ff6600"
BLOOMBERG_GOLD = "#ffa500"
BLOOMBERG_GREEN = "#00c853"
BLOOMBERG_RED = "#f44336"
BLOOMBERG_GREY = "#888888"
BLOOMBERG_WHITE = "#e8e8e8"
BLOOMBERG_BLUE = "#1e88e5"

PLOTLY_TEMPLATE = dict(
    layout=go.Layout(
        paper_bgcolor=BLOOMBERG_SURFACE,
        plot_bgcolor=BLOOMBERG_PANEL,
        font=dict(color=BLOOMBERG_WHITE, family="Courier New, monospace"),
        xaxis=dict(gridcolor=BLOOMBERG_BORDER, zerolinecolor=BLOOMBERG_BORDER),
        yaxis=dict(gridcolor=BLOOMBERG_BORDER, zerolinecolor=BLOOMBERG_BORDER),
        legend=dict(bgcolor=BLOOMBERG_SURFACE, bordercolor=BLOOMBERG_BORDER),
        colorway=[BLOOMBERG_ORANGE, BLOOMBERG_BLUE, BLOOMBERG_GREEN, BLOOMBERG_RED, BLOOMBERG_GOLD],
    )
)

# ---------------------------------------------------------------------------
# Page config (must be first Streamlit call)
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Bloomberg Terminal | Hamza Ahmad",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get Help": None,
        "Report a bug": None,
        "About": "Bloomberg Terminal Clone — Built by Hamza Ahmad, ETS Montreal",
    },
)

# ---------------------------------------------------------------------------
# Global CSS — Bloomberg dark theme
# ---------------------------------------------------------------------------

st.markdown(
    f"""
    <style>
    /* ── Root ── */
    html, body, [data-testid="stAppViewContainer"] {{
        background-color: {BLOOMBERG_BG};
        color: {BLOOMBERG_WHITE};
        font-family: "Courier New", Courier, monospace;
    }}
    [data-testid="stSidebar"] {{
        background-color: {BLOOMBERG_SURFACE};
        border-right: 1px solid {BLOOMBERG_BORDER};
    }}
    [data-testid="stSidebar"] * {{
        color: {BLOOMBERG_WHITE} !important;
    }}
    /* ── Metric cards ── */
    [data-testid="metric-container"] {{
        background-color: {BLOOMBERG_PANEL};
        border: 1px solid {BLOOMBERG_BORDER};
        border-radius: 4px;
        padding: 12px;
    }}
    [data-testid="stMetricValue"] {{
        color: {BLOOMBERG_ORANGE} !important;
        font-size: 1.5rem !important;
        font-weight: bold;
    }}
    [data-testid="stMetricLabel"] {{
        color: {BLOOMBERG_GREY} !important;
        font-size: 0.75rem !important;
        text-transform: uppercase;
        letter-spacing: 0.08em;
    }}
    /* ── Headers ── */
    h1, h2, h3, h4 {{
        color: {BLOOMBERG_ORANGE} !important;
        font-family: "Courier New", Courier, monospace !important;
    }}
    /* ── Inputs ── */
    input, select, textarea {{
        background-color: {BLOOMBERG_PANEL} !important;
        color: {BLOOMBERG_WHITE} !important;
        border: 1px solid {BLOOMBERG_BORDER} !important;
    }}
    /* ── Buttons ── */
    [data-testid="stButton"] button {{
        background-color: {BLOOMBERG_ORANGE};
        color: #000;
        font-weight: bold;
        border: none;
        border-radius: 3px;
        font-family: "Courier New", monospace;
    }}
    [data-testid="stButton"] button:hover {{
        background-color: {BLOOMBERG_GOLD};
    }}
    /* ── Tables ── */
    [data-testid="stDataFrame"] table {{
        background-color: {BLOOMBERG_PANEL};
    }}
    /* ── Dividers ── */
    hr {{
        border-color: {BLOOMBERG_BORDER};
    }}
    /* ── Select boxes ── */
    [data-testid="stSelectbox"] > div > div {{
        background-color: {BLOOMBERG_PANEL};
        border-color: {BLOOMBERG_BORDER};
        color: {BLOOMBERG_WHITE};
    }}
    /* ── Scrollbar ── */
    ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
    ::-webkit-scrollbar-track {{ background: {BLOOMBERG_BG}; }}
    ::-webkit-scrollbar-thumb {{ background: {BLOOMBERG_BORDER}; border-radius: 3px; }}
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def api_get(path: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Make a GET request to the backend API and return parsed JSON, or None on error."""
    url = f"{API_URL}{path}"
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        st.error(f"Cannot connect to API at {API_URL}. Is the server running?")
    except requests.exceptions.HTTPError as exc:
        detail = ""
        try:
            detail = exc.response.json().get("detail", "")
        except Exception:
            pass
        st.error(f"API error {exc.response.status_code}: {detail or str(exc)}")
    except Exception as exc:
        st.error(f"Unexpected error: {exc}")
    return None


def fmt_large_number(n: Optional[float]) -> str:
    """Format large numbers: 2.95T, 450B, 1.2M, etc."""
    if n is None:
        return "N/A"
    n = float(n)
    if abs(n) >= 1e12:
        return f"{n/1e12:.2f}T"
    if abs(n) >= 1e9:
        return f"{n/1e9:.2f}B"
    if abs(n) >= 1e6:
        return f"{n/1e6:.2f}M"
    return f"{n:,.2f}"


def change_color(val: float) -> str:
    return BLOOMBERG_GREEN if val >= 0 else BLOOMBERG_RED


def change_arrow(val: float) -> str:
    return "▲" if val >= 0 else "▼"


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown(
        f"<h2 style='color:{BLOOMBERG_ORANGE}; margin-bottom:0'>📊 BLOOMBERG</h2>"
        f"<p style='color:{BLOOMBERG_GREY}; font-size:0.7rem; margin-top:2px'>Built by Hamza Ahmad · ETS Montreal</p>",
        unsafe_allow_html=True,
    )
    st.markdown(f"<hr style='border-color:{BLOOMBERG_BORDER}'>", unsafe_allow_html=True)

    page = st.selectbox(
        "Navigation",
        options=[
            "Market Overview",
            "Options Chain",
            "Sentiment Analysis",
            "Portfolio Analyzer",
            "Stock Screener",
        ],
        index=0,
    )

    st.markdown(f"<hr style='border-color:{BLOOMBERG_BORDER}'>", unsafe_allow_html=True)

    ticker_input = st.text_input(
        "Ticker Symbol",
        value="AAPL",
        max_chars=10,
        help="Enter a stock ticker (e.g. AAPL, MSFT, TSLA)",
    ).upper().strip()

    period_options = {"1 Day": "1d", "1 Week": "1w", "1 Month": "1m", "3 Months": "3m", "1 Year": "1y"}
    selected_period_label = st.selectbox("Chart Period", list(period_options.keys()), index=2)
    selected_period = period_options[selected_period_label]

    st.markdown(f"<hr style='border-color:{BLOOMBERG_BORDER}'>", unsafe_allow_html=True)
    st.markdown(
        f"<p style='color:{BLOOMBERG_GREY}; font-size:0.65rem;'>"
        f"API: <code style='color:{BLOOMBERG_ORANGE}'>{API_URL}</code></p>",
        unsafe_allow_html=True,
    )


# ===========================================================================
# PAGE 1 — MARKET OVERVIEW
# ===========================================================================

if page == "Market Overview":
    # Auto-refresh counter
    if "last_refresh" not in st.session_state:
        st.session_state.last_refresh = time.time()

    elapsed = time.time() - st.session_state.last_refresh
    if elapsed >= AUTO_REFRESH_INTERVAL:
        st.session_state.last_refresh = time.time()
        st.rerun()

    st.markdown(f"<h1>MARKET OVERVIEW — {ticker_input}</h1>", unsafe_allow_html=True)

    col_refresh, col_timer = st.columns([8, 2])
    with col_refresh:
        if st.button("⟳ Refresh Now"):
            st.session_state.last_refresh = time.time()
            st.rerun()
    with col_timer:
        remaining = max(0, int(AUTO_REFRESH_INTERVAL - elapsed))
        st.markdown(
            f"<p style='color:{BLOOMBERG_GREY}; text-align:right; font-size:0.75rem;'>"
            f"Auto-refresh in {remaining}s</p>",
            unsafe_allow_html=True,
        )

    # ── Quote card ──
    quote_data = api_get(f"/api/quote/{ticker_input}")

    if quote_data:
        price = quote_data["price"]
        change = quote_data["change"]
        change_pct = quote_data["change_pct"]
        color = change_color(change)
        arrow = change_arrow(change)

        st.markdown(
            f"""
            <div style="background:{BLOOMBERG_PANEL}; border:1px solid {BLOOMBERG_BORDER};
                        border-left: 3px solid {color}; border-radius:4px;
                        padding:16px 24px; margin-bottom:16px;">
                <div style="display:flex; align-items:baseline; gap:16px; flex-wrap:wrap;">
                    <span style="color:{BLOOMBERG_GREY}; font-size:0.8rem; text-transform:uppercase;
                                 letter-spacing:0.1em;">{quote_data.get('name','')}</span>
                    <span style="color:{BLOOMBERG_ORANGE}; font-weight:bold; font-size:0.9rem;">
                        {ticker_input}</span>
                </div>
                <div style="display:flex; align-items:baseline; gap:20px; margin-top:8px; flex-wrap:wrap;">
                    <span style="color:{BLOOMBERG_WHITE}; font-size:2.8rem; font-weight:bold;
                                 font-family:'Courier New';">${price:,.2f}</span>
                    <span style="color:{color}; font-size:1.4rem; font-weight:bold;">
                        {arrow} {abs(change):,.2f} ({abs(change_pct):,.2f}%)</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("Open", f"${quote_data['open']:,.2f}")
        c2.metric("High", f"${quote_data['high']:,.2f}")
        c3.metric("Low", f"${quote_data['low']:,.2f}")
        c4.metric("Prev Close", f"${quote_data['prev_close']:,.2f}")
        c5.metric("Volume", fmt_large_number(quote_data["volume"]))
        c6.metric("Avg Volume", fmt_large_number(quote_data["avg_volume"]))

        c7, c8, c9, c10 = st.columns(4)
        c7.metric("Market Cap", fmt_large_number(quote_data.get("market_cap")))
        c8.metric("P/E Ratio", f"{quote_data['pe_ratio']:.1f}" if quote_data.get("pe_ratio") else "N/A")
        c9.metric("52W High", f"${quote_data['week_52_high']:,.2f}" if quote_data.get("week_52_high") else "N/A")
        c10.metric("52W Low", f"${quote_data['week_52_low']:,.2f}" if quote_data.get("week_52_low") else "N/A")

    st.markdown(f"<hr style='border-color:{BLOOMBERG_BORDER}'>", unsafe_allow_html=True)

    # ── Candlestick chart ──
    hist_data = api_get(f"/api/history/{ticker_input}", params={"period": selected_period})

    if hist_data and hist_data.get("bars"):
        bars = hist_data["bars"]
        df = pd.DataFrame(bars)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values("timestamp")

        # Moving averages
        df["MA20"] = df["close"].rolling(window=20, min_periods=1).mean()
        df["MA50"] = df["close"].rolling(window=50, min_periods=1).mean()

        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.04,
            row_heights=[0.75, 0.25],
            subplot_titles=["", "Volume"],
        )

        # Candlesticks
        fig.add_trace(
            go.Candlestick(
                x=df["timestamp"],
                open=df["open"], high=df["high"],
                low=df["low"], close=df["close"],
                name=ticker_input,
                increasing_line_color=BLOOMBERG_GREEN,
                decreasing_line_color=BLOOMBERG_RED,
                increasing_fillcolor=BLOOMBERG_GREEN,
                decreasing_fillcolor=BLOOMBERG_RED,
            ),
            row=1, col=1,
        )

        # MA overlays
        if len(df) >= 20:
            fig.add_trace(
                go.Scatter(
                    x=df["timestamp"], y=df["MA20"],
                    mode="lines", name="MA20",
                    line=dict(color=BLOOMBERG_GOLD, width=1.2, dash="dot"),
                ),
                row=1, col=1,
            )
        if len(df) >= 50:
            fig.add_trace(
                go.Scatter(
                    x=df["timestamp"], y=df["MA50"],
                    mode="lines", name="MA50",
                    line=dict(color=BLOOMBERG_BLUE, width=1.2, dash="dash"),
                ),
                row=1, col=1,
            )

        # Volume bars
        vol_colors = [
            BLOOMBERG_GREEN if df["close"].iloc[i] >= df["open"].iloc[i] else BLOOMBERG_RED
            for i in range(len(df))
        ]
        fig.add_trace(
            go.Bar(
                x=df["timestamp"], y=df["volume"],
                name="Volume", marker_color=vol_colors, showlegend=False,
            ),
            row=2, col=1,
        )

        fig.update_layout(
            **PLOTLY_TEMPLATE["layout"].to_plotly_json(),
            height=580,
            title=dict(
                text=f"{ticker_input} — {selected_period_label}",
                font=dict(color=BLOOMBERG_ORANGE, size=14),
            ),
            xaxis_rangeslider_visible=False,
            margin=dict(l=10, r=10, t=40, b=10),
        )
        fig.update_xaxes(showgrid=True, gridcolor=BLOOMBERG_BORDER)
        fig.update_yaxes(showgrid=True, gridcolor=BLOOMBERG_BORDER)

        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No historical data available for the selected period.")


# ===========================================================================
# PAGE 2 — OPTIONS CHAIN
# ===========================================================================

elif page == "Options Chain":
    st.markdown(f"<h1>OPTIONS CHAIN — {ticker_input}</h1>", unsafe_allow_html=True)

    options_data = api_get(f"/api/options/{ticker_input}")

    if options_data:
        current_price = options_data["current_price"]
        expiry_dates = options_data["expiry_dates"]

        st.markdown(
            f"<p style='color:{BLOOMBERG_GREY}'>Underlying: "
            f"<span style='color:{BLOOMBERG_WHITE}; font-weight:bold'>${current_price:,.2f}</span>"
            f"&nbsp;&nbsp;|&nbsp;&nbsp;Expiries available: "
            f"<span style='color:{BLOOMBERG_ORANGE}'>{len(expiry_dates)}</span></p>",
            unsafe_allow_html=True,
        )

        selected_expiry = st.selectbox("Select Expiry Date", expiry_dates, index=0)

        calls = pd.DataFrame(options_data["calls"])
        puts = pd.DataFrame(options_data["puts"])

        def style_itm(df: pd.DataFrame) -> pd.DataFrame:
            """Highlight in-the-money rows."""
            return df

        def color_itm_rows(row: pd.Series) -> List[str]:
            base = f"background-color: {BLOOMBERG_PANEL}; color: {BLOOMBERG_WHITE};"
            itm_style = f"background-color: #1a2a1a; color: {BLOOMBERG_GREEN}; font-weight: bold;"
            return [itm_style if row.get("in_the_money", False) else base] * len(row)

        # Display columns
        display_cols = ["strike", "bid", "ask", "last", "volume", "open_interest", "implied_volatility", "in_the_money"]
        display_cols_calls = [c for c in display_cols if c in calls.columns]
        display_cols_puts = [c for c in display_cols if c in puts.columns]

        col_calls, col_puts = st.columns(2)

        with col_calls:
            st.markdown(
                f"<h3 style='color:{BLOOMBERG_GREEN}'>CALLS</h3>",
                unsafe_allow_html=True,
            )
            if not calls.empty:
                calls_display = calls[display_cols_calls].copy()
                calls_display["implied_volatility"] = (calls_display["implied_volatility"] * 100).round(1).astype(str) + "%"
                st.dataframe(
                    calls_display.style.apply(color_itm_rows, axis=1),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("No call data available.")

        with col_puts:
            st.markdown(
                f"<h3 style='color:{BLOOMBERG_RED}'>PUTS</h3>",
                unsafe_allow_html=True,
            )
            if not puts.empty:
                puts_display = puts[display_cols_puts].copy()
                puts_display["implied_volatility"] = (puts_display["implied_volatility"] * 100).round(1).astype(str) + "%"
                st.dataframe(
                    puts_display.style.apply(color_itm_rows, axis=1),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("No put data available.")

        # ── IV Heatmap ──
        st.markdown(f"<hr style='border-color:{BLOOMBERG_BORDER}'>", unsafe_allow_html=True)
        st.markdown(f"<h3>Implied Volatility Surface</h3>", unsafe_allow_html=True)

        if not calls.empty and not puts.empty:
            heatmap_data_calls = calls[["strike", "implied_volatility"]].copy()
            heatmap_data_calls["type"] = "Call IV"
            heatmap_data_puts = puts[["strike", "implied_volatility"]].copy()
            heatmap_data_puts["type"] = "Put IV"
            combined_iv = pd.concat([heatmap_data_calls, heatmap_data_puts])
            combined_iv["implied_volatility_pct"] = combined_iv["implied_volatility"] * 100

            pivot = combined_iv.pivot_table(
                index="type", columns="strike", values="implied_volatility_pct", aggfunc="mean"
            )

            fig_iv = px.imshow(
                pivot,
                color_continuous_scale=[
                    [0, "#003300"],
                    [0.3, "#00aa00"],
                    [0.6, "#ffaa00"],
                    [1.0, "#ff0000"],
                ],
                labels={"x": "Strike Price", "y": "Option Type", "color": "IV (%)"},
                title=f"IV Heatmap — {ticker_input}",
                aspect="auto",
            )
            fig_iv.update_layout(
                **PLOTLY_TEMPLATE["layout"].to_plotly_json(),
                height=220,
                margin=dict(l=10, r=10, t=40, b=10),
            )
            st.plotly_chart(fig_iv, use_container_width=True)


# ===========================================================================
# PAGE 3 — SENTIMENT ANALYSIS
# ===========================================================================

elif page == "Sentiment Analysis":
    st.markdown(f"<h1>SENTIMENT ANALYSIS — {ticker_input}</h1>", unsafe_allow_html=True)

    with st.spinner("Fetching and scoring news articles …"):
        sent_data = api_get(f"/api/sentiment/{ticker_input}")

    if sent_data:
        overall = sent_data["overall_sentiment"].upper()
        score = sent_data["overall_score"]
        n_articles = sent_data["articles_analyzed"]
        bull_pct = sent_data["bullish_pct"]
        bear_pct = sent_data["bearish_pct"]
        neut_pct = sent_data["neutral_pct"]

        score_color = BLOOMBERG_GREEN if score > 0.1 else (BLOOMBERG_RED if score < -0.1 else BLOOMBERG_GREY)

        col_gauge, col_pie = st.columns([1, 1])

        # ── Gauge chart ──
        with col_gauge:
            fig_gauge = go.Figure(go.Indicator(
                mode="gauge+number+delta",
                value=score * 100,
                delta={"reference": 0, "valueformat": ".1f"},
                title={"text": f"Sentiment Score<br><span style='font-size:0.8em'>({overall})</span>",
                       "font": {"color": score_color, "size": 16}},
                number={"suffix": "", "valueformat": ".1f", "font": {"color": score_color, "size": 32}},
                gauge={
                    "axis": {"range": [-100, 100], "tickcolor": BLOOMBERG_GREY,
                              "tickfont": {"color": BLOOMBERG_GREY}},
                    "bar": {"color": score_color, "thickness": 0.25},
                    "bgcolor": BLOOMBERG_PANEL,
                    "bordercolor": BLOOMBERG_BORDER,
                    "steps": [
                        {"range": [-100, -10], "color": "#2a0a0a"},
                        {"range": [-10, 10], "color": "#1a1a1a"},
                        {"range": [10, 100], "color": "#0a2a0a"},
                    ],
                    "threshold": {
                        "line": {"color": BLOOMBERG_ORANGE, "width": 2},
                        "thickness": 0.8,
                        "value": score * 100,
                    },
                },
            ))
            fig_gauge.update_layout(
                **PLOTLY_TEMPLATE["layout"].to_plotly_json(),
                height=320,
                margin=dict(l=20, r=20, t=60, b=20),
            )
            st.plotly_chart(fig_gauge, use_container_width=True)

            col_m1, col_m2, col_m3 = st.columns(3)
            col_m1.metric("Articles Analyzed", n_articles)
            col_m2.metric("Bullish", f"{bull_pct:.1f}%")
            col_m3.metric("Bearish", f"{bear_pct:.1f}%")

        # ── Pie chart ──
        with col_pie:
            fig_pie = go.Figure(go.Pie(
                labels=["Bullish", "Bearish", "Neutral"],
                values=[bull_pct, bear_pct, neut_pct],
                marker=dict(colors=[BLOOMBERG_GREEN, BLOOMBERG_RED, BLOOMBERG_GREY]),
                textinfo="percent+label",
                textfont=dict(color=BLOOMBERG_WHITE, size=13),
                hole=0.45,
                hovertemplate="<b>%{label}</b><br>%{percent}<extra></extra>",
            ))
            fig_pie.update_layout(
                **PLOTLY_TEMPLATE["layout"].to_plotly_json(),
                height=320,
                title=dict(text="Sentiment Breakdown", font=dict(color=BLOOMBERG_ORANGE, size=14)),
                margin=dict(l=10, r=10, t=50, b=10),
                showlegend=True,
            )
            st.plotly_chart(fig_pie, use_container_width=True)

        # ── Article list ──
        st.markdown(f"<hr style='border-color:{BLOOMBERG_BORDER}'>", unsafe_allow_html=True)
        st.markdown(f"<h3>News Articles ({n_articles})</h3>", unsafe_allow_html=True)

        sentiment_label_colors = {
            "bullish": BLOOMBERG_GREEN,
            "bearish": BLOOMBERG_RED,
            "neutral": BLOOMBERG_GREY,
        }
        sentiment_label_icons = {"bullish": "▲", "bearish": "▼", "neutral": "■"}

        for article in sent_data.get("articles", []):
            label = article["sentiment"]
            art_color = sentiment_label_colors.get(label, BLOOMBERG_GREY)
            icon = sentiment_label_icons.get(label, "·")
            score_val = article["sentiment_score"]
            pub = article["published"][:10] if article.get("published") else ""

            st.markdown(
                f"""
                <div style="background:{BLOOMBERG_PANEL}; border:1px solid {BLOOMBERG_BORDER};
                            border-left: 3px solid {art_color}; border-radius:3px;
                            padding:10px 14px; margin-bottom:6px;">
                    <div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap;">
                        <a href="{article['url']}" target="_blank"
                           style="color:{BLOOMBERG_WHITE}; text-decoration:none; font-size:0.9rem;
                                  flex:1; min-width:0; margin-right:12px;">
                            {article['title']}
                        </a>
                        <span style="color:{art_color}; font-weight:bold; font-size:0.85rem;
                                     white-space:nowrap;">
                            {icon} {label.upper()} ({score_val:+.2f})
                        </span>
                    </div>
                    <div style="color:{BLOOMBERG_GREY}; font-size:0.72rem; margin-top:4px;">
                        {article.get('source','Yahoo Finance')} &nbsp;·&nbsp; {pub}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


# ===========================================================================
# PAGE 4 — PORTFOLIO ANALYZER
# ===========================================================================

elif page == "Portfolio Analyzer":
    st.markdown("<h1>PORTFOLIO ANALYZER</h1>", unsafe_allow_html=True)

    st.markdown(
        f"<p style='color:{BLOOMBERG_GREY}'>Enter tickers and adjust weights. "
        f"Analysis uses 1-year daily returns vs SPY benchmark.</p>",
        unsafe_allow_html=True,
    )

    tickers_raw = st.text_input(
        "Portfolio Tickers (comma-separated)",
        value="AAPL,MSFT,GOOGL,AMZN",
        help="e.g. AAPL,MSFT,TSLA,NVDA",
    )

    tickers_list = [t.strip().upper() for t in tickers_raw.split(",") if t.strip()]
    n = len(tickers_list)

    if n == 0:
        st.warning("Please enter at least one ticker.")
        st.stop()

    st.markdown(f"<h3>Weight Allocation ({n} assets)</h3>", unsafe_allow_html=True)

    # Equal weight default
    default_weight = round(1.0 / n, 4)
    weights: List[float] = []

    weight_cols = st.columns(min(n, 4))
    for i, tkr in enumerate(tickers_list):
        col = weight_cols[i % 4]
        w = col.slider(
            tkr,
            min_value=0.0,
            max_value=1.0,
            value=default_weight,
            step=0.01,
            format="%.2f",
            key=f"weight_{tkr}_{i}",
        )
        weights.append(w)

    total_w = sum(weights)
    weight_color = BLOOMBERG_GREEN if abs(total_w - 1.0) < 0.01 else BLOOMBERG_RED
    st.markdown(
        f"<p style='color:{weight_color}; font-weight:bold;'>Total weight: {total_w:.2f} "
        f"{'✓' if abs(total_w - 1.0) < 0.01 else '⚠ Weights must sum to 1.0'}</p>",
        unsafe_allow_html=True,
    )

    if st.button("Run Analysis", disabled=(abs(total_w - 1.0) >= 0.01)):
        weights_str = ",".join(f"{w:.4f}" for w in weights)
        tickers_str = ",".join(tickers_list)

        with st.spinner("Downloading 1-year price history and computing metrics …"):
            result = api_get(
                "/api/portfolio/analyze",
                params={"tickers": tickers_str, "weights": weights_str},
            )

        if result:
            st.markdown(f"<hr style='border-color:{BLOOMBERG_BORDER}'>", unsafe_allow_html=True)
            st.markdown("<h3>Risk / Return Metrics</h3>", unsafe_allow_html=True)

            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.metric("Annualized Return", f"{result['annualized_return_pct']:.2f}%",
                       delta=f"{result['total_return_pct']:.2f}% total")
            mc2.metric("Sharpe Ratio", f"{result['sharpe_ratio']:.3f}",
                       delta="RF = 5.25%")
            mc3.metric("Beta (vs SPY)", f"{result['beta']:.3f}")
            mc4.metric("Volatility (Ann.)", f"{result['volatility_annualized']:.2f}%")

            mc5, mc6, mc7, mc8 = st.columns(4)
            mc5.metric("Max Drawdown", f"-{result['max_drawdown_pct']:.2f}%")
            mc6.metric("VaR 95% (1-day)", f"-{result['var_95_pct']:.2f}%")
            mc7.metric("Benchmark", result["benchmark"])
            mc8.metric("Total Return", f"{result['total_return_pct']:.2f}%")

            st.markdown(f"<hr style='border-color:{BLOOMBERG_BORDER}'>", unsafe_allow_html=True)

            # ── Correlation heatmap ──
            st.markdown("<h3>Correlation Matrix</h3>", unsafe_allow_html=True)
            corr_dict = result["correlation_matrix"]
            corr_df = pd.DataFrame(corr_dict)

            fig_corr = px.imshow(
                corr_df,
                color_continuous_scale=[
                    [0.0, BLOOMBERG_RED],
                    [0.5, BLOOMBERG_SURFACE],
                    [1.0, BLOOMBERG_GREEN],
                ],
                zmin=-1, zmax=1,
                text_auto=".2f",
                title="Pairwise Pearson Correlations",
                aspect="auto",
            )
            fig_corr.update_layout(
                **PLOTLY_TEMPLATE["layout"].to_plotly_json(),
                height=max(300, 80 * len(tickers_list)),
                margin=dict(l=10, r=10, t=50, b=10),
            )
            fig_corr.update_traces(textfont_size=12, textfont_color=BLOOMBERG_WHITE)
            st.plotly_chart(fig_corr, use_container_width=True)

            # ── Cumulative return chart vs SPY ──
            st.markdown("<h3>Portfolio vs SPY — Cumulative Return</h3>", unsafe_allow_html=True)
            with st.spinner("Fetching cumulative return data …"):
                history_payloads: Dict[str, List[float]] = {}
                import yfinance as yf
                all_syms = tickers_list + ["SPY"]
                raw_prices = yf.download(
                    " ".join(all_syms),
                    period="1y", interval="1d",
                    auto_adjust=True, progress=False, group_by="ticker",
                )

                try:
                    if isinstance(raw_prices.columns, pd.MultiIndex):
                        closes = raw_prices.xs("Close", axis=1, level=0)
                        closes.columns = [str(c).upper() for c in closes.columns]
                    else:
                        closes = raw_prices[["Close"]]
                        closes.columns = [tickers_list[0]]

                    daily_rets = closes.pct_change().dropna()
                    port_rets = (daily_rets[tickers_list] * weights).sum(axis=1)
                    cum_port = (1 + port_rets).cumprod() - 1
                    cum_spy = (1 + daily_rets["SPY"]).cumprod() - 1 if "SPY" in daily_rets.columns else None

                    fig_cum = go.Figure()
                    fig_cum.add_trace(go.Scatter(
                        x=cum_port.index, y=(cum_port * 100).round(2),
                        mode="lines", name="Portfolio",
                        line=dict(color=BLOOMBERG_ORANGE, width=2),
                        fill="tozeroy",
                        fillcolor="rgba(255,102,0,0.08)",
                    ))
                    if cum_spy is not None:
                        fig_cum.add_trace(go.Scatter(
                            x=cum_spy.index, y=(cum_spy * 100).round(2),
                            mode="lines", name="SPY",
                            line=dict(color=BLOOMBERG_BLUE, width=1.5, dash="dot"),
                        ))
                    fig_cum.add_hline(y=0, line_dash="dash", line_color=BLOOMBERG_GREY, line_width=1)
                    fig_cum.update_layout(
                        **PLOTLY_TEMPLATE["layout"].to_plotly_json(),
                        height=380,
                        yaxis_title="Cumulative Return (%)",
                        xaxis_title="Date",
                        margin=dict(l=10, r=10, t=20, b=10),
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                    )
                    st.plotly_chart(fig_cum, use_container_width=True)
                except Exception as exc:
                    st.warning(f"Could not render cumulative return chart: {exc}")


# ===========================================================================
# PAGE 5 — STOCK SCREENER
# ===========================================================================

elif page == "Stock Screener":
    st.markdown("<h1>STOCK SCREENER</h1>", unsafe_allow_html=True)
    st.markdown(
        f"<p style='color:{BLOOMBERG_GREY}'>Filters applied to a universe of 50 popular tickers. "
        f"Results cached for 2 minutes.</p>",
        unsafe_allow_html=True,
    )

    # ── Filters ──
    filter_col1, filter_col2, filter_col3 = st.columns(3)

    with filter_col1:
        price_range = st.slider(
            "Price Range (USD)",
            min_value=0, max_value=5000,
            value=(0, 2000), step=10,
            format="$%d",
        )
        min_price, max_price = price_range

    with filter_col2:
        market_cap_options = {
            "Any": 0,
            "Small Cap (>$300M)": 300_000_000,
            "Mid Cap (>$2B)": 2_000_000_000,
            "Large Cap (>$10B)": 10_000_000_000,
            "Mega Cap (>$200B)": 200_000_000_000,
        }
        min_cap_label = st.selectbox("Min Market Cap", list(market_cap_options.keys()), index=0)
        min_market_cap = market_cap_options[min_cap_label]

    with filter_col3:
        sector_options = [
            "all", "Technology", "Healthcare", "Financials", "Consumer Discretionary",
            "Communication Services", "Industrials", "Consumer Staples",
            "Energy", "Utilities", "Materials", "Real Estate",
        ]
        sector = st.selectbox("Sector", sector_options, index=0)

    if st.button("Run Screener"):
        with st.spinner("Scanning universe of 50 tickers …"):
            screener_data = api_get(
                "/api/screener",
                params={
                    "min_price": min_price,
                    "max_price": max_price,
                    "min_market_cap": min_market_cap,
                    "sector": sector,
                },
            )

        if screener_data:
            count = screener_data["count"]
            stocks = screener_data["stocks"]

            st.markdown(
                f"<p style='color:{BLOOMBERG_ORANGE}; font-weight:bold;'>"
                f"Found {count} matching stocks</p>",
                unsafe_allow_html=True,
            )

            if stocks:
                df_screen = pd.DataFrame(stocks)

                # Formatting helpers
                df_screen["market_cap_fmt"] = df_screen["market_cap"].apply(fmt_large_number)
                df_screen["volume_fmt"] = df_screen["volume"].apply(lambda x: fmt_large_number(x))
                df_screen["price_fmt"] = df_screen["price"].apply(lambda x: f"${x:,.2f}")
                df_screen["pe_fmt"] = df_screen["pe_ratio"].apply(
                    lambda x: f"{x:.1f}" if pd.notna(x) and x else "N/A"
                )

                display_df = df_screen[["ticker", "name", "price_fmt", "change_pct",
                                        "market_cap_fmt", "pe_fmt", "volume_fmt", "sector"]].copy()
                display_df.columns = ["Ticker", "Name", "Price", "Change %",
                                       "Market Cap", "P/E", "Volume", "Sector"]

                # Style change_pct column
                def color_change(val: float) -> str:
                    try:
                        v = float(val)
                        color = BLOOMBERG_GREEN if v >= 0 else BLOOMBERG_RED
                        return f"color: {color}; font-weight: bold;"
                    except Exception:
                        return ""

                def row_style(row: pd.Series) -> List[str]:
                    base = f"background-color: {BLOOMBERG_PANEL}; color: {BLOOMBERG_WHITE};"
                    return [base] * len(row)

                styled = (
                    display_df.style
                    .apply(row_style, axis=1)
                    .map(lambda v: color_change(v), subset=["Change %"])
                    .format({"Change %": "{:.2f}%"})
                )

                st.dataframe(styled, use_container_width=True, hide_index=True, height=500)

                # ── Summary bar chart ──
                st.markdown(f"<hr style='border-color:{BLOOMBERG_BORDER}'>", unsafe_allow_html=True)
                st.markdown("<h3>Daily Change % — All Results</h3>", unsafe_allow_html=True)

                bar_colors = [
                    BLOOMBERG_GREEN if v >= 0 else BLOOMBERG_RED
                    for v in df_screen["change_pct"]
                ]
                fig_bar = go.Figure(go.Bar(
                    x=df_screen["ticker"],
                    y=df_screen["change_pct"],
                    marker_color=bar_colors,
                    text=df_screen["change_pct"].apply(lambda x: f"{x:+.2f}%"),
                    textposition="outside",
                    textfont=dict(color=BLOOMBERG_WHITE, size=10),
                ))
                fig_bar.add_hline(y=0, line_color=BLOOMBERG_GREY, line_width=1)
                fig_bar.update_layout(
                    **PLOTLY_TEMPLATE["layout"].to_plotly_json(),
                    height=360,
                    yaxis_title="Daily Change (%)",
                    xaxis_title="Ticker",
                    margin=dict(l=10, r=10, t=20, b=10),
                    showlegend=False,
                )
                st.plotly_chart(fig_bar, use_container_width=True)
            else:
                st.info("No stocks matched the selected filters.")


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.markdown(
    f"""
    <div style="margin-top:40px; padding:12px; border-top: 1px solid {BLOOMBERG_BORDER};
                text-align:center; color:{BLOOMBERG_GREY}; font-size:0.7rem;">
        Bloomberg Terminal Clone &nbsp;·&nbsp; Built by
        <span style="color:{BLOOMBERG_ORANGE}">Hamza Ahmad</span>
        &nbsp;·&nbsp; ETS Montreal &nbsp;·&nbsp;
        Data via yfinance / Yahoo Finance RSS &nbsp;·&nbsp; Sentiment by ProsusAI/FinBERT
    </div>
    """,
    unsafe_allow_html=True,
)
