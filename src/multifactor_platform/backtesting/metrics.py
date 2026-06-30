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


def summarize_returns(returns: pd.Series, turnovers: pd.Series | None = None) -> dict[str, float]:
    return {
        "cagr": annualized_return(returns),
        "sharpe": sharpe_ratio(returns),
        "volatility": annualized_volatility(returns),
        "max_drawdown": max_drawdown(returns),
        "win_rate": float((returns > 0).mean()) if not returns.empty else 0.0,
        "average_turnover": float(turnovers.mean()) if turnovers is not None and not turnovers.empty else 0.0,
    }
