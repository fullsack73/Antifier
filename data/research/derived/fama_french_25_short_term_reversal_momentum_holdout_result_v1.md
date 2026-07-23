# Frozen Short-Term Reversal-Momentum Locked Holdout

- Split: `fama-french-25-short-term-reversal-momentum-holdout-1971-1982-v1`
- Frozen from: `fama-french-25-short-term-reversal-momentum-research-1932-1955-v1`
- Passed cases: 3 / 4
- Aggregate gate: `rejected`
- Promotion eligible: `False`

## Cases

| Case | Candidate IC | Baseline IC | Candidate spread | Baseline spread | Gate |
|---|---:|---:|---:|---:|---|
| small_size | 0.3124 | 0.2809 | 0.0183 | 0.0155 | passed |
| large_size | 0.1194 | 0.0895 | 0.0068 | 0.0036 | passed |
| prior_losers | 0.1778 | 0.1861 | 0.0116 | 0.0102 | rejected |
| prior_winners | 0.1836 | 0.1696 | 0.0088 | 0.0065 | passed |

## Aggregate

- P(higher mean rank IC): `0.7045`
- P(higher mean spread): `0.8475`
- Holm-adjusted p-value: `0.2955`

## Decision

- All four deterministic cases and aggregate statistical gate must pass.
- This is the final locked holdout evaluation.
