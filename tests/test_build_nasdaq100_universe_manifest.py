import pandas as pd

from tools.build_nasdaq100_universe_manifest import (
    build_membership_events,
)
from universe_manifest import universe_snapshot


def test_build_membership_events_reverse_reconstructs_interval():
    changes = pd.DataFrame([
        {
            "effective_date": pd.Timestamp("2024-01-02"),
            "added_ticker": "D",
            "added_security": "D",
            "removed_ticker": "A",
            "removed_security": "A",
            "reason": "test",
        },
        {
            "effective_date": pd.Timestamp("2023-01-02"),
            "added_ticker": "C",
            "added_security": "C",
            "removed_ticker": "B",
            "removed_security": "B",
            "reason": "test",
        },
    ])

    events = build_membership_events(
        ["C", "D"],
        changes,
        "2022-12-31",
        "2024-12-31",
    )

    assert universe_snapshot(events, "2022-12-31") == ["A", "B"]
    assert universe_snapshot(events, "2023-12-31") == ["A", "C"]
    assert universe_snapshot(events, "2024-12-31") == ["C", "D"]


def test_build_membership_events_preserves_same_ticker_replacement():
    changes = pd.DataFrame([
        {
            "effective_date": pd.Timestamp("2024-01-02"),
            "added_ticker": "A",
            "added_security": "New A",
            "removed_ticker": "A",
            "removed_security": "Old A",
            "reason": "test",
        },
    ])

    events = build_membership_events(
        ["A"],
        changes,
        "2023-12-31",
        "2024-12-31",
    )

    assert universe_snapshot(events, "2023-12-31") == ["A"]
    assert universe_snapshot(events, "2024-12-31") == ["A"]
