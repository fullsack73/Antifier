# Quality-Momentum Research

- Split: `fama-french-25-quality-momentum-research-1965-1999-v1`
- Promotion eligible: `True`
- Candidate gate: `passed`
- Paired improvement gate: `passed`

## Signal quality

| Signal | Periods | Mean rank IC | Positive IC | Mean top-bottom | P(IC>0) | P(spread>0) |
|---|---:|---:|---:|---:|---:|---:|
| quality_momentum | 137 | 0.1085 | 0.6131 | 0.0130 | 0.9995 | 0.9985 |
| momentum_12_1 | 137 | 0.0668 | 0.5839 | 0.0070 | 0.9965 | 0.9810 |

## Paired candidate minus baseline

- Mean rank IC difference: `0.0417`
- Mean top-bottom difference: `0.0061`
- P(higher mean rank IC): `0.9795`
- P(higher mean spread): `0.9855`
- Holm-adjusted p-value: `0.0205`

## Guardrail

- Portfolio validation is allowed only if candidate and paired gates pass.
- Do not tune blend weight, lookback, skip, or horizon on this result.
