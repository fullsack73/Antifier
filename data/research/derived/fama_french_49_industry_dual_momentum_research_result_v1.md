# Risk Allocator Research

- Split: `fama-french-49-industry-dual-momentum-research-2011-2017-v1`
- Namespace: `alpha-v7-dual-horizon-industry-portfolios`
- Rows: 2265
- Tickers: 49
- Data promotion safe: `True`
- Split locked: `True`
- Risk gate passed: `False`
- Promotion eligible: `False`

## Performance

| Model | CAGR | Volatility | Sharpe | Sortino | Max DD | Daily CVaR | Risk exposure | Avg turnover | Risk MAE | P(vol lower) | P(Sharpe higher) | Gate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| equal_weight | 0.1319 | 0.1522 | 0.8756 | 1.2276 | -0.2337 | 0.0233 | 0.9940 | 0.0365 | 0.0600 | NA | NA | baseline |
| min_variance | 0.1367 | 0.1130 | 1.1718 | 1.6742 | -0.1244 | 0.0167 | 0.9874 | 0.1392 | 0.0361 | NA | NA | baseline |
| risk_parity | 0.1352 | 0.1418 | 0.9500 | 1.3349 | -0.2107 | 0.0217 | 0.9742 | 0.0388 | 0.0550 | NA | NA | baseline |
| momentum_6m | 0.1245 | 0.1538 | 0.8259 | 1.1506 | -0.2416 | 0.0236 | 0.9793 | 0.1779 | 0.0606 | NA | NA | baseline |
| dual_horizon_momentum | 0.1217 | 0.1564 | 0.7987 | 1.1163 | -0.2537 | 0.0240 | 0.9815 | 0.1044 | 0.0614 | 0.0560 | 0.2200 | rejected |

## Guardrail

- Research split only; no default or promotion change.
- A risk candidate must improve its closest baseline and survive the inverse-vol guard.
- Freeze a candidate before any validation run.
