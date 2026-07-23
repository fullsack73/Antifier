# Cross-sectional Forecast Research

- Split: `nasdaq100-quarterly-ttm-predictor-research-2020-2021-v1`
- Namespace: `pit-factor-v5-quarterly-ttm-predictor-nasdaq100`
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
| factor_residual_nested_ridge | rejected | 7 | -0.0505 | NA | 0.4286 | -0.0263 | NA | 0.8649 | 0.1762 | 7 | 10.96 | 15.36 |

## Guardrail

- Research split only; no portfolio construction or promotion decision.
- Freeze one candidate before any validation run.
- Do not use validation or locked-holdout outcomes for objective tuning.
