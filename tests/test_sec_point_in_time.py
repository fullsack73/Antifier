import json
import sys
import subprocess
from pathlib import Path

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from sec_point_in_time import (  # noqa: E402
    SecCompanyFactsDirectoryClient,
    SecEdgarClient,
    build_sec_pit_features,
    build_company_pit_features,
    build_company_quarterly_ttm_features,
    extract_cik_from_filing_metadata,
    normalize_ticker_cik_history,
    normalize_ticker_cik_map,
    parse_ticker_cik_map,
)


def _duration_fact(value, start, end, filed, accession, form="10-K"):
    return {
        "start": start,
        "end": end,
        "val": value,
        "accn": accession,
        "fy": int(end[:4]),
        "fp": "FY",
        "form": form,
        "filed": filed,
    }


def _instant_fact(value, end, filed, accession, form="10-K"):
    return {
        "end": end,
        "val": value,
        "accn": accession,
        "fy": int(end[:4]),
        "fp": "FY",
        "form": form,
        "filed": filed,
    }


def _company_facts(include_future_amendment=False):
    years = [
        ("2022-01-01", "2022-12-31", "2023-02-10", "a1"),
        ("2023-01-01", "2023-12-31", "2024-02-09", "a2"),
    ]

    def durations(values):
        return [
            _duration_fact(value, start, end, filed, accession)
            for value, (start, end, filed, accession) in zip(values, years)
        ]

    def instants(values):
        return [
            _instant_fact(value, end, filed, accession)
            for value, (_, end, filed, accession) in zip(values, years)
        ]

    net_income = durations([100.0, 150.0])
    if include_future_amendment:
        net_income.append(
            _duration_fact(
                999.0,
                "2022-01-01",
                "2022-12-31",
                "2024-04-01",
                "a1-amended",
                form="10-K/A",
            )
        )
    return {
        "entityName": "Example Corp",
        "facts": {
            "us-gaap": {
                "NetIncomeLoss": {"units": {"USD": net_income}},
                "Revenues": {"units": {"USD": durations([1000.0, 1200.0])}},
                "GrossProfit": {"units": {"USD": durations([400.0, 500.0])}},
                "NetCashProvidedByUsedInOperatingActivities": {
                    "units": {"USD": durations([180.0, 220.0])}
                },
                "Assets": {"units": {"USD": instants([2000.0, 2300.0])}},
                "AssetsCurrent": {
                    "units": {"USD": instants([600.0, 700.0])}
                },
                "LiabilitiesCurrent": {
                    "units": {"USD": instants([300.0, 350.0])}
                },
            },
            "dei": {
                "EntityCommonStockSharesOutstanding": {
                    "units": {"shares": instants([100.0, 110.0])}
                }
            },
        },
    }


def _quarterly_company_facts(include_future_amendment=False):
    periods = [
        (
            "2023-01-01",
            "2023-03-31",
            "2023-05-01",
            "q1",
            "10-Q",
        ),
        (
            "2023-04-01",
            "2023-06-30",
            "2023-08-01",
            "q2",
            "10-Q",
        ),
        (
            "2023-07-01",
            "2023-09-30",
            "2023-11-01",
            "q3",
            "10-Q",
        ),
        (
            "2023-01-01",
            "2023-12-31",
            "2024-02-15",
            "k1",
            "10-K",
        ),
    ]

    def flows(values):
        return [
            _duration_fact(
                value,
                start,
                end,
                filed,
                accession,
                form=form,
            )
            for value, (start, end, filed, accession, form)
            in zip(values, periods)
        ]

    def instants(values):
        return [
            _instant_fact(
                value,
                end,
                filed,
                accession,
                form=form,
            )
            for value, (_, end, filed, accession, form)
            in zip(values, periods)
        ]

    net_income = flows([10.0, 20.0, 30.0, 100.0])
    if include_future_amendment:
        net_income.append(
            _duration_fact(
                999.0,
                "2023-01-01",
                "2023-12-31",
                "2024-04-01",
                "k1-amended",
                form="10-K/A",
            )
        )
    operating_cash_flow = [
        _duration_fact(
            15.0,
            "2023-01-01",
            "2023-03-31",
            "2023-05-01",
            "q1",
            form="10-Q",
        ),
        _duration_fact(
            40.0,
            "2023-01-01",
            "2023-06-30",
            "2023-08-01",
            "q2",
            form="10-Q",
        ),
        _duration_fact(
            75.0,
            "2023-01-01",
            "2023-09-30",
            "2023-11-01",
            "q3",
            form="10-Q",
        ),
        _duration_fact(
            130.0,
            "2023-01-01",
            "2023-12-31",
            "2024-02-15",
            "k1",
            form="10-K",
        ),
    ]
    return {
        "entityName": "Quarterly Example Corp",
        "facts": {
            "us-gaap": {
                "NetIncomeLoss": {"units": {"USD": net_income}},
                "Revenues": {
                    "units": {"USD": flows([100.0, 200.0, 300.0, 1000.0])}
                },
                "GrossProfit": {
                    "units": {"USD": flows([40.0, 80.0, 120.0, 400.0])}
                },
                "NetCashProvidedByUsedInOperatingActivities": {
                    "units": {"USD": operating_cash_flow}
                },
                "Assets": {
                    "units": {"USD": instants([800.0, 850.0, 900.0, 1000.0])}
                },
                "AssetsCurrent": {
                    "units": {"USD": instants([200.0, 220.0, 240.0, 300.0])}
                },
                "LiabilitiesCurrent": {
                    "units": {"USD": instants([100.0, 110.0, 120.0, 150.0])}
                },
            },
            "dei": {
                "EntityCommonStockSharesOutstanding": {
                    "units": {"shares": instants([10.0, 10.0, 10.0, 10.0])}
                }
            },
        },
    }


