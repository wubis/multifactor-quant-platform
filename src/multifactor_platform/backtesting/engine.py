import numpy as np
import pandas as pd

from multifactor_platform.research import ResearchDataError, require_historical_research

from multifactor_platform.backtesting.costs import estimate_trading_costs
from multifactor_platform.backtesting.metrics import summarize_returns
from multifactor_platform.backtesting.portfolio import (
    calculate_turnover,
    equal_weight_sector_neutral_top_n,
    equal_weight_top_n,
)
from multifactor_platform.risk.exposures import compute_factor_exposures


def monthly_signal_dates(ranked: pd.DataFrame) -> pd.DatetimeIndex:
    dates = pd.to_datetime(ranked["date"].drop_duplicates()).sort_values()
    return pd.DatetimeIndex(dates).to_period("M").to_timestamp("M").drop_duplicates()


def build_forward_returns(prices: pd.DataFrame) -> pd.DataFrame:
    sorted_prices = prices.sort_values(["ticker", "date"]).copy()
    month_end = (
        sorted_prices.set_index("date")
        .groupby("ticker")["adj_close"]
        .resample("ME")
        .last()
        .rename("month_end_price")
        .reset_index()
    )
    month_end["forward_1m_return"] = month_end.groupby("ticker")["month_end_price"].shift(-1) / month_end["month_end_price"] - 1
    return month_end


def _available_market_dates(prices: pd.DataFrame) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(pd.to_datetime(prices["date"].drop_duplicates()).sort_values())


def _first_market_date_on_or_after(market_dates: pd.DatetimeIndex, target_date: pd.Timestamp) -> pd.Timestamp | None:
    candidates = market_dates[market_dates >= target_date]
    return candidates[0] if len(candidates) else None


def _build_trade_schedule(
    ranked: pd.DataFrame,
    prices: pd.DataFrame,
    rebalance_delay_days: int,
) -> list[dict]:
    signal_dates = monthly_signal_dates(ranked)
    market_dates = _available_market_dates(prices)
    schedule = []

    for month_end in signal_dates:
        available_signals = ranked.loc[ranked["date"] <= month_end]
        if available_signals.empty:
            continue

        signal_date = pd.Timestamp(available_signals["date"].max())
        target_trade_date = signal_date + pd.Timedelta(days=rebalance_delay_days)
        trade_date = _first_market_date_on_or_after(market_dates, target_trade_date)
        if trade_date is None:
            continue

        schedule.append(
            {
                "rebalance_date": pd.Timestamp(month_end),
                "signal_date": signal_date,
                "trade_date": trade_date,
            }
        )

    return schedule


def _asset_returns(prices, tickers, start_date, end_date):
    period_prices = prices.loc[
        prices["ticker"].isin(tickers) & prices["date"].isin([start_date, end_date]),
        ["date", "ticker", "adj_close"],
    ]
    pivot = period_prices.pivot(index="ticker", columns="date", values="adj_close")
    pivot = pivot.reindex(index=list(tickers), columns=[start_date, end_date])
    invalid = pivot.isna() | ~np.isfinite(pivot) | (pivot <= 0)
    if invalid.any().any():
        bad = pivot.index[invalid.any(axis=1)].tolist()
        raise ResearchDataError(
            f"Missing or invalid execution prices for {bad} between {start_date} and {end_date}"
        )
    return pivot[end_date] / pivot[start_date] - 1


def _period_return(prices, tickers, weights, start_date, end_date) -> float:
    returns = _asset_returns(prices, tickers, start_date, end_date)
    return float((weights * returns).sum())


def _benchmark_return(prices, start_date, end_date, benchmark_ticker) -> float:
    return float(_asset_returns(prices, [benchmark_ticker], start_date, end_date).iloc[0])


def _sector_exposure(portfolio: pd.DataFrame, rebalance_date: pd.Timestamp) -> pd.DataFrame:
    if "sector" not in portfolio.columns or portfolio.empty:
        return pd.DataFrame(columns=["date", "sector", "weight"])

    exposure = portfolio.groupby("sector", dropna=False)["weight"].sum().reset_index()
    exposure["sector"] = exposure["sector"].fillna("Unknown")
    exposure["date"] = rebalance_date
    return exposure[["date", "sector", "weight"]]


