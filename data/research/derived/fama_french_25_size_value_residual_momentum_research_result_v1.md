# Factor-Residual Momentum Research

- Split: `fama-french-25-size-value-residual-momentum-research-1935-1970-v1`
- Promotion eligible: `False`
- Candidate gate: `rejected`
- Paired improvement gate: `rejected`

## Signal quality

| Signal | Periods | Mean rank IC | Positive IC | Mean top-bottom | P(IC>0) | P(spread>0) |
|---|---:|---:|---:|---:|---:|---:|
| factor_residual_momentum | 154 | 0.0119 | 0.5260 | -0.0008 | 0.7370 | 0.3725 |
| momentum_12_1 | 154 | 0.0613 | 0.5649 | 0.0070 | 0.9760 | 0.9420 |

## Paired candidate minus baseline

- Mean rank IC difference: `-0.0494`
- Mean top-bottom difference: `-0.0078`
- P(higher mean rank IC): `0.0540`
- P(higher mean spread): `0.0565`
- Holm-adjusted p-value: `0.9460`

## Guardrail

- Portfolio validation is allowed only if candidate and paired gates pass.
- Do not tune lookbacks or factor set on this result.
