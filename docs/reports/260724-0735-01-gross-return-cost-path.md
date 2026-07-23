# Gross-Return Costless Path Fix

## 결정

- gross period return을 동일한 pre-cost controlled target의 별도 costless
  기간 경로로 계산하도록 수정했습니다.
- Net execution, optimizer target, covariance, forecast, promotion gate는
  변경하지 않았습니다.
- 이미 본 연구 split의 gross metric 변화는 execution diagnostic으로만
  사용하며 candidate 승격 근거로 재사용하지 않습니다.

## 결함

기존 계산:

`gross_return = (net_period_end_value + starting_transaction_cost) /
starting_value - 1`

이 방식은 비용을 기간말에 현금으로 되돌립니다. 실제 costless
counterfactual에서는 비용으로 줄었던 매수 주문 또는 현금이 기간 동안
자산/현금 수익을 얻어야 합니다.

Synthetic 예:

- 시작 가치: `10,000`
- 자산 기간 수익률: `+100%`
- transaction cost: `10%`
- 비용 후 실제 투자액: `9,090.91`
- net 기간말 가치: `18,181.82`

| Metric | 기존 근사 | 수정 |
|---|---:|---:|
| Gross period return | 90.91% | 100.00% |
| Net period return | 81.82% | 81.82% |
| Transaction-cost drag | 9.09%p | 18.18%p |

## 구현

각 rebalance에서 다음 두 경로를 같은 기간 가격으로 평가합니다.

- Net: transaction cost를 현금과 매수 주문에서 실제 차감한 target
- Gross: trade control까지 적용했지만 transaction cost는 차감하지 않은
  pre-cost target과 잔여 현금

Rebalance record에 다음 값을 추가했습니다.

- `gross_period_end_value`
- `net_period_end_value`

`gross_period_return`, `gross_cumulative_return`,
`transaction_cost_return_drag`는 costless path를 사용합니다.

## Mechanical diagnostic

이미 본
`fama-french-36-source-49-minvar-replication-1928-1969-v1`을 reporting
차이 확인에만 사용했습니다.

| Model | Old gross cumulative | Exact gross cumulative | Correction |
|---|---:|---:|---:|
| Equal weight | 5,407.08% | 5,408.30% | +1.22%p |
| Historical BL | 5,357.09% | 5,358.56% | +1.47%p |
| Lightweight BL | 7,131.77% | 7,134.20% | +2.43%p |
| Risk parity | 5,354.09% | 5,355.24% | +1.14%p |
| Minimum variance | 4,102.85% | 4,104.55% | +1.70%p |

- Net cumulative return: 모든 모델 불변
- Weight/turnover/transaction cost: 불변
- Gross return과 reported cost drag만 교정

## 검증

- +100% asset return/high-cost synthetic regression
- exact gross/net period end value 검증
- gross/net cumulative compounding 검증
- 기존 portfolio backtest suite
