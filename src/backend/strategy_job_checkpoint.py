"""Atomic job specifications used to replay committed walk-forward decisions."""
import json
import os
from pathlib import Path
import re
import tempfile
from candidate_search import POLICY_VERSION


def _path(request_id):
    if not re.fullmatch(r'backtest_[a-f0-9]{32}', request_id):
        raise ValueError('Invalid backtest request ID')
    root = Path(os.environ.get('ANTIFIER_BACKTEST_CHECKPOINT_DIR', 'logs/strategy_backtest_jobs'))
    root.mkdir(parents=True, exist_ok=True)
    return root / (request_id + '.json')


def save(request_id, settings):
    path = _path(request_id)
    with tempfile.NamedTemporaryFile('w', dir=path.parent, delete=False) as file:
        json.dump({'version': POLICY_VERSION, 'settings': settings}, file)
        temporary = file.name
    os.replace(temporary, path)


def load(request_id):
    path = _path(request_id)
    if not path.exists():
        return None
    value = json.loads(path.read_text())
    if value.get('version') != POLICY_VERSION:
        raise ValueError('Backtest policy version changed; start a new run')
    return value['settings']