def _portfolio_holdings(portfolio: pd.DataFrame, rebalance_date: pd.Timestamp) -> pd.DataFrame:
    if portfolio.empty:
        return pd.DataFrame(columns=["date", "ticker", "sector", "rank", "weight"])

    holdings = portfolio.copy()
    holdings["date"] = rebalance_date
    for column in ["sector", "rank"]:
        if column not in holdings.columns:
            holdings[column] = None
    return holdings[["date", "ticker", "sector", "rank", "weight"]]


def _backtest_warnings(
    returns: pd.Series,
    turnover: pd.Series,
    holdings: pd.DataFrame,
    rebalance_log: pd.DataFrame,
) -> list[str]:
    warnings = []
    if len(returns) < 12:
        warnings.append(
            f"Backtest has only {len(returns)} monthly observations; treat performance as directional, not conclusive."
        )
    if len(returns) < 36:
        warnings.append(
            "Backtest history is shorter than 36 months, so alpha and Sharpe estimates may be unstable."
        )
    ongoing_turnover = turnover.iloc[1:] if len(turnover) > 1 else turnover
    if not ongoing_turnover.empty and ongoing_turnover.max() == 0:
        warnings.append("Holdings did not change after the initial rebalance.")
    if not holdings.empty:
        holding_counts = holdings.groupby("date")["ticker"].nunique()
        if not holding_counts.empty and holding_counts.min() < 10:
            warnings.append("Some rebalance dates have fewer than 10 holdings.")
    if not rebalance_log.empty and "available_universe" in rebalance_log.columns:
        selected_ratio = rebalance_log["holdings"] / rebalance_log["available_universe"].replace(0, pd.NA)
        if selected_ratio.dropna().median() >= 0.8:
            warnings.append(
                "Strategy selects most of the available universe; use fewer holdings or expand the universe."
            )
    return warnings


