# Unmodeled Exposure Performance Coverage

## 결정

- Post-control portfolio에 optimizer model universe 밖 기존 보유가 남으면
  return, risk, Sharpe를 계산 불가로 반환합니다.
- 미모델 위험자산을 현금으로 대체하지 않습니다.
- Controlled weights와 주문 생성은 유지하되 metric coverage를 명시합니다.

## 결함

Turnover cap은 데이터/forecast/covariance 단계에서 제외된 기존 보유를 한 번에
청산하지 못하게 할 수 있습니다.

재현:

- modeled target: `AAA 60% / BBB 40%`
- current: `AAA 10% / BBB 10% / OLD 80%`
- max gross turnover: `20%`
- controlled:
  `AAA 16.25% / BBB 13.75% / OLD 70%`

실제 risky exposure는 100%입니다. 그러나 `_performance_for_weights`가
mu/covariance에 없는 `OLD`를 reindex 과정에서 제거한 뒤 남은 70%를
risk-free cash처럼 처리했습니다.

기존 false metric:

- expected return: `3.85%`
- volatility: `5.25%`
- Sharpe: `0.3523`
- 실질적으로 `OLD 70%`의 return, variance, covariance는 미지수

## 수정

최종 controlled portfolio를 다음으로 분해합니다.

- `modeled_risky_exposure`
- `unmodeled_risky_exposure`
- `cash_weight`
- `unmodeled_weights`
- `performance_coverage = 1 - unmodeled_risky_exposure`

미모델 exposure가 `1e-8`보다 크면:

- `performance_status = unavailable_unmodeled_exposure`
- `return = null`
- `risk = null`
- `sharpe_ratio = null`
- `performance_warning` 제공

재현 결과:

- modeled risky exposure: `30%`
- unmodeled risky exposure: `70%`
- cash: `0%`
- performance coverage: `30%`
- return/risk/Sharpe: 계산 불가

## Frontend

- null-safe percentage/ratio formatter 추가
- 영문 `Unavailable`, 한국어 `계산 불가`
- retained unmodeled holding 경고 표시
- JSON download와 controlled weights 표시는 유지

## 검증

- modeled/unmodeled/cash exposure identity
- unmodeled ticker와 weight 보존
- incomplete coverage에서 numeric metric 차단
- complete coverage에서 기존 cash-aware metric 유지
- React restored-job null metric rendering
- 한국어/영어 i18n 동시 업데이트
