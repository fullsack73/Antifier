# Raw Momentum Rank-Tilt Research

- 작업 일시: 2026-07-24 05:49 (KST)
- 상태: locked research 탈락
- split: `fama-french-17-industry-raw-momentum-research-2000-2011-v1`
- namespace: `alpha-v12-raw-momentum-industry-portfolios`

## 목적

Long-history 30-industry 연구에서 강했던 raw 12-1 rank tilt를 바로 승격하지 않고, fresh 17-industry outcome 기간에서 current production-default 대응 `lightweight_bl`과 독립 비교했습니다.

## 고정 사양

- candidate: `momentum_12_1_rank_tilt`
- primary baseline: `lightweight_bl`
- 252일 lookback, 최근 21일 skip
- cross-sectional rank를 equal weight 주변 20% active-share tilt로 변환
- 504일 train, 63일 horizon/rebalance, 10bp cost
- 10% asset cap, 2% band, 35% turnover cap
- candidate absolute signal, paired signal, paired portfolio 4개 가설을 95% bootstrap와 통합 Holm correction으로 평가
- equal weight, risk parity, historical BL deterministic guard

## 데이터

- source: Kenneth R. French Data Library 17 Industry Portfolios Daily
- price panel: 1998-01-02~2011-12-30, 3,523행 × 17 industries
- evaluation: 2000-01-03~2011-12-30
- 기존 17-industry lightweight 연구 evaluation은 1969~1999이므로 outcome 기간 비중복
- risk-free: backward-asof FRED DGS3MO daily-equivalent
- raw archive, price, factor, ordered basket, provenance, split SHA 검증 통과

## Signal 결과

| Signal | Periods | Mean rank IC | Positive IC | Mean spread |
|---|---:|---:|---:|---:|
| Lightweight point forecast | 48 | -0.0120 | 47.92% | -0.4209% |
| Raw 12-1 momentum | 48 | 0.0042 | 45.83% | -0.2496% |

- candidate P(IC>0/spread>0): `53.65% / 44.35%`
- candidate minus baseline IC/spread: `+0.01620 / +0.00171`
- paired P(higher IC/spread): `62.45% / 56.95%`

## Portfolio 결과

| Model | CAGR | Volatility | Sharpe | Max DD | Turnover |
|---|---:|---:|---:|---:|---:|
| Equal weight | 5.88% | 21.09% | 0.2693 | -53.75% | 3.06% |
| Risk parity | 6.20% | 20.24% | 0.2868 | -52.80% | 3.84% |
| Historical BL | 5.59% | 21.14% | 0.2562 | -53.52% | 2.75% |
| Lightweight BL | 4.91% | 21.40% | 0.2256 | -56.61% | 11.93% |
| Raw momentum rank tilt | 5.94% | 21.75% | 0.2700 | -54.26% | 18.72% |

- P(higher return vs lightweight): `96.35%`
- P(higher Sharpe vs lightweight): `95.40%`
- signal Holm-adjusted p-value: `0.7510`
- portfolio Holm-adjusted p-value: `0.1460`
- risk-parity Sharpe and drawdown guard: rejected
- combined gate: rejected

## 결정

- Current lightweight baseline weakness는 재확인됐지만 raw momentum의 absolute signal과 regime robustness가 replacement 기준을 충족하지 못했습니다.
- Raw momentum 단독 후보를 폐기하고 validation/locked holdout을 열지 않습니다.
- 다음은 17-industry 결과에 weight를 맞추지 않은 fixed risk-parity/momentum construction diversification을 fresh split에서 검증합니다.

## 검증

- raw-momentum deterministic guard tests: `2 passed`
- shared signal/portfolio/Holm gate tests: `2 passed`
- split manifest self-hash와 data provenance SHA 검증 통과
