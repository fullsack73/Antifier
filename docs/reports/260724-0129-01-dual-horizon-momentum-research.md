# Dual-Horizon Momentum Research

- 작업 일시: 2026-07-24 01:29 (KST)
- 상태: 후보 폐기
- split: `fama-french-49-industry-dual-momentum-research-2011-2017-v1`
- namespace: `alpha-v7-dual-horizon-industry-portfolios`

## 데이터

- source: Kenneth R. French Data Library, 49 Industry Portfolios Daily
- section: Average Value Weighted Returns
- 기존 원본 ZIP 재사용: 4.0MB, SHA-256 `e214c54a…f77097`
- 추가 외부 다운로드: 없음
- derived price index: 2009-01-02~2017-12-29, 2,265행 × 49 industries
- research evaluation: 2011-01-03~2017-12-29
- historical risk-free: FRED DGS3MO daily-equivalent, backward-asof only

## 후보

- baseline: 6-month cross-sectional momentum rank
- candidate: 6-month rank 50% + 12-1-month rank 50%
- component weight와 lookback은 결과 확인 전에 split manifest에 고정했습니다.
- 504일 train, 63일 rebalance, 10bp cost, 10% asset cap, 2% band, 35% turnover cap

## 결과

| Model | CAGR | Volatility | Sharpe | Max DD | Turnover |
|---|---:|---:|---:|---:|---:|
| 6-month momentum | 12.45% | 15.38% | 0.8259 | -24.16% | 17.79% |
| Dual-horizon momentum | 12.17% | 15.64% | 0.7987 | -25.37% | 10.44% |

- candidate minus baseline volatility: `+0.265%p`
- candidate minus baseline Sharpe: `-0.0272`
- P(lower volatility): `5.60%`
- P(higher return): `36.20%`
- P(higher Sharpe): `22.00%`
- promotion eligible: false

## 결정

- dual-horizon 후보를 폐기하고 production default를 변경하지 않습니다.
- 회전율 감소만으로 더 낮은 Sharpe와 더 큰 drawdown을 정당화하지 않습니다.
- 같은 2011~2017 결과에 맞춘 component weight, lookback, rebalance 주기 재탐색을 금지합니다.
- validation과 holdout을 실행하지 않습니다.