def _quarterly_company_facts_with_next_year():
    facts = _quarterly_company_facts()
    us_gaap = facts["facts"]["us-gaap"]
    flow_values = {
        "NetIncomeLoss": 25.0,
        "Revenues": 250.0,
        "GrossProfit": 100.0,
        "NetCashProvidedByUsedInOperatingActivities": 35.0,
    }
    for concept, value in flow_values.items():
        us_gaap[concept]["units"]["USD"].append(
            _duration_fact(
                value,
                "2024-01-01",
                "2024-03-31",
                "2024-05-01",
                "q5",
                form="10-Q",
            )
        )
    instant_values = {
        "Assets": 1100.0,
        "AssetsCurrent": 330.0,
        "LiabilitiesCurrent": 165.0,
    }
    for concept, value in instant_values.items():
        us_gaap[concept]["units"]["USD"].append(
            _instant_fact(
                value,
                "2024-03-31",
                "2024-05-01",
                "q5",
                form="10-Q",
            )
        )
    facts["facts"]["dei"]["EntityCommonStockSharesOutstanding"][
        "units"
    ]["shares"].append(
        _instant_fact(
            10.0,
            "2024-03-31",
            "2024-05-01",
            "q5",
            form="10-Q",
        )
    )
    return facts


def test_company_features_use_sec_filing_date_and_filing_date_price():
    prices = pd.Series(
        [9.0, 10.0, 19.0, 20.0],
        index=pd.to_datetime(
            ["2023-02-09", "2023-02-10", "2024-02-08", "2024-02-09"]
        ),
    )

    result = build_company_pit_features(
        "exm",
        _company_facts(),
        {"sic": "3571"},
        prices,
        include_cash_accrual_quality=True,
    )

    assert list(result["available_date"]) == [
        pd.Timestamp("2023-02-10"),
        pd.Timestamp("2024-02-09"),
    ]
    first = result.iloc[0]
    assert first["ticker"] == "EXM"
    assert first["sector"] == "Manufacturing"
    assert first["market_cap"] == pytest.approx(1000.0)
    assert first["quality"] == pytest.approx(180.0 / 2000.0)
    assert first["profitability"] == pytest.approx(400.0 / 1000.0)
    assert first["valuation"] == pytest.approx(100.0 / 1000.0)
    assert first["liquidity"] == pytest.approx(2.0)
    assert first["cash_accrual_quality"] == pytest.approx(
        (180.0 - 100.0) / 2000.0
    )


def test_cash_accrual_feature_is_opt_in():
    prices = pd.Series(
        [10.0, 20.0],
        index=pd.to_datetime(["2023-02-10", "2024-02-09"]),
    )

    core = build_company_pit_features(
        "EXM",
        _company_facts(),
        {"sic": "3571"},
        prices,
    )
    extended = build_company_pit_features(
        "EXM",
        _company_facts(),
        {"sic": "3571"},
        prices,
        include_cash_accrual_quality=True,
    )

    assert "cash_accrual_quality" not in core.columns
    assert "cash_accrual_quality" in extended.columns


