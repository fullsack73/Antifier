# Cashflow-Yield Momentum Research

- Split: `fama-french-cashflow-yield-momentum-research-1969-1998-v1`
- Promotion eligible: `False`

## Signal quality

| Signal | Periods | Mean rank IC | Positive IC | Mean top-bottom | P(IC>0) | P(spread>0) | Gate |
|---|---:|---:|---:|---:|---:|---:|---|
| cashflow_yield_momentum | 30 | 0.0970 | 0.6000 | 0.0178 | 0.8315 | 0.7555 | rejected |
| cashflow_yield | 30 | 0.2291 | 0.6333 | 0.0480 | 0.9745 | 0.9415 | rejected |
| momentum_12_1 | 30 | -0.0869 | 0.4667 | -0.0270 | 0.1780 | 0.1215 | rejected |

## Candidate minus momentum

- Mean rank IC difference: `0.1839`
- Mean top-bottom difference: `0.0447`
- P(higher mean rank IC): `0.9960`
- P(higher mean spread): `0.9995`
- Paired gate: `passed`

## Guardrail

- 2000+ validation and holdout remain sealed after this research.
- Do not tune blend weight, horizon, or rebalance step on this result.
