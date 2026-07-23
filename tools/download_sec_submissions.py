#!/usr/bin/env python3
"""Download SEC submissions JSON for issuers in a security master."""

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests


URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--security-master", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--provenance-output", required=True)
    parser.add_argument("--user-agent", required=True)
    parser.add_argument("--minimum-interval", type=float, default=0.12)
    args = parser.parse_args(argv)

    try:
        master_path = Path(
            args.security_master
        ).expanduser().resolve()
        frame = pd.read_csv(master_path)
        if "cik" not in frame.columns:
            raise ValueError("Security master requires cik")
        ciks = sorted({int(value) for value in frame["cik"]})
        output_dir = Path(args.output_dir).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        interval = max(0.1, float(args.minimum_interval))
        session = requests.Session()
        session.headers.update({
            "User-Agent": args.user_agent,
            "Accept-Encoding": "gzip, deflate",
        })

        records = []
        last_request = 0.0
        for cik in ciks:
            output_path = output_dir / f"CIK{cik:010d}.json"
            if not output_path.is_file():
                elapsed = time.monotonic() - last_request
                if elapsed < interval:
                    time.sleep(interval - elapsed)
                response = session.get(URL.format(cik=cik), timeout=30)
                last_request = time.monotonic()
                response.raise_for_status()
                payload = response.json()
                if int(payload.get("cik", -1)) != cik:
                    raise ValueError(
                        f"SEC submissions CIK mismatch for {cik}"
                    )
                temporary = output_path.with_suffix(".tmp")
                temporary.write_bytes(response.content)
                temporary.replace(output_path)
            else:
                payload = json.loads(
                    output_path.read_text(encoding="utf-8")
                )
                if int(payload.get("cik", -1)) != cik:
                    raise ValueError(
                        f"Cached submissions CIK mismatch for {cik}"
                    )
            records.append({
                "cik": cik,
                "file": str(output_path),
                "bytes": output_path.stat().st_size,
                "sha256": _sha256(output_path),
            })

        provenance_path = Path(
            args.provenance_output
        ).expanduser().resolve()
        provenance_path.parent.mkdir(parents=True, exist_ok=True)
        provenance_path.write_text(
            json.dumps(
                {
                    "source": (
                        "SEC EDGAR submissions API "
                        "https://data.sec.gov/submissions/"
                    ),
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "security_master": str(master_path),
                    "security_master_sha256": _sha256(master_path),
                    "issuer_count": len(records),
                    "total_bytes": sum(
                        record["bytes"] for record in records
                    ),
                    "files": records,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception as exc:
        parser.exit(2, f"error: {exc}\n")

    print(f"Wrote {len(records)} SEC submissions files to {output_dir}")
    print(f"Wrote {provenance_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
