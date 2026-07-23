# Frozen Trend Risk Parity Validation

- Split: `fama-french-49-industry-trend-risk-parity-validation-2018-2021-v1`
- Frozen from: `fama-french-30-industry-trend-risk-parity-replication-1928-1971-v1`
- Passed cases: 0 / 4
- Aggregate gate: `rejected`
- Promotion eligible: `False`

## Cases

| Case | Candidate vol | Baseline vol | Candidate Sharpe | Baseline Sharpe | Candidate DD | Baseline DD | Gate |
|---|---:|---:|---:|---:|---:|---:|---|
| defensive_consumption_health | 0.1644 | 0.1755 | 0.4752 | 0.6841 | -0.3138 | -0.3063 | rejected |
| industrial_cyclical | 0.1505 | 0.2443 | 0.4168 | 0.6329 | -0.2908 | -0.4143 | rejected |
| technology_services | 0.1864 | 0.2257 | 0.5830 | 0.7803 | -0.3259 | -0.3707 | rejected |
| real_assets_financials | 0.1378 | 0.2306 | 0.3653 | 0.4908 | -0.2991 | -0.4007 | rejected |

## Aggregate

- P(lower volatility): `1.0000`
- P(higher Sharpe): `0.0205`
- Holm-adjusted p-value: `0.9795`

## Decision

- All four deterministic cases and the aggregate statistical gate must pass.
- Locked holdout remains sealed unless validation passes.