def test_future_amendment_does_not_rewrite_earlier_filing_row():
    prices = pd.Series(
        [10.0, 20.0, 22.0],
        index=pd.to_datetime(["2023-02-10", "2024-02-09", "2024-04-01"]),
    )
    baseline = build_company_pit_features(
        "EXM",
        _company_facts(),
        {"sic": "3571"},
        prices,
        end_date="2023-12-31",
        include_cash_accrual_quality=True,
    )
    amended = build_company_pit_features(
        "EXM",
        _company_facts(include_future_amendment=True),
        {"sic": "3571"},
        prices,
        end_date="2023-12-31",
        include_cash_accrual_quality=True,
    )

    pd.testing.assert_frame_equal(baseline, amended)
    assert amended.iloc[0]["valuation"] == pytest.approx(0.10)


def test_company_features_fall_back_to_weighted_average_shares():
    facts = _company_facts()
    facts["facts"]["dei"] = {}
    facts["facts"]["us-gaap"][
        "WeightedAverageNumberOfSharesOutstandingBasic"
    ] = {
        "units": {
            "shares": [
                _duration_fact(
                    90.0,
                    "2022-01-01",
                    "2022-12-31",
                    "2023-02-10",
                    "a1",
                ),
                _duration_fact(
                    100.0,
                    "2023-01-01",
                    "2023-12-31",
                    "2024-02-09",
                    "a2",
                ),
            ]
        }
    }
    prices = pd.Series(
        [10.0, 20.0],
        index=pd.to_datetime(["2023-02-10", "2024-02-09"]),
    )

    result = build_company_pit_features(
        "EXM",
        facts,
        {"sic": "3571"},
        prices,
    )

    assert list(result["shares_outstanding"]) == [90.0, 100.0]
    assert list(result["market_cap"]) == [900.0, 2000.0]


def test_company_features_accept_ifrs_20f_facts():
    facts = _company_facts()
    us_gaap = facts["facts"].pop("us-gaap")
    facts["facts"]["ifrs-full"] = {
        "ProfitLoss": us_gaap["NetIncomeLoss"],
        "Revenue": us_gaap["Revenues"],
        "GrossProfit": us_gaap["GrossProfit"],
        "CashFlowsFromUsedInOperatingActivities": (
            us_gaap["NetCashProvidedByUsedInOperatingActivities"]
        ),
        "Assets": us_gaap["Assets"],
        "CurrentAssets": us_gaap["AssetsCurrent"],
        "CurrentLiabilities": us_gaap["LiabilitiesCurrent"],
    }
    for taxonomy in ("ifrs-full", "dei"):
        for concept in facts["facts"][taxonomy].values():
            for entries in concept["units"].values():
                for entry in entries:
                    entry["form"] = "20-F"
    prices = pd.Series(
        [10.0, 20.0],
        index=pd.to_datetime(["2023-02-10", "2024-02-09"]),
    )

    result = build_company_pit_features(
        "EXM",
        facts,
        {"sic": "2834"},
        prices,
    )

    assert len(result) == 2
    assert result.iloc[0]["profitability"] == pytest.approx(0.4)


def test_quarterly_ttm_features_derive_ytd_and_fourth_quarter_flows():
    prices = pd.Series(
        [10.0, 10.0, 10.0, 10.0],
        index=pd.to_datetime(
            [
                "2023-05-01",
                "2023-08-01",
                "2023-11-01",
                "2024-02-15",
            ]
        ),
    )

    result = build_company_quarterly_ttm_features(
        "EXM",
        _quarterly_company_facts(),
        {"sic": "3571"},
        prices,
        include_cash_accrual_quality=True,
    )

    assert len(result) == 4
    row = result.iloc[-1]
    assert row["available_date"] == pd.Timestamp("2024-02-15")
    assert row["filing_form"] == "10-K"
    assert row["market_cap"] == pytest.approx(100.0)
    assert row["quality"] == pytest.approx(0.13)
    assert row["profitability"] == pytest.approx(0.40)
    assert row["valuation"] == pytest.approx(1.0)
    assert row["liquidity"] == pytest.approx(2.0)
    assert row["cash_accrual_quality"] == pytest.approx(
        (130.0 - 100.0) / 1000.0
    )


