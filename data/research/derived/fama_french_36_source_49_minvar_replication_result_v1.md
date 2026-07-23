# Plain Minimum-Variance Promotion Research

- Split: `fama-french-36-source-49-minvar-replication-1928-1969-v1`
- Namespace: `allocator-v1-minvar-default-independent-replication`
- Gate: `rejected`
- Promotion eligible: `False`

## Portfolio

| Model | CAGR | Volatility | Sharpe | Max DD | Turnover |
|---|---:|---:|---:|---:|---:|
| equal_weight | 0.0820 | 0.1492 | 0.5072 | -0.8005 | 0.0107 |
| historical_bl | 0.0907 | 0.1718 | 0.5080 | -0.8386 | 0.0167 |
| lightweight_bl | 0.0953 | 0.1695 | 0.5373 | -0.8393 | 0.1589 |
| risk_parity | 0.0810 | 0.1533 | 0.4912 | -0.8284 | 0.0148 |
| min_variance | 0.0853 | 0.1227 | 0.6119 | -0.7769 | 0.1281 |

## Paired vs lightweight_bl

- P(lower volatility): `1.0000`
- P(higher Sharpe): `0.8670`

## Paired vs risk_parity

- P(lower volatility): `1.0000`
- P(higher Sharpe): `0.9805`

## Guardrail

- Candidate uses no return forecast or expected-return model.
- Configured guard baselines are deterministic checks.
- Validation remains sealed unless deterministic and 4-hypothesis Holm gates pass.
