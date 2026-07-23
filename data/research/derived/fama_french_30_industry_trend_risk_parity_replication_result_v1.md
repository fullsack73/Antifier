# Risk Allocator Research

- Split: `fama-french-30-industry-trend-risk-parity-replication-1928-1971-v1`
- Namespace: `risk-v9-trend-filtered-risk-parity-replication`
- Rows: 12332
- Tickers: 30
- Data promotion safe: `True`
- Split locked: `True`
- Risk gate passed: `True`
- Promotion eligible: `True`

## Performance

| Model | CAGR | Volatility | Sharpe | Sortino | Max DD | Daily CVaR | Risk exposure | Avg turnover | Risk MAE | P(vol lower) | P(Sharpe higher) | Gate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| equal_weight | 0.0802 | 0.1563 | 0.4722 | 0.6610 | -0.8257 | 0.0245 | 0.8991 | 0.0110 | 0.0436 | NA | NA | baseline |
| min_variance | 0.0926 | 0.1305 | 0.6252 | 0.8814 | -0.7904 | 0.0203 | 0.9909 | 0.0995 | 0.0377 | NA | NA | baseline |
| risk_parity | 0.0819 | 0.1524 | 0.4909 | 0.6894 | -0.8270 | 0.0239 | 0.9364 | 0.0165 | 0.0433 | NA | NA | baseline |
| momentum_6m | 0.1018 | 0.1698 | 0.5647 | 0.7873 | -0.8160 | 0.0267 | 0.9804 | 0.2307 | 0.0473 | NA | NA | baseline |
| trend_filtered_risk_parity | 0.0846 | 0.0974 | 0.7237 | 0.9645 | -0.3777 | 0.0153 | 0.6778 | 0.1070 | 0.0270 | 1.0000 | 0.9860 | passed |

## Guardrail

- Research split only; no default or promotion change.
- A risk candidate must improve its closest baseline and survive the inverse-vol guard.
- Freeze a candidate before any validation run.
