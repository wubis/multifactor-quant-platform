import argparse

from multifactor_platform.jobs.common import add_source_argument, parse_source, print_json
from multifactor_platform.utils.platform_data import load_platform_data


def run(source: str = "sample") -> dict:
    parsed_source = parse_source(source)
    _, features, rankings = load_platform_data(parsed_source)
    latest_date = features["date"].max()
    latest_rankings = rankings.loc[rankings["date"] == latest_date]
    return {
        "source": parsed_source,
        "feature_rows": len(features),
        "ranking_rows": len(rankings),
        "latest_date": latest_date.date().isoformat(),
        "latest_ranked_stocks": int(latest_rankings["ticker"].nunique()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute features and rankings for a source.")
    add_source_argument(parser)
    args = parser.parse_args()
    print_json(run(args.source))


if __name__ == "__main__":
    main()
