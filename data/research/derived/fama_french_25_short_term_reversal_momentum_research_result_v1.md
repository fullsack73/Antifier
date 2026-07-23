# Short-Term Reversal Momentum Research

- Split: `fama-french-25-short-term-reversal-momentum-research-1932-1955-v1`
- Promotion eligible: `True`

## Signal quality

| Signal | Periods | Mean rank IC | Positive IC | Mean top-bottom | P(IC>0) | P(spread>0) | Gate |
|---|---:|---:|---:|---:|---:|---:|---|
| short_term_reversal_momentum | 287 | 0.2251 | 0.7456 | 0.0219 | 1.0000 | 1.0000 | passed |
| short_term_reversal | 287 | 0.2311 | 0.7247 | 0.0215 | 1.0000 | 1.0000 | rejected |
| momentum_12_1 | 287 | 0.1644 | 0.6899 | 0.0164 | 1.0000 | 1.0000 | passed |

## Candidate minus momentum

- Mean rank IC difference: `0.0606`
- Mean top-bottom difference: `0.0054`
- P(higher mean rank IC): `1.0000`
- P(higher mean spread): `1.0000`
- Paired gate: `passed`

## Guardrail

- 2000+ validation and holdout remain sealed after this research.
- Do not tune blend weight, horizon, or rebalance step on this result.
