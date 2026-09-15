import numpy as np
import pandas as pd


def annualized_return(returns: pd.Series, periods_per_year: int = 12) -> float:
    if returns.empty:
        return 0.0
    cumulative = float((1 + returns).prod())
    years = len(returns) / periods_per_year
    return cumulative ** (1 / years) - 1 if years > 0 else 0.0


def annualized_volatility(returns: pd.Series, periods_per_year: int = 12) -> float:
    return float(returns.std(ddof=0) * np.sqrt(periods_per_year)) if not returns.empty else 0.0


def sharpe_ratio(
    returns: pd.Series, periods_per_year: int = 12, risk_free_return: float = 0.0,
) -> float:
    """Arithmetic excess-return Sharpe; risk_free_return is per observation."""
    excess = returns - risk_free_return
    vol = annualized_volatility(excess, periods_per_year)
    if vol == 0:
        return 0.0
    return float(excess.mean() * periods_per_year / vol)


def max_drawdown(returns: pd.Series) -> float:
    equity = (1 + returns).cumprod()
    drawdown = equity / equity.cummax().clip(lower=1.0) - 1
    return float(drawdown.min()) if not drawdown.empty else 0.0


def tracking_error(excess_returns: pd.Series, periods_per_year: int = 12) -> float:
    return annualized_volatility(excess_returns, periods_per_year)


def information_ratio(excess_returns: pd.Series, periods_per_year: int = 12) -> float:
    error = tracking_error(excess_returns, periods_per_year)
    if error == 0:
        return 0.0
    return float(excess_returns.mean() * periods_per_year / error)


def summarize_returns(
    returns: pd.Series,
    turnovers: pd.Series | None = None,
    benchmark_returns: pd.Series | None = None,
    periods_per_year: int = 12,
    risk_free_returns: pd.Series | None = None,
    elapsed_years: float | None = None,
) -> dict[str, float]:
    if returns.isna().any() or not np.isfinite(returns).all():
        raise ValueError("Returns must be finite and complete")
    cash = risk_free_returns if risk_free_returns is not None else pd.Series(0.0, index=returns.index)
    if not cash.index.equals(returns.index) or cash.isna().any() or not np.isfinite(cash).all():
        raise ValueError("Cash returns must have identical, complete observation dates")

    def cagr(values):
        if elapsed_years is None:
            return annualized_return(values, periods_per_year)
        if elapsed_years <= 0:
            raise ValueError("CAGR requires positive elapsed time")
        return float((1 + values).prod() ** (1 / elapsed_years) - 1)

    ongoing_turnovers = turnovers.iloc[1:] if turnovers is not None and len(turnovers) > 1 else turnovers
    summary = {
        "cagr": cagr(returns),
        "sharpe": sharpe_ratio(returns - cash, periods_per_year),
        "volatility": annualized_volatility(returns, periods_per_year),
        "max_drawdown": max_drawdown(returns),
        "win_rate": float((returns > 0).mean()) if not returns.empty else 0.0,
        "average_turnover": float(turnovers.mean()) if turnovers is not None and not turnovers.empty else 0.0,
        "average_rebalance_turnover": (
            float(ongoing_turnovers.mean())
            if ongoing_turnovers is not None and not ongoing_turnovers.empty
            else 0.0
        ),
    }

    if benchmark_returns is None or benchmark_returns.empty:
        summary.update(
            {
                "benchmark_cagr": 0.0,
                "benchmark_sharpe": 0.0,
                "excess_cagr": 0.0,
                "alpha": 0.0,
                "cagr_spread": 0.0,
                "tracking_error": 0.0,
                "information_ratio": 0.0,
            }
        )
        return summary

    if not returns.index.equals(benchmark_returns.index) or benchmark_returns.isna().any():
        raise ValueError("Strategy and benchmark must have identical, complete observation dates")
    aligned = pd.concat([returns.rename("strategy"), benchmark_returns.rename("benchmark")], axis=1)
    excess = aligned["strategy"] - aligned["benchmark"]
    benchmark_cagr = cagr(aligned["benchmark"])
    strategy_cagr = cagr(aligned["strategy"])
    summary.update(
        {
            "benchmark_cagr": benchmark_cagr,
            "benchmark_sharpe": sharpe_ratio(aligned["benchmark"] - cash, periods_per_year),
            "excess_cagr": cagr(excess),
            "alpha": strategy_cagr - benchmark_cagr,  # Legacy API alias, not regression alpha.
            "cagr_spread": strategy_cagr - benchmark_cagr,
            "tracking_error": tracking_error(excess, periods_per_year),
            "information_ratio": information_ratio(excess, periods_per_year),
        }
    )
    return summary
