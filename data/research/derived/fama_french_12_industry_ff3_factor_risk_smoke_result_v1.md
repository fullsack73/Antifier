# Risk Allocator Research

- Split: `fama-french-12-industry-ff3-factor-risk-smoke-2021-2025-v1`
- Namespace: `ff3-factor-risk-gmv-v1-consumed-smoke`
- Rows: 1760
- Tickers: 12
- Data promotion safe: `True`
- Manifest locked: `True`
- Promotion safe: `False`
- Risk gate passed: `False`
- Promotion eligible: `False`

## Performance

| Model | CAGR | Volatility | Sharpe | Sortino | Max DD | Daily CVaR | Risk exposure | Avg turnover | Risk MAE | P(vol lower) | P(Sharpe higher) | Gate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| equal_weight | 0.1192 | 0.1590 | 0.5817 | 0.8275 | -0.1947 | 0.0231 | 0.9999 | 0.0805 | 0.0722 | NA | NA | baseline |
| min_variance | 0.0343 | 0.1319 | 0.0731 | 0.1011 | -0.2144 | 0.0193 | 0.9999 | 0.1457 | 0.0581 | NA | NA | baseline |
| risk_parity | 0.0946 | 0.1481 | 0.4632 | 0.6551 | -0.2019 | 0.0217 | 0.9999 | 0.0655 | 0.0698 | NA | NA | baseline |
| momentum_6m | 0.1091 | 0.1647 | 0.5121 | 0.7238 | -0.1906 | 0.0235 | 0.9996 | 0.3626 | 0.0713 | NA | NA | baseline |
| factor_model_minimum_variance | 0.0411 | 0.1297 | 0.1224 | 0.1694 | -0.1960 | 0.0186 | 0.9999 | 0.1083 | 0.0335 | 0.9290 | 0.8100 | rejected |

## FF3 diagnostics

```json
{
  "rebalance_count": 20,
  "estimated_count": 20,
  "fallback_count": 0,
  "fallback_rate": 0.0,
  "fallback_reasons": {},
  "average_covariance_condition_number": 63.17848239237846,
  "average_covariance_effective_rank": 3.9749097144884074,
  "factor_exposure_stability": {
    "successive_ticker_pair_count": 228,
    "mean_l2_change": 0.05292230740645629,
    "median_l2_change": 0.040286268206208384,
    "mean_absolute_change_by_factor": {
      "mkt_rf": 0.026029647246868542,
      "smb": 0.028123748873419306,
      "hml": 0.023800337520997316
    }
  }
}
```

## Guardrail

- Research split only; no default or promotion change.
- A risk candidate must improve its closest baseline and survive the inverse-vol guard.
- Freeze a candidate before any validation run.
