# Long-Term Reversal Momentum Research

- Split: `fama-french-25-long-term-reversal-momentum-research-1983-1998-v1`
- Promotion eligible: `False`

## Signal quality

| Signal | Periods | Mean rank IC | Positive IC | Mean top-bottom | P(IC>0) | P(spread>0) | Gate |
|---|---:|---:|---:|---:|---:|---:|---|
| long_term_reversal_momentum | 16 | 0.1200 | 0.6250 | 0.0439 | 0.9005 | 0.9710 | rejected |
| long_term_reversal | 16 | 0.0630 | 0.6875 | 0.0266 | 0.6765 | 0.7425 | rejected |
| momentum_12_1 | 16 | 0.1636 | 0.6875 | 0.0234 | 0.9955 | 0.8220 | rejected |

## Candidate minus momentum

- Mean rank IC difference: `-0.0435`
- Mean top-bottom difference: `0.0205`
- P(higher mean rank IC): `0.3605`
- P(higher mean spread): `0.6870`
- Paired gate: `rejected`

## Guardrail

- 2000+ validation and holdout remain sealed after this research.
- Do not tune blend weight, horizon, or rebalance step on this result.
