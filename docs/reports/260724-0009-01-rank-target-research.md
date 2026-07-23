# Factor-Residual Rank-Target Research

- 작업 일시: 2026-07-24 00:09 (KST)
- 범위: historical-DOW research-only signal objective
- 결론: rank-target nested ridge 폐기

## 가설

Nasdaq-100 locked holdout에서 raw residual ridge의 mean rank IC는 양수였지만
top-minus-bottom spread가 음수였다. 새 namespace에서 factor-residual return의
cross-sectional percentile rank를 직접 학습하면 tail ordering이 개선되는지
검증했다.

Nasdaq holdout은 이 가설의 parameter 선택이나 평가에 재사용하지 않았다.

## 구현

- objective: `factor_residual_rank_nested_ridge`
- predictors: 기존 price + PIT quality/profitability/valuation/liquidity
- train target: signal date별 centered percentile rank
- realized evaluation target: 원래 factor-residual forward return
- penalty grid: `[1, 5, 20, 100]`
- inner selection: 완료된 최근 3개 period의 mean rank IC
- no-lookahead: inner training `forward_end_date <= validation_date`

## Locked research contract

- split ID: `historical-dow-factor-rank-research-2011-2025-v4`
- namespace: `pit-factor-v4-rank-target-historical-dow`
- evaluation: 2011-01-01~2025-09-30
- OOS periods: 59
- manifest digest: `af020f8a60d52d013dbf40625ef387ad311e0a93f7f19c3921af22af4491ecb6`

| Objective | Rank IC | Positive IC | Spread | P(IC > 0) | P(spread > 0) |
|---|---:|---:|---:|---:|---:|
| Raw nested ridge | 0.0627 | 61.02% | 0.0153 | 98.70% | 97.45% |
| Rank-target nested ridge | 0.0538 | 57.63% | 0.0078 | 97.75% | 86.00% |

Rank-target minus raw paired result:

- rank IC: `-0.00897`, P(higher) `18.75%`
- spread: `-0.00749`, P(higher) `1.75%`
- spread difference 95% interval: `[-0.01436, -0.00062]`

Rank-target objective는 개별 signal gate와 two-objective Holm gate 모두
통과하지 못했다. 계산비용도 raw 25.43초 대비 27.29초로 개선이 없었다.

## 판정

- rank-target objective를 production/default candidate로 승격하지 않는다.
- Nasdaq holdout 또는 같은 DOW 기간을 이용해 rank transform, penalty,
  tail weight를 추가 탐색하지 않는다.
- 다음 research는 새 universe와 새 feature family를 먼저 선언한다.
