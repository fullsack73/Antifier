# Risk Allocator Research

- Split: `fama-french-12-industry-conditional-volatility-research-2021-2025-v1`
- Namespace: `conditional-volatility-gmv-v1-fresh-industry-portfolios`
- Rows: 1760
- Tickers: 12
- Data promotion safe: `True`
- Split locked: `True`
- Risk gate passed: `False`
- Promotion eligible: `False`

## Performance

| Model | CAGR | Volatility | Sharpe | Sortino | Max DD | Daily CVaR | Risk exposure | Avg turnover | Risk MAE | P(vol lower) | P(Sharpe higher) | Gate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| equal_weight | 0.1192 | 0.1590 | 0.5817 | 0.8275 | -0.1947 | 0.0231 | 0.9999 | 0.0805 | 0.0722 | NA | NA | baseline |
| min_variance | 0.0343 | 0.1319 | 0.0731 | 0.1011 | -0.2144 | 0.0193 | 0.9999 | 0.1457 | 0.0581 | NA | NA | baseline |
| risk_parity | 0.0946 | 0.1481 | 0.4632 | 0.6551 | -0.2019 | 0.0217 | 0.9999 | 0.0655 | 0.0698 | NA | NA | baseline |
| momentum_6m | 0.1091 | 0.1647 | 0.5121 | 0.7238 | -0.1906 | 0.0235 | 0.9996 | 0.3626 | 0.0713 | NA | NA | baseline |
| conditional_volatility_minimum_variance | 0.0627 | 0.1323 | 0.2781 | 0.3873 | -0.1934 | 0.0194 | 0.9996 | 0.3821 | 0.0630 | 0.3585 | 0.9840 | rejected |

## Guardrail

- Research split only; no default or promotion change.
- A risk candidate must improve its closest baseline and survive the inverse-vol guard.
- Freeze a candidate before any validation run.
