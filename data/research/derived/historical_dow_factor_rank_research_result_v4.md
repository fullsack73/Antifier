# Cross-sectional Forecast Research

- Split: `historical-dow-factor-rank-research-2011-2025-v4`
- Namespace: `pit-factor-v4-rank-target-historical-dow`
- Price rows: 4780
- Tickers: 49
- Selection: `no_signal_candidate`
- Data promotion safe: `False`
- Split locked: `True`
- Signal gate passed: `False`
- Promotion eligible: `False`

## Signal-only comparison

| Objective | Gate | Periods | Rank IC | P(IC>0) | Positive IC | Top-bottom | P(Spread>0) | Coverage | OOS radius | Fits | Seconds | Peak MiB |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| factor_residual_nested_ridge | passed | 59 | 0.0627 | 0.9870 | 0.6102 | 0.0153 | 0.9745 | 0.9825 | 0.0940 | 59 | 25.43 | 11.79 |
| factor_residual_rank_nested_ridge | rejected | 59 | 0.0538 | 0.9775 | 0.5763 | 0.0078 | 0.8600 | 0.9825 | 0.1237 | 59 | 27.29 | 11.66 |

## Paired candidate improvement

| Comparison | Gate | Δ rank IC | P(higher IC) | Δ spread | P(higher spread) |
|---|---|---:|---:|---:|---:|
| factor_residual_rank_nested_ridge_vs_factor_residual_nested_ridge | rejected | -0.0090 | 0.1875 | -0.0075 | 0.0175 |

## Guardrail

- Research split only; no portfolio construction or promotion decision.
- Freeze one candidate before any validation run.
- Do not use validation or locked-holdout outcomes for objective tuning.
