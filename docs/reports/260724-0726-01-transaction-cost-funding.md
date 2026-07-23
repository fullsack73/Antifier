# Transaction-Cost Funding Fix

## 결정

- backtest transaction cost를 실제 실행된 gross traded notional과
  자기일관되게 계산하도록 수정했습니다.
- 목표 현금이 비용을 충당하면 target을 유지합니다.
- 현금이 부족하면 기존 보유 전체를 비례 축소하지 않고 매수 주문만 같은
  비율로 줄입니다.
- Forecast, covariance, optimizer objective, promotion gate는 변경하지
  않았습니다.

## 결함

기존 흐름은 trade control target으로 비용을 먼저 계산한 뒤 target asset
전체를 `portfolio_value - cost`에 맞춰 비례 축소했습니다.

예: 현재 `[500, 500]`, target `[600, 400]`, portfolio `1,000`, 비용
`1%`.

- 사전 gross trade: `200`
- 사전 계산 비용: `2`
- 기존 결과: target 전체 비례 축소
- 문제: 매수 주문뿐 아니라 기존 보유에도 숨은 추가 매도가 생기지만
  turnover와 transaction cost에는 포함되지 않음

## 수정

비용률을 `r`, 사전 gross trade를 `G`, target 이후 현금을 `C`라 할 때
현금 부족분은 다음 매수 축소액으로 충당합니다.

`buy_reduction = (rG - C) / (1 + r)`

축소 뒤 실제 delta, gross trade, transaction cost를 다시 계산합니다.
위 예의 결과는 다음과 같습니다.

- target: `[598.019802, 400]`
- 실제 gross trade: `198.019802`
- transaction cost: `1.980198`
- 잔여 현금: `0`

추가 diagnostics:

- `pre_cost_controlled_trade_value`
- `transaction_cost_rate`
- `transaction_cost_funding_buy_reduction`
- `cash_before_transaction_cost`
- `cash_after_transaction_cost`

## Mechanical diagnostic

이미 결과를 본 `fama-french-36-source-49-minvar-replication-1928-1969-v1`
panel을 회계 전후 영향 확인에만 재사용했습니다. 승격 판정에는 사용하지
않습니다.

| Model | CAGR before | CAGR after | Sharpe before | Sharpe after | Mean cash after |
|---|---:|---:|---:|---:|---:|
| Equal weight | 9.1573% | 9.1568% | 0.5005 | 0.5004 | 0.0015% |
| Historical BL | 9.1333% | 9.1327% | 0.5041 | 0.5041 | 0.0021% |
| Lightweight BL | 9.7994% | 9.7266% | 0.5514 | 0.5473 | 0.0204% |
| Risk parity | 9.0698% | 9.1316% | 0.5146 | 0.5173 | 0.0020% |
| Minimum variance | 8.4499% | 8.4540% | 0.6116 | 0.6120 | 0.0153% |

- 모든 rebalance의
  `transaction_cost == actual_gross_trade * cost_rate`
- 최대 비용 항등식 오차: `0`
- 최소 비용 후 현금: `0`
- 숨은 비례매도 제거로 모델별 경로는 소폭 달라짐

## 데이터

- 기존 로컬 `companyfacts/`: 20,087개 JSON, 18GB
- 기존 Nasdaq SEC submissions: 174개 JSON, 25MB
- 추가 외부 다운로드: 없음
- 전체 SEC `submissions.zip`은 현재 연구 범위에 필요한 SIC 자료가 이미
  있으므로 중복 다운로드하지 않았습니다.

## 검증

- 매수 주문만 축소하는 self-financing 단위 테스트
- 기존 목표 현금을 먼저 사용하는 단위 테스트
- end-to-end 실제 체결액/비용/자산/현금 항등식 테스트
- early-history mechanical diagnostic
