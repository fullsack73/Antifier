# Risk Allocator Research

- Split: `global-multi-asset-volatility-target-research-2017-2025-v2`
- Namespace: `risk-v6-volatility-target-initial-deployment-fred-rf`
- Rows: 2262
- Tickers: 10
- Data promotion safe: `False`
- Split locked: `True`
- Risk gate passed: `False`
- Promotion eligible: `False`

## Performance

| Model | CAGR | Volatility | Sharpe | Sortino | Max DD | Daily CVaR | Risk exposure | Avg turnover | Risk MAE | P(vol lower) | P(Sharpe higher) | Gate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| equal_weight | 0.0833 | 0.0988 | 0.5870 | 0.8022 | -0.1976 | 0.0146 | 0.9630 | 0.0509 | 0.0368 | NA | NA | baseline |
| min_variance | 0.0653 | 0.0774 | 0.5083 | 0.7094 | -0.1760 | 0.0114 | 0.9788 | 0.1194 | 0.0233 | NA | NA | baseline |
| risk_parity | 0.0700 | 0.0860 | 0.5170 | 0.7147 | -0.1878 | 0.0127 | 0.9933 | 0.0619 | 0.0307 | NA | NA | baseline |
| momentum_6m | 0.0971 | 0.1029 | 0.6907 | 0.9525 | -0.1833 | 0.0153 | 0.9971 | 0.3436 | 0.0377 | NA | NA | baseline |
| volatility_targeted_min_variance | 0.0561 | 0.0673 | 0.4449 | 0.6145 | -0.1480 | 0.0099 | 0.8737 | 0.1429 | 0.0207 | 1.0000 | 0.1980 | rejected |

## Guardrail

- Research split only; no default or promotion change.
- A risk candidate must improve its closest baseline and survive the inverse-vol guard.
- Freeze a candidate before any validation run.
