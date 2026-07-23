# Nested Clustered Minimum-Variance Promotion Research

- Split: `fama-french-38-source-30-complete-nco-research-1929-1969-v1`
- Namespace: `allocator-v2-nested-clustered-minvar-industry-portfolios`
- Gate: `rejected`
- Promotion eligible: `False`

## Portfolio

| Model | CAGR | Volatility | Sharpe | Max DD | Turnover |
|---|---:|---:|---:|---:|---:|
| equal_weight | 0.0767 | 0.1624 | 0.4525 | -0.8132 | 0.0116 |
| historical_bl | 0.0795 | 0.1752 | 0.4467 | -0.8368 | 0.0129 |
| min_variance | 0.0799 | 0.1183 | 0.5933 | -0.7810 | 0.1017 |
| risk_parity | 0.0772 | 0.1457 | 0.4900 | -0.7865 | 0.0170 |
| lightweight_bl | 0.0866 | 0.1735 | 0.4870 | -0.8176 | 0.1318 |
| nested_clustered_minimum_variance | 0.0762 | 0.1176 | 0.5671 | -0.7895 | 0.1365 |

## Paired vs min_variance

- P(lower volatility): `0.8665`
- P(higher Sharpe): `0.1390`

## Paired vs risk_parity

- P(lower volatility): `1.0000`
- P(higher Sharpe): `0.8500`

## Paired vs lightweight_bl

- P(lower volatility): `1.0000`
- P(higher Sharpe): `0.8455`

## Guardrail

- Candidate uses no return forecast or expected-return model.
- Configured guard baselines are deterministic checks.
- Validation remains sealed unless deterministic and 6-hypothesis Holm gates pass.
