"""Convert explicit SimFin quarterly exports, retaining source evidence."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import tempfile

import pandas as pd

from multifactor_platform.ingestion.simfin_statements import convert_simfin_quarterly


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['income', 'balance', 'cashflow', 'crosswalk', 'retrieved-at', 'output']:
        parser.add_argument(f'--{name}', required=True)
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        parser.error('Output directory already exists; use a new vintage directory')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as temporary:
        staging = Path(temporary) / 'bundle'
        raw = staging / 'raw'
        raw.mkdir(parents=True)
        frames, sources = {}, {}
        for name in ['income', 'balance', 'cashflow', 'crosswalk']:
            original = Path(getattr(args, name))
            copy = raw / f'{name}.csv'
            shutil.copyfile(original, copy)
            sources[name] = {'filename': copy.name, 'sha256': sha256(copy.read_bytes()).hexdigest()}
            frames[name] = pd.read_csv(copy, sep=',' if name == 'crosswalk' else ';',
                                       dtype={'SimFinId': str})
        result = convert_simfin_quarterly(**frames, retrieved_at=args.retrieved_at)
        for name in ['fundamentals', 'provenance']:
            result[name].to_csv(staging / f'{name}.csv', index=False)
        report = {**result['report'], 'raw_sources': sources}
        (staging / 'conversion_report.json').write_text(json.dumps(report, indent=2) + '\n')
        staging.rename(output)
    print(json.dumps({'path': str(output.resolve()), **report}, indent=2))


if __name__ == '__main__':
    main()
