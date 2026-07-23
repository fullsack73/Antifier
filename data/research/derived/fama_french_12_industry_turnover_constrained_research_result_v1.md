# Turnover-Constrained Minimum-Variance Promotion Research

- Split: `fama-french-12-industry-turnover-constrained-research-2000-2011-v1`
- Namespace: `allocator-v4-turnover-constrained-minvar-industry-portfolios`
- Gate: `rejected`
- Promotion eligible: `False`

## Portfolio

| Model | CAGR | Volatility | Sharpe | Max DD | Turnover |
|---|---:|---:|---:|---:|---:|
| equal_weight | 0.0429 | 0.2023 | 0.1968 | -0.5220 | 0.0354 |
| historical_bl | 0.0418 | 0.1940 | 0.1914 | -0.4999 | 0.0284 |
| min_variance | 0.0660 | 0.1711 | 0.3265 | -0.4277 | 0.1144 |
| risk_parity | 0.0479 | 0.1944 | 0.2216 | -0.5143 | 0.0340 |
| lightweight_bl | 0.0371 | 0.2019 | 0.1695 | -0.5298 | 0.0581 |
| turnover_constrained_minimum_variance | 0.0660 | 0.1709 | 0.3272 | -0.4262 | 0.1171 |

## Paired vs min_variance

- P(lower volatility): `1.0000`
- P(higher Sharpe): `0.6025`

## Paired vs risk_parity

- P(lower volatility): `1.0000`
- P(higher Sharpe): `0.9610`

## Paired vs lightweight_bl

- P(lower volatility): `1.0000`
- P(higher Sharpe): `0.9805`

## Guardrail

- Candidate uses no return forecast or expected-return model.
- Configured guard baselines are deterministic checks.
- Validation remains sealed unless deterministic and 6-hypothesis Holm gates pass.
