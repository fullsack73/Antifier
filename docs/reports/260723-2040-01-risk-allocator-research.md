# Risk Allocator Research and Validation

## Summary

alpha signal과 독립적인 optimizer risk layer를 quant-grade 수준으로 높이기 위해 robust covariance, exact ERC, HRP를 구현하고 staged research/validation을 실행했습니다.

- public optimizer default는 변경하지 않았습니다.
- 기존 Ledoit-Wolf minimum variance를 primary baseline으로 유지합니다.
- locked holdout은 실행하지 않았습니다.

## Implementation

- covariance blend: Ledoit-Wolf 50%, Oracle Approximating 30%, 180일 exponential covariance 20%
- spectral positive-semidefinite repair
- condition number, eigenvalue, effective rank, average correlation diagnostics
- exact equal-risk-contribution SLSQP optimizer와 risk contribution dispersion
- hierarchical risk parity clustering
- long-only capped-simplex projection으로 weight sum 1과 per-asset cap 동시 보장

## Research split

2005-2013 sector ETF 9종, 2,264일, 504일 train, 63일 rebalance, 10 bps cost.

| Model | CAGR | Volatility | Sharpe | Max DD | Avg turnover |
|---|---:|---:|---:|---:|---:|
| equal weight | 0.0654 | 0.2191 | 0.2070 | -0.5223 | 0.0466 |
| Ledoit-Wolf minimum variance | 0.0751 | 0.1785 | 0.3084 | -0.4671 | 0.0752 |
| inverse-vol baseline | 0.0634 | 0.1995 | 0.2177 | -0.4969 | 0.0439 |
| robust minimum variance | 0.0757 | 0.1777 | 0.3134 | -0.4626 | 0.0810 |
| exact ERC | 0.0677 | 0.1960 | 0.2433 | -0.4871 | 0.0469 |
| HRP | 0.0655 | 0.1879 | 0.2422 | -0.4807 | 0.1026 |

robust minimum variance가 가장 가까운 Ledoit-Wolf baseline을 모든 research metric에서 소폭 개선해 단일 frozen candidate로 선택됐습니다.

## Frozen validation

| Basket / regime | Candidate Sharpe | Baseline Sharpe | Candidate vol | Baseline vol | Candidate DD | Baseline DD | Gate |
|---|---:|---:|---:|---:|---:|---:|---|
| SP500 sample / bull | 0.9173 | 0.9811 | 0.1235 | 0.1230 | -0.1627 | -0.1625 | rejected |
| tech / crash | 1.9618 | 1.9161 | 0.2440 | 0.2432 | -0.1209 | -0.1205 | rejected |
| defensive / inflation-rate shock | 0.0554 | 0.0082 | 0.1189 | 0.1193 | -0.1125 | -0.1166 | passed |
| mixed ETF-like / sideways | 0.1496 | 0.1541 | 0.0492 | 0.0473 | -0.0601 | -0.0579 | rejected |

결과는 1/4입니다. static covariance blend는 regime 전반에서 기존 Ledoit-Wolf를 안정적으로 개선하지 못했습니다.

## Decision

- robust minimum variance를 default로 승격하지 않습니다.
- blend weight와 exponential span을 validation 결과에 맞춰 재튜닝하지 않습니다.
- exact ERC와 HRP는 research allocator로 유지하되 이번 validation 이후 대체 후보로 순차 시험하지 않습니다.
- 다음 risk candidate는 fresh research split에서 covariance forecast error, correlation shock, regime conditioning을 먼저 통과해야 합니다.
- locked holdout은 잠금 상태를 유지합니다.

## Fresh research follow-up

validation과 겹치지 않는 2008-2013 style/value/growth/small/mid/credit/REIT ETF 10종 research split에서 regime-conditioned covariance, historical minimum-CVaR, nested estimator selection을 추가 비교했습니다.

| Model | CAGR | Volatility | Sharpe | Sortino | Max DD | Daily CVaR | Avg turnover | Gate |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Ledoit-Wolf minimum variance | 0.1289 | 0.1092 | 0.9974 | 1.4109 | -0.1278 | 0.0167 | 0.1211 | baseline |
| robust minimum variance | 0.1291 | 0.1091 | 0.9998 | 1.4147 | -0.1274 | 0.0166 | 0.1148 | research pass only |
| regime minimum variance | 0.1287 | 0.1092 | 0.9952 | 1.4077 | -0.1279 | 0.0167 | 0.1431 | rejected |
| historical minimum-CVaR | 0.1296 | 0.1115 | 0.9829 | 1.3880 | -0.1325 | 0.0171 | 0.0956 | rejected |
| nested estimator minimum variance | 0.1178 | 0.1065 | 0.9186 | 1.2962 | -0.1260 | 0.0163 | 0.2296 | rejected |

