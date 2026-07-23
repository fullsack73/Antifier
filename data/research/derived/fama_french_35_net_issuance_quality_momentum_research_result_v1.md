# Net-Issuance Quality Momentum Research

- Split: `fama-french-35-net-issuance-quality-momentum-research-1969-1998-v1`
- Promotion eligible: `True`

## Signal quality

| Signal | Periods | Mean rank IC | Positive IC | Mean top-bottom | P(IC>0) | P(spread>0) | Gate |
|---|---:|---:|---:|---:|---:|---:|---|
| net_issuance_quality_momentum | 30 | 0.2476 | 0.7667 | 0.0586 | 1.0000 | 1.0000 | passed |
| net_issuance_quality | 30 | 0.2313 | 0.8333 | 0.0574 | 1.0000 | 1.0000 | rejected |
| momentum_12_1 | 30 | 0.1590 | 0.7000 | 0.0374 | 0.9945 | 0.9940 | passed |

## Candidate minus momentum

- Mean rank IC difference: `0.0885`
- Mean top-bottom difference: `0.0211`
- P(higher mean rank IC): `0.9760`
- P(higher mean spread): `0.9835`
- Paired gate: `passed`

## Guardrail

- 2000+ validation and holdout remain sealed after this research.
- Do not tune blend weight, horizon, or rebalance step on this result.
