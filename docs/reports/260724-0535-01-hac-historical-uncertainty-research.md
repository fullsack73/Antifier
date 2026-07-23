# HAC Historical Uncertainty Research

- 작업 일시: 2026-07-24 05:35 (KST)
- 상태: locked research 탈락
- split: `fama-french-35-industry-hac-historical-research-2000-2014-v1`
- namespace: `mean-v2-hac-historical-industry-portfolios`

## 목적

Historical BL의 모든 자산에 동일하게 적용되는 fixed 20% view uncertainty를 통계적 estimation uncertainty로 교체했습니다. Point estimate는 historical CAGR로 유지해 James–Stein point shrinkage와 다른 candidate family로 분리했습니다.

## 고정 사양

- candidate: `hac_historical_bl`
- closest baseline: `historical_bl`
- uncertainty: annualized Newey-West/HAC standard error of the daily mean
- lag rule: `floor(4*(T/100)^(2/9))`
- Bartlett kernel, manual lag/scale hyperparameter 없음
- BL prior, Ledoit-Wolf covariance, long-only cap, execution controls와 비용은 baseline과 동일
- 504일 train, 63일 rebalance, 10bp cost, 10% asset cap, 2% band, 35% turnover cap

## 데이터

- source: Kenneth R. French Data Library 38 Industry Portfolios Daily
- value-weighted, source portfolio가 시점별 구성 종목을 재구성
- `Govt`, `Steam`, `Water`는 exact source-name 결측 diagnostics와 함께 사전 제외
- price panel: 1998-01-02~2014-12-31, 4,277행 × 35 industries
- evaluation: 2000-01-03~2014-12-31
- risk-free: backward-asof FRED DGS3MO daily-equivalent
- raw archive, price, factor, ordered basket, split manifest SHA 검증 통과

## 결과

| Model | CAGR | Volatility | Sharpe | Max DD | Avg turnover |
|---|---:|---:|---:|---:|---:|
| Equal weight | 8.75% | 17.94% | 0.4557 | -49.22% | 2.27% |
| Minimum variance | 10.45% | 15.90% | 0.5901 | -48.38% | 13.61% |
| Risk parity | 8.97% | 18.18% | 0.4630 | -52.88% | 2.58% |
| Historical BL | 7.75% | 19.45% | 0.3872 | -54.70% | 2.82% |
| HAC historical BL | 8.89% | 20.23% | 0.4318 | -55.14% | 14.36% |

- 60 rebalance median uncertainty의 평균: `16.26%`
- baseline/candidate average confidence: `50.00% / 59.65%`
- P(lower volatility): `0.00%`
- P(higher return): `96.25%`
- P(higher Sharpe): `90.20%`
- Holm-adjusted p-value: `1.0000`
- deterministic/statistical/inverse-vol gates: rejected
- promotion eligible: false

## 결정

- Statistical uncertainty는 fixed uncertainty보다 return과 Sharpe를 높였지만 더 공격적인 view retention으로 volatility와 turnover를 악화시켰습니다.
- 같은 split에서 HAC lag, uncertainty multiplier, confidence mapping을 재튜닝하지 않습니다.
- validation과 locked holdout을 열지 않습니다.
- `hac_historical_bl`은 auditable research-only model로 유지하고 production/default optimizer는 변경하지 않습니다.

## 검증

- HAC no-lookahead/autocorrelation/opt-in tests: `3 passed`
- risk-runner closest-baseline test: `1 passed`
- split manifest self-hash와 data provenance SHA 검증 통과
