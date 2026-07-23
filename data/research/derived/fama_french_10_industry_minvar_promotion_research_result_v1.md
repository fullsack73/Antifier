# Plain Minimum-Variance Promotion Research

- Split: `fama-french-10-industry-minvar-promotion-research-2000-2011-v1`
- Namespace: `allocator-v1-minvar-default-industry-portfolios`
- Gate: `rejected`
- Promotion eligible: `False`

## Portfolio

| Model | CAGR | Volatility | Sharpe | Max DD | Turnover |
|---|---:|---:|---:|---:|---:|
| equal_weight | 0.0435 | 0.2006 | 0.1997 | -0.5122 | 0.0350 |
| historical_bl | 0.0427 | 0.1980 | 0.1961 | -0.5060 | 0.0294 |
| lightweight_bl | 0.0401 | 0.2000 | 0.1834 | -0.5169 | 0.0530 |
| risk_parity | 0.0542 | 0.1865 | 0.2551 | -0.4834 | 0.0399 |
| min_variance | 0.0661 | 0.1734 | 0.3254 | -0.4319 | 0.1117 |

## Paired vs lightweight_bl

- P(lower volatility): `1.0000`
- P(higher Sharpe): `0.9795`

## Paired vs risk_parity

- P(lower volatility): `1.0000`
- P(higher Sharpe): `0.9150`

## Guardrail

- Candidate uses no return forecast or expected-return model.
- Equal weight and historical BL are deterministic guards.
- Validation remains sealed unless deterministic and four-hypothesis Holm gates pass.
