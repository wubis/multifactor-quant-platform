import pandas as pd

from multifactor_platform.backtesting.costs import estimate_trading_costs
from multifactor_platform.backtesting.metrics import summarize_returns
from multifactor_platform.backtesting.portfolio import (
    calculate_turnover,
    equal_weight_sector_neutral_top_n,
    equal_weight_top_n,
)


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
    month_end["forward_1m_return"] = month_end.groupby("ticker")["month_end_price"].pct_change().shift(-1)
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


def _period_return(
    prices: pd.DataFrame,
    tickers: pd.Series,
    weights: pd.Series,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
) -> float:
    period_prices = prices.loc[
        prices["ticker"].isin(tickers) & prices["date"].isin([start_date, end_date]),
        ["date", "ticker", "adj_close"],
    ]
    pivot = period_prices.pivot(index="ticker", columns="date", values="adj_close")
    if start_date not in pivot.columns or end_date not in pivot.columns:
        return 0.0

    returns = (pivot[end_date] / pivot[start_date] - 1).replace([pd.NA, pd.NaT], 0).fillna(0)
    aligned = pd.concat([weights.rename("weight"), returns.rename("return")], axis=1).fillna(0)
    return float((aligned["weight"] * aligned["return"]).sum())


def _benchmark_return(
    prices: pd.DataFrame,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
    benchmark_ticker: str,
) -> float:
    benchmark_prices = prices.loc[
        (prices["ticker"] == benchmark_ticker) & prices["date"].isin([start_date, end_date]),
        ["date", "adj_close"],
    ].set_index("date")["adj_close"]
    if start_date not in benchmark_prices.index or end_date not in benchmark_prices.index:
        return 0.0
    return float(benchmark_prices.loc[end_date] / benchmark_prices.loc[start_date] - 1)


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
    n: int = 50,
    construction: str = "top_n",
    commission_bps: float = 1.0,
    slippage_bps: float = 4.0,
    cost_bps: float | None = None,
    rebalance_delay_days: int = 1,
    benchmark_ticker: str = "SPY",
) -> dict:
    if cost_bps is not None:
        commission_bps = cost_bps
        slippage_bps = 0.0

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

        gross_return = _period_return(
            prices,
            portfolio["ticker"],
            current_weights,
            trade_date,
            next_trade_date,
        )
        benchmark_return = _benchmark_return(prices, trade_date, next_trade_date, benchmark_ticker)
        trading_cost = turnover * ((commission_bps + slippage_bps) / 10_000)
        net_return = gross_return - trading_cost

        portfolio_returns.append((rebalance_date, net_return))
        benchmark_returns.append((rebalance_date, benchmark_return))
        turnovers.append((rebalance_date, turnover))
        costs.append(
            (
                rebalance_date,
                turnover,
                turnover * (commission_bps / 10_000),
                turnover * (slippage_bps / 10_000),
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
        previous_weights = current_weights

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

    return {
        "returns": returns,
        "benchmark_returns": benchmark,
        "excess_returns": excess_returns,
        "turnover": turnover_series,
        "costs": cost_frame.sort_index(),
        "sector_exposure": sector_frame,
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
        },
    }
