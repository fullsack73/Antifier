# Risk Allocator Research

- Split: `fama-french-49-industry-rmt-research-2000-2010-v1`
- Namespace: `risk-v7-rmt-industry-portfolios`
- Rows: 3271
- Tickers: 49
- Data promotion safe: `True`
- Split locked: `True`
- Risk gate passed: `False`
- Promotion eligible: `False`

## Performance

| Model | CAGR | Volatility | Sharpe | Sortino | Max DD | Daily CVaR | Risk exposure | Avg turnover | Risk MAE | P(vol lower) | P(Sharpe higher) | Gate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| equal_weight | 0.0731 | 0.1701 | 0.3548 | 0.4953 | -0.4629 | 0.0252 | 0.8911 | 0.0281 | 0.0564 | NA | NA | baseline |
| min_variance | 0.0805 | 0.1522 | 0.4227 | 0.5934 | -0.4355 | 0.0228 | 0.9965 | 0.1390 | 0.0501 | NA | NA | baseline |
| risk_parity | 0.0702 | 0.1732 | 0.3362 | 0.4701 | -0.4852 | 0.0258 | 0.9111 | 0.0299 | 0.0590 | NA | NA | baseline |
| momentum_6m | 0.0887 | 0.1988 | 0.4029 | 0.5652 | -0.5208 | 0.0297 | 0.9727 | 0.1266 | 0.0681 | NA | NA | baseline |
| random_matrix_minimum_variance | 0.0751 | 0.1533 | 0.3882 | 0.5469 | -0.4370 | 0.0228 | 0.9978 | 0.1589 | 0.0504 | 0.0315 | 0.2100 | rejected |

## Guardrail

- Research split only; no default or promotion change.
- A risk candidate must improve its closest baseline and survive the inverse-vol guard.
- Freeze a candidate before any validation run.
