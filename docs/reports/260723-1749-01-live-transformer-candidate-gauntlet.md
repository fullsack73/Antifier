# Live Transformer Candidate Portfolio Gauntlet

## Summary

2026-07-23에 남은 ML rank 후보인 `transformer_rank_bl`을 live yfinance 데이터로 staged candidate gauntlet에 실행했습니다.

- 완료: 4 / 4 representative cases
- 설정: 504일 train window, 63일 forecast/rebalance horizon, 거래비용 10 bps, rebalance band 2%, max turnover 35%
- raw ML forecast: 216개 생성 및 SQLite 저장
- forecast cache namespace: `transformer-rank-v1`
- promotion: `not_promoted`
- survival: 0 / 4
- candidate gate 탈락에 따라 standard 180-case는 실행하지 않았습니다.

## Case Metrics

| Basket / Regime | Sharpe | CAGR | Max DD | Avg Rank IC | Positive IC Rate | Mean L1 vs Equal Weight |
|---|---:|---:|---:|---:|---:|---:|
| SP500 sample / bull | 0.8319 | 0.1565 | -0.2354 | -0.0023 | 50.0% | 0.0366% |
| tech basket / crash | 2.1282 | 0.5787 | -0.1281 | -0.0991 | 25.0% | 0.0193% |
| defensive / inflation-rate shock | 0.1154 | 0.0345 | -0.1121 | 0.1280 | 62.5% | 0.0110% |
| mixed ETF-like / sideways | 0.7133 | 0.0693 | -0.0519 | -0.1726 | 50.0% | 0.0209% |

`Mean L1 vs Equal Weight`는 각 rebalance의 pre-control target weight와 equal-weight target 사이 L1 distance의 평균입니다.

## Failure Pattern

- SP500 bull: equal weight, risk parity, low-volatility보다 Sharpe가 낮고 drawdown이 컸습니다.
- tech crash: equal weight보다 Sharpe와 drawdown이 모두 열세였고 momentum 12-1, market-cap weight보다 Sharpe가 낮았습니다.
- defensive inflation/rate shock: equal weight와 momentum 6m, market-cap weight보다 Sharpe가 낮았습니다.
- mixed ETF-like sideways: equal weight와 market-cap weight보다 Sharpe가 낮고 drawdown도 컸습니다.
- 4개 case 중 3개에서 평균 rank IC가 음수였고, positive IC rate도 일관되지 않았습니다.
- candidate target은 equal weight 대비 평균 L1 distance가 0.0110%~0.0366%에 불과해 portfolio construction 단계에서 신호가 거의 소멸했습니다.

## Decision

- `transformer_rank_bl`을 optimizer 기본값으로 승격하지 않습니다.
- 이전 `arima_transformer_rank_bl` 0/4 결과와 이번 `transformer_rank_bl` 0/4 결과를 합쳐 현재 두 ML rank 후보의 live candidate 검증을 종료합니다.
- 통과 후보가 없으므로 standard 180-case 실행은 보류합니다.
- 후속 작업은 `docs/todo/portfolio-alpha-diagnostics-redesign.md`에서 signal quality, portfolio construction, execution을 분리 진단한 뒤 새 cross-sectional alpha candidate를 설계하는 것입니다.
- `docs/todo/portfolio-gauntlet-live-run.md`는 완료 처리하고 삭제했습니다.

## Outputs

- `logs/portfolio_gauntlet_candidate_transformer_20260723.json`
- `logs/portfolio_gauntlet_candidate_transformer_20260723.md`
- `logs/portfolio_gauntlet_candidate_transformer_20260723.json.checkpoint.jsonl`
- `logs/portfolio_gauntlet_forecasts.sqlite3`

## Verification

- live yfinance candidate gauntlet process exited with code 0
- checkpoint contains 4 completed cases
- JSON reports `completed_count: 4`, `status: not_promoted`, `survival_count: 0`
- persistent forecast cache reports 216 new writes and 432 total entries across the two isolated namespaces
