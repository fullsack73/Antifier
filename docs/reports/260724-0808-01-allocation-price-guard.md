# Allocation Price Coverage Guard

## 결정

- Frontend 투자금 배분에서 가격 없는 ticker의 `$1` fallback을
  제거했습니다.
- Positive target weight를 가진 모든 ticker에 유효한 가격이 있어야
  share plan을 계산합니다.
- 누락 ticker를 사용자에게 표시하고 allocation 생성을 차단합니다.

## 결함

`Optimizer.jsx`의 기존 allocation 계산:

`const price = prices[ticker] ?? 1`

Post-control portfolio에 model universe 밖 기존 보유가 남으면 backend
`weights`에는 ticker가 있지만 `prices`에는 없을 수 있습니다. 이때 UI는
해당 자산을 실제 가격 미지수가 아니라 `$1` 자산으로 처리했습니다.

재현:

- controlled weights: `AAPL 30% / OLD 70%`
- prices: `AAPL $100`, `OLD missing`
- budget: `$10,000`
- 기존 OLD allocation: `$7,000`, `7,000 shares @ $1`

이는 실행 불가능한 가짜 주문 계획입니다.

## 수정

Allocation 전에 다음을 검증합니다.

- investment budget가 finite number
- investment budget `> 0`
- weight `> 0.01%`인 모든 ticker의 price가 finite
- 모든 필수 price `> 0`

하나라도 실패하면:

- 기존 allocation 제거
- share/amount 계산 중단
- 누락 ticker 목록 경고
- 한/영 i18n 메시지 표시

가격이 확인된 ticker만으로 weight를 재정규화하거나 누락 자산을 현금으로
간주하지 않습니다.

## 검증

- restored completed optimizer result
- null performance metric rendering
- positive-weight `OLD` price 누락
- 누락 ticker 포함 경고
- allocation result 미생성
- React state update warning 없는 async assertion
