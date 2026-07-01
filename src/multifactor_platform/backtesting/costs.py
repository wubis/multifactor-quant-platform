import pandas as pd


def apply_transaction_costs(returns: pd.Series, turnovers: pd.Series, cost_bps: float) -> pd.Series:
    cost = turnovers.reindex(returns.index).fillna(0) * (cost_bps / 10_000)
    return returns - cost


def estimate_trading_costs(
    turnovers: pd.Series,
    commission_bps: float = 1.0,
    slippage_bps: float = 4.0,
) -> pd.DataFrame:
    aligned_turnover = turnovers.astype(float).copy()
    commission = aligned_turnover * (commission_bps / 10_000)
    slippage = aligned_turnover * (slippage_bps / 10_000)
    return pd.DataFrame(
        {
            "turnover": aligned_turnover,
            "commission_cost": commission,
            "slippage_cost": slippage,
            "total_cost": commission + slippage,
        }
    )
