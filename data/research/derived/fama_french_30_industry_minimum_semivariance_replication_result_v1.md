# Risk Allocator Research

- Split: `fama-french-30-industry-minimum-semivariance-replication-2000-2011-v1`
- Namespace: `allocator-v1-minimum-semivariance-independent-replication-30-industry-2000-2011`
- Rows: 3523
- Tickers: 30
- Data promotion safe: `True`
- Split locked: `True`
- Risk gate passed: `False`
- Promotion eligible: `False`

## Performance

| Model | CAGR | Volatility | Sharpe | Sortino | Max DD | Daily CVaR | Risk exposure | Avg turnover | Risk MAE | P(vol lower) | P(Sharpe higher) | Gate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| equal_weight | 0.0659 | 0.2127 | 0.2998 | 0.4191 | -0.5548 | 0.0322 | 1.0000 | 0.0312 | 0.0752 | NA | NA | baseline |
| min_variance | 0.0795 | 0.1523 | 0.4297 | 0.6056 | -0.3873 | 0.0228 | 0.9998 | 0.1830 | 0.0524 | NA | NA | baseline |
| risk_parity | 0.0634 | 0.2045 | 0.2922 | 0.4085 | -0.5467 | 0.0310 | 1.0000 | 0.0329 | 0.0731 | NA | NA | baseline |
| momentum_6m | 0.0665 | 0.2117 | 0.3030 | 0.4219 | -0.5400 | 0.0318 | 0.9997 | 0.2978 | 0.0748 | NA | NA | baseline |
| minimum_semivariance | 0.0807 | 0.1508 | 0.4397 | 0.6182 | -0.3810 | 0.0225 | 0.9998 | 0.1910 | 0.0517 | 1.0000 | 0.6935 | rejected |

## Guardrail

- Research split only; no default or promotion change.
- A risk candidate must improve its closest baseline and survive the inverse-vol guard.
- Freeze a candidate before any validation run.
