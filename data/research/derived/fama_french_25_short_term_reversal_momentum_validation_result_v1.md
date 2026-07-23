# Frozen Short-Term Reversal-Momentum Validation

- Split: `fama-french-25-short-term-reversal-momentum-validation-1958-1969-v1`
- Frozen from: `fama-french-25-short-term-reversal-momentum-research-1932-1955-v1`
- Passed cases: 4 / 4
- Aggregate gate: `passed`
- Promotion eligible: `True`

## Cases

| Case | Candidate IC | Baseline IC | Candidate spread | Baseline spread | Gate |
|---|---:|---:|---:|---:|---|
| small_size | 0.2166 | 0.1444 | 0.0111 | 0.0072 | passed |
| large_size | 0.1548 | 0.0946 | 0.0068 | 0.0043 | passed |
| prior_losers | 0.0716 | 0.0348 | 0.0059 | 0.0040 | passed |
| prior_winners | 0.0615 | 0.0305 | 0.0031 | 0.0016 | passed |

## Aggregate

- P(higher mean rank IC): `0.9990`
- P(higher mean spread): `0.9980`
- Holm-adjusted p-value: `0.0020`

## Decision

- All four deterministic cases and aggregate statistical gate must pass.
- Reserved locked holdout remains sealed unless validation passes.
