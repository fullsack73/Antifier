# Risk Allocator Research

- Split: `fama-french-49-industry-trend-minvar-research-1983-1999-v1`
- Namespace: `risk-v8-trend-filtered-minvar-industry-portfolios`
- Rows: 4635
- Tickers: 49
- Data promotion safe: `True`
- Split locked: `True`
- Risk gate passed: `False`
- Promotion eligible: `False`

## Performance

| Model | CAGR | Volatility | Sharpe | Sortino | Max DD | Daily CVaR | Risk exposure | Avg turnover | Risk MAE | P(vol lower) | P(Sharpe higher) | Gate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| equal_weight | 0.1428 | 0.1329 | 0.6345 | 0.8483 | -0.3434 | 0.0193 | 0.9551 | 0.0184 | 0.0406 | NA | NA | baseline |
| min_variance | 0.1033 | 0.1070 | 0.4301 | 0.5592 | -0.3177 | 0.0161 | 0.9955 | 0.1640 | 0.0311 | NA | NA | baseline |
| risk_parity | 0.1431 | 0.1266 | 0.6618 | 0.8852 | -0.3297 | 0.0184 | 0.9302 | 0.0205 | 0.0389 | NA | NA | baseline |
| momentum_6m | 0.1480 | 0.1367 | 0.6544 | 0.8746 | -0.3553 | 0.0200 | 0.9848 | 0.1344 | 0.0413 | NA | NA | baseline |
| trend_filtered_minimum_variance | 0.1027 | 0.0879 | 0.4957 | 0.6420 | -0.2848 | 0.0132 | 0.7880 | 0.2554 | 0.0227 | 1.0000 | 0.7345 | rejected |

## Guardrail

- Research split only; no default or promotion change.
- A risk candidate must improve its closest baseline and survive the inverse-vol guard.
- Freeze a candidate before any validation run.
