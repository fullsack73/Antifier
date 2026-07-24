# Cashflow-Yield Momentum Research

- Split: `fama-french-6-size-cashflow-yield-only-research-2000-2011-v1`
- Promotion eligible: `False`

## Signal quality

| Signal | Periods | Mean rank IC | Positive IC | Mean top-bottom | P(IC>0) | P(spread>0) | Gate |
|---|---:|---:|---:|---:|---:|---:|---|
| cashflow_yield_only | 12 | 0.3287 | 0.6667 | 0.0681 | 1.0000 | 1.0000 | rejected |
| cashflow_yield | 12 | 0.3287 | 0.6667 | 0.0681 | 1.0000 | 1.0000 | rejected |
| momentum_12_1 | 12 | 0.1952 | 0.7500 | 0.0374 | 0.9485 | 0.9315 | rejected |

## Candidate minus momentum

- Mean rank IC difference: `0.1334`
- Mean top-bottom difference: `0.0306`
- P(higher mean rank IC): `0.8005`
- P(higher mean spread): `0.7660`
- Paired gate: `rejected`

## Guardrail

- 2000+ validation and holdout remain sealed after this research.
- Do not tune blend weight, horizon, or rebalance step on this result.
