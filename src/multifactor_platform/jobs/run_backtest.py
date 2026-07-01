import argparse

from multifactor_platform.backtesting.engine import run_top_n_backtest
from multifactor_platform.jobs.common import add_source_argument, parse_source, print_json
from multifactor_platform.utils.platform_data import load_platform_data


def run(source: str = "sample", top_n: int = 10) -> dict:
    parsed_source = parse_source(source)
    prices, _, rankings = load_platform_data(parsed_source)
    result = run_top_n_backtest(rankings, prices, n=top_n)
    return {
        "source": parsed_source,
        "strategy": f"top-{top_n}-monthly-equal-weight",
        "periods": len(result["returns"]),
        "metrics": result["metrics"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the monthly top-N backtest.")
    add_source_argument(parser)
    parser.add_argument("--top-n", type=int, default=10, help="Number of ranked stocks to hold.")
    args = parser.parse_args()
    print_json(run(args.source, args.top_n))


if __name__ == "__main__":
    main()