nested estimator는 outer train window 안에서만 252일 train/63일 validation fold를 사용해 Ledoit-Wolf, OAS, exponential 60/180, static blend 중 하나를 선택했습니다. 미래 데이터 누출 없이 realized volatility와 drawdown은 개선했지만 return/Sharpe와 turnover 안정성을 잃었습니다. 복잡도 증가 자체를 성능 개선으로 간주하지 않습니다.

## Statistical follow-up

각 model의 net daily return을 baseline과 날짜별 paired한 뒤 21일 circular block bootstrap 2,000회를 실행했습니다. volatility와 Sharpe 개선 확률 95%를 모두 요구하고 동시 후보는 Holm-Bonferroni correction을 적용했습니다.

country ETF 2004-2012 split에서 deterministic improvement를 보였던 후보의 Sharpe improvement probability:

| Candidate | P(vol lower) | P(Sharpe higher) | Holm significant | Decision |
|---|---:|---:|---|---|
| robust minimum variance | 100.00% | 74.10% | no | rejected |
| exact ERC | 100.00% | 82.60% | no | rejected |
| continuous regime minimum variance v1 | 100.00% | 83.65% | no | rejected |
| minimum-CVaR | 98.15% | 80.25% | no | rejected |

추가 fresh splits에서 stability-regularized, resampled minimum variance, risk-managed momentum, continuous regime covariance v2도 가장 가까운 baseline과 statistical gate를 통과하지 못했습니다.

## OOS covariance forecast ensemble follow-up

hard estimator selection의 turnover 불안정을 줄이기 위해 다음 completed inner OOS loss를 직접 측정하는 soft ensemble을 추가했습니다.

- covariance relative Frobenius error
- off-diagonal correlation RMSE
- equal/inverse-vol probe portfolio log-variance calibration error
- inverse-loss weight와 50% equal-estimator prior의 결합
- PSD correlation/volatility shock stress amplification

validation과 겹치지 않는 fixed-income ETF 8종(`SHY`, `IEF`, `TLT`, `TIP`, `LQD`, `HYG`, `MBB`, `EMB`) 2008-2013 split, 504일 train, 63일 rebalance에서 평가했습니다.

| Model | Volatility | Sharpe | Max DD | Avg turnover | P(vol lower) | P(Sharpe higher) | Decision |
|---|---:|---:|---:|---:|---:|---:|---|
| Ledoit-Wolf minimum variance | 0.0280 | 0.5119 | -0.0548 | 0.1371 | - | - | baseline |
| OOS forecast-loss ensemble | 0.0273 | 0.5265 | -0.0545 | 0.1584 | 99.50% | 62.60% | rejected |

deterministic 지표는 모두 개선했지만 Sharpe 개선 확률이 95% gate에 미달했습니다. candidate를 freeze하거나 validation에 보내지 않습니다. 252일 outer train은 252/63 inner fold를 확보하지 못해 baseline fallback과 동일하므로 research CLI에서 최소 315일을 강제합니다.

## Outputs

- `logs/risk_allocator_research_sector_etfs_2005_2013.json`
- `logs/risk_allocator_research_sector_etfs_2005_2013.md`
- `logs/risk_allocator_candidate_validation_20260723.json`
- `logs/risk_allocator_candidate_validation_20260723.md`
- `logs/risk_allocator_research_style_credit_reit_2008_2013.json`
- `logs/risk_allocator_research_style_credit_reit_2008_2013_nested.json`
- `logs/risk_allocator_research_fixed_income_2008_2013_cov_ensemble_504.json`

## Verification

- `PYTHONPATH=src/backend .venv/bin/python -m pytest tests/test_portfolio_risk_models.py -q`: 12 passed
- `PYTHONPATH=src/backend .venv/bin/python -m pytest tests -q`: 139 passed
- research run completed for six allocator families
- frozen validation completed 4/4 cases with candidate survival 1/4
- OOS covariance ensemble follow-up 이후 risk model test `23 passed`, 전체 backend test `174 passed`
