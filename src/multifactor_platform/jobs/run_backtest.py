import argparse

from multifactor_platform.artifacts import replay_run, save_run
from multifactor_platform.backtesting.engine import run_top_n_backtest
from multifactor_platform.jobs.common import add_source_argument, parse_source, print_json
from multifactor_platform.utils.platform_data import load_platform_data


def run(source: str = 'sample', top_n: int = 10,
        output_dir: str = 'data/processed/research', replay: str | None = None) -> dict:
    if replay:
        result, artifact = replay_run(replay)
        return {'replayed': True, 'artifact': artifact, 'metrics': result['metrics']}
    parsed_source = parse_source(source)
    prices, features, rankings = load_platform_data(parsed_source)
    parameters = {'n': top_n}
    result = run_top_n_backtest(rankings, prices, features=features, **parameters)
    artifact = save_run({'prices': prices, 'features': features, 'rankings': rankings},
                        result, parameters, output_dir)
    return {
        'source': parsed_source, 'strategy': f'top-{top_n}-monthly-equal-weight',
        'periods': len(result['returns']), 'daily_observations': len(result['daily_ledger']),
        'metrics': result['metrics'], 'settings': result['settings'], 'artifact': artifact,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description='Run and archive a daily-accounted monthly strategy.')
    add_source_argument(parser)
    parser.add_argument('--top-n', type=int, default=10)
    parser.add_argument('--output-dir', default='data/processed/research')
    parser.add_argument('--replay-run', help='Path to a saved run bundle; requires matching code/dependencies.')
    args = parser.parse_args()
    print_json(run(args.source, args.top_n, args.output_dir, args.replay_run))


if __name__ == '__main__':
    main()