def test_seasonal_earnings_change_is_opt_in_and_point_in_time():
    prices = pd.Series(
        [10.0] * 5,
        index=pd.to_datetime(
            [
                "2023-05-01",
                "2023-08-01",
                "2023-11-01",
                "2024-02-15",
                "2024-05-01",
            ]
        ),
    )
    facts = _quarterly_company_facts_with_next_year()

    core = build_company_quarterly_ttm_features(
        "EXM",
        facts,
        {"sic": "3571"},
        prices,
    )
    extended = build_company_quarterly_ttm_features(
        "EXM",
        facts,
        {"sic": "3571"},
        prices,
        include_seasonal_earnings_change=True,
    )

    assert "seasonal_earnings_change" not in core.columns
    assert extended.iloc[:4]["seasonal_earnings_change"].isna().all()
    assert extended.iloc[-1]["seasonal_earnings_change"] == pytest.approx(
        (25.0 - 10.0) / 1100.0
    )


def test_seasonal_earnings_change_requires_quarterly_feature_set():
    with pytest.raises(ValueError, match="requires quarterly-ttm"):
        build_sec_pit_features(
            [],
            pd.DataFrame(),
            object(),
            filing_frequency="annual",
            include_seasonal_earnings_change=True,
        )


def test_future_quarterly_amendment_does_not_rewrite_prior_row():
    prices = pd.Series(
        [10.0, 10.0, 10.0, 10.0, 10.0],
        index=pd.to_datetime(
            [
                "2023-05-01",
                "2023-08-01",
                "2023-11-01",
                "2024-02-15",
                "2024-04-01",
            ]
        ),
    )
    baseline = build_company_quarterly_ttm_features(
        "EXM",
        _quarterly_company_facts(),
        {"sic": "3571"},
        prices,
        end_date="2024-03-01",
        include_cash_accrual_quality=True,
    )
    amended = build_company_quarterly_ttm_features(
        "EXM",
        _quarterly_company_facts(include_future_amendment=True),
        {"sic": "3571"},
        prices,
        end_date="2024-03-01",
        include_cash_accrual_quality=True,
    )

    pd.testing.assert_frame_equal(baseline, amended)


def test_sec_client_requires_declared_contact_and_does_not_pin_host(tmp_path):
    with pytest.raises(ValueError, match="email address or project URL"):
        SecEdgarClient("Antifier", cache_dir=tmp_path)

    client = SecEdgarClient(
        "Antifier research https://github.com/example/antifier",
        cache_dir=tmp_path,
    )
    assert "Host" not in client.session.headers
    assert "Antifier research" in client.session.headers["User-Agent"]


def test_parse_ticker_cik_map_ignores_invalid_rows():
    payload = {
        "0": {"ticker": "aapl", "cik_str": 320193},
        "1": {"ticker": "", "cik_str": 1},
        "2": {"ticker": "bad", "cik_str": "not-a-number"},
    }

    assert parse_ticker_cik_map(payload) == {"AAPL": 320193}


def test_sec_builder_cli_requires_declared_user_agent(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "build_sec_pit_features.py"),
            "--tickers",
            "AAPL",
            "--start",
            "2020-01-01",
            "--end",
            "2020-12-31",
            "--output",
            str(tmp_path / "features.csv"),
        ],
        cwd=ROOT,
        env={"PATH": str(Path(sys.executable).parent)},
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "SEC_USER_AGENT" in result.stderr


def test_local_companyfacts_client_reads_official_archive_layout(tmp_path):
    companyfacts_dir = tmp_path / "companyfacts"
    companyfacts_dir.mkdir()
    payload = _company_facts()
    payload["cik"] = 123
    (companyfacts_dir / "CIK0000000123.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    client = SecCompanyFactsDirectoryClient(
        companyfacts_dir,
        {"exm": 123},
    )

    assert client.ticker_cik_map() == {"EXM": 123}
    assert client.company_facts(123)["entityName"] == "Example Corp"
    assert client.submissions(123) == {}
    assert "bulk archive" in client.source_description


def test_local_companyfacts_client_reads_optional_submissions_directory(
    tmp_path,
):
    companyfacts_dir = tmp_path / "companyfacts"
    submissions_dir = tmp_path / "submissions"
    companyfacts_dir.mkdir()
    submissions_dir.mkdir()
    payload = _company_facts()
    payload["cik"] = 123
    (companyfacts_dir / "CIK0000000123.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    (submissions_dir / "CIK0000000123.json").write_text(
        json.dumps({
            "cik": 123,
            "sic": "3571",
            "sicDescription": "Electronic Computers",
        }),
        encoding="utf-8",
    )

    client = SecCompanyFactsDirectoryClient(
        companyfacts_dir,
        {"EXM": 123},
        submissions_dir=submissions_dir,
    )

    assert client.submissions(123)["sic"] == "3571"
    assert client.submissions(999) == {}


