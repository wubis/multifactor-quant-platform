"""Content-addressed research inputs and immutable, auditable run bundles.

CSV uses round-trip float parsing and an explicit dtype schema. Loading verifies
hashes; it never executes serialized code. Source copies document the run; replay
requires the current code and numerical dependencies to match the manifest.
"""
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import json
import platform
import shutil
import tempfile

import pandas as pd

from multifactor_platform.research import ResearchDataError


FORMAT_VERSION = 1


def _json(value):
    return json.dumps(value, sort_keys=True, indent=2, allow_nan=False, default=str).encode()


def _digest(data):
    return sha256(data).hexdigest()


def _frame_files(frame):
    frame = frame.copy().reset_index(drop=True)
    data = frame.to_csv(index=False, float_format='%.17g', na_rep='').encode()
    schema = {
        'dtypes': {column: str(dtype) for column, dtype in frame.dtypes.items()},
        'attrs': frame.attrs,
    }
    return data, schema


def _read_frame(data_path, schema):
    if not schema['dtypes']:
        result = pd.DataFrame()
    else:
        dates = [key for key, dtype in schema['dtypes'].items() if dtype.startswith('datetime')]
        types = {key: dtype for key, dtype in schema['dtypes'].items() if key not in dates}
        result = pd.read_csv(data_path, dtype=types, parse_dates=dates,
                             float_precision='round_trip', keep_default_na=False, na_values=[''])
    result.attrs.update(schema['attrs'])
    return result


def _publish(root, identifier, files):
    root.mkdir(parents=True, exist_ok=True)
    destination = root / identifier
    if destination.exists():
        for name, data in files.items():
            if (destination / name).read_bytes() != data:
                raise ResearchDataError(f"Immutable artifact conflict: {destination / name}")
        return destination
    temporary = Path(tempfile.mkdtemp(prefix='.pending-', dir=root))
    try:
        for name, data in files.items():
            path = temporary / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        temporary.rename(destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return destination


def save_dataset(frames, root):
    files, schema = {}, {}
    for name, frame in sorted(frames.items()):
        data, metadata = _frame_files(frame)
        files[f'{name}.csv'] = data
        schema[name] = metadata
    manifest = dict(format_version=FORMAT_VERSION, frames=schema,
                    hashes={name: _digest(data) for name, data in files.items()})
    data = _json(manifest)
    identifier = _digest(data)
    files['manifest.json'] = data
    return _publish(Path(root) / 'datasets', identifier, files)


def _verified_manifest(path):
    path = Path(path)
    data = (path / 'manifest.json').read_bytes()
    manifest = json.loads(data)
    if manifest['format_version'] != FORMAT_VERSION or _digest(data) != path.name:
        raise ResearchDataError("Artifact manifest identity or version mismatch")
    for name, expected in manifest['hashes'].items():
        file = (path / name).resolve()
        if not file.is_relative_to(path.resolve()) or _digest(file.read_bytes()) != expected:
            raise ResearchDataError(f"Artifact checksum mismatch: {name}")
    return manifest


def load_dataset(path):
    path = Path(path)
    manifest = _verified_manifest(path)
    return {name: _read_frame(path / f'{name}.csv', schema)
            for name, schema in manifest['frames'].items()}


def _source_files():
    package = Path(__file__).resolve().parent
    return {f'source/{path.relative_to(package)}': path.read_bytes()
            for path in sorted(package.rglob('*.py'))}


def _environment():
    packages = {}
    for package in ['numpy', 'pandas', 'scipy', 'scikit-learn', 'xgboost', 'lightgbm']:
        try:
            packages[package] = version(package)
        except PackageNotFoundError:
            packages[package] = None
    return dict(python=platform.python_version(), packages=packages)


def save_run(frames, result, parameters, root='data/processed/research'):
    root = Path(root)
    dataset = save_dataset(frames, root)
    files = _source_files()
    tables = {}
    for name, value in result.items():
        if isinstance(value, pd.Series):
            value = value.rename('value').rename_axis('date').reset_index()
        elif isinstance(value, pd.DataFrame) and value.index.name:
            value = value.reset_index()
        if isinstance(value, pd.DataFrame):
            data, schema = _frame_files(value)
            files[f'outputs/{name}.csv'] = data
            tables[name] = schema
    files['summary.json'] = _json({key: result[key] for key in ['metrics', 'settings', 'warnings']})
    manifest = dict(format_version=FORMAT_VERSION, dataset_id=dataset.name,
                    parameters=parameters, environment=_environment(), tables=tables,
                    hashes={name: _digest(data) for name, data in files.items()})
    data = _json(manifest)
    identifier = _digest(data)
    files['manifest.json'] = data
    path = _publish(root / 'runs', identifier, files)
    return {'run_id': identifier, 'dataset_id': dataset.name, 'path': str(path.resolve())}


def replay_run(path):
    from multifactor_platform.backtesting.engine import run_top_n_backtest
    path = Path(path)
    manifest = _verified_manifest(path)
    current_source = {name: _digest(data) for name, data in _source_files().items()}
    recorded_source = {name: value for name, value in manifest['hashes'].items() if name.startswith('source/')}
    if current_source != recorded_source or _environment() != manifest['environment']:
        raise ResearchDataError("Replay requires the recorded source and numerical dependency versions")
    dataset_id = manifest['dataset_id']
    if len(dataset_id) != 64 or any(c not in '0123456789abcdef' for c in dataset_id):
        raise ResearchDataError("Invalid dataset identity")
    frames = load_dataset(path.parent.parent / 'datasets' / dataset_id)
    result = run_top_n_backtest(frames['rankings'], frames['prices'],
                                features=frames.get('features'), **manifest['parameters'])
    # Verify every regenerated table and scalar summary, not just headline returns.
    regenerated = save_run(frames, result, manifest['parameters'], path.parent.parent)
    if regenerated['run_id'] != path.name:
        raise ResearchDataError("Replay output differs from the recorded run")
    return result, regenerated
