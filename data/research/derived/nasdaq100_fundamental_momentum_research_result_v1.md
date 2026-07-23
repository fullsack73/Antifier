# Cross-sectional Forecast Research

- Split: `nasdaq100-fundamental-momentum-research-2018-2019-v1`
- Namespace: `pit-factor-v6-fundamental-momentum-nasdaq100`
- Price rows: 1762
- Tickers: 149
- Selection: `no_signal_candidate`
- Data promotion safe: `True`
- Split locked: `True`
- Signal gate passed: `False`
- Promotion eligible: `False`

## Signal-only comparison

| Objective | Gate | Periods | Rank IC | P(IC>0) | Positive IC | Top-bottom | P(Spread>0) | Coverage | OOS radius | Fits | Seconds | Peak MiB |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| factor_residual_nested_ridge | rejected | 21 | 0.0681 | 0.9650 | 0.7619 | 0.0209 | 0.8945 | 0.8192 | 0.1434 | 21 | 37.75 | 16.33 |
| factor_residual_fundamental_momentum_nested_ridge | rejected | 21 | 0.0461 | 0.9060 | 0.6667 | 0.0055 | 0.6735 | 0.8192 | 0.1458 | 21 | 55.31 | 19.71 |

## Paired candidate improvement

| Comparison | Gate | Δ rank IC | P(higher IC) | Δ spread | P(higher spread) |
|---|---|---:|---:|---:|---:|
| factor_residual_fundamental_momentum_nested_ridge_vs_factor_residual_nested_ridge | rejected | -0.0220 | 0.1235 | -0.0155 | 0.0120 |

## Guardrail

- Research split only; no portfolio construction or promotion decision.
- Freeze one candidate before any validation run.
- Do not use validation or locked-holdout outcomes for objective tuning.
