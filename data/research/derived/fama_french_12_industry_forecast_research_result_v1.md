# Cross-sectional Forecast Research

- Split: `fama-french-12-industry-forecast-research-2022-2025-v1`
- Namespace: `forecast-v1-fresh-industry-portfolios`
- Price rows: 1760
- Tickers: 12
- Selection: `no_signal_candidate`
- Data promotion safe: `True`
- Split locked: `True`
- Signal gate passed: `False`
- Promotion eligible: `False`

## Signal-only comparison

| Objective | Gate | Periods | Rank IC | P(IC>0) | Positive IC | Top-bottom | P(Spread>0) | Coverage | OOS radius | Fits | Seconds | Peak MiB |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| relative_ridge | rejected | 14 | 0.0480 | 0.6390 | 0.5000 | 0.0157 | 0.6260 | 1.0000 | 0.0969 | 14 | 1.01 | 2.12 |
| relative_nested_ridge | rejected | 14 | 0.0654 | 0.7190 | 0.5714 | 0.0174 | 0.6565 | 1.0000 | 0.0976 | 14 | 2.73 | 1.92 |

## Paired candidate improvement

| Comparison | Gate | Δ rank IC | P(higher IC) | Δ spread | P(higher spread) |
|---|---|---:|---:|---:|---:|
| relative_nested_ridge_vs_relative_ridge | rejected | 0.0175 | 0.7225 | 0.0018 | 0.6010 |

## Guardrail

- Research split only; no portfolio construction or promotion decision.
- Freeze one candidate before any validation run.
- Do not use validation or locked-holdout outcomes for objective tuning.
