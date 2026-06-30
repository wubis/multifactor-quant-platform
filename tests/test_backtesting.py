import pandas as pd

from multifactor_platform.backtesting.portfolio import calculate_turnover, equal_weight_top_n


def test_portfolio_weights_sum_to_one():
    ranked = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-31"] * 3),
            "ticker": ["AAA", "BBB", "CCC"],
            "rank": [1, 2, 3],
        }
    )

    portfolio = equal_weight_top_n(ranked, "2024-01-31", n=2)

    assert portfolio["weight"].sum() == 1
    assert portfolio["ticker"].tolist() == ["AAA", "BBB"]


def test_turnover_between_rebalances():
    current = pd.Series({"AAA": 0.5, "BBB": 0.5})
    previous = pd.Series({"AAA": 1.0})

    assert calculate_turnover(current, previous) == 0.5
