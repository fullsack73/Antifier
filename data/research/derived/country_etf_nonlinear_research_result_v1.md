# Cross-sectional Forecast Research

- Split: `country-etf-nonlinear-research-2010-2016-v1`
- Namespace: `price-v1-relative-hist-gradient-boosting-country-etf`
- Price rows: 4780
- Tickers: 15
- Selection: `no_signal_candidate`
- Data promotion safe: `False`
- Split locked: `True`
- Signal gate passed: `False`
- Promotion eligible: `False`

## Signal-only comparison

| Objective | Gate | Periods | Rank IC | P(IC>0) | Positive IC | Top-bottom | P(Spread>0) | Coverage | OOS radius | Fits | Seconds | Peak MiB |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| relative_ridge | rejected | 27 | 0.0164 | 0.6795 | 0.4815 | -0.0030 | 0.3580 | 1.0000 | 0.0656 | 27 | 3.65 | 6.81 |
| relative_hist_gradient_boosting | rejected | 27 | -0.0139 | 0.3980 | 0.5185 | 0.0001 | 0.5090 | 1.0000 | 0.0664 | 27 | 8.23 | 6.79 |

## Paired candidate improvement

| Comparison | Gate | Δ rank IC | P(higher IC) | Δ spread | P(higher spread) |
|---|---|---:|---:|---:|---:|
| relative_hist_gradient_boosting_vs_relative_ridge | rejected | -0.0303 | 0.2565 | 0.0031 | 0.5735 |

## Guardrail

- Research split only; no portfolio construction or promotion decision.
- Freeze one candidate before any validation run.
- Do not use validation or locked-holdout outcomes for objective tuning.
