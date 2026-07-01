import numpy as np
import pandas as pd


def annualized_return(returns: pd.Series, periods_per_year: int = 12) -> float:
    if returns.empty:
        return 0.0
    cumulative = float((1 + returns).prod())
    years = len(returns) / periods_per_year
    return cumulative ** (1 / years) - 1 if years > 0 else 0.0


def annualized_volatility(returns: pd.Series, periods_per_year: int = 12) -> float:
    return float(returns.std(ddof=0) * np.sqrt(periods_per_year))


def sharpe_ratio(returns: pd.Series, periods_per_year: int = 12) -> float:
    vol = annualized_volatility(returns, periods_per_year)
    if vol == 0:
        return 0.0
    return float(annualized_return(returns, periods_per_year) / vol)


def max_drawdown(returns: pd.Series) -> float:
    equity = (1 + returns).cumprod()
    drawdown = equity / equity.cummax() - 1
    return float(drawdown.min()) if not drawdown.empty else 0.0


def tracking_error(excess_returns: pd.Series, periods_per_year: int = 12) -> float:
    return float(excess_returns.std(ddof=0) * np.sqrt(periods_per_year))


def information_ratio(excess_returns: pd.Series, periods_per_year: int = 12) -> float:
    error = tracking_error(excess_returns, periods_per_year)
    if error == 0:
        return 0.0
    return float(annualized_return(excess_returns, periods_per_year) / error)


def summarize_returns(
    returns: pd.Series,
    turnovers: pd.Series | None = None,
    benchmark_returns: pd.Series | None = None,
) -> dict[str, float]:
    ongoing_turnovers = turnovers.iloc[1:] if turnovers is not None and len(turnovers) > 1 else turnovers
    summary = {
        "cagr": annualized_return(returns),
        "sharpe": sharpe_ratio(returns),
        "volatility": annualized_volatility(returns),
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
                "tracking_error": 0.0,
                "information_ratio": 0.0,
            }
        )
        return summary

    aligned = pd.concat([returns.rename("strategy"), benchmark_returns.rename("benchmark")], axis=1).fillna(0)
    excess = aligned["strategy"] - aligned["benchmark"]
    benchmark_cagr = annualized_return(aligned["benchmark"])
    strategy_cagr = annualized_return(aligned["strategy"])
    summary.update(
        {
            "benchmark_cagr": benchmark_cagr,
            "benchmark_sharpe": sharpe_ratio(aligned["benchmark"]),
            "excess_cagr": annualized_return(excess),
            "alpha": strategy_cagr - benchmark_cagr,
            "tracking_error": tracking_error(excess),
            "information_ratio": information_ratio(excess),
        }
    )
    return summary
