# Constant-Correlation Minimum-Variance Promotion Research

- Split: `fama-french-38-source-33-complete-constant-correlation-research-1971-1980-v1`
- Namespace: `allocator-v3-constant-correlation-minvar-industry-portfolios`
- Gate: `rejected`
- Promotion eligible: `False`

## Portfolio

| Model | CAGR | Volatility | Sharpe | Max DD | Turnover |
|---|---:|---:|---:|---:|---:|
| equal_weight | 0.0896 | 0.1271 | 0.2080 | -0.4516 | 0.0311 |
| historical_bl | 0.0917 | 0.1343 | 0.2180 | -0.4728 | 0.0328 |
| min_variance | 0.1034 | 0.1033 | 0.3514 | -0.3465 | 0.1903 |
| risk_parity | 0.0886 | 0.1217 | 0.2038 | -0.4419 | 0.0354 |
| lightweight_bl | 0.0968 | 0.1333 | 0.2535 | -0.4432 | 0.1868 |
| constant_correlation_minimum_variance | 0.1056 | 0.1024 | 0.3729 | -0.3459 | 0.2006 |

## Paired vs min_variance

- P(lower volatility): `1.0000`
- P(higher Sharpe): `0.8985`

## Paired vs risk_parity

- P(lower volatility): `1.0000`
- P(higher Sharpe): `0.8565`

## Paired vs lightweight_bl

- P(lower volatility): `1.0000`
- P(higher Sharpe): `0.7690`

## Guardrail

- Candidate uses no return forecast or expected-return model.
- Configured guard baselines are deterministic checks.
- Validation remains sealed unless deterministic and 6-hypothesis Holm gates pass.
