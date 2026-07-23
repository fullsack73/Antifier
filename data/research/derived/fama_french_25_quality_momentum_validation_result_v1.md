# Frozen Quality-Momentum Validation

- Split: `fama-french-25-quality-momentum-validation-2000-2011-v1`
- Frozen from: `fama-french-25-quality-momentum-research-1965-1999-v1`
- Passed cases: 4 / 4
- Aggregate gate: `rejected`
- Promotion eligible: `False`

## Cases

| Case | Candidate IC | Baseline IC | Candidate spread | Baseline spread | Gate |
|---|---:|---:|---:|---:|---|
| low_profitability | 0.0459 | -0.0182 | 0.0137 | 0.0007 | passed |
| high_profitability | 0.0463 | 0.0205 | 0.0173 | 0.0075 | passed |
| low_investment | 0.0650 | -0.0262 | 0.0075 | -0.0051 | passed |
| high_investment | 0.0679 | 0.0313 | 0.0176 | 0.0115 | passed |

## Aggregate

- P(higher mean rank IC): `0.9850`
- P(higher mean spread): `0.9990`
- Holm-adjusted p-value: `0.0150`

## Decision

- All four deterministic cases and aggregate statistical gate must pass.
- 2012+ locked holdout remains sealed unless validation passes.
