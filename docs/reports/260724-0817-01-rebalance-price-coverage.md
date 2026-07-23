# Rebalance Execution Price Coverage

- 작업 일시: 2026-07-24 08:17 KST
- 범위: production portfolio-management order generation
- 성격: execution correctness 개선, alpha/default model 승격 아님

## 문제

`calculate_rebalance_orders`는 최신 가격이 없는 기존 보유를 0원으로 평가하고, 가격이 없는 신규 target은 주문에서 조용히 생략했습니다. 따라서 일부 자산만 포함된 buy/sell list가 성공 응답으로 반환될 수 있었습니다.

## 변경

- 양수 보유수량과 양수 target weight의 합집합을 필수 가격 universe로 정의했습니다.
- 필수 ticker의 최신 가격은 finite 양수여야 합니다.
- 하나라도 누락/0/음수/NaN/무한이면 partial order를 만들지 않습니다.
- 수량, target weight, 현금 주입도 finite non-negative 입력만 허용합니다.
- 성공 응답은 `required_price_tickers`와 `execution_price_coverage=1.0`을 반환합니다.
- 실패 응답은 HTTP 400과 `required_price_tickers`, `missing_price_tickers`, 실제 coverage 비율을 반환합니다.
- 0수량/0weight ticker는 실행 노출이 없으므로 필수 가격 universe에서 제외합니다.

## 검증

- portfolio-management targeted suite: `39 passed`
- backend 전체 suite: `331 passed in 81.03s`
- `git diff --check`: 통과

대표 재현은 target `AAPL` 가격은 있지만 기존 보유 `OLD` 가격이 없는 경우입니다. 필수 2종 중 1종만 가격이 있으므로 coverage는 `0.5`이며 buy/sell list 없이 오류가 반환됩니다.

## 데이터

외부 다운로드는 없었습니다. 기존 로컬 SEC companyfacts 20,087개와 submissions 174개는 이 execution 검증에 필요하지 않습니다.

## 결론

실행 주문의 완전성과 관측 가능성은 개선됐습니다. 이는 forecast alpha, covariance model, optimizer default의 통계적 성능 향상을 증명하지 않으므로 quant-standard 승격 상태는 그대로 미완료입니다.
