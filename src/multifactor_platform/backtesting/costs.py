import pandas as pd


def apply_transaction_costs(returns: pd.Series, turnovers: pd.Series, cost_bps: float) -> pd.Series:
    cost = turnovers.reindex(returns.index).fillna(0) * (cost_bps / 10_000)
    return returns - cost
