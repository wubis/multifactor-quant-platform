import numpy as np
import pandas as pd

from multifactor_platform.research import ResearchDataError, require_historical_research

from multifactor_platform.backtesting.ledger import simulate_daily_ledger
from multifactor_platform.backtesting.metrics import summarize_returns
from multifactor_platform.backtesting.portfolio import (
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
        if len(market_dates) == 0 or month_end > market_dates[-1]:
            continue
        available_signals = ranked.loc[
            (ranked["date"] <= month_end)
            & (ranked["date"].dt.to_period("M") == month_end.to_period("M"))
        ]
        if available_signals.empty:
            continue

        signal_date = pd.Timestamp(available_signals["date"].max())
        month_market_dates = market_dates[market_dates.to_period("M") == month_end.to_period("M")]
        if len(month_market_dates) and signal_date < month_market_dates[-1]:
            continue  # Do not manufacture a month-end forecast from stale predictions.
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
    evaluation_start=None,
    evaluation_end=None,
    initial_capital: float = 1_000_000,
    cash_fraction: float = 0.0,
    annual_cash_rate: float = 0.0,
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

    if not 0 <= cash_fraction <= 1:
        raise ValueError("cash_fraction must be between zero and one")
    schedule = _build_trade_schedule(ranked, prices, rebalance_delay_days)
    if not schedule:
        raise ResearchDataError("No executable rebalance signals")
    start = pd.Timestamp(evaluation_start) if evaluation_start is not None else schedule[0]['trade_date']
    end = pd.Timestamp(evaluation_end) if evaluation_end is not None else prices.date.max()
    schedule = [event for event in schedule if start <= event['trade_date'] < end]
    if not schedule or schedule[0]['trade_date'] != start:
        raise ResearchDataError("Evaluation must start at an executable rebalance shared by the strategy")
    holdings, targets, sector_exposures, rebalance_log = [], [], [], []
    for i, event in enumerate(schedule):
        signal_date, trade_date = event['signal_date'], event['trade_date']
        constructor = equal_weight_sector_neutral_top_n if construction == 'sector_neutral' else equal_weight_top_n
        portfolio = constructor(ranked, signal_date, n=n)
        if portfolio.empty:
            raise ResearchDataError(f"No eligible holdings on {signal_date}")
        portfolio['weight'] *= 1 - cash_fraction
        target = portfolio.copy()
        target['date'] = trade_date
        targets.append(target)
        # Retain legacy rebalance labels for period charts; exposure joins use signal dates.
        holdings.append(_portfolio_holdings(portfolio, event['rebalance_date']))
        sector_exposures.append(_sector_exposure(portfolio, event['rebalance_date']))
        rebalance_log.append({
            'date': event['rebalance_date'], 'signal_date': signal_date, 'trade_date': trade_date,
            'next_trade_date': schedule[i + 1]['trade_date'] if i + 1 < len(schedule) else end,
            'holdings': len(portfolio),
            'available_universe': ranked.loc[ranked.date == signal_date, 'ticker'].nunique(),
        })
    daily = simulate_daily_ledger(
        prices, pd.concat(targets, ignore_index=True), start, end,
        benchmark_ticker=benchmark_ticker, initial_capital=initial_capital,
        commission_bps=commission_bps, slippage_bps=slippage_bps, annual_cash_rate=annual_cash_rate,
    )
    ledger = daily['daily_ledger']
    returns, benchmarks, turnovers, costs = {}, {}, {}, []
    previous_tickers = set()
    for event, portfolio in zip(rebalance_log, holdings):
        trade_date, next_date, label = event['trade_date'], event['next_trade_date'], event['date']
        before = ledger.loc[trade_date, 'nav_before_trade']
        # Next rebalance costs belong to the next holding period.
        after = ledger.loc[next_date, 'nav_before_trade']
        returns[label] = after / before - 1
        benchmarks[label] = _benchmark_return(prices, trade_date, next_date, benchmark_ticker)
        rebalance = daily['daily_rebalances'].loc[trade_date]
        turnovers[label] = float(rebalance.turnover)
        costs.append({'date': label, **rebalance.to_dict()})
        event['turnover'] = float(rebalance.turnover)
        tickers = set(portfolio.ticker)
        event['changed_positions'] = len(tickers.symmetric_difference(previous_tickers))
        previous_tickers = tickers
    returns = pd.Series(returns, dtype=float).sort_index()
    benchmark = pd.Series(benchmarks, dtype=float).sort_index()
    turnover_series = pd.Series(turnovers, dtype=float).sort_index()
    holdings_frame = pd.concat(holdings, ignore_index=True)
    rebalance_frame = pd.DataFrame(rebalance_log)
    exposure_holdings = holdings_frame.merge(
        rebalance_frame[['date', 'signal_date']], on='date', validate='many_to_one')
    factor_exposure_frame = (
        compute_factor_exposures(exposure_holdings, features) if features is not None
        else pd.DataFrame(columns=['date', 'factor', 'exposure'])
    )
    metrics = summarize_returns(
        ledger.daily_return, turnover_series, ledger.benchmark_return, periods_per_year=252,
        risk_free_returns=ledger.cash_return, elapsed_years=(end - start).days / 365.25,
    )
    return {
        **daily,
        'returns': returns, 'benchmark_returns': benchmark,
        'excess_returns': returns - benchmark, 'turnover': turnover_series,
        'costs': pd.DataFrame(costs).set_index('date'),
        'sector_exposure': pd.concat(sector_exposures, ignore_index=True),
        'factor_exposure': factor_exposure_frame,
        'holdings': holdings_frame, 'rebalance_log': rebalance_frame,
        'metrics': metrics,
        'warnings': _backtest_warnings(returns, turnover_series, holdings_frame, rebalance_frame),
        'settings': {
            'top_n': n, 'construction': construction,
            'commission_bps': commission_bps, 'slippage_bps': slippage_bps,
            'rebalance_delay_days': rebalance_delay_days, 'benchmark_ticker': benchmark_ticker,
            'initial_capital': initial_capital, 'cash_fraction': cash_fraction,
            'annual_cash_rate': annual_cash_rate,
            'evaluation_start': start.date().isoformat(), 'evaluation_end': end.date().isoformat(),
            'risk_sampling': 'daily; 252 observations per year; entry costs included',
            'cagr_clock': 'actual elapsed calendar days / 365.25',
            'cost_convention': 'per dollar bought or sold, funded at rebalance close',
            'turnover_convention': 'half gross traded notional / pre-trade NAV, including entry',
            'price_convention': 'adjusted total-return units, not raw executable shares',
            'terminal_convention': 'mark to market; no forced liquidation or terminal entry',
            'alpha_definition': 'legacy alias of cagr_spread; not risk-adjusted alpha',
            'data_period': prices.attrs.get('period'),
            'data_universe_limit': prices.attrs.get('universe_limit'),
            'price_ticker_count': int(prices.ticker.nunique()),
            'price_start_date': prices.date.min().date().isoformat(),
            'price_end_date': prices.date.max().date().isoformat(),
        },
    }
