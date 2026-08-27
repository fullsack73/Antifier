# DFL Covariance Research Result

- Experiment: `fama-french-49-industry-dfl-covariance-reproduction-2010-2023-v1`
- Decision: **REJECT**
- Checkpoint 1: `REJECT`
- Promotion safe: `False`
- Test samples: `11`

## Checkpoint 1

| Model | Mean annualized realized volatility |
|---|---:|
| equal_weight | 0.173487 |
| historical_sample_covariance_gmv | 0.162324 |
| ledoit_wolf_constant_variance_gmv | 0.132244 |
| ledoit_wolf_constant_correlation_gmv | 0.140167 |
| oas_gmv | 0.131749 |
| PFL five-seed mean | 0.278908 |
| DFL five-seed mean | 0.138941 |

## Gate reasons

- DFL mean volatility did not improve strongest shrinkage baseline oas_gmv.

## Checkpoint 2

Skipped by the preregistered Checkpoint 1 stop rule.

## Guardrail

This is reproduction-only diagnostic evidence. Production Ledoit-Wolf GMV remains unchanged.
