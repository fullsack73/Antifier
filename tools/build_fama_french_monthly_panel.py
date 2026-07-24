#!/usr/bin/env python3
"""Build a provenance-tracked price index from French monthly returns."""

import argparse
import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


SOURCE_URL = (
    "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
    "25_Portfolios_ME_AC_5x5_CSV.zip"
)
SECTION_LABEL = "Average Value Weighted Returns -- Monthly"


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _basket_digest(tickers):
    return hashlib.sha256(
        json.dumps(
            list(tickers),
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def parse_value_weighted_monthly_returns(
    zip_path,
    section_label=SECTION_LABEL,
):
    """Parse the first average value-weighted monthly return section."""
    with zipfile.ZipFile(zip_path) as archive:
        members = archive.namelist()
        if len(members) != 1:
            raise ValueError("Expected one CSV inside the French archive")
        text = archive.read(members[0]).decode("utf-8")
    lines = text.splitlines()
    try:
        section_index = next(
            index
            for index, line in enumerate(lines)
            if section_label in line
        )
    except StopIteration as exc:
        raise ValueError(
            "French archive is missing the value-weighted monthly section"
        ) from exc
    header_index = section_index + 1
    while header_index < len(lines) and not lines[header_index].strip():
        header_index += 1
    data_end = header_index + 1
    while data_end < len(lines) and lines[data_end].strip():
        data_end += 1
    frame = pd.read_csv(
        io.StringIO("\n".join(lines[header_index:data_end]))
    )
    date_column = frame.columns[0]
    frame = frame.rename(columns={date_column: "date"})
    dates = pd.to_datetime(
        frame["date"].astype(str).str.strip(),
        format="%Y%m",
        errors="raise",
    ) + pd.offsets.MonthEnd(0)
    frame = frame.drop(columns="date")
    frame.index = pd.DatetimeIndex(dates, name="date")
    frame.columns = [str(column).strip() for column in frame.columns]
    frame = frame.apply(pd.to_numeric, errors="coerce") / 100.0
    return frame.mask(frame <= -0.99)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--source-url",
        default=SOURCE_URL,
        help="Official source URL recorded in provenance",
    )
    parser.add_argument(
        "--portfolio-policy",
        required=True,
        help="Portfolio construction policy recorded in provenance",
    )
    parser.add_argument(
        "--section-label",
        default=SECTION_LABEL,
        help="Exact monthly return section label recorded in provenance",
    )
    parser.add_argument(
        "--include-columns",
        nargs="*",
        default=[],
        help=(
            "Exact source columns retained in declared order; "
            "recorded in provenance"
        ),
    )
    args = parser.parse_args(argv)

    try:
        start = pd.Timestamp(args.start)
        end = pd.Timestamp(args.end)
        if start > end:
            raise ValueError("--start must be on or before --end")
        archive_path = Path(args.archive).expanduser().resolve()
        returns = parse_value_weighted_monthly_returns(
            archive_path,
            section_label=args.section_label,
        )
        returns = returns.loc[
            (returns.index >= start) & (returns.index <= end)
        ]
        if returns.empty:
            raise ValueError("No French monthly rows in requested interval")
        source_columns = list(returns.columns)
        selected_columns = list(dict.fromkeys(args.include_columns))
        if selected_columns:
            unknown = [
                column
                for column in selected_columns
                if column not in returns.columns
            ]
            if unknown:
                raise ValueError(
                    "Unknown French monthly columns: "
                    + ", ".join(unknown)
                )
            returns = returns.loc[:, selected_columns]
        missing = {
            column: int(returns[column].isna().sum())
            for column in returns.columns
            if returns[column].isna().any()
        }
        if missing:
            raise ValueError(
                "Requested French monthly interval contains missing data: "
                + json.dumps(missing, sort_keys=True)
            )
        prices = (1.0 + returns).cumprod() * 100.0
        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        prices.to_csv(output_path)
        provenance_path = output_path.with_suffix(".provenance.json")
        provenance_path.write_text(
            json.dumps(
                {
                    "source": "Kenneth R. French Data Library",
                    "source_url": args.source_url,
                    "source_section": args.section_label,
                    "source_portfolio_policy": args.portfolio_policy,
                    "return_weighting": "value_weighted",
                    "frequency": "monthly",
                    "date_semantics": "calendar_month_end",
                    "retrieved_at": datetime.now(
                        timezone.utc
                    ).isoformat(),
                    "raw_archive": str(archive_path),
                    "raw_archive_sha256": _sha256(archive_path),
                    "start_date": prices.index.min().strftime("%Y-%m-%d"),
                    "end_date": prices.index.max().strftime("%Y-%m-%d"),
                    "row_count": int(len(prices)),
                    "source_ticker_count": int(len(source_columns)),
                    "ticker_count": int(len(prices.columns)),
                    "selected_source_tickers": list(prices.columns),
                    "tickers": list(prices.columns),
                    "column_selection_policy": (
                        "exact_declared_source_columns"
                        if selected_columns
                        else "all_source_columns"
                    ),
                    "basket_manifest_sha256": _basket_digest(
                        prices.columns
                    ),
                    "price_file": str(output_path),
                    "price_file_sha256": _sha256(output_path),
                    "survivorship_policy": (
                        "source portfolios include eligible NYSE, AMEX, "
                        "and NASDAQ firms through time"
                    ),
                    "promotion_safe": True,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception as exc:
        parser.exit(2, f"error: {exc}\n")

    print(f"Wrote {output_path}")
    print(f"Wrote {provenance_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
