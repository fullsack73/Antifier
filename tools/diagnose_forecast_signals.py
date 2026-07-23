#!/usr/bin/env python3
"""Diagnose cached portfolio forecasts without retraining or portfolio tuning."""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "src" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from forecast_signal_research import prediction_distribution_diagnostics  # noqa: E402


def _load_cache_rows(cache_path):
    connection = sqlite3.connect(str(Path(cache_path).expanduser()))
    try:
        rows = connection.execute(
            """
            SELECT key_payload, prediction_payload, created_at
            FROM forecast_predictions
            ORDER BY created_at, cache_key
            """
        ).fetchall()
    finally:
        connection.close()

    parsed = []
    for key_payload, prediction_payload, created_at in rows:
        key = json.loads(key_payload)
        prediction = json.loads(prediction_payload)
        parsed.append({
            "schema_version": key[0],
            "namespace": key[1],
            "method": key[2],
            "ticker": key[3],
            "horizon": key[4],
            "train_rows": key[5],
            "train_start": key[6],
            "train_end": key[7],
            "prediction": prediction,
            "created_at": created_at,
        })
    return parsed


def _component_predictions(rows, component):
    values = []
    for row in rows:
        prediction = row["prediction"]
        component_value = prediction.get("components", {}).get(component)
        values.append({
            "expected_return": component_value,
            "uncertainty": prediction.get("uncertainty"),
        })
    return values


def diagnose_cache(cache_path):
    rows = _load_cache_rows(cache_path)
    groups = {}
    for row in rows:
        key = (row["namespace"], row["method"])
        groups.setdefault(key, []).append(row)

    reports = []
    for (namespace, method), group_rows in sorted(groups.items()):
        predictions = [row["prediction"] for row in group_rows]
        components = sorted({
            component
            for prediction in predictions
            for component in prediction.get("components", {})
        })
        reports.append({
            "namespace": namespace,
            "method": method,
            "schema_versions": sorted({
                row["schema_version"] for row in group_rows
            }),
            "horizons": sorted({int(row["horizon"]) for row in group_rows}),
            "ticker_count": len({row["ticker"] for row in group_rows}),
            "train_window_count": len({
                (row["train_start"], row["train_end"]) for row in group_rows
            }),
            "created_at_start": min(row["created_at"] for row in group_rows),
            "created_at_end": max(row["created_at"] for row in group_rows),
            "predictions": prediction_distribution_diagnostics(predictions),
            "components": {
                component: prediction_distribution_diagnostics(
                    _component_predictions(group_rows, component)
                )
                for component in components
            },
        })

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": str(Path(cache_path).expanduser().resolve()),
        "purpose": "historical validation diagnostics only; not model tuning",
        "row_count": len(rows),
        "groups": reports,
    }


def _format_rate(value):
    return "NA" if value is None else f"{float(value):.1%}"


def write_markdown(payload, output_path):
    lines = [
        "# Forecast Signal Cache Diagnostics",
        "",
        f"- Source: `{payload['source']}`",
        f"- Cached predictions: {payload['row_count']}",
        f"- Purpose: {payload['purpose']}",
        "",
        "## Distribution",
        "",
        "| Namespace | Method | Count | Coverage | Saturation | Unique | Tie rate | Mean uncertainty |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for group in payload["groups"]:
        metrics = group["predictions"]
        lines.append(
            "| {namespace} | {method} | {count} | {coverage} | {saturation} | "
            "{unique} | {ties} | {uncertainty} |".format(
                namespace=group["namespace"],
                method=group["method"],
                count=metrics["prediction_count"],
                coverage=_format_rate(metrics["coverage_rate"]),
                saturation=_format_rate(metrics["boundary_saturation_rate"]),
                unique=metrics["unique_value_count"],
                ties=_format_rate(metrics["tie_rate"]),
                uncertainty=(
                    "NA"
                    if metrics["mean_reported_uncertainty"] is None
                    else f"{metrics['mean_reported_uncertainty']:.4f}"
                ),
            )
        )
    lines.extend([
        "",
        "## Components",
        "",
        "| Namespace | Component | Count | Saturation | Unique | Tie rate |",
        "|---|---|---:|---:|---:|---:|",
    ])
    for group in payload["groups"]:
        for component, metrics in group["components"].items():
            lines.append(
                "| {namespace} | {component} | {count} | {saturation} | "
                "{unique} | {ties} |".format(
                    namespace=group["namespace"],
                    component=component,
                    count=metrics["prediction_count"],
                    saturation=_format_rate(metrics["boundary_saturation_rate"]),
                    unique=metrics["unique_value_count"],
                    ties=_format_rate(metrics["tie_rate"]),
                )
            )
    lines.extend([
        "",
        "## Interpretation boundary",
        "",
        "- This report diagnoses already-consumed validation forecasts.",
        "- It must not be used to tune a replacement model against the same validation cases.",
        "- OOS error calibration requires matching realized returns from a separate research split.",
    ])
    markdown_path = Path(output_path).with_suffix(".md")
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return markdown_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", required=True, help="Forecast SQLite cache")
    parser.add_argument("--output", required=True, help="Output JSON path")
    args = parser.parse_args(argv)

    try:
        payload = diagnose_cache(args.cache)
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        markdown_path = write_markdown(payload, output_path)
    except Exception as exc:
        parser.exit(2, f"error: {exc}\n")

    print(f"Wrote {output_path}")
    print(f"Wrote {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
