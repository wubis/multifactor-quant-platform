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


def optimize_ranked_portfolio(
    ranked: pd.DataFrame,
    constraints: PortfolioConstraints | None = None,
    candidate_limit: int = 50,
    previous_weights: pd.Series | None = None,
) -> dict:
    constraints = constraints or PortfolioConstraints()
    if any(not 0 <= value <= 1 for value in [
        constraints.max_position_size, constraints.min_position_size,
        constraints.max_sector_exposure, constraints.max_turnover, constraints.cash_minimum,
    ]) or constraints.min_position_size > constraints.max_position_size:
        raise ValueError("Invalid portfolio constraints")
    if previous_weights is not None and (
        previous_weights.isna().any() or (previous_weights < 0).any()
        or previous_weights.sum() > 1 + 1e-10 or previous_weights.index.has_duplicates
    ):
        raise ValueError("Previous weights must describe a valid long-only portfolio")
    candidates = ranked.sort_values(["rank", "composite_score"], ascending=[True, False]).head(
        candidate_limit
    )
    target_invested = 1 - constraints.cash_minimum
    remaining = target_invested
    sector_weights: dict[str, float] = {}
    rows = []

    for record in candidates.to_dict(orient="records"):
        if remaining <= 1e-12:
            break

        sector = record.get("sector") or "Unknown"
        current_sector_weight = sector_weights.get(sector, 0.0)
        sector_capacity = max(constraints.max_sector_exposure - current_sector_weight, 0.0)
        weight = min(constraints.max_position_size, sector_capacity, remaining)
        if weight < constraints.min_position_size:
            continue

        sector_weights[sector] = current_sector_weight + weight
        remaining -= weight
        rows.append(
            {
                "ticker": record["ticker"],
                "sector": sector,
                "rank": record["rank"],
                "composite_score": record["composite_score"],
                "weight": weight,
            }
        )

    positions = pd.DataFrame(rows)
    if positions.empty:
        positions = pd.DataFrame(columns=["ticker", "sector", "rank", "composite_score", "weight"])

    current_weights = positions.set_index("ticker")["weight"] if not positions.empty else pd.Series(dtype=float)
    turnover = 0.0
    if previous_weights is not None:
        aligned = pd.concat([current_weights, previous_weights], axis=1).fillna(0)
        aligned.columns = ["current", "previous"]
        turnover = float((aligned["current"] - aligned["previous"]).abs().sum() / 2)

    if previous_weights is not None and turnover > constraints.max_turnover:
        scale = constraints.max_turnover / turnover
        # Move along the trade vector; scaling only new holdings liquidates old ones.
        weights = aligned["previous"] + scale * (aligned["current"] - aligned["previous"])
        weights = weights.loc[weights > 1e-12]
        metadata = ranked.drop_duplicates("ticker").set_index("ticker")
        missing = weights.index.difference(metadata.index)
        if len(missing):
            raise ValueError(f"Metadata required for retained holdings: {missing.tolist()}")
        positions = metadata.loc[weights.index, ["sector", "rank", "composite_score"]].copy()
        positions["weight"] = weights
        positions = positions.rename_axis("ticker").reset_index()
        current_weights = positions.set_index("ticker")["weight"]
        actual = pd.concat([current_weights, previous_weights], axis=1).fillna(0)
        turnover = float((actual.iloc[:, 0] - actual.iloc[:, 1]).abs().sum() / 2)

    # A turnover-limited transition may retain positions that violate new limits.
    # Reject that transition rather than report constraints that were not achieved.
    if not positions.empty:
        positions["sector"] = positions["sector"].fillna("Unknown")
        if (
            (positions["weight"] > constraints.max_position_size + 1e-10).any()
            or (positions["weight"] < constraints.min_position_size - 1e-10).any()
            or (positions.groupby("sector")["weight"].sum() > constraints.max_sector_exposure + 1e-10).any()
            or positions["weight"].sum() > target_invested + 1e-10
        ):
            raise ValueError("Turnover-limited transition violates portfolio constraints")

    invested_weight = float(positions["weight"].sum()) if not positions.empty else 0.0
    cash_weight = max(1 - invested_weight, 0.0)
    sector_exposure = (
        positions.groupby("sector")["weight"].sum().sort_values(ascending=False).reset_index()
        if not positions.empty
        else pd.DataFrame(columns=["sector", "weight"])
    )

    return {
        "positions": positions,
        "warnings": ["Beta target is informational; this allocator does not enforce beta."],
        "sector_exposure": sector_exposure,
        "cash_weight": cash_weight,
        "invested_weight": invested_weight,
        "turnover": turnover,
        "constraints": {
            "max_position_size": constraints.max_position_size,
            "min_position_size": constraints.min_position_size,
            "max_sector_exposure": constraints.max_sector_exposure,
            "max_turnover": constraints.max_turnover,
            "beta_target": constraints.beta_target,
            "cash_minimum": constraints.cash_minimum,
        },
    }
