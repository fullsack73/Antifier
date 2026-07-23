import json
import zipfile

import pandas as pd

from tools.build_fama_french_industry_panel import (
    main as build_industry_panel,
    parse_value_weighted_daily_returns,
)


def test_french_industry_parser_selects_value_weighted_daily_section(
    tmp_path,
):
    archive_path = tmp_path / "industries.zip"
    payload = "\n".join([
        "Metadata",
        "",
        "Average Value Weighted Returns -- Daily",
        ",Agric,Food",
        "20000103,1.00,-0.50",
        "20000104,-99.99,0.25",
        "",
        "Average Equal Weighted Returns -- Daily",
        ",Agric,Food",
        "20000103,9.00,9.00",
        "",
    ])
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("industries.csv", payload)

    result = parse_value_weighted_daily_returns(archive_path)

    assert list(result.columns) == ["Agric", "Food"]
    assert result.index[0] == pd.Timestamp("2000-01-03")
    assert result.loc["2000-01-03", "Agric"] == 0.01
    assert result.loc["2000-01-03", "Food"] == -0.005
    assert pd.isna(result.loc["2000-01-04", "Agric"])


def test_french_industry_builder_records_selected_source_and_count(
    tmp_path,
):
    archive_path = tmp_path / "industries.zip"
    output_path = tmp_path / "prices.csv"
    source_url = "https://example.test/30-industries.zip"
    payload = "\n".join([
        "Metadata",
        "",
        "Average Value Weighted Returns -- Daily",
        ",Agric,Food",
        "20000103,1.00,-0.50",
        "20000104,0.25,0.25",
        "",
    ])
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("industries.csv", payload)

    status = build_industry_panel([
        "--archive",
        str(archive_path),
        "--start",
        "2000-01-03",
        "--end",
        "2000-01-04",
        "--output",
        str(output_path),
        "--source-url",
        source_url,
        "--portfolio-policy",
        "synthetic two-portfolio test",
    ])

    provenance = json.loads(
        output_path.with_suffix(".provenance.json").read_text()
    )
    assert status == 0
    assert provenance["source_url"] == source_url
    assert provenance["ticker_count"] == 2
    assert provenance["source_portfolio_policy"] == (
        "synthetic two-portfolio test"
    )
