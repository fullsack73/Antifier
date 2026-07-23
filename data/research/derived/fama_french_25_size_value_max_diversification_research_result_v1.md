# Risk Allocator Research

- Split: `fama-french-25-size-value-max-diversification-research-1971-1999-v1`
- Namespace: `risk-v10-maximum-diversification-size-value`
- Rows: 7832
- Tickers: 25
- Data promotion safe: `True`
- Split locked: `True`
- Risk gate passed: `False`
- Promotion eligible: `False`

## Performance

| Model | CAGR | Volatility | Sharpe | Sortino | Max DD | Daily CVaR | Risk exposure | Avg turnover | Risk MAE | P(vol lower) | P(Sharpe higher) | Gate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| equal_weight | 0.1482 | 0.1183 | 0.6871 | 0.9273 | -0.5001 | 0.0178 | 0.9721 | 0.0123 | 0.0351 | NA | NA | baseline |
| min_variance | 0.1623 | 0.1063 | 0.8663 | 1.1687 | -0.3952 | 0.0161 | 0.9897 | 0.1065 | 0.0326 | NA | NA | baseline |
| risk_parity | 0.1513 | 0.1166 | 0.7188 | 0.9692 | -0.4691 | 0.0176 | 0.9758 | 0.0129 | 0.0348 | NA | NA | baseline |
| momentum_6m | 0.1538 | 0.1216 | 0.7117 | 0.9615 | -0.4689 | 0.0184 | 0.9850 | 0.2590 | 0.0360 | NA | NA | baseline |
| maximum_diversification | 0.1529 | 0.1150 | 0.7387 | 1.0024 | -0.4267 | 0.0171 | 0.9938 | 0.1173 | 0.0337 | 0.9995 | 0.7555 | rejected |

## Guardrail

- Research split only; no default or promotion change.
- A risk candidate must improve its closest baseline and survive the inverse-vol guard.
- Freeze a candidate before any validation run.
