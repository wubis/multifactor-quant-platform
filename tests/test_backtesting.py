import pandas as pd

from multifactor_platform.backtesting.engine import run_top_n_backtest
from multifactor_platform.backtesting.portfolio import (
    calculate_turnover,
    equal_weight_sector_neutral_top_n,
    equal_weight_top_n,
)


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


def test_sector_neutral_portfolio_spreads_holdings_across_sectors():
    ranked = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-31"] * 6),
            "ticker": ["A1", "A2", "A3", "B1", "B2", "C1"],
            "sector": ["Tech", "Tech", "Tech", "Health", "Health", "Energy"],
            "rank": [1, 2, 3, 4, 5, 6],
        }
    )

    portfolio = equal_weight_sector_neutral_top_n(ranked, "2024-01-31", n=3)

    assert portfolio["weight"].sum() == 1
    assert set(portfolio["sector"]) == {"Energy", "Health", "Tech"}


def test_backtest_uses_rebalance_delay_and_reports_benchmark_risk_series():
    ranked = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-31", "2024-01-31", "2024-02-29", "2024-02-29", "2024-03-29", "2024-03-29"]),
            "ticker": ["AAA", "BBB", "AAA", "BBB", "AAA", "BBB"],
            "sector": ["Tech", "Health", "Tech", "Health", "Tech", "Health"],
            "rank": [1, 2, 2, 1, 1, 2],
        }
    )
    prices = pd.DataFrame(
        {
            "date": pd.to_datetime(
                [
                    "2024-02-01", "2024-03-01", "2024-04-01",
                    "2024-02-01", "2024-03-01", "2024-04-01",
                    "2024-02-01", "2024-03-01", "2024-04-01",
                ]
            ),
            "ticker": ["AAA", "AAA", "AAA", "BBB", "BBB", "BBB", "SPY", "SPY", "SPY"],
            "adj_close": [100, 110, 99, 100, 90, 99, 100, 105, 110],
        }
    )

    result = run_top_n_backtest(
        ranked,
        prices,
        n=1,
        commission_bps=1,
        slippage_bps=4,
        rebalance_delay_days=1,
    )

    assert len(result["returns"]) == 2
    assert result["rebalance_log"]["signal_date"].dt.strftime("%Y-%m-%d").tolist()[0] == "2024-01-31"
    assert result["rebalance_log"]["trade_date"].dt.strftime("%Y-%m-%d").tolist()[0] == "2024-02-01"
    assert "benchmark_cagr" in result["metrics"]
    assert "information_ratio" in result["metrics"]
    assert not result["benchmark_returns"].empty
    assert not result["excess_returns"].empty
    assert not result["costs"].empty
    assert result["costs"]["slippage_cost"].iloc[0] > result["costs"]["commission_cost"].iloc[0]
    assert set(result["sector_exposure"]["sector"]) == {"Tech", "Health"}
