# Adaptive Value-Investment-Momentum Research

- Split: `fama-french-25-adaptive-value-investment-momentum-research-1968-1999-v1`
- Promotion eligible: `False`
- Candidate gate: `passed`
- Paired improvement gate: `rejected`

## Signal quality

| Signal | Periods | Mean rank IC | Positive IC | Mean top-bottom | P(IC>0) | P(spread>0) |
|---|---:|---:|---:|---:|---:|---:|
| adaptive_value_investment_momentum | 125 | 0.0698 | 0.5920 | 0.0118 | 0.9940 | 0.9985 |
| momentum_12_1 | 125 | 0.0627 | 0.6320 | 0.0083 | 0.9905 | 0.9840 |

## Paired candidate minus baseline

- Mean rank IC difference: `0.0071`
- Mean top-bottom difference: `0.0035`
- P(higher mean rank IC): `0.6400`
- P(higher mean spread): `0.8740`
- Holm-adjusted p-value: `0.3600`

## Guardrail

- Portfolio validation is allowed only if candidate and paired gates pass.
- Do not tune blend weight, lookback, skip, or horizon on this result.
