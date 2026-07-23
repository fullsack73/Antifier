# Post-Control Cash-Aware Performance

## 결정

- Production optimizer의 post-control performance를 실제 위험자산/현금
  exposure 기준으로 계산하도록 수정했습니다.
- 잔여 현금은 risk-free return을 얻는 zero-volatility asset으로
  취급합니다.
- Target optimizer, forecast, covariance, execution weight는 변경하지
  않았습니다.

## 결함

Rebalance band 또는 max-turnover control은 현재 portfolio에 현금이 있거나
목표 매수를 한 번에 완료할 수 없을 때 위험자산 weight 합계를 1보다 작게
남길 수 있습니다.

기존 `_performance_for_weights`는 반환 weight를 항상 합계 1로
재정규화했습니다. 따라서 실제 controlled weight가 `[30%, 30%]`, cash
`40%`여도 성과는 `[50%, 50%]`, cash `0%`로 표시됐습니다.

재현 입력:

- expected returns: `[10%, 6%]`
- covariance diagonal: `[0.04, 0.09]`
- risk-free rate: `2%`
- controlled risky weights: `[30%, 30%]`
- cash: `40%`

| Metric | 기존 표시 | 수정 |
|---|---:|---:|
| Risky exposure | 100% | 60% |
| Cash weight | 0% | 40% |
| Expected return | 8.00% | 5.60% |
| Volatility | 18.03% | 10.82% |
| Sharpe | 0.3328 | 0.3328 |

Risk-free cash로 위험자산 exposure만 선형 축소하면 excess return과
volatility가 같은 비율로 줄어 Sharpe는 유지되는 것이 맞습니다.

## 구현

`_performance_for_weights`에 `preserve_cash_exposure`를 추가했습니다.

- Solver candidate 비교: 기존처럼 fully-invested weight normalization
- 최종 사용자 반환 weight: 실제 합계를 보존
- `cash_weight = max(0, 1 - risky_weight_sum)`
- expected return:
  `risky_weights @ expected_returns + cash_weight * risk_free_rate`
- variance:
  `risky_weights.T @ covariance @ risky_weights`

Production optimizer 응답 추가:

- `risky_exposure`
- `cash_weight`
- `pre_control_cash_weight`
- `controlled_cash_weight`

## 검증

- 직접 cash-aware return/risk/Sharpe 단위 테스트
- max-turnover로 40% cash가 남는 production optimizer 통합 테스트
- controlled weight 합계와 exposure/cash identity
- risk-free cash expected-return 기여
- covariance의 실제 risky exposure scaling
