import argparse

from multifactor_platform.jobs.common import add_source_argument, parse_source, print_json
from multifactor_platform.models.ml import evaluate_models
from multifactor_platform.utils.platform_data import load_platform_data


def run(source: str = "sample") -> dict:
    parsed_source = parse_source(source)
    _, features, _ = load_platform_data(parsed_source)
    results = evaluate_models(features)
    return {
        "source": parsed_source,
        "models": [
            {
                "name": result["name"],
                "engine": result["engine"],
                "status": result["status"],
                "fold_count": len(result["folds"]),
                "feature_count": result["feature_count"],
                **result["metrics"],
            }
            for result in results
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate ranking models with walk-forward validation.")
    add_source_argument(parser)
    args = parser.parse_args()
    print_json(run(args.source))


if __name__ == "__main__":
    main()
