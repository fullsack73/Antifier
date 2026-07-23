# Risk–Momentum Blend Research

- 작업 일시: 2026-07-24 05:56 (KST)
- 상태: locked research 탈락
- split: `fama-french-12-industry-risk-momentum-research-1970-1999-v1`
- namespace: `construction-v1-risk-momentum-industry-portfolios`

## 목적

Regime별로 강점이 달랐던 inverse-volatility risk parity와 raw 12-1 momentum rank tilt를 fixed 50/50으로 결합하면 두 component보다 안정적인 risk-adjusted return을 만드는지 검증했습니다.

## 고정 사양

- candidate: `risk_momentum_blend`
- baselines: `risk_parity`, `momentum_12_1_rank_tilt`
- component weight: 50% / 50%, tuning grid 없음
- momentum: 252일 lookback, 최근 21일 skip, 20% active-share rank tilt
- 504일 train, 63일 horizon/rebalance, 10bp cost
- 20% asset cap, 2% band, 35% turnover cap
- momentum absolute IC/spread와 두 baseline별 lower-volatility/higher-Sharpe를 six-hypothesis Holm correction

## 데이터

- source: Kenneth R. French Data Library 12 Industry Portfolios Daily
- price panel: 1968-01-02~1999-12-31, 8,058행 × 12 industries
- evaluation: 1970-02-11~1999-12-31
- 기존 12-industry regime research evaluation 1933~1952와 비중복
- risk-free: same-date official French daily one-month Treasury-bill return
- raw archive, price, factor, ordered basket, provenance, split SHA 검증 통과

## Signal 결과

- periods: `120`
- mean rank IC: `0.0868`
- positive IC rate: `60.00%`
- mean top-bottom spread: `0.9896%`
- P(IC>0): `99.75%`
- P(spread>0): `98.25%`
- absolute signal gate: passed

## Portfolio 결과

| Model | CAGR | Volatility | Sharpe | Max DD | Turnover |
|---|---:|---:|---:|---:|---:|
| Equal weight | 13.57% | 13.31% | 0.5423 | -47.31% | 1.78% |
| Risk parity | 13.68% | 13.06% | 0.5581 | -46.25% | 2.35% |
| Momentum rank tilt | 14.47% | 13.68% | 0.5893 | -44.45% | 19.81% |
| Risk–momentum blend | 13.87% | 13.36% | 0.5610 | -45.79% | 6.76% |

- vs risk parity P(lower volatility/higher Sharpe): `0.00% / 59.00%`
- vs momentum P(lower volatility/higher Sharpe): `100.00% / 4.35%`
- signal spread Holm-adjusted p-value: `0.0700`
- joint gate: rejected
- promotion eligible: false

## 결정

- Convex blend는 두 component 사이의 risk-return을 만들었지만 frontier를 공동 지배하지 못했습니다.
- 동일 split에서 component weight, momentum horizon, active share를 재튜닝하지 않습니다.
- Validation과 locked holdout을 열지 않습니다.
- 다음 independent construction은 fixed Ledoit-Wolf minimum-variance/momentum blend입니다.

## 검증

- exact blend/no-lookahead tests: `2 passed`
- dual-component deterministic gate tests: `2 passed`
- split manifest self-hash와 data provenance SHA 검증 통과
