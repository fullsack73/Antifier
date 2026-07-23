# 52-Week-High Momentum Research

- 작업 일시: 2026-07-24 05:43 (KST)
- 상태: locked research 탈락
- split: `fama-french-30-industry-high-momentum-research-1973-1999-v1`
- namespace: `alpha-v11-high-momentum-industry-portfolios`

## 목적

52-week-high proximity가 raw 12-1 momentum의 cross-sectional ordering을 안정적으로 개선하는지 검증했습니다. Candidate와 baseline에 같은 rank transform, 20% active-share tilt, execution controls를 적용해 signal 차이만 비교했습니다.

## 고정 사양

- candidate: `high_momentum_rank_tilt`
- baseline: `momentum_12_1_rank_tilt`
- 12-1 momentum: 252일 lookback, 최근 21일 skip
- 52-week-high: 현재 가격 / 직전 252일 최고가
- component rank weight: 50% / 50%
- blended score를 다시 cross-sectional rank
- 504일 train, 63일 horizon/rebalance, 10bp cost
- 10% asset cap, 2% band, 35% turnover cap
- candidate absolute signal, paired signal, paired portfolio 4개 가설을 95% bootstrap와 통합 Holm correction으로 평가

## 데이터

- source: Kenneth R. French Data Library 30 Industry Portfolios Daily
- value-weighted, source portfolio가 시점별 구성 종목을 재구성
- price panel: 1971-04-01~1999-12-31, 7,266행 × 30 industries
- evaluation: 1973-04-02~1999-12-31
- 선행 30-industry trend 연구 종료일 1971-03-11 이후로 완전 분리
- risk-free: same-date official French daily one-month Treasury-bill return
- raw archive, price, factor, ordered basket, provenance, split SHA 검증 통과

## Signal 결과

| Signal | Periods | Mean rank IC | Positive IC | Mean spread |
|---|---:|---:|---:|---:|
| Raw 12-1 momentum | 108 | 0.1098 | 67.59% | 2.1545% |
| 52-week-high blend | 108 | 0.0985 | 67.59% | 1.6321% |

- candidate absolute P(IC>0/spread>0): `100.00% / 99.60%`
- candidate minus baseline IC: `-0.01135`
- candidate minus baseline spread: `-0.00522`
- P(higher IC): `18.70%`
- P(higher spread): `7.90%`

## Portfolio 결과

| Model | CAGR | Volatility | Sharpe | Max DD | Turnover |
|---|---:|---:|---:|---:|---:|
| Equal weight | 13.35% | 13.19% | 0.5169 | -42.65% | 1.53% |
| Risk parity | 13.27% | 12.61% | 0.5288 | -42.81% | 1.80% |
| Raw momentum rank tilt | 14.91% | 13.92% | 0.5955 | -40.22% | 10.02% |
| 52-week-high blend | 14.66% | 13.93% | 0.5791 | -40.69% | 11.04% |

- P(higher return): `9.70%`
- P(higher Sharpe): `9.25%`
- four-hypothesis Holm-adjusted p-values: all `1.0000`
- combined gate: rejected
- promotion eligible: false

## 결정

- 52-week-high component는 raw momentum ordering을 개선하지 못해 폐기합니다.
- 같은 split에서 component weight, lookback, skip 또는 transform을 재튜닝하지 않습니다.
- validation과 locked holdout을 열지 않습니다.
- Raw 12-1 rank tilt의 strong baseline result는 새 fresh-universe candidate 연구의 가설 근거로만 사용하며 이 결과에서 직접 승격하지 않습니다.

## 검증

- 52-week-high ordering/no-lookahead/equal-construction tests: `3 passed`
- combined gate tests: `2 passed`
- split manifest self-hash와 data provenance SHA 검증 통과
