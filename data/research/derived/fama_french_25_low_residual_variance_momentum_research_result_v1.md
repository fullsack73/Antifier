# Low Residual-Variance Momentum Research

- Split: `fama-french-25-low-residual-variance-momentum-research-1969-1989-v1`
- Promotion eligible: `False`

## Signal quality

| Signal | Periods | Mean rank IC | Positive IC | Mean top-bottom | P(IC>0) | P(spread>0) | Gate |
|---|---:|---:|---:|---:|---:|---:|---|
| low_residual_variance_momentum | 82 | 0.2800 | 0.7317 | 0.0360 | 1.0000 | 1.0000 | passed |
| low_residual_variance | 82 | 0.2267 | 0.6951 | 0.0277 | 1.0000 | 0.9995 | rejected |
| momentum_12_1 | 82 | 0.2450 | 0.7073 | 0.0325 | 1.0000 | 1.0000 | passed |

## Candidate minus momentum

- Mean rank IC difference: `0.0351`
- Mean top-bottom difference: `0.0035`
- P(higher mean rank IC): `0.8075`
- P(higher mean spread): `0.7715`
- Paired gate: `rejected`

## Guardrail

- 2000+ validation and holdout remain sealed after this research.
- Do not tune blend weight, horizon, or rebalance step on this result.
