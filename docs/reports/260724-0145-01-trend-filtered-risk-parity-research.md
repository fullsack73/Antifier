# Trend-Filtered Risk Parity Research

- 작업 일시: 2026-07-24 01:45 (KST)
- 상태: 후보 폐기
- split: `fama-french-49-industry-trend-risk-parity-research-1973-1981-v1`
- namespace: `risk-v9-trend-filtered-risk-parity-industry-portfolios`

## 데이터

- source: Kenneth R. French Data Library, 49 Industry Portfolios Daily
- 기존 official raw archive 재사용, 추가 다운로드 없음
- derived price index: 1971-03-12~1981-08-31, 2,645행 × 49 industries
- research evaluation: 1973-03-13~1981-08-31
- historical risk-free: French daily one-month Treasury-bill return
- DGS3MO 시작 전 구간에 미래 금리를 역채우지 않았습니다.
- 1971-03-11의 단일 `Softw` 결측 이후부터 완전 패널을 시작했습니다.

## 후보

- baseline: inverse-volatility risk parity
- candidate: baseline sleeve 중 252일 trailing return이 양수인 자산만 보유
- 비활성 sleeve는 같은 날짜의 official French risk-free cash로 유지
- lookback과 0% threshold는 결과 확인 전에 split manifest에 고정했습니다.
- 504일 train, 63일 rebalance, 10bp cost, 10% asset cap, 2% band, 35% turnover cap

## 결과

| Model | CAGR | Volatility | Sharpe | Max DD | CVaR | Risk exposure | Turnover |
|---|---:|---:|---:|---:|---:|---:|---:|
| Risk parity | 9.62% | 13.53% | 0.1738 | -43.34% | 1.951% | 98.28% | 3.44% |
| Trend-filtered risk parity | 10.63% | 7.43% | 0.3544 | -14.54% | 1.108% | 59.34% | 8.15% |

- candidate minus baseline volatility: `-6.103%p`
- candidate minus baseline Sharpe: `+0.1806`
- P(lower volatility): `100.00%`
- P(higher return): `52.30%`
- P(higher Sharpe): `75.55%`
- promotion eligible: false

## 결정

- deterministic risk/return gate는 통과했지만 statistical Sharpe gate와 Holm correction을 통과하지 못했습니다.
- 평균 Sharpe와 drawdown 개선만으로 승격하지 않고 후보를 폐기합니다.
- 같은 1973~1981 결과에 맞춘 lookback, threshold, exposure floor 재탐색을 금지합니다.
- validation과 holdout을 실행하지 않습니다.
