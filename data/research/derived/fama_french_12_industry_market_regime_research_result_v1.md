# Cross-sectional Forecast Research

- Split: `fama-french-12-industry-market-regime-research-1933-1952-v1`
- Namespace: `alpha-v14-market-regime-interactions`
- Price rows: 12332
- Tickers: 12
- Selection: `no_signal_candidate`
- Data promotion safe: `True`
- Split locked: `True`
- Signal gate passed: `False`
- Promotion eligible: `False`

## Signal-only comparison

| Objective | Gate | Periods | Rank IC | P(IC>0) | Positive IC | Top-bottom | P(Spread>0) | Coverage | OOS radius | Fits | Seconds | Peak MiB |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| relative_nested_ridge | rejected | 93 | 0.0193 | 0.6965 | 0.5161 | 0.0044 | 0.7500 | 1.0000 | 0.0639 | 93 | 32.68 | 15.13 |
| relative_market_regime_nested_ridge | rejected | 93 | 0.0050 | 0.5520 | 0.4946 | 0.0029 | 0.6345 | 1.0000 | 0.0650 | 93 | 50.64 | 23.52 |

## Paired candidate improvement

| Comparison | Gate | Δ rank IC | P(higher IC) | Δ spread | P(higher spread) |
|---|---|---:|---:|---:|---:|
| relative_market_regime_nested_ridge_vs_relative_nested_ridge | rejected | -0.0144 | 0.3575 | -0.0016 | 0.4025 |

## Guardrail

- Research split only; no portfolio construction or promotion decision.
- Freeze one candidate before any validation run.
- Do not use validation or locked-holdout outcomes for objective tuning.
