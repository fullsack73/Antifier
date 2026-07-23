# Risk Allocator Research

- Split: `fama-french-49-industry-trend-risk-parity-research-1973-1981-v1`
- Namespace: `risk-v9-trend-filtered-risk-parity-industry-portfolios`
- Rows: 2645
- Tickers: 49
- Data promotion safe: `True`
- Split locked: `True`
- Risk gate passed: `False`
- Promotion eligible: `False`

## Performance

| Model | CAGR | Volatility | Sharpe | Sortino | Max DD | Daily CVaR | Risk exposure | Avg turnover | Risk MAE | P(vol lower) | P(Sharpe higher) | Gate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| equal_weight | 0.0960 | 0.1368 | 0.1724 | 0.2385 | -0.4377 | 0.0198 | 0.9484 | 0.0330 | 0.0383 | NA | NA | baseline |
| min_variance | 0.1185 | 0.1106 | 0.3675 | 0.5036 | -0.3593 | 0.0166 | 0.9905 | 0.2013 | 0.0321 | NA | NA | baseline |
| risk_parity | 0.0962 | 0.1353 | 0.1738 | 0.2410 | -0.4334 | 0.0195 | 0.9828 | 0.0344 | 0.0386 | NA | NA | baseline |
| momentum_6m | 0.1114 | 0.1412 | 0.2704 | 0.3739 | -0.4012 | 0.0205 | 0.9856 | 0.1615 | 0.0404 | NA | NA | baseline |
| trend_filtered_risk_parity | 0.1063 | 0.0743 | 0.3544 | 0.4847 | -0.1454 | 0.0111 | 0.5934 | 0.0815 | 0.0205 | 1.0000 | 0.7555 | rejected |

## Guardrail

- Research split only; no default or promotion change.
- A risk candidate must improve its closest baseline and survive the inverse-vol guard.
- Freeze a candidate before any validation run.
