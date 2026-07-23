# Risk Allocator Research

- Split: `global-multi-asset-scenario-robust-research-2008-2016-v4`
- Namespace: `risk-v4-scenario-worst-case-fred-rf`
- Rows: 2267
- Tickers: 10
- Data promotion safe: `False`
- Split locked: `True`
- Risk gate passed: `False`
- Promotion eligible: `False`

## Performance

| Model | CAGR | Volatility | Sharpe | Sortino | Max DD | Daily CVaR | Avg turnover | Risk MAE | P(vol lower) | P(Sharpe higher) | Gate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| equal_weight | 0.0520 | 0.0817 | 0.6487 | 0.9254 | -0.1346 | 0.0119 | 0.0481 | 0.0441 | NA | NA | baseline |
| min_variance | 0.0544 | 0.0501 | 1.0605 | 1.5339 | -0.0938 | 0.0073 | 0.0731 | 0.0177 | NA | NA | baseline |
| risk_parity | 0.0513 | 0.0590 | 0.8591 | 1.2377 | -0.1018 | 0.0086 | 0.0499 | 0.0263 | NA | NA | baseline |
| momentum_6m | 0.0363 | 0.0863 | 0.4437 | 0.6116 | -0.1104 | 0.0135 | 0.3178 | 0.0494 | NA | NA | baseline |
| scenario_robust_min_variance | 0.0526 | 0.0508 | 1.0126 | 1.4597 | -0.0987 | 0.0074 | 0.0815 | 0.0178 | 0.0015 | 0.1030 | rejected |

## Guardrail

- Research split only; no default or promotion change.
- A risk candidate must improve its closest baseline and survive the inverse-vol guard.
- Freeze a candidate before any validation run.
