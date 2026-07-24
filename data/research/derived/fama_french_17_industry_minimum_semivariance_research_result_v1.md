# Risk Allocator Research

- Split: `fama-french-17-industry-minimum-semivariance-research-2012-2017-v1`
- Namespace: `allocator-v1-minimum-semivariance-17-industry-2012-2017`
- Rows: 2013
- Tickers: 17
- Data promotion safe: `True`
- Split locked: `True`
- Risk gate passed: `False`
- Promotion eligible: `False`

## Performance

| Model | CAGR | Volatility | Sharpe | Sortino | Max DD | Daily CVaR | Risk exposure | Avg turnover | Risk MAE | P(vol lower) | P(Sharpe higher) | Gate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| equal_weight | 0.1431 | 0.1310 | 1.0678 | 1.5321 | -0.1793 | 0.0191 | 1.0000 | 0.0492 | 0.0531 | NA | NA | baseline |
| min_variance | 0.1453 | 0.1041 | 1.3311 | 1.9469 | -0.1001 | 0.0149 | 0.9999 | 0.1034 | 0.0372 | NA | NA | baseline |
| risk_parity | 0.1474 | 0.1238 | 1.1532 | 1.6572 | -0.1528 | 0.0182 | 1.0000 | 0.0470 | 0.0497 | NA | NA | baseline |
| momentum_6m | 0.1475 | 0.1286 | 1.1155 | 1.5905 | -0.1459 | 0.0191 | 0.9996 | 0.3548 | 0.0502 | NA | NA | baseline |
| minimum_semivariance | 0.1473 | 0.1041 | 1.3485 | 1.9742 | -0.0990 | 0.0149 | 0.9999 | 0.1140 | 0.0370 | 0.5225 | 0.7440 | rejected |

## Guardrail

- Research split only; no default or promotion change.
- A risk candidate must improve its closest baseline and survive the inverse-vol guard.
- Freeze a candidate before any validation run.
