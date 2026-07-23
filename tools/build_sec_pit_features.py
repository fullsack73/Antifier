#!/usr/bin/env python3
"""Build filing-date point-in-time factor data from official SEC APIs."""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from portfolio_alpha_v2 import normalize_point_in_time_features  # noqa: E402
from portfolio_backtest import fetch_backtest_price_data  # noqa: E402
from sec_point_in_time import (  # noqa: E402
    SEC_COMPANY_FACTS_URL,
    SEC_SUBMISSIONS_URL,
    SEC_TICKERS_URL,
    SecEdgarClient,
    SecCompanyFactsDirectoryClient,
    build_sec_pit_features,
    normalize_ticker_cik_map,
)
from universe_manifest import (  # noqa: E402
    manifest_tickers_during,
    normalize_universe_manifest,
    universe_manifest_digest,
    validate_universe_provenance,
)


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load_universe(args):
    if not args.universe_manifest:
        return None, {
            "source": "explicit CLI ticker list",
            "universe_policy": "static requested tickers",
            "survivorship_policy": "not_asserted",
            "promotion_safe": False,
        }
    if not args.universe_provenance:
        raise ValueError(
            "--universe-manifest requires --universe-provenance"
        )
    manifest = normalize_universe_manifest(
        pd.read_csv(args.universe_manifest)
    )
    provenance = validate_universe_provenance(
        json.loads(
            Path(args.universe_provenance).read_text(encoding="utf-8")
        ),
        require_promotion_safe=args.require_promotion_safe_universe,
    )
    provenance["manifest_sha256"] = universe_manifest_digest(manifest)
    return manifest, provenance


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--tickers", nargs="+", help="SEC-listed tickers")
    source.add_argument(
        "--universe-manifest",
        help="Dated effective_date,ticker,in_universe CSV",
    )
    parser.add_argument(
        "--universe-provenance",
        help="JSON provenance for the dated universe manifest",
    )
    parser.add_argument(
        "--require-promotion-safe-universe",
        action="store_true",
        help="Reject manifests without a PIT/survivorship-safe policy",
    )
    parser.add_argument("--start", required=True, help="First filing date")
    parser.add_argument("--end", required=True, help="Last filing date")
    parser.add_argument("--output", required=True, help="Output factor CSV")
    parser.add_argument(
        "--provenance-output",
        help="Output JSON; defaults beside factor CSV",
    )
    parser.add_argument(
        "--user-agent",
        default=os.environ.get("SEC_USER_AGENT"),
        help="Declared SEC User-Agent; defaults to SEC_USER_AGENT",
    )
    parser.add_argument("--cache-dir", default=".cache/sec")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument(
        "--companyfacts-dir",
        help="Extracted official SEC companyfacts directory; avoids API calls",
    )
    parser.add_argument(
        "--ticker-cik-map",
        help="CSV with ticker,cik columns for --companyfacts-dir",
    )
    parser.add_argument(
        "--submissions-dir",
        help="Optional extracted SEC submissions directory for SIC metadata",
    )
    args = parser.parse_args(argv)

    try:
        start = pd.Timestamp(args.start)
        end = pd.Timestamp(args.end)
        if start > end:
            raise ValueError("--start must be on or before --end")
        manifest, universe_provenance = _load_universe(args)
        tickers = (
            sorted({ticker.strip().upper() for ticker in args.tickers})
            if args.tickers
            else manifest_tickers_during(manifest, start, end)
        )
        if not tickers:
            raise ValueError("No active tickers in the requested interval")
        uses_local_companyfacts = bool(args.companyfacts_dir)
        if uses_local_companyfacts != bool(args.ticker_cik_map):
            raise ValueError(
                "--companyfacts-dir and --ticker-cik-map must be used together"
            )
        if args.submissions_dir and not uses_local_companyfacts:
            raise ValueError(
                "--submissions-dir requires --companyfacts-dir"
            )
        if not uses_local_companyfacts and not args.user_agent:
            raise ValueError(
                "Set SEC_USER_AGENT to an application name plus contact "
                "email or project URL, or provide --companyfacts-dir and "
                "--ticker-cik-map"
            )

        price_start = (start - pd.Timedelta(days=14)).strftime("%Y-%m-%d")
        price_end = (end + pd.Timedelta(days=2)).strftime("%Y-%m-%d")
        prices = fetch_backtest_price_data(
            tickers=tickers,
            start_date=price_start,
            end_date=price_end,
        )
        client = (
            SecCompanyFactsDirectoryClient(
                args.companyfacts_dir,
                normalize_ticker_cik_map(
                    pd.read_csv(args.ticker_cik_map)
                ),
                submissions_dir=args.submissions_dir,
            )
            if uses_local_companyfacts
            else SecEdgarClient(
                args.user_agent,
                cache_dir=args.cache_dir,
            )
        )
        features, sec_provenance = build_sec_pit_features(
            tickers,
            prices,
            client,
            start_date=start,
            end_date=end,
            refresh=args.refresh,
        )
        if features.empty:
            failure_summary = json.dumps(
                sec_provenance["failures"],
                sort_keys=True,
            )
            raise ValueError(
                "SEC produced no usable PIT feature rows: "
                + failure_summary
            )
        normalize_point_in_time_features(features)
        features = features.sort_values(
            ["available_date", "ticker"]
        ).reset_index(drop=True)
        for column in ("available_date", "report_end"):
            features[column] = pd.to_datetime(features[column]).dt.strftime(
                "%Y-%m-%d"
            )

        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        features.to_csv(output_path, index=False)
        provenance_path = (
            Path(args.provenance_output).expanduser().resolve()
            if args.provenance_output
            else output_path.with_suffix(".provenance.json")
        )
        provenance_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            **sec_provenance,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "official_endpoints": {
                "ticker_mapping": SEC_TICKERS_URL,
                "company_facts": SEC_COMPANY_FACTS_URL,
                "submissions": SEC_SUBMISSIONS_URL,
            },
            "requested_start": start.strftime("%Y-%m-%d"),
            "requested_end": end.strftime("%Y-%m-%d"),
            "row_count": int(len(features)),
            "feature_file": str(output_path),
            "feature_file_sha256": _sha256(output_path),
            "universe": universe_provenance,
            "ingestion_mode": (
                "local_official_companyfacts_archive"
                if uses_local_companyfacts
                else "sec_edgar_api"
            ),
            "companyfacts_directory": (
                str(Path(args.companyfacts_dir).expanduser().resolve())
                if uses_local_companyfacts
                else None
            ),
            "submissions_directory": (
                str(Path(args.submissions_dir).expanduser().resolve())
                if args.submissions_dir
                else None
            ),
            "ticker_cik_map_sha256": (
                _sha256(args.ticker_cik_map)
                if uses_local_companyfacts
                else None
            ),
            "user_agent_declared": bool(
                args.user_agent and not uses_local_companyfacts
            ),
        }
        provenance_path.write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        parser.exit(2, f"error: {exc}\n")

    print(f"Wrote {output_path}")
    print(f"Wrote {provenance_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
