# Frozen Value-Quality-Momentum Validation

- Split: `fama-french-25-value-quality-momentum-validation-2000-2011-v1`
- Frozen from: `fama-french-25-value-quality-momentum-research-1965-1999-v1`
- Passed cases: 2 / 4
- Aggregate gate: `rejected`
- Promotion eligible: `False`

## Cases

| Case | Candidate IC | Baseline IC | Candidate spread | Baseline spread | Gate |
|---|---:|---:|---:|---:|---|
| low_value | -0.0380 | -0.1028 | 0.0056 | -0.0180 | rejected |
| high_value | 0.1607 | 0.1172 | 0.0444 | 0.0320 | passed |
| low_profitability | -0.0161 | -0.0368 | 0.0073 | -0.0034 | rejected |
| high_profitability | 0.1376 | 0.1273 | 0.0363 | 0.0197 | passed |

## Aggregate

- P(higher mean rank IC): `0.9385`
- P(higher mean spread): `0.9420`
- Holm-adjusted p-value: `0.0615`

## Decision

- All four deterministic cases and aggregate statistical gate must pass.
- 2012+ locked holdout remains sealed unless validation passes.
