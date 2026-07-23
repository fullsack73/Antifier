# Cross-sectional Forecast Research

- Split: `nasdaq100-cash-accrual-research-2017-v1`
- Namespace: `pit-factor-v7-cash-accrual-nasdaq100`
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
| factor_residual_nested_ridge | rejected | 6 | -0.0298 | NA | 0.3333 | 0.0074 | NA | 0.7468 | 0.1370 | 6 | 10.21 | 15.89 |
| factor_residual_cash_accrual_nested_ridge | rejected | 6 | -0.0451 | NA | 0.3333 | -0.0074 | NA | 0.7468 | 0.1387 | 6 | 10.91 | 17.58 |

## Paired candidate improvement

| Comparison | Gate | Δ rank IC | P(higher IC) | Δ spread | P(higher spread) |
|---|---|---:|---:|---:|---:|
| factor_residual_cash_accrual_nested_ridge_vs_factor_residual_nested_ridge | rejected | NA | NA | NA | NA |

## Guardrail

- Research split only; no portfolio construction or promotion decision.
- Freeze one candidate before any validation run.
- Do not use validation or locked-holdout outcomes for objective tuning.
