# Initial-Cost Metric Anchor Fix

## 결정

- Primary portfolio metrics의 시작 base를 최초 transaction cost 차감 후
  value가 아니라 배치 전 `initial_value`로 교정했습니다.
- 최초 비용은 첫 실제 일수익률과 wealth drawdown에 포함합니다.
- Net execution, terminal wealth, weights, turnover, transaction-cost 금액은
  변경하지 않았습니다.

## 결함

Backtest value timeline은 첫 rebalance date의 비용 차감 후 value부터
시작했습니다. `_portfolio_metrics`가 이 값을 새 원금으로 사용해 최초 배치
비용이 CAGR, daily return, volatility, Sharpe, downside/tail risk,
drawdown에서 사라졌습니다.

Flat-price synthetic:

- initial value: `10,000`
- transaction cost rate: `10%`
- 실제 cost: `909.09`
- terminal value: `9,090.91`
- net cumulative return: `-9.09%`
- 기존 primary CAGR: `0%`

Terminal wealth와 period return은 비용을 반영했지만 primary performance
metric만 반영하지 않는 모순이었습니다.

## 수정

`_portfolio_metrics`에 선택적 `initial_value` anchor를 추가했습니다.

- CAGR base: pre-cost `initial_value`
- 첫 실제 daily return:
  `second_daily_value / initial_value - 1`
- drawdown path:
  `[initial_value, first_post_cost_value, ...]`
- evaluation trading-period 수는 기존 실제 기간을 유지해 synthetic
  timestamp를 추가하지 않음
- 직접 호출하는 기존 metric helper는 anchor 미지정 시 종전 동작 유지

Flat-price synthetic 결과:

- terminal/net cumulative return: `-9.09%`
- max drawdown: `-9.09%`
- CAGR: 동일 terminal loss와 실제 2거래일에 맞춰 계산
- annual volatility: 최초 비용을 포함해 `> 0`

## Mechanical diagnostic

이미 본
`fama-french-36-source-49-minvar-replication-1928-1969-v1`에서 metric
교정 영향만 확인했습니다. 승격 판정에는 재사용하지 않습니다.

| Model | CAGR before | CAGR after | Sharpe before | Sharpe after |
|---|---:|---:|---:|---:|
| Equal weight | 9.1568% | 9.1544% | 0.50043 | 0.50031 |
| Historical BL | 9.1327% | 9.1303% | 0.50407 | 0.50395 |
| Lightweight BL | 9.7266% | 9.7242% | 0.54731 | 0.54719 |
| Risk parity | 9.1316% | 9.1293% | 0.51729 | 0.51716 |
| Minimum variance | 8.4540% | 8.4516% | 0.61199 | 0.61182 |

- Terminal wealth: 모든 모델 불변
- `final_value / initial_value - 1 == net_cumulative_return`
- 최대 terminal identity error: `5.7e-14`
- 최초 10bps 비용을 포함하면서 CAGR 약 `0.0024%p` 하향

## 검증

- flat-price/high-cost synthetic regression
- initial cost 포함 CAGR
- initial peak 기준 max drawdown
- annual volatility nonzero
- terminal wealth/net cumulative return identity
- 기존 portfolio backtest suite
