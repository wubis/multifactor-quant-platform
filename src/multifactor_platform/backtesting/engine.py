import pandas as pd

from multifactor_platform.backtesting.costs import apply_transaction_costs
from multifactor_platform.backtesting.metrics import summarize_returns
from multifactor_platform.backtesting.portfolio import calculate_turnover, equal_weight_top_n


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


def run_top_n_backtest(
    ranked: pd.DataFrame,
    prices: pd.DataFrame,
    n: int = 50,
    cost_bps: float = 5.0,
) -> dict:
    forward_returns = build_forward_returns(prices)
    signal_dates = monthly_signal_dates(ranked)
    portfolio_returns = []
    turnovers = []
    previous_weights: pd.Series | None = None

    for signal_date in signal_dates:
        available = ranked.loc[ranked["date"] <= signal_date]
        if available.empty:
            continue
        actual_signal_date = available["date"].max()
        portfolio = equal_weight_top_n(ranked, actual_signal_date, n=n)
        if portfolio.empty:
            continue

        month_returns = forward_returns.loc[forward_returns["date"] == signal_date]
        portfolio = portfolio.merge(month_returns[["ticker", "forward_1m_return"]], on="ticker", how="left")
        portfolio_return = float((portfolio["weight"] * portfolio["forward_1m_return"].fillna(0)).sum())
        current_weights = portfolio.set_index("ticker")["weight"]
        turnover = calculate_turnover(current_weights, previous_weights)
        previous_weights = current_weights
        portfolio_returns.append((signal_date, portfolio_return))
        turnovers.append((signal_date, turnover))

    returns = pd.Series(dict(portfolio_returns), dtype=float).sort_index()
    turnover_series = pd.Series(dict(turnovers), dtype=float).sort_index()
    net_returns = apply_transaction_costs(returns, turnover_series, cost_bps)
    return {
        "returns": net_returns,
        "turnover": turnover_series,
        "metrics": summarize_returns(net_returns, turnover_series),
    }
