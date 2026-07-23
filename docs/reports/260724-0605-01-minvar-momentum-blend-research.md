# Minimum-Variance–Momentum Blend Research

- 작업 일시: 2026-07-24 06:05 (KST)
- 상태: locked research 탈락
- split: `fama-french-10-industry-minvar-momentum-research-1970-1999-v1`
- namespace: `construction-v2-minvar-momentum-industry-portfolios`

## 목적

Ledoit-Wolf minimum variance와 raw momentum rank tilt의 fixed 50/50 결합이 두 component를 동시에 개선하는지 검증했습니다.

## 고정 사양

- candidate: `minvar_momentum_blend`
- baselines: `min_variance`, `momentum_12_1_rank_tilt`
- component weight: 50% / 50%, tuning grid 없음
- risk sleeve: Ledoit-Wolf long-only minimum variance
- momentum: 252일 lookback, 21일 skip, 20% active-share rank tilt
- 504일 train, 63일 horizon/rebalance, 10bp cost
- 20% asset cap, 2% band, 35% turnover cap
- momentum absolute IC/spread와 두 baseline lower-volatility/higher-Sharpe의 six-hypothesis Holm correction

## 데이터

- source: Kenneth R. French Data Library 10 Industry Portfolios Daily
- price panel: 1968-01-02~1999-12-31, 8,058행 × 10 industries
- evaluation: 1970-02-11~1999-12-31
- 선행 10-industry online-ensemble outcome 1928~1969 이후로 분리
- risk-free: same-date official French daily one-month Treasury-bill return
- raw archive, price, factor, ordered basket, provenance, split SHA 검증 통과

## Signal 결과

- periods: `120`
- mean rank IC: `0.0675`
- mean top-bottom spread: `1.4104%`
- P(IC>0): `97.20%`
- P(spread>0): `98.55%`
- absolute signal gate: passed

## Portfolio 결과

| Model | CAGR | Volatility | Sharpe | Max DD | Turnover |
|---|---:|---:|---:|---:|---:|
| Equal weight | 13.69% | 13.33% | 0.5498 | -47.17% | 1.83% |
| Minimum variance | 14.84% | 11.95% | 0.6829 | -42.21% | 10.51% |
| Momentum rank tilt | 14.44% | 13.67% | 0.5878 | -44.32% | 20.83% |
| Minvar–momentum blend | 14.59% | 12.70% | 0.6325 | -42.75% | 11.37% |

- vs minvar P(lower volatility/higher Sharpe): `0.00% / 6.45%`
- vs momentum P(lower volatility/higher Sharpe): `100.00% / 94.10%`
- six-hypothesis Holm gate: rejected
- promotion eligible: false

## 결정

- Blend는 momentum보다 risk-adjusted performance를 개선했지만 plain minimum variance를 약화시켰습니다.
- 동일 split에서 component weight, signal horizon, active share를 재튜닝하지 않습니다.
- Validation과 locked holdout을 열지 않습니다.
- Plain Ledoit-Wolf minimum variance를 fresh period에서 current lightweight/default 대비 독립 promotion candidate로 검증합니다.

## 검증

- exact blend/no-lookahead tests: `2 passed`
- dual-component deterministic gate tests: `2 passed`
- split manifest self-hash와 data provenance SHA 검증 통과
