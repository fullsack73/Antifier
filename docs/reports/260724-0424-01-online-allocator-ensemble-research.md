# Online Allocator Ensemble Research

## 결정

- completed-history online allocator ensemble은 6-month momentum보다 volatility와 turnover를 낮췄지만 Sharpe를 개선하지 못했습니다.
- deterministic all-expert/closest-baseline gate, paired Sharpe gate, Holm familywise gate에서 탈락했습니다.
- exact candidate를 폐기하고 production/default allocator를 변경하지 않습니다.
- reserved 1970~1999 validation과 2000~2025 locked holdout은 열지 않습니다.
- 같은 split에서 outer window, expert set, loss, learning rate를 재튜닝하지 않습니다.

## 데이터와 split

- source: Kenneth R. French Data Library 10 Industry Portfolios
- source URL: `https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/10_Industry_Portfolios_daily_CSV.zip`
- archive size: `931,865` bytes
- archive SHA-256: `fed1f7cbe4143b047f86757f6e071176dc0df2a51933fb0d9bd513563e49359b`
- derived panel: 1926-07-01~1969-12-31, 12,030 days × 10 portfolios
- price SHA-256: `50e3cf1c6f5df73f59d3e970493940944835f0340eb78164ab5ed2a09d53668a`
- universe manifest SHA-256: `e28d8a113d98153912b92e152216c5213424d8a283097556c849e5ce541a0b42`
- historical French RF SHA-256: `af5df62ecef99c3e3db207e5dd82e56060ba8d3ee979ff774590a6e83e418778`
- split: `fama-french-10-industry-online-ensemble-research-1928-1969-v1`
- namespace: `risk-v10-online-allocator-ensemble`
- research: 1928-03-07~1969-12-31
- reserved validation: 1970-01-01~1999-12-31
- reserved locked holdout: 2000-01-01~2025-12-31
- split manifest SHA-256: `3a6aca3ed7e9767f31c87a8bddf78ef25b62d24fa90672244a756ab8d9f1f89f`
- survivorship policy: official portfolios dynamically reconstitute eligible underlying firms; promotion-safe

## 사전 고정 사양

- experts: equal-weight, Ledoit-Wolf minimum variance, inverse-volatility risk parity, 6-month momentum
- outer training window: 504 trading days
- inner completed fold: 252-day train + 63-day validation
- expert loss: each completed fold의 cross-expert total-return rank, best 0 and worst 1
- update: Hedge with `eta = sqrt(2 log(N) / completed_folds)`
- prior: uniform
- portfolio: posterior-weighted convex combination of capped expert targets
- rebalance: 63 trading days
- transaction cost: 10 bps
- rebalance band / maximum turnover: 2% / 35%
- paired baseline: `momentum_6m`
- gate: Sharpe above every expert, momentum 대비 volatility/Sharpe/drawdown 개선, paired 95% lower-volatility/higher-Sharpe, Holm significance

각 outer signal date에는 training window 안에서 validation outcome이 모두 완료된 inner fold만 사용합니다. 결과를 보고 선택하는 hyperparameter grid는 없습니다.

## 결과

| Model | CAGR | Volatility | Sharpe | Max DD | Daily CVaR | Avg controlled turnover |
|---|---:|---:|---:|---:|---:|---:|
| equal weight | 8.85% | 17.02% | 0.4991 | -81.13% | 2.641% | 1.82% |
| minimum variance | 8.38% | 13.86% | 0.5466 | -75.05% | 2.155% | 6.66% |
| risk parity | 8.59% | 15.86% | 0.5088 | -80.55% | 2.470% | 2.65% |
| 6m momentum | 9.98% | 17.08% | 0.5585 | -79.47% | 2.656% | 32.10% |
| online ensemble | 9.16% | 15.79% | 0.5434 | -79.03% | 2.461% | 16.17% |

Candidate minus 6m momentum:

- annualized return: `-0.956%p`
- annualized volatility: `-1.284%p`
- Sharpe: `-0.0151`
- P(lower volatility): `100.00%`
- P(higher return): `0.05%`
- P(higher Sharpe): `19.80%`
- Holm-adjusted p-value: `0.8020`
- risk gate: rejected
- promotion eligible: false

Risk reduction은 강하고 turnover도 약 절반으로 줄었지만 return sacrifice가 더 커 Sharpe가 하락했습니다. Minimum variance의 Sharpe `0.5466`도 넘지 못해 all-expert gate 역시 실패했습니다.

## Online diagnostics

- OOS rebalance periods: 183
- completed inner folds per outer window: 3 for all 183 periods
- average posterior:
  - equal weight: `21.96%`
  - minimum variance: `26.26%`
  - risk parity: `18.24%`
  - 6m momentum: `33.53%`
- candidate risk forecast MAE: `0.0448`
- momentum risk forecast MAE: `0.0473`
- candidate average risky exposure: `99.14%`

Hedge는 momentum을 평균 최대로 배분하면서 risk experts로 변동성을 낮췄습니다. 3개 completed fold만으로는 future return efficiency를 안정적으로 식별하지 못했습니다. 이 진단으로 같은 split의 window나 learning rate를 변경하지 않습니다.

## 구현 및 검증

- capped expert target과 parameter-free Hedge posterior 결합 추가
- incomplete latest fold가 posterior를 바꾸지 않는 no-lookahead 회귀 테스트 추가
- expert returns/losses, cumulative loss, posterior, latest completed validation date 기록
- risk research split lineage에서 explicit universe manifest SHA를 legacy basket hash보다 우선
- backend pytest `259`개 통과
- result JSON SHA-256: `00b1acbcb9db5df6710902ee588e76e8fc0b5f2f17165fb48b4b584fe5b7220f`

## 후속

- exact online ensemble candidate는 폐기합니다.
- 1970+ reserved data를 이 후보 평가에 사용하지 않습니다.
- 다음 후보는 같은 expert weighting 재튜닝보다 독립적인 alpha/target 정보 또는 optimizer objective가 필요합니다.
- current engine은 아직 quant-standard performance 승격 조건을 충족하지 못합니다.
