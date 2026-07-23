# Value-Quality-Momentum Research

- Split: `fama-french-25-value-quality-momentum-research-1965-1999-v1`
- Promotion eligible: `True`
- Candidate gate: `passed`
- Paired improvement gate: `passed`

## Signal quality

| Signal | Periods | Mean rank IC | Positive IC | Mean top-bottom | P(IC>0) | P(spread>0) |
|---|---:|---:|---:|---:|---:|---:|
| value_quality_momentum | 137 | 0.1238 | 0.6350 | 0.0205 | 1.0000 | 1.0000 |
| momentum_12_1 | 137 | 0.0780 | 0.5839 | 0.0141 | 0.9995 | 0.9980 |

## Paired candidate minus baseline

- Mean rank IC difference: `0.0458`
- Mean top-bottom difference: `0.0064`
- P(higher mean rank IC): `0.9820`
- P(higher mean spread): `0.9575`
- Holm-adjusted p-value: `0.0425`

## Guardrail

- Portfolio validation is allowed only if candidate and paired gates pass.
- Do not tune blend weight, lookback, skip, or horizon on this result.
