# Accrual-Quality Momentum Research

- Split: `fama-french-25-size-accrual-quality-momentum-research-1969-1998-v1`
- Promotion eligible: `False`
- Economic benchmark only: French working-capital accrual is related to, but not identical with, SEC cash-accrual quality.

## Signal quality

| Signal | Periods | Mean rank IC | Positive IC | Mean top-bottom | P(IC>0) | P(spread>0) | Gate |
|---|---:|---:|---:|---:|---:|---:|---|
| accrual_quality_momentum | 30 | 0.2044 | 0.7667 | 0.0434 | 1.0000 | 0.9845 | passed |
| accrual_quality | 30 | 0.1636 | 0.7667 | 0.0378 | 1.0000 | 1.0000 | rejected |
| momentum_12_1 | 30 | 0.1405 | 0.6333 | 0.0337 | 0.9785 | 0.9415 | rejected |

## Candidate minus momentum

- Mean rank IC difference: `0.0639`
- Mean top-bottom difference: `0.0097`
- P(higher mean rank IC): `0.9550`
- P(higher mean spread): `0.8475`
- Paired gate: `rejected`

## Guardrail

- 2000+ validation and holdout remain sealed after this research.
- Do not tune blend weight, horizon, or rebalance step on this result.
