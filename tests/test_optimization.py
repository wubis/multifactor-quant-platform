import pandas as pd

from multifactor_platform.optimization.constraints import PortfolioConstraints
from multifactor_platform.optimization.optimizer import optimize_ranked_portfolio


def test_optimizer_respects_position_and_sector_caps():
    ranked = pd.DataFrame(
        {
            "ticker": ["AAA", "BBB", "CCC", "DDD", "EEE"],
            "sector": ["Tech", "Tech", "Health", "Health", "Energy"],
            "rank": [1, 2, 3, 4, 5],
            "composite_score": [5, 4, 3, 2, 1],
        }
    )

    result = optimize_ranked_portfolio(
        ranked,
        constraints=PortfolioConstraints(
            max_position_size=0.2,
            max_sector_exposure=0.3,
            cash_minimum=0.1,
        ),
        candidate_limit=5,
    )

    positions = result["positions"]
    sectors = result["sector_exposure"]

    assert positions["weight"].max() <= 0.2
    assert sectors["weight"].max() <= 0.3
    assert result["cash_weight"] >= 0.1


def test_optimizer_leaves_cash_when_constraints_bind():
    ranked = pd.DataFrame(
        {
            "ticker": ["AAA", "BBB"],
            "sector": ["Tech", "Tech"],
            "rank": [1, 2],
            "composite_score": [2, 1],
        }
    )

    result = optimize_ranked_portfolio(
        ranked,
        constraints=PortfolioConstraints(
            max_position_size=0.1,
            max_sector_exposure=0.15,
            cash_minimum=0.02,
        ),
    )

    assert result["invested_weight"] == 0.15
    assert result["cash_weight"] == 0.85
