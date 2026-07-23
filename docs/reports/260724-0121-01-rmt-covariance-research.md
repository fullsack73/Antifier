# RMT Covariance Research

- 작업 일시: 2026-07-24 01:21 (KST)
- 상태: 후보 폐기
- split: `fama-french-49-industry-rmt-research-2000-2010-v1`
- namespace: `risk-v7-rmt-industry-portfolios`

## 데이터

- source: Kenneth R. French Data Library, 49 Industry Portfolios Daily
- section: Average Value Weighted Returns
- 원본 ZIP: 4.0MB, SHA-256 `e214c54a…f77097`
- derived price index: 1998-01-02~2010-12-31, 3,271행 × 49 industries
- research evaluation: 2000-01-03~2010-12-31
- historical risk-free: FRED DGS3MO daily-equivalent, backward-asof only
- 2011+ data는 다운로드한 archive 안에 존재하지만 파생 research panel과 평가에서 제외했습니다.

## 후보

- baseline: Ledoit-Wolf minimum variance
- candidate: Marchenko-Pastur sample-correlation denoising + Ledoit-Wolf diagonal variance
- 504일 train, 63일 rebalance, 10bp cost, 10% asset cap, 2% band, 35% turnover cap
- 44개 rebalance에서 noise eigenvalue 46~47개, signal eigenvalue 2~3개

## 결과

| Model | CAGR | Volatility | Sharpe | Max DD | Turnover | Risk MAE |
|---|---:|---:|---:|---:|---:|---:|
| Ledoit-Wolf | 8.05% | 15.22% | 0.4227 | -43.55% | 13.90% | 5.01% |
| RMT | 7.51% | 15.33% | 0.3882 | -43.70% | 15.89% | 5.04% |

- candidate minus baseline volatility: `+0.108%p`
- candidate minus baseline Sharpe: `-0.0345`
- P(lower volatility): `3.15%`
- P(higher Sharpe): `21.0%`
- Holm-adjusted p-value: `0.9685`
- promotion eligible: false

## 결정

- RMT 후보를 폐기하고 Ledoit-Wolf를 유지합니다.
- threshold, variance blend, train window를 같은 결과에 맞춰 재탐색하지 않습니다.
- validation과 holdout을 실행하지 않습니다.
