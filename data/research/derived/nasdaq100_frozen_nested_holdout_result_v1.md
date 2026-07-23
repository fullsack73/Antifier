# Cross-sectional Forecast Research

- Split: `nasdaq100-frozen-nested-holdout-2022-2025-v1`
- Namespace: `pit-factor-v2-nested-independent-nasdaq100`
- Price rows: 2261
- Tickers: 179
- Selection: `no_signal_candidate`
- Data promotion safe: `True`
- Split locked: `True`
- Signal gate passed: `False`
- Promotion eligible: `False`

## Signal-only comparison

| Objective | Gate | Periods | Rank IC | P(IC>0) | Positive IC | Top-bottom | P(Spread>0) | Coverage | OOS radius | Fits | Seconds | Peak MiB |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| factor_residual_ridge | rejected | 15 | 0.0255 | 0.8615 | 0.5333 | -0.0030 | 0.3905 | 0.9289 | 0.1709 | 15 | 5.46 | 15.50 |
| factor_residual_nested_ridge | rejected | 15 | 0.0260 | 0.8870 | 0.4667 | -0.0022 | 0.4190 | 0.9289 | 0.1714 | 15 | 20.57 | 15.46 |

## Paired candidate improvement

| Comparison | Gate | Δ rank IC | P(higher IC) | Δ spread | P(higher spread) |
|---|---|---:|---:|---:|---:|
| factor_residual_nested_ridge_vs_factor_residual_ridge | rejected | 0.0004 | 0.6055 | 0.0007 | 0.6135 |

## Guardrail

- Research split only; no portfolio construction or promotion decision.
- Freeze one candidate before any validation run.
- Do not use validation or locked-holdout outcomes for objective tuning.
