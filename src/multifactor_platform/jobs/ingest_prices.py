import argparse

from multifactor_platform.data_quality import report_to_dict, validate_price_history
from multifactor_platform.jobs.common import add_source_argument, parse_source, print_json
from multifactor_platform.utils.platform_data import load_platform_data


def run(source: str = "sample") -> dict:
    parsed_source = parse_source(source)
    prices, _, _ = load_platform_data(parsed_source)
    report = validate_price_history(prices, parsed_source)
    return report_to_dict(report)


def main() -> None:
    parser = argparse.ArgumentParser(description="Load price data and run basic quality checks.")
    add_source_argument(parser)
    args = parser.parse_args()
    print_json(run(args.source))


if __name__ == "__main__":
    main()
