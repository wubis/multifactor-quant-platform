import argparse

from multifactor_platform.db.persistence import database_status
from multifactor_platform.jobs.common import add_database_argument, print_json


def run(database_url: str | None = None) -> dict:
    return database_status(database_url=database_url)


def main() -> None:
    parser = argparse.ArgumentParser(description="Show persisted database row counts.")
    add_database_argument(parser)
    args = parser.parse_args()
    print_json(run(args.database_url))


if __name__ == "__main__":
    main()
