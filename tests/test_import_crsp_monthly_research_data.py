import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = ROOT / "tools" / "import_crsp_monthly_research_data.py"
SPEC = importlib.util.spec_from_file_location(
    "import_crsp_monthly_research_data",
    TOOL_PATH,
)
IMPORTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(IMPORTER)


def _stock_rows():
    return pd.DataFrame([
        {
            "permno": 10001,
            "date": "2020-01-31",
            "ret": 0.10,
            "dlret": np.nan,
            "prc": 10.0,
            "shrout": 100.0,
            "shrcd": 10,
            "exchcd": 1,
            "ticker": "OLD",
        },
        {
            "permno": 10001,
            "date": "2020-02-29",
            "ret": 0.05,
            "dlret": -0.50,
            "prc": 5.0,
            "shrout": 100.0,
            "shrcd": 10,
            "exchcd": 1,
            "ticker": "NEW",
        },
        {
            "permno": 20002,
            "date": "2020-02-29",
            "ret": 0.02,
            "dlret": np.nan,
            "prc": 20.0,
            "shrout": 200.0,
            "shrcd": 11,
            "exchcd": 3,
            "ticker": "LIVE",
        },
    ])


def _identity_links():
    return pd.DataFrame([
        {
            "permno": 10001,
            "cik": 111,
            "effective_start": "2019-01-01",
            "effective_end": "2020-01-31",
        },
        {
            "permno": 10001,
            "cik": 222,
            "effective_start": "2020-02-01",
            "effective_end": "",
        },
        {
            "permno": 20002,
            "cik": 333,
            "effective_start": "",
            "effective_end": "",
        },
    ])


def test_combines_regular_and_delisting_returns():
    combined = IMPORTER.combine_crsp_returns(
        pd.Series([0.10, 0.05, np.nan]),
        pd.Series([np.nan, -0.50, -1.0]),
    )

    assert combined.tolist() == pytest.approx([0.10, -0.475, -1.0])


def test_rejects_overlapping_permno_cik_links():
    links = _identity_links()
    links.loc[1, "effective_start"] = "2020-01-01"

    with pytest.raises(ValueError, match="Overlapping"):
        IMPORTER.normalize_crsp_cik_links(links)


def test_builds_permno_panels_without_leading_backfill():
    artifacts = IMPORTER.build_crsp_research_artifacts(
        _stock_rows(),
        _identity_links(),
    )

    prices = artifacts["prices"]
    returns = artifacts["returns"]
    master = artifacts["security_master"]

    assert pd.isna(prices.loc["2020-01-31", "PERMNO_20002"])
    assert returns.loc["2020-02-29", "PERMNO_10001"] == pytest.approx(
        -0.475
    )
    assert prices.loc["2020-02-29", "PERMNO_10001"] == pytest.approx(
        100.0 * 1.10 * 0.525
    )
    assert set(master.loc[
        master["ticker"] == "PERMNO_10001",
        "cik",
    ]) == {111, 222}
    assert set(master["display_ticker"]) == {"NEW", "LIVE"}
    assert artifacts["diagnostics"]["identity_coverage_rate"] == 1.0


def test_rejects_missing_point_in_time_identity_coverage():
    links = _identity_links().loc[
        lambda frame: frame["permno"] != 20002
    ]

    with pytest.raises(ValueError, match="lack point-in-time CIK"):
        IMPORTER.build_crsp_research_artifacts(_stock_rows(), links)


def test_cli_writes_promotion_safe_sha_provenance(tmp_path):
    stock_path = tmp_path / "stock.csv"
    links_path = tmp_path / "links.csv"
    output_dir = tmp_path / "output"
    _stock_rows().to_csv(stock_path, index=False)
    _identity_links().to_csv(links_path, index=False)

    result = IMPORTER.main([
        "--stock-data",
        str(stock_path),
        "--identity-links",
        str(links_path),
        "--output-dir",
        str(output_dir),
        "--name",
        "sample",
    ])

    provenance = json.loads(
        (output_dir / "sample.provenance.json").read_text()
    )
    assert result == 0
    assert provenance["promotion_safe"] is True
    assert provenance["diagnostics"]["delisting_return_count"] == 1
    assert provenance["universe_manifest_sha256"]
    assert set(provenance["outputs"]) == {
        "returns",
        "prices",
        "market_caps",
        "universe",
        "security_master",
    }
