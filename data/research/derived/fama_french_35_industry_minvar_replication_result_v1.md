# Plain Minimum-Variance Promotion Research

- Split: `fama-french-35-industry-minvar-replication-2012-2017-v1`
- Namespace: `allocator-v1-minvar-independent-replication-35-industry-2012-2017`
- Gate: `rejected`
- Promotion eligible: `False`

## Portfolio

| Model | CAGR | Volatility | Sharpe | Max DD | Turnover |
|---|---:|---:|---:|---:|---:|
| equal_weight | 0.1545 | 0.1312 | 1.1610 | -0.1569 | 0.0452 |
| historical_bl | 0.1504 | 0.1258 | 1.1764 | -0.1455 | 0.0484 |
| lightweight_bl | 0.1602 | 0.1289 | 1.2177 | -0.1397 | 0.1871 |
| risk_parity | 0.1523 | 0.1238 | 1.2071 | -0.1402 | 0.0434 |
| min_variance | 0.1268 | 0.1011 | 1.2318 | -0.0907 | 0.1631 |

## Paired vs lightweight_bl

- P(lower volatility): `1.0000`
- P(higher Sharpe): `0.5205`

## Paired vs risk_parity

- P(lower volatility): `1.0000`
- P(higher Sharpe): `0.5360`

## Guardrail

- Candidate uses no return forecast or expected-return model.
- Configured guard baselines are deterministic checks.
- Validation remains sealed unless deterministic and 4-hypothesis Holm gates pass.
