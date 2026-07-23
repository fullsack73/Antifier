# James–Stein Mean Shrinkage Research

- Split: `fama-french-49-industry-james-stein-research-1983-1999-v1`
- Namespace: `mean-v1-james-stein-industry-portfolios`
- Candidate: `james_stein_bl`
- Closest baseline: `historical_bl`
- Locked research split: `True`
- Promotion eligible: `False`

## Performance

| Model | CAGR | Volatility | Sharpe | Max DD | Avg turnover |
|---|---:|---:|---:|---:|---:|
| equal_weight | 0.1428 | 0.1329 | 0.6345 | -0.3434 | 0.0184 |
| min_variance | 0.1033 | 0.1070 | 0.4301 | -0.3177 | 0.1640 |
| risk_parity | 0.1431 | 0.1266 | 0.6618 | -0.3297 | 0.0205 |
| historical_bl | 0.1521 | 0.1387 | 0.6725 | -0.3458 | 0.0215 |
| james_stein_bl | 0.1452 | 0.1346 | 0.6436 | -0.3445 | 0.0178 |

## Gate

- Deterministic: `rejected`
- Statistical: `rejected`
- Holm significant: `False`
- P(lower volatility): `1.0000`
- P(higher Sharpe): `0.0350`
- Mean shrinkage intensity: `0.4739`

## Decision

- Reject candidate; do not open validation or change the production default.

The candidate changes only the historical expected-return estimator. Covariance, Black–Litterman policy, constraints, execution controls, and costs match the baseline.
