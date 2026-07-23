# Production Transaction-Cost Funding

- 작업 일시: 2026-07-24 08:30 KST
- 범위: portfolio manager live rebalance execution
- 성격: execution truth 개선, alpha/default model 승격 아님

## 문제

Walk-forward backtest는 gross traded value에 transaction cost를 적용하고 비용을 현금/매수 축소로 조달했지만, `POST /api/manage-portfolio`의 production 주문은 비용을 0으로 가정했습니다. Fully-invested target은 주문 market value만 예산을 모두 사용하므로 실제 수수료·슬리피지를 지불하면 현금이 음수가 될 수 있었습니다. UI도 비용 전 optimizer weight를 목표 비중으로 표시했습니다.

## 변경

- backtest의 검증된 transaction-cost funding 함수를 optimizer 공용 모듈로 이동해 live/backtest가 같은 수학을 사용합니다.
- portfolio manager 기본값은 10bps이며 `0 <= transaction_cost_bps < 10000`만 허용합니다.
- target이 보유한 현금을 비용에 먼저 사용하고 부족분만 buy notional에서 비례 축소합니다.
- 정수/소수 주문을 만든 뒤 실제 gross traded value로 비용·investable value·잔여현금을 다시 계산합니다.
- `execution_target_weights`, `gross_trade_value`, `transaction_cost`, `investable_value`, `remaining_cash`, `transaction_cost_diagnostics`를 반환합니다.
- UI advanced settings에서 bps를 저장·전송하고 실행 가능 비중, 예상 거래비용, 잔여현금을 표시합니다.
- 목표 보유 CSV와 benchmark용 JSON top-level `weights`도 optimizer 희망 weight가 아니라 실행 가능 weight를 기록합니다.

## 불변식

모든 성공 주문은 다음을 만족합니다.

`실행 target 보유가치 + transaction cost + remaining cash = total target value`

비용 부족분은 매수에서만 조달하므로 비용 반영을 위해 기존 보유를 비례 축소하는 숨은 매도는 없습니다. 정수 주식은 비용을 낸 뒤 매수 가능한 수량만 남기며 잔여현금을 명시합니다.

## 검증

- transaction-cost/portfolio targeted backend: `48 passed`
- backend 전체: `335 passed in 81.38s`
- frontend lint: 통과
- frontend tests: `14 passed`
- frontend production build: 통과
- 기존 Plotly 대형 chunk 경고만 유지
- `git diff --check`: 통과

## 데이터

외부 다운로드는 없었습니다. 이 변경은 시장 데이터나 SEC 원천이 아니라 live execution 회계의 일관성을 수정합니다.

## 결론

Backtest와 production 주문의 비용 가정이 일치하고 예산 초과 주문이 제거됐습니다. 이는 실현 가능성과 성과 측정 신뢰도를 높이지만 forecast alpha 또는 covariance/default allocator의 통계적 우위를 증명하지 않으므로 quant-standard 승격 상태는 아직 미완료입니다.
