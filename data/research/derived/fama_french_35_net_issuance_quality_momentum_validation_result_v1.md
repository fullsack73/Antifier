# Frozen Net-Issuance Quality-Momentum Validation

- Split: `fama-french-35-net-issuance-quality-momentum-validation-2000-2011-v1`
- Frozen from: `fama-french-35-net-issuance-quality-momentum-research-1969-1998-v1`
- Passed cases: 3 / 4
- Aggregate gate: `rejected`
- Promotion eligible: `False`

## Cases

| Case | Candidate IC | Baseline IC | Candidate spread | Baseline spread | Gate |
|---|---:|---:|---:|---:|---|
| small_size | 0.1237 | 0.0422 | 0.0709 | 0.0630 | passed |
| large_size | 0.1453 | -0.0290 | 0.0521 | 0.0136 | passed |
| low_net_issuance | 0.0185 | 0.0604 | 0.0039 | 0.0277 | rejected |
| high_net_issuance | 0.2506 | 0.0675 | 0.0861 | 0.0363 | passed |

## Aggregate

- P(higher mean rank IC): `1.0000`
- P(higher mean spread): `0.9805`
- Holm-adjusted p-value: `0.0195`

## Decision

- All four deterministic cases and aggregate statistical gate must pass.
- 2012+ locked holdout remains sealed unless validation passes.
