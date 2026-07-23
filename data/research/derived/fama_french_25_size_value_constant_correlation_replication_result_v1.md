# Constant-Correlation Minimum-Variance Promotion Research

- Split: `fama-french-25-size-value-constant-correlation-replication-2000-2011-v1`
- Namespace: `allocator-v3-constant-correlation-minvar-size-value-replication`
- Gate: `rejected`
- Promotion eligible: `False`

## Portfolio

| Model | CAGR | Volatility | Sharpe | Max DD | Turnover |
|---|---:|---:|---:|---:|---:|
| equal_weight | 0.0718 | 0.2371 | 0.3158 | -0.5914 | 0.0251 |
| historical_bl | 0.0684 | 0.2371 | 0.3026 | -0.5949 | 0.0245 |
| min_variance | 0.1055 | 0.2053 | 0.4811 | -0.5534 | 0.2056 |
| risk_parity | 0.0774 | 0.2320 | 0.3401 | -0.5949 | 0.0309 |
| lightweight_bl | 0.0661 | 0.2343 | 0.2941 | -0.5844 | 0.1131 |
| constant_correlation_minimum_variance | 0.1064 | 0.2046 | 0.4860 | -0.5497 | 0.2040 |

## Paired vs min_variance

- P(lower volatility): `0.9685`
- P(higher Sharpe): `0.8300`

## Paired vs risk_parity

- P(lower volatility): `1.0000`
- P(higher Sharpe): `0.9995`

## Paired vs lightweight_bl

- P(lower volatility): `1.0000`
- P(higher Sharpe): `0.9995`

## Guardrail

- Candidate uses no return forecast or expected-return model.
- Configured guard baselines are deterministic checks.
- Validation remains sealed unless deterministic and 6-hypothesis Holm gates pass.
