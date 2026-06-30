import pandas as pd

from multifactor_platform.optimization.constraints import PortfolioConstraints


def cap_and_rescale_weights(
    candidates: pd.DataFrame,
    constraints: PortfolioConstraints | None = None,
) -> pd.DataFrame:
    constraints = constraints or PortfolioConstraints()
    output = candidates.copy()
    output["weight"] = output["weight"].clip(
        lower=constraints.min_position_size,
        upper=constraints.max_position_size,
    )
    investable_weight = 1 - constraints.cash_minimum
    weight_sum = output["weight"].sum()
    if weight_sum > 0:
        output["weight"] = output["weight"] / weight_sum * investable_weight
    return output
