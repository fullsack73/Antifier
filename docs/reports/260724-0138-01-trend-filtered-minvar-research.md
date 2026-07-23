# Trend-Filtered Minimum Variance Research

- 작업 일시: 2026-07-24 01:38 (KST)
- 상태: 후보 폐기
- split: `fama-french-49-industry-trend-minvar-research-1983-1999-v1`
- namespace: `risk-v8-trend-filtered-minvar-industry-portfolios`

## 데이터

- source: Kenneth R. French Data Library, 49 Industry Portfolios Daily
- 기존 원본 ZIP과 FRED DGS3MO 파일 재사용, 추가 다운로드 없음
- derived price index: 1981-09-01~1999-12-31, 4,635행 × 49 industries
- research evaluation: 1983-08-29~1999-12-31
- historical risk-free: FRED DGS3MO daily-equivalent, backward-asof only

## 후보

- baseline: Ledoit-Wolf minimum variance
- candidate: baseline sleeve 중 252일 trailing return이 양수인 자산만 보유
- 비활성 sleeve는 해당 날짜의 historical risk-free cash로 유지
- lookback과 0% threshold는 결과 확인 전에 split manifest에 고정했습니다.
- 504일 train, 63일 rebalance, 10bp cost, 10% asset cap, 2% band, 35% turnover cap

## 결과

| Model | CAGR | Volatility | Sharpe | Max DD | CVaR | Risk exposure | Turnover |
|---|---:|---:|---:|---:|---:|---:|---:|
| Ledoit-Wolf minimum variance | 10.33% | 10.70% | 0.4301 | -31.77% | 1.608% | 99.55% | 16.40% |
| Trend-filtered minimum variance | 10.27% | 8.79% | 0.4957 | -28.48% | 1.319% | 78.80% | 25.54% |

- candidate minus baseline volatility: `-1.902%p`
- candidate minus baseline Sharpe: `+0.0655`
- P(lower volatility): `100.00%`
- P(higher return): `41.50%`
- P(higher Sharpe): `73.45%`
- promotion eligible: false

## 결정

- deterministic risk/return gate는 통과했지만 statistical Sharpe gate와 Holm correction을 통과하지 못했습니다.
- 평균 Sharpe 개선만으로 승격하지 않고 후보를 폐기합니다.
- 같은 1983~1999 결과에 맞춘 lookback, trend threshold, cash floor 재탐색을 금지합니다.
- validation과 holdout을 실행하지 않습니다.
