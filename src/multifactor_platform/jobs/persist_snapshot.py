import argparse

from multifactor_platform.db.persistence import persist_pipeline_snapshot
from multifactor_platform.jobs.common import (
    add_database_argument,
    add_source_argument,
    parse_source,
    print_json,
)


def run(source: str = "sample", database_url: str | None = None) -> dict:
    parsed_source = parse_source(source)
    return persist_pipeline_snapshot(parsed_source, database_url=database_url)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Persist source data, features, rankings, and backtest summary."
    )
    add_source_argument(parser)
    add_database_argument(parser)
    args = parser.parse_args()
    print_json(run(args.source, args.database_url))


if __name__ == "__main__":
    main()
