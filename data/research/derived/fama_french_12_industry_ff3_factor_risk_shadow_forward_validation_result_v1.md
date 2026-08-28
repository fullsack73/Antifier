# FF3 Factor-Risk Shadow-Forward Validation

- Split: `fama-french-12-industry-ff3-factor-risk-shadow-forward-validation-2012-2018-v1`
- Evaluation: 2012-01-03~2018-10-05, 27 complete 63-trading-day OOS origins
- Design: specification-frozen, previously unopened historical holdout; not live post-2025 collection
- Baseline: Ledoit-Wolf long-only capped GMV
- Candidate: fixed FF3 factor-risk GMV
- Result: **rejected**; production Ledoit-Wolf/API/UI defaults remain unchanged

## Performance

| Metric | Ledoit-Wolf GMV | FF3 factor-risk GMV |
|---|---:|---:|
| Annual realized volatility | 10.5515% | 10.5426% |
| CAGR | 13.0492% | 13.0019% |
| Sharpe | 1.1748 | 1.1718 |
| Sortino | 1.6863 | 1.6842 |
| Maximum drawdown | -10.4374% | -10.3572% |
| Net cumulative return | 128.8520% | 128.2064% |
| Average controlled turnover | 10.4046% | 9.4403% |
| Average concentration HHI | 0.1864 | 0.1932 |
| HHI effective holdings | 5.36 | 5.18 |
| Average predicted annual volatility | 11.9743% | 11.1452% |
| Average realized period annual volatility | 10.0353% | 10.0408% |
| Realized/predicted volatility ratio | 0.8733 | 0.9601 |
| Risk forecast MAE | 3.7529% | 3.2602% |

FF3 lowered point-estimate volatility by only 0.89 bp and slightly improved drawdown, turnover, and forecast calibration. It reduced CAGR and Sharpe and increased concentration.

## Paired statistical gate

- Circular block bootstrap: 2,000 samples, 21-day block, seed 42, 1,701 paired daily observations
- P(FF3 lower volatility): 66.50%
- P(FF3 higher Sharpe): 43.20%
- Volatility difference 95% interval: -4.52 bp to +2.44 bp
- Sharpe difference 95% interval: -0.0506 to +0.0462
- Holm raw/adjusted p-value: 0.5680 / 0.5680; significant `false`
- Required probability: 95% for both realized volatility and Sharpe

## Factor and execution diagnostics

- Successful FF3 covariance estimates: 27/27
- Ledoit-Wolf fallback: 0/27; no fallback reasons
- Average covariance condition number/effective rank: 88.1256 / 3.0596
- Successive ticker exposure pairs: 312
- Exposure mean/median L2 change: 0.05094 / 0.04403
- Mean absolute beta change: market 0.01554, SMB 0.02370, HML 0.03586
- Turnover cap hits: 0 for both models

## Decision

The fresh holdout does not reproduce the smoke improvement at the required confidence. The candidate is not promotion-eligible, and this result must not be used to retune the frozen parameters or change production defaults.
