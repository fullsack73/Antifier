# Trend Risk Parity Validation

- 작업 일시: 2026-07-24 01:59 (KST)
- 상태: validation 탈락
- split: `fama-french-49-industry-trend-risk-parity-validation-2018-2021-v1`
- frozen from: `fama-french-30-industry-trend-risk-parity-replication-1928-1971-v1`

## 검증 계약

- frozen research result SHA-256 `9d087320…f8417a`
- candidate specification 변경 없음
- 4개 산업 basket deterministic gate 전부 통과 요구
- 전체 49-industry deterministic, paired bootstrap 95%, Holm gate 통과 요구
- validation manifest role, data/factor/universe/frozen-result SHA를 실행 전에 잠갔습니다.

## 데이터

- source: Kenneth R. French Data Library, 49 Industry Portfolios Daily
- derived price index: 2016-01-04~2021-12-31, 1,511행 × 49 industries
- validation evaluation: 2018-01-03~2021-12-31
- 2016~2017은 training prehistory에만 사용했습니다.
- historical risk-free: FRED DGS3MO daily-equivalent, backward-asof only
- 2022+ locked holdout는 열지 않았습니다.

## 전체 결과

| Model | CAGR | Volatility | Sharpe | Max DD | Risk exposure | Turnover |
|---|---:|---:|---:|---:|---:|---:|
| Risk parity | 13.98% | 21.06% | 0.6752 | -36.76% | 99.43% | 6.41% |
| Trend-filtered risk parity | 7.82% | 15.30% | 0.4969 | -28.21% | 73.94% | 18.00% |

- P(lower volatility): `100.00%`
- P(higher return): `1.85%`
- P(higher Sharpe): `2.05%`
- Holm-adjusted p-value: `0.9795`
- aggregate gate: rejected

## 4-case 결과

| Case | Candidate vol | Baseline vol | Candidate Sharpe | Baseline Sharpe | Candidate DD | Baseline DD | Gate |
|---|---:|---:|---:|---:|---:|---:|---|
| defensive consumption/health | 16.44% | 17.55% | 0.4752 | 0.6841 | -31.38% | -30.63% | rejected |
| industrial cyclical | 15.05% | 24.43% | 0.4168 | 0.6329 | -29.08% | -41.43% | rejected |
| technology/services | 18.64% | 22.57% | 0.5830 | 0.7803 | -32.59% | -37.07% | rejected |
| real assets/financials | 13.78% | 23.06% | 0.3653 | 0.4908 | -29.91% | -40.07% | rejected |

- passed cases: `0 / 4`

## 결정

- frozen trend-filtered risk parity 후보를 폐기합니다.
- validation에서 낮은 위험을 얻었지만 return/cash drag로 Sharpe가 모든 case에서 하락했습니다.
- validation 결과로 lookback, threshold, exposure floor, base allocator를 재튜닝하지 않습니다.
- 2022~2025 locked holdout은 계속 봉인합니다.
