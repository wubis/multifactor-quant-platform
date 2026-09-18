"""Download explicit symbols with persistent free-tier budgets and immutable caching."""
import argparse
import json

from multifactor_platform.ingestion.tiingo_client import TiingoClient
from multifactor_platform.research import ResearchDataError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--symbols', nargs='+', required=True)
    parser.add_argument('--start-date', required=True)
    parser.add_argument('--end-date', required=True)
    parser.add_argument('--cache-dir', default='data/external/tiingo')
    parser.add_argument('--usage-db', help='Shared budget ledger for all clients using this account')
    parser.add_argument('--refresh', action='store_true')
    args = parser.parse_args()
    client = TiingoClient(cache_dir=args.cache_dir, usage_db=args.usage_db)
    for symbol in dict.fromkeys(args.symbols):
        try:
            receipt = client.download(symbol, args.start_date, args.end_date, refresh=args.refresh)
        except (ResearchDataError, ValueError) as exc:
            parser.exit(1, f'{symbol}: {exc}\nCompleted responses remain cached.\n')
        print(json.dumps(receipt), flush=True)


if __name__ == '__main__':
    main()
