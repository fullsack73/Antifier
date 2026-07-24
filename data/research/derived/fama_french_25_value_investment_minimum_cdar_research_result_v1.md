# Risk Allocator Research

- Split: `fama-french-25-value-investment-minimum-cdar-research-2000-2011-v1`
- Namespace: `allocator-v1-minimum-cdar-value-investment-2000-2011`
- Rows: 3523
- Tickers: 25
- Data promotion safe: `True`
- Split locked: `True`
- Risk gate passed: `False`
- Promotion eligible: `False`

## Performance

| Model | CAGR | Volatility | Sharpe | Sortino | Max DD | Daily CVaR | Risk exposure | Avg turnover | Risk MAE | P(vol lower) | P(Sharpe higher) | Gate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| equal_weight | 0.0578 | 0.2253 | 0.2617 | 0.3666 | -0.5965 | 0.0342 | 1.0000 | 0.0276 | 0.0850 | NA | NA | baseline |
| min_variance | 0.0754 | 0.1970 | 0.3525 | 0.4936 | -0.5588 | 0.0300 | 0.9997 | 0.2678 | 0.0706 | NA | NA | baseline |
| risk_parity | 0.0625 | 0.2220 | 0.2824 | 0.3956 | -0.5895 | 0.0337 | 1.0000 | 0.0322 | 0.0832 | NA | NA | baseline |
| momentum_6m | 0.0690 | 0.2192 | 0.3110 | 0.4366 | -0.5740 | 0.0330 | 0.9997 | 0.3067 | 0.0825 | NA | NA | baseline |
| minimum_cdar | 0.0518 | 0.2074 | 0.2381 | 0.3338 | -0.5673 | 0.0313 | 0.9997 | 0.3256 | 0.0746 | 0.0000 | 0.0155 | rejected |

## Guardrail

- Research split only; no default or promotion change.
- A risk candidate must improve its closest baseline and survive the inverse-vol guard.
- Freeze a candidate before any validation run.
