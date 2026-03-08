# Built by Hamzy - ETS Montreal
# Portfolio analytics service: Sharpe, Beta, VaR, Max Drawdown, Correlation

from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf
from loguru import logger

from app.models.schemas import PortfolioMetrics

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RISK_FREE_RATE_ANNUAL: float = 0.0525   # 5.25 % annualised (Fed Funds proxy)
TRADING_DAYS_PER_YEAR: int = 252
BENCHMARK_TICKER: str = "SPY"
HISTORY_PERIOD: str = "1y"
HISTORY_INTERVAL: str = "1d"
VAR_CONFIDENCE: float = 0.95


# ---------------------------------------------------------------------------
# AnalyticsService
# ---------------------------------------------------------------------------

class AnalyticsService:
    """
    Computes risk/return metrics for an arbitrary multi-asset portfolio.

    All maths are done with pure pandas / numpy — no QuantLib or similar.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def calculate_portfolio_metrics(
        self,
        tickers: List[str],
        weights: List[float],
    ) -> PortfolioMetrics:
        """
        Download 1-year daily close prices for *tickers* + SPY benchmark,
        then compute the full set of portfolio metrics.

        Parameters
        ----------
        tickers : list of ticker strings (upper-cased internally)
        weights : corresponding portfolio weights (must sum to 1.0)

        Returns
        -------
        PortfolioMetrics pydantic model
        """
        if len(tickers) != len(weights):
            raise ValueError("tickers and weights must have the same length")

        weight_sum = sum(weights)
        if abs(weight_sum - 1.0) > 0.01:
            raise ValueError(f"Weights must sum to 1.0, got {weight_sum:.4f}")

        tickers_upper = [t.upper().strip() for t in tickers]
        weights_arr = np.array(weights, dtype=float)

        logger.info(
            "Calculating portfolio metrics for tickers={} weights={}",
            tickers_upper, list(weights_arr),
        )
        start = time.perf_counter()

        # ----------------------------------------------------------------
        # 1. Download price data
        # ----------------------------------------------------------------
        all_tickers = list(dict.fromkeys(tickers_upper + [BENCHMARK_TICKER]))
        prices_raw = yf.download(
            " ".join(all_tickers),
            period=HISTORY_PERIOD,
            interval=HISTORY_INTERVAL,
            auto_adjust=True,
            progress=False,
            group_by="ticker",
        )

        prices = self._extract_close_prices(prices_raw, all_tickers)

        # Drop rows where ANY portfolio ticker is NaN (keep benchmark for beta)
        portfolio_cols = [t for t in tickers_upper if t in prices.columns]
        prices = prices.dropna(subset=portfolio_cols)

        if prices.empty or len(prices) < 10:
            raise ValueError("Insufficient price history to compute metrics (need >= 10 trading days).")

        logger.debug("Price matrix shape after cleaning: {}", prices.shape)

        # ----------------------------------------------------------------
        # 2. Daily returns
        # ----------------------------------------------------------------
        returns: pd.DataFrame = prices.pct_change().dropna()

        portfolio_returns: pd.Series = (returns[tickers_upper] * weights_arr).sum(axis=1)
        benchmark_returns: Optional[pd.Series] = (
            returns[BENCHMARK_TICKER] if BENCHMARK_TICKER in returns.columns else None
        )

        # ----------------------------------------------------------------
        # 3. Total & annualised return
        # ----------------------------------------------------------------
        total_return_pct = self._total_return(portfolio_returns)
        annualized_return_pct = self._annualized_return(portfolio_returns)

        # ----------------------------------------------------------------
        # 4. Annualised volatility
        # ----------------------------------------------------------------
        volatility_annualized = self._annualized_volatility(portfolio_returns)

        # ----------------------------------------------------------------
        # 5. Sharpe ratio
        # ----------------------------------------------------------------
        sharpe = self._sharpe_ratio(annualized_return_pct, volatility_annualized)

        # ----------------------------------------------------------------
        # 6. Beta vs SPY
        # ----------------------------------------------------------------
        beta = self._beta(portfolio_returns, benchmark_returns)

        # ----------------------------------------------------------------
        # 7. Max drawdown
        # ----------------------------------------------------------------
        max_drawdown_pct = self._max_drawdown(portfolio_returns)

        # ----------------------------------------------------------------
        # 8. VaR 95 % (historical simulation)
        # ----------------------------------------------------------------
        var_95_pct = self._var_historical(portfolio_returns, VAR_CONFIDENCE)

        # ----------------------------------------------------------------
        # 9. Correlation matrix between individual tickers
        # ----------------------------------------------------------------
        corr_matrix = self._correlation_matrix(returns[tickers_upper])

        elapsed = round(time.perf_counter() - start, 2)
        logger.success(
            "Portfolio metrics computed in {}s — sharpe={:.3f} beta={:.3f} "
            "maxDD={:.2f}% VaR={:.2f}% vol={:.2f}%",
            elapsed, sharpe, beta, max_drawdown_pct, var_95_pct, volatility_annualized,
        )

        return PortfolioMetrics(
            tickers=tickers_upper,
            weights=list(weights_arr),
            total_return_pct=total_return_pct,
            annualized_return_pct=annualized_return_pct,
            sharpe_ratio=sharpe,
            beta=beta,
            max_drawdown_pct=max_drawdown_pct,
            var_95_pct=var_95_pct,
            volatility_annualized=volatility_annualized,
            correlation_matrix=corr_matrix,
            benchmark=BENCHMARK_TICKER,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_close_prices(
        raw: pd.DataFrame,
        tickers: List[str],
    ) -> pd.DataFrame:
        """
        Normalise the yfinance download output into a plain DataFrame of
        close prices with tickers as columns.

        yfinance >= 0.2.x returns a MultiIndex (Price, Ticker) for multi-ticker
        downloads; older versions return (Ticker, Price).  We handle both.
        """
        if raw.empty:
            return pd.DataFrame()

        # Single ticker: flat columns
        if not isinstance(raw.columns, pd.MultiIndex):
            return raw[["Close"]].rename(columns={"Close": tickers[0]})

        # MultiIndex — figure out which level is the price field
        levels = [list(raw.columns.get_level_values(i)) for i in range(raw.columns.nlevels)]
        price_level = next(
            (i for i, lvl in enumerate(levels) if "Close" in lvl), 0
        )
        ticker_level = 1 - price_level  # the other level

        # Swap levels so we always have (Price, Ticker)
        if price_level != 0:
            raw.columns = raw.columns.swaplevel(0, 1)

        try:
            closes = raw["Close"]
        except KeyError:
            closes = raw.xs("Close", axis=1, level=0)

        if isinstance(closes, pd.Series):
            closes = closes.to_frame(name=tickers[0])

        # Ensure column names are upper-case strings
        closes.columns = [str(c).upper() for c in closes.columns]
        return closes

    @staticmethod
    def _total_return(returns: pd.Series) -> float:
        """Cumulative total return as a percentage."""
        total = (1 + returns).prod() - 1
        return round(float(total) * 100, 4)

    @staticmethod
    def _annualized_return(returns: pd.Series) -> float:
        """Annualised return using the geometric mean formula."""
        n = len(returns)
        if n < 2:
            return 0.0
        cumulative = (1 + returns).prod()
        years = n / TRADING_DAYS_PER_YEAR
        ann = cumulative ** (1.0 / years) - 1
        return round(float(ann) * 100, 4)

    @staticmethod
    def _annualized_volatility(returns: pd.Series) -> float:
        """Annualised volatility (std dev of daily returns × √252) as a percentage."""
        vol = returns.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR)
        return round(float(vol) * 100, 4)

    @staticmethod
    def _sharpe_ratio(annualized_return_pct: float, volatility_annualized: float) -> float:
        """Sharpe ratio = (annualised return − risk-free rate) / annualised volatility."""
        if volatility_annualized == 0:
            return 0.0
        rf_pct = RISK_FREE_RATE_ANNUAL * 100
        sharpe = (annualized_return_pct - rf_pct) / volatility_annualized
        return round(float(sharpe), 4)

    @staticmethod
    def _beta(
        portfolio_returns: pd.Series,
        benchmark_returns: Optional[pd.Series],
    ) -> float:
        """
        Portfolio beta vs benchmark using OLS formula:
        β = Cov(portfolio, benchmark) / Var(benchmark)
        """
        if benchmark_returns is None or benchmark_returns.empty:
            logger.warning("Benchmark returns unavailable; defaulting beta to 1.0")
            return 1.0

        # Align on common index
        combined = pd.concat(
            [portfolio_returns, benchmark_returns], axis=1, join="inner"
        ).dropna()
        combined.columns = ["portfolio", "benchmark"]

        if len(combined) < 5:
            return 1.0

        cov_matrix = np.cov(combined["portfolio"], combined["benchmark"])
        beta = cov_matrix[0, 1] / cov_matrix[1, 1]
        return round(float(beta), 4)

    @staticmethod
    def _max_drawdown(returns: pd.Series) -> float:
        """
        Maximum drawdown = largest peak-to-trough decline in cumulative returns.
        Returned as a positive percentage (e.g. 25.3 means −25.3 % drawdown).
        """
        cumulative = (1 + returns).cumprod()
        running_max = cumulative.cummax()
        drawdown = (cumulative - running_max) / running_max
        max_dd = drawdown.min()  # most negative value
        return round(abs(float(max_dd)) * 100, 4)

    @staticmethod
    def _var_historical(returns: pd.Series, confidence: float = 0.95) -> float:
        """
        Historical simulation VaR at *confidence* level.
        Returns the loss (positive number) at the (1-confidence) quantile.
        E.g. VaR 95% = 2.5 means there is a 5% chance of losing more than 2.5% in a day.
        """
        quantile = np.percentile(returns, (1 - confidence) * 100)
        return round(abs(float(quantile)) * 100, 4)

    @staticmethod
    def _correlation_matrix(returns: pd.DataFrame) -> Dict[str, Dict[str, float]]:
        """
        Compute pairwise Pearson correlation matrix between ticker returns.
        Returns a nested dict: {ticker: {ticker: corr_value}}.
        """
        corr = returns.corr()
        result: Dict[str, Dict[str, float]] = {}
        for ticker in corr.index:
            result[str(ticker)] = {
                str(col): round(float(corr.loc[ticker, col]), 4)
                for col in corr.columns
            }
        return result
