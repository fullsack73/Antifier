# James–Stein Mean Shrinkage Research

- 작업 일시: 2026-07-24 05:25 (KST)
- 상태: locked research 탈락
- split: `fama-french-49-industry-james-stein-research-1983-1999-v1`
- namespace: `mean-v1-james-stein-industry-portfolios`

## 목적

Production optimizer의 historical expected-return view가 raw CAGR에 의존하는 estimation-error gap을 점검했습니다. Transformer 구조나 hyperparameter는 바꾸지 않고, 표본평균을 global-minimum-variance expected return으로 수축하는 parameter-free Jorion/Bayes-Stein 후보를 비교했습니다.

## 고정 사양

- candidate: `james_stein_bl`
- closest baseline: `historical_bl`
- 일별 표본평균과 공분산만 사용
- shrinkage intensity: `(N + 2) / (N + 2 + T × Mahalanobis distance)`
- annualization: arithmetic daily mean × 252
- BL prior, Ledoit-Wolf covariance, fixed uncertainty, long-only cap, rebalance control, transaction cost는 baseline과 동일
- 504일 train, 63일 rebalance, 10bp cost, 10% asset cap, 2% band, 35% turnover cap

## 데이터

- source: Kenneth R. French Data Library 49 Industry Portfolios Daily
- value-weighted, source portfolio가 시점별 구성 종목을 재구성
- price panel: 1981-09-01~1999-12-31, 4,635행 × 49 industries
- evaluation: 1983-08-29~1999-12-31
- risk-free: backward-asof FRED DGS3MO daily-equivalent
- price, factor, ordered basket, split manifest SHA 검증 통과

## 결과

| Model | CAGR | Volatility | Sharpe | Max DD | Avg turnover |
|---|---:|---:|---:|---:|---:|
| Equal weight | 14.28% | 13.29% | 0.6345 | -34.34% | 1.84% |
| Minimum variance | 10.33% | 10.70% | 0.4301 | -31.77% | 16.40% |
| Risk parity | 14.31% | 12.66% | 0.6618 | -32.97% | 2.05% |
| Historical BL | 15.21% | 13.87% | 0.6725 | -34.58% | 2.15% |
| James–Stein BL | 14.52% | 13.46% | 0.6436 | -34.45% | 1.78% |

- 66 rebalance의 mean shrinkage intensity: `47.39%`
- range: `34.23%~58.23%`
- P(lower volatility): `100.00%`
- P(higher return): `0.40%`
- P(higher Sharpe): `3.50%`
- Holm-adjusted p-value: `0.9650`
- deterministic gate: rejected
- statistical gate: rejected
- promotion eligible: false

## 결정

- 후보는 위험과 turnover를 낮췄지만 더 큰 return loss로 Sharpe를 악화시켰습니다.
- 동일 research 결과에 맞춰 수축 강도, target, train window를 조절하지 않습니다.
- validation과 locked holdout을 열지 않습니다.
- `james_stein_bl`은 재현 가능한 research-only 모델로 유지하고 production/default optimizer는 변경하지 않습니다.

## 검증

- James–Stein estimator dispersion/no-lookahead/opt-in tests: `3 passed`
- portfolio backtest regression: `52 passed`
- research runner, split contract 포함 focused backend tests: `59 passed`
- locked split self-hash와 data provenance SHA 검증 통과