def test_normalize_ticker_cik_map_rejects_ambiguous_ticker():
    with pytest.raises(ValueError, match="multiple CIKs"):
        normalize_ticker_cik_map(
            [
                {"ticker": "ABC", "cik": 1},
                {"ticker": "abc", "cik": 2},
            ]
        )


def test_ticker_cik_history_rejects_overlapping_issuer_intervals():
    with pytest.raises(ValueError, match="overlapping"):
        normalize_ticker_cik_history([
            {
                "ticker": "ABC",
                "cik": 1,
                "effective_start": "2020-01-01",
                "effective_end": "2021-12-31",
            },
            {
                "ticker": "ABC",
                "cik": 2,
                "effective_start": "2021-01-01",
            },
        ])


def test_ticker_cik_history_accepts_normalized_mapping():
    normalized = normalize_ticker_cik_history([
        {
            "ticker": "DIS",
            "cik": 1001039,
            "effective_end": "2019-03-19",
        },
        {
            "ticker": "DIS",
            "cik": 1744489,
            "effective_start": "2019-03-20",
        },
    ])

    assert normalize_ticker_cik_history(normalized) == normalized


def test_sec_builder_cli_requires_security_master_provenance(tmp_path):
    companyfacts_dir = tmp_path / "companyfacts"
    companyfacts_dir.mkdir()
    security_master = tmp_path / "security_master.csv"
    pd.DataFrame([{"ticker": "AAPL", "cik": 320193}]).to_csv(
        security_master,
        index=False,
    )

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "build_sec_pit_features.py"),
            "--tickers",
            "AAPL",
            "--start",
            "2020-01-01",
            "--end",
            "2020-12-31",
            "--output",
            str(tmp_path / "features.csv"),
            "--companyfacts-dir",
            str(companyfacts_dir),
            "--security-master",
            str(security_master),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "--security-master-provenance" in result.stderr


def test_sec_builder_combines_dated_issuer_identities(tmp_path):
    companyfacts_dir = tmp_path / "companyfacts"
    companyfacts_dir.mkdir()
    first = _company_facts()
    first["cik"] = 123
    second = _company_facts()
    second["cik"] = 456
    (companyfacts_dir / "CIK0000000123.json").write_text(
        json.dumps(first),
        encoding="utf-8",
    )
    (companyfacts_dir / "CIK0000000456.json").write_text(
        json.dumps(second),
        encoding="utf-8",
    )
    history = [
        {
            "ticker": "EXM",
            "cik": 123,
            "effective_end": "2023-12-31",
            "sector": "Legacy Sector",
        },
        {
            "ticker": "EXM",
            "cik": 456,
            "effective_start": "2024-01-01",
            "sector": "Modern Sector",
        },
    ]
    client = SecCompanyFactsDirectoryClient(
        companyfacts_dir,
        {"EXM": 456},
        ticker_cik_history=history,
    )
    prices = pd.DataFrame(
        {"EXM": [10.0, 20.0]},
        index=pd.to_datetime(["2023-02-10", "2024-02-09"]),
    )

    features, provenance = build_sec_pit_features(
        ["EXM"],
        prices,
        client,
    )

    assert list(features["sector"]) == [
        "Legacy Sector",
        "Modern Sector",
    ]
    assert list(features["available_date"]) == [
        pd.Timestamp("2023-02-10"),
        pd.Timestamp("2024-02-09"),
    ]
    assert len(provenance["company_metadata"]["EXM"]["identities"]) == 2


def test_extract_cik_from_yahoo_filing_metadata():
    filings = [
        {
            "edgarUrl": (
                "https://finance.yahoo.com/sec-filing/"
                "AAPL/0001140361-26-023149_320193"
            ),
            "exhibits": {
                "SD": (
                    "https://cdn.yahoofinance.com/prod/sec-filings/"
                    "0001140361/example.htm"
                )
            },
        }
    ]

    assert extract_cik_from_filing_metadata(filings) == 320193
    assert extract_cik_from_filing_metadata([]) is None