def run_top_n_backtest(
    ranked: pd.DataFrame,
    prices: pd.DataFrame,
    features: pd.DataFrame | None = None,
    n: int = 50,
    construction: str = "top_n",
    commission_bps: float = 1.0,
    slippage_bps: float = 4.0,
    cost_bps: float | None = None,
    rebalance_delay_days: int = 1,
    benchmark_ticker: str = "SPY",
) -> dict:
    require_historical_research(ranked)
    require_historical_research(prices)
    if rebalance_delay_days < 1:
        raise ValueError("Close-based signals require a rebalance delay of at least one day")
    if n < 1 or construction not in {"top_n", "sector_neutral"}:
        raise ValueError("Invalid portfolio size or construction")
    if cost_bps is not None:
        commission_bps = cost_bps
        slippage_bps = 0.0

    if commission_bps < 0 or slippage_bps < 0:
        raise ValueError("Trading costs must be nonnegative")

    ranked = ranked.copy()
    prices = prices.copy()
    ranked["date"] = pd.to_datetime(ranked["date"])
    prices["date"] = pd.to_datetime(prices["date"])

    schedule = _build_trade_schedule(ranked, prices, rebalance_delay_days)
    portfolio_returns = []
    benchmark_returns = []
    turnovers = []
    costs = []
    sector_exposures = []
    holdings = []
    rebalance_log = []
    previous_weights: pd.Series | None = None

    for current, following in zip(schedule, schedule[1:]):
        signal_date = current["signal_date"]
        rebalance_date = current["rebalance_date"]
        trade_date = current["trade_date"]
        next_trade_date = following["trade_date"]
        available_universe = ranked.loc[ranked["date"] == signal_date, "ticker"].nunique()

        if construction == "sector_neutral":
            portfolio = equal_weight_sector_neutral_top_n(ranked, signal_date, n=n)
        else:
            portfolio = equal_weight_top_n(ranked, signal_date, n=n)
        if portfolio.empty:
            continue

        current_weights = portfolio.set_index("ticker")["weight"]
        prior_weights = previous_weights
        turnover = calculate_turnover(current_weights, prior_weights)

        asset_returns = _asset_returns(prices, current_weights.index, trade_date, next_trade_date)
        gross_return = float((current_weights * asset_returns).sum())
        benchmark_return = _benchmark_return(prices, trade_date, next_trade_date, benchmark_ticker)
        # Costs are per dollar bought OR sold. Solve for post-cost investable NAV,
        # since target weights apply to that NAV and trading itself consumes cash.
        rate = (commission_bps + slippage_bps) / 10_000
        if rate >= 1:
            raise ValueError("Trading costs must be less than 100% of traded notional")
        prior = prior_weights if prior_weights is not None else pd.Series(dtype=float)
        aligned = pd.concat([current_weights, prior], axis=1).fillna(0)
        aligned.columns = ["target", "prior"]
        low, high = 0.0, 1.0
        for _ in range(60):
            invested = (low + high) / 2
            traded_notional = float((invested * aligned.target - aligned.prior).abs().sum())
            if invested + rate * traded_notional > 1:
                high = invested
            else:
                low = invested
        invested = (low + high) / 2
        traded_notional = float((invested * aligned.target - aligned.prior).abs().sum())
        trading_cost = rate * traded_notional
        net_return = invested * (1 + gross_return) - 1

        portfolio_returns.append((rebalance_date, net_return))
        benchmark_returns.append((rebalance_date, benchmark_return))
        turnovers.append((rebalance_date, turnover))
        costs.append(
            (
                rebalance_date,
                turnover,
                traded_notional * (commission_bps / 10_000),
                traded_notional * (slippage_bps / 10_000),
                trading_cost,
            )
        )
        sector_exposures.append(_sector_exposure(portfolio, rebalance_date))
        holdings.append(_portfolio_holdings(portfolio, rebalance_date))
        rebalance_log.append(
            {
                "date": rebalance_date,
                "signal_date": signal_date,
                "trade_date": trade_date,
                "next_trade_date": next_trade_date,
                "holdings": len(portfolio),
                "available_universe": available_universe,
                "turnover": turnover,
                "changed_positions": (
                    len(
                        set(current_weights.index).symmetric_difference(
                            set(prior_weights.index) if prior_weights is not None else set()
                        )
                    )
                    if prior_weights is not None
                    else len(current_weights)
                ),
            }
        )
        previous_weights = current_weights * (1 + asset_returns) / (1 + gross_return)

    returns = pd.Series(dict(portfolio_returns), dtype=float).sort_index()
    benchmark = pd.Series(dict(benchmark_returns), dtype=float).sort_index()
    turnover_series = pd.Series(dict(turnovers), dtype=float).sort_index()
    cost_frame = pd.DataFrame(
        costs,
        columns=["date", "turnover", "commission_cost", "slippage_cost", "total_cost"],
    ).set_index("date") if costs else estimate_trading_costs(turnover_series, commission_bps, slippage_bps)
    sector_frame = (
        pd.concat(sector_exposures, ignore_index=True)
        if sector_exposures
        else pd.DataFrame(columns=["date", "sector", "weight"])
    )
    holdings_frame = (
        pd.concat(holdings, ignore_index=True)
        if holdings
        else pd.DataFrame(columns=["date", "ticker", "sector", "rank", "weight"])
    )
    rebalance_frame = pd.DataFrame(rebalance_log)
    excess_returns = returns.subtract(benchmark.reindex(returns.index).fillna(0), fill_value=0)
    factor_exposure_frame = (
        compute_factor_exposures(holdings_frame, features)
        if features is not None
        else pd.DataFrame(columns=["date", "factor", "exposure"])
    )

    return {
        "returns": returns,
        "benchmark_returns": benchmark,
        "excess_returns": excess_returns,
        "turnover": turnover_series,
        "costs": cost_frame.sort_index(),
        "sector_exposure": sector_frame,
        "factor_exposure": factor_exposure_frame,
        "holdings": holdings_frame,
        "rebalance_log": rebalance_frame,
        "metrics": summarize_returns(returns, turnover_series, benchmark),
        "warnings": _backtest_warnings(returns, turnover_series, holdings_frame, rebalance_frame),
        "settings": {
            "top_n": n,
            "construction": construction,
            "commission_bps": commission_bps,
            "slippage_bps": slippage_bps,
            "rebalance_delay_days": rebalance_delay_days,
            "benchmark_ticker": benchmark_ticker,
            "cost_convention": "per dollar bought or sold, paid before holding-period returns",
            "risk_free_return_per_period": 0.0,
            "risk_sampling": "monthly; intramonth drawdowns are not measured",
            "alpha_definition": "legacy alias of cagr_spread; not risk-adjusted alpha",
            "data_period": prices.attrs.get("period"),
            "data_universe_limit": prices.attrs.get("universe_limit"),
            "price_ticker_count": int(prices["ticker"].nunique()) if not prices.empty else 0,
            "price_start_date": (
                prices["date"].min().date().isoformat() if not prices.empty else None
            ),
            "price_end_date": (
                prices["date"].max().date().isoformat() if not prices.empty else None
            ),
        },
    }
