import sys
from pathlib import Path

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from universe_manifest import (  # noqa: E402
    manifest_tickers_during,
    normalize_universe_manifest,
    snapshots_to_membership_events,
    universe_manifest_digest,
    universe_snapshot,
    validate_universe_provenance,
)


def _manifest():
    return pd.DataFrame(
        [
            {"effective_date": "2020-01-01", "ticker": "AAA", "in_universe": True},
            {"effective_date": "2020-01-01", "ticker": "BBB", "in_universe": True},
            {"effective_date": "2020-06-01", "ticker": "BBB", "in_universe": False},
            {"effective_date": "2020-06-01", "ticker": "CCC", "in_universe": True},
            {"effective_date": "2021-01-01", "ticker": "DDD", "in_universe": True},
        ]
    )


def test_universe_snapshot_never_uses_future_membership_events():
    manifest = _manifest()

    assert universe_snapshot(manifest, "2019-12-31") == []
    assert universe_snapshot(manifest, "2020-05-31") == ["AAA", "BBB"]
    assert universe_snapshot(manifest, "2020-06-01") == ["AAA", "CCC"]


def test_manifest_interval_returns_assets_active_at_any_time():
    assert manifest_tickers_during(
        _manifest(),
        "2020-05-01",
        "2020-12-31",
    ) == ["AAA", "BBB", "CCC"]


def test_snapshots_to_membership_events_reconstructs_each_snapshot():
    snapshots = pd.DataFrame([
        {"effective_date": "2020-01-01", "ticker": "AAA"},
        {"effective_date": "2020-01-01", "ticker": "BBB"},
        {"effective_date": "2021-01-01", "ticker": "BBB"},
        {"effective_date": "2021-01-01", "ticker": "CCC"},
    ])

    events = snapshots_to_membership_events(snapshots)

    assert universe_snapshot(events, "2020-06-01") == ["AAA", "BBB"]
    assert universe_snapshot(events, "2021-06-01") == ["BBB", "CCC"]
    assert len(events) == 4


def test_manifest_normalization_rejects_duplicate_events():
    duplicate = pd.concat([_manifest(), _manifest().iloc[[0]]], ignore_index=True)

    with pytest.raises(ValueError, match="duplicate"):
        normalize_universe_manifest(duplicate)


def test_manifest_digest_is_stable_under_input_order():
    manifest = _manifest()
    reversed_manifest = manifest.iloc[::-1].reset_index(drop=True)

    assert universe_manifest_digest(manifest) == universe_manifest_digest(
        reversed_manifest
    )


def test_universe_provenance_enforces_survivorship_policy():
    unsafe = {
        "source": "current index members",
        "retrieved_at": "2026-07-23T00:00:00Z",
        "universe_policy": "current_members_only",
        "survivorship_policy": "current_constituents",
    }

    assert not validate_universe_provenance(unsafe)["promotion_safe"]
    with pytest.raises(ValueError, match="not promotion-safe"):
        validate_universe_provenance(unsafe, require_promotion_safe=True)

    safe = {
        **unsafe,
        "universe_policy": "dated membership events",
        "survivorship_policy": "point_in_time_membership",
    }
    assert validate_universe_provenance(
        safe,
        require_promotion_safe=True,
    )["promotion_safe"]
