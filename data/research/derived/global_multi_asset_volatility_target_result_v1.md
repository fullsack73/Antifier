# Risk Allocator Research

- Split: `global-multi-asset-volatility-target-research-2017-2025-v1`
- Namespace: `risk-v5-volatility-target-cash-fred-rf`
- Rows: 2262
- Tickers: 10
- Data promotion safe: `False`
- Split locked: `True`
- Risk gate passed: `False`
- Promotion eligible: `False`

## Performance

| Model | CAGR | Volatility | Sharpe | Sortino | Max DD | Daily CVaR | Risk exposure | Avg turnover | Risk MAE | P(vol lower) | P(Sharpe higher) | Gate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| equal_weight | 0.0728 | 0.0972 | 0.4956 | 0.6756 | -0.1940 | 0.0145 | 0.9310 | 0.0477 | 0.0360 | NA | NA | baseline |
| min_variance | 0.0605 | 0.0770 | 0.4522 | 0.6304 | -0.1766 | 0.0114 | 0.9558 | 0.1143 | 0.0234 | NA | NA | baseline |
| risk_parity | 0.0671 | 0.0827 | 0.5017 | 0.6982 | -0.1758 | 0.0122 | 0.9510 | 0.0655 | 0.0294 | NA | NA | baseline |
| momentum_6m | 0.0896 | 0.1019 | 0.6299 | 0.8672 | -0.1818 | 0.0153 | 0.9578 | 0.3224 | 0.0374 | NA | NA | baseline |
| volatility_targeted_min_variance | 0.0524 | 0.0671 | 0.3934 | 0.5426 | -0.1485 | 0.0099 | 0.8478 | 0.1391 | 0.0206 | 1.0000 | 0.2105 | rejected |

## Guardrail

- Research split only; no default or promotion change.
- A risk candidate must improve its closest baseline and survive the inverse-vol guard.
- Freeze a candidate before any validation run.
