# Profitability-Momentum Research

- Split: `fama-french-25-size-profitability-momentum-research-1965-1999-v1`
- Promotion eligible: `False`
- Candidate gate: `passed`
- Paired improvement gate: `rejected`

## Signal quality

| Signal | Periods | Mean rank IC | Positive IC | Mean top-bottom | P(IC>0) | P(spread>0) |
|---|---:|---:|---:|---:|---:|---:|
| profitability_momentum | 137 | 0.0951 | 0.6350 | 0.0122 | 0.9990 | 1.0000 |
| momentum_12_1 | 137 | 0.1177 | 0.6204 | 0.0126 | 0.9990 | 0.9960 |

## Paired candidate minus baseline

- Mean rank IC difference: `-0.0226`
- Mean top-bottom difference: `-0.0004`
- P(higher mean rank IC): `0.2240`
- P(higher mean spread): `0.4505`
- Holm-adjusted p-value: `0.7760`

## Guardrail

- Portfolio validation is allowed only if candidate and paired gates pass.
- Do not tune blend weight, lookback, skip, or horizon on this result.
