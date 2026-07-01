import argparse
import json
from typing import Any

from multifactor_platform.utils.platform_data import DataSource


def add_source_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--source",
        choices=["sample", "yfinance"],
        default="sample",
        help="Data source to run through the pipeline.",
    )


def add_database_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--database-url",
        default=None,
        help="Optional SQLAlchemy database URL. Defaults to configured local SQLite.",
    )


def parse_source(value: str) -> DataSource:
    if value not in {"sample", "yfinance"}:
        raise ValueError(f"Unsupported source: {value}")
    return value  # type: ignore[return-value]


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))
