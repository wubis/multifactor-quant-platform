"""Close-to-close total-return simulation with explicit cash and trading entries.

Units reference adjusted prices, not executable raw shares. Dividends and splits
are incorporated by the input total-return series; no second cash dividend is paid.
"""
import numpy as np
import pandas as pd

from multifactor_platform.research import ResearchDataError


def simulate_daily_ledger(
    prices: pd.DataFrame,
    targets: pd.DataFrame,
    start_date,
    end_date,
    benchmark_ticker: str = "SPY",
    initial_capital: float = 1_000_000,
    commission_bps: float = 1,
    slippage_bps: float = 4,
    annual_cash_rate: float = 0,
) -> dict:
    if not np.isfinite([initial_capital, commission_bps, slippage_bps, annual_cash_rate]).all():
        raise ValueError("Ledger parameters must be finite")
    if initial_capital <= 0 or min(commission_bps, slippage_bps) < 0 or annual_cash_rate <= -1:
        raise ValueError("Invalid capital, costs, or cash rate")
    fee_rate = (commission_bps + slippage_bps) / 10_000
    if fee_rate >= 1:
        raise ValueError("Trading cost rate must be less than one")
    prices = prices.copy()
    prices['date'] = pd.to_datetime(prices.date)
    if prices.duplicated(['date', 'ticker']).any():
        raise ResearchDataError("Duplicate daily prices")
    matrix = prices.pivot(index='date', columns='ticker', values='adj_close').sort_index()
    if benchmark_ticker not in matrix:
        raise ResearchDataError("Benchmark calendar is unavailable")
    # All observed dates in the simulation must have an actual benchmark mark.
    dates = matrix.loc[pd.Timestamp(start_date):pd.Timestamp(end_date)].index
    if len(dates) < 2 or dates[0] != pd.Timestamp(start_date) or dates[-1] != pd.Timestamp(end_date):
        raise ResearchDataError("Evaluation needs at least two observed dates and exact endpoints")
    benchmark = matrix.loc[dates, benchmark_ticker]
    if (~np.isfinite(benchmark) | (benchmark <= 0)).any():
        raise ResearchDataError("Missing or invalid daily benchmark prices")
    targets = targets.copy()
    targets['date'] = pd.to_datetime(targets.date)
    if not targets.date.isin(dates).all() or targets.duplicated(['date', 'ticker']).any():
        raise ResearchDataError("Targets must have unique tickers on observed evaluation dates")
    if targets.date.eq(dates[-1]).any():
        raise ValueError("Do not open positions at the terminal valuation")
    if (~np.isfinite(targets.weight) | (targets.weight < 0)).any():
        raise ValueError("Target weights must be finite and nonnegative")
    if (targets.groupby('date').weight.sum() > 1 + 1e-12).any():
        raise ValueError("Target weights exceed available capital")
    by_date = {date: frame.set_index('ticker') for date, frame in targets.groupby('date')}
    units = pd.Series(dtype=float)
    cash = previous_nav = float(initial_capital)
    previous_values = pd.Series(dtype=float)
    previous_date = dates[0]
    ledger, holdings, trades, rebalances = [], [], [], []
    for date in dates:
        target = by_date.get(date)
        required = units.index.union(target.index if target is not None else [])
        marks = matrix.loc[date].reindex(required)
        if (~np.isfinite(marks) | (marks <= 0)).any():
            bad = marks.index[(~np.isfinite(marks) | (marks <= 0))].tolist()
            raise ResearchDataError(f"Missing or invalid daily prices on {date.date()}: {bad}")
        values = units * marks.reindex(units.index)
        market_pnl = float(values.sum() - previous_values.sum())
        cash_return = (1 + annual_cash_rate) ** ((date - previous_date).days / 365.25) - 1
        interest = cash * cash_return
        cash += interest
        pre_nav = cash + float(values.sum())
        commission = slippage = traded_notional = 0.0
        if target is not None:
            weights = target.weight.reindex(required).fillna(0)
            prior_values = values.reindex(required).fillna(0)
            lo, hi = 0.0, pre_nav
            for _ in range(60):
                post_nav = (lo + hi) / 2
                notional = float((weights * post_nav - prior_values).abs().sum())
                if post_nav + fee_rate * notional > pre_nav:
                    hi = post_nav
                else:
                    lo = post_nav
            post_nav = (lo + hi) / 2
            delta = weights * post_nav - prior_values
            traded_notional = float(delta.abs().sum())
            commission = traded_notional * commission_bps / 10_000
            slippage = traded_notional * slippage_bps / 10_000
            cash -= float(delta.sum()) + commission + slippage
            values = (weights * post_nav).loc[lambda v: v > 0]
            units = values / marks.reindex(values.index)
            for ticker, notional in delta.items():
                if abs(notional) > 1e-10:
                    trades.append(dict(date=date, ticker=ticker, adjusted_price=marks[ticker],
                                       adjusted_units=notional / marks[ticker], notional=notional,
                                       commission=abs(notional) * commission_bps / 10_000,
                                       slippage=abs(notional) * slippage_bps / 10_000))
            rebalances.append(dict(date=date, nav_before_trade=pre_nav, traded_notional=traded_notional,
                                   turnover=traded_notional / pre_nav / 2,
                                   commission_cost=commission / pre_nav,
                                   slippage_cost=slippage / pre_nav,
                                   total_cost=(commission + slippage) / pre_nav))
        nav = cash + float(values.sum())
        if cash < -1e-7 or not np.isclose(nav, previous_nav + market_pnl + interest - commission - slippage,
                                        rtol=1e-12, atol=1e-7):
            raise ArithmeticError("Cash / NAV ledger does not reconcile")
        ledger.append(dict(date=date, opening_nav=previous_nav, market_pnl=market_pnl,
                           cash_interest=interest, nav_before_trade=pre_nav, commission=commission,
                           slippage=slippage, traded_notional=traded_notional, cash=cash,
                           positions_value=float(values.sum()), nav=nav,
                           daily_return=nav / previous_nav - 1, cash_return=cash_return,
                           benchmark_return=0.0 if date == dates[0] else
                           float(benchmark.loc[date] / benchmark.loc[previous_date] - 1)))
        for ticker, value in values.items():
            holdings.append(dict(date=date, ticker=ticker, adjusted_units=units[ticker],
                                 adjusted_price=marks[ticker], market_value=value, weight=value / nav))
        previous_values, previous_nav, previous_date = values.copy(), nav, date
    return {
        'daily_ledger': pd.DataFrame(ledger).set_index('date'),
        'daily_holdings': pd.DataFrame(holdings, columns=[
            'date', 'ticker', 'adjusted_units', 'adjusted_price', 'market_value', 'weight']),
        'trades': pd.DataFrame(trades, columns=[
            'date', 'ticker', 'adjusted_price', 'adjusted_units', 'notional', 'commission', 'slippage']),
        'daily_rebalances': pd.DataFrame(rebalances).set_index('date') if rebalances else
            pd.DataFrame(columns=['nav_before_trade', 'traded_notional', 'turnover',
                                  'commission_cost', 'slippage_cost', 'total_cost']),
    }
