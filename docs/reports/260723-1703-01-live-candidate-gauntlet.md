# Live Candidate Portfolio Gauntlet

## Summary

2026-07-23에 staged gauntlet의 primary `arima_transformer_rank_bl` 후보를 live yfinance 데이터로 실행했습니다.

- 완료: 4 / 4 representative cases
- 실행 시간: 약 23분 30초
- raw ML forecast: 216개 생성 및 SQLite 저장
- 재생 검증: 216 persistent cache hit, 신규 학습 0회
- promotion: `not_promoted`
- survival: 0 / 4
- 설계된 candidate gate에서 탈락했으므로 standard 180-case는 실행하지 않았습니다.

## Case Metrics

| Basket / Regime | Sharpe | CAGR | Max DD | Avg Rank IC | Positive IC Rate |
|---|---:|---:|---:|---:|---:|
| SP500 sample / bull | 0.8318 | 0.1565 | -0.2354 | 0.0152 | 62.5% |
| tech basket / crash | 2.1282 | 0.5787 | -0.1281 | -0.0060 | 50.0% |
| defensive / inflation-rate shock | 0.1154 | 0.0345 | -0.1121 | 0.1161 | 50.0% |
| mixed ETF-like / sideways | 0.7134 | 0.0694 | -0.0519 | 0.0212 | 75.0% |

## Failure Pattern

- SP500 bull: equal weight, risk parity, low volatility보다 Sharpe가 낮고 drawdown이 컸습니다.
- tech crash: equal weight보다 미세하게 낮고 momentum 12-1, market-cap weight보다 Sharpe가 낮았습니다.
- defensive inflation/rate shock: equal weight, momentum 6m, market-cap weight보다 Sharpe가 낮았습니다.
- mixed ETF-like sideways: equal weight와 market-cap weight보다 Sharpe가 낮고 drawdown도 나빴습니다.
- candidate weight는 equal weight 대비 평균 L1 차이가 case별 약 0.012%~0.038%에 그쳐 기본 uncertainty 설정에서는 ML rank view가 사실상 소멸했습니다.

## Uncertainty Replay

저장된 raw forecast를 사용해 `FORECAST_RANK_VIEW_UNCERTAINTY`를 0.30, 0.20, 0.15, 0.10으로 낮춰 재학습 없이 재생했습니다.

- 모든 설정에서 survival은 0 / 4였습니다.
- tech crash는 신호가 강해질 때 소폭 개선됐지만 market-cap/momentum baseline을 넘지 못했습니다.
- SP500 bull, defensive, mixed ETF-like에서는 신호를 강하게 할수록 성과가 악화됐습니다.
- 따라서 단순히 BL view 강도를 높이는 변경은 채택하지 않았습니다.

## Decision

- primary 후보를 optimizer 기본값으로 승격하지 않습니다.
- 현재 raw forecast rank IC는 대부분 0 근처이며 regime 간 일관성이 부족합니다.
- 다음 모델 변경은 allocation 강도 조정보다 cross-sectional rank IC와 positive IC rate 개선을 우선해야 합니다.
- rank IC 진단을 backtest summary와 rebalance record에 추가해 이후 후보가 실제 forward ranking signal을 갖는지 먼저 확인하도록 했습니다.

## Outputs

- `logs/portfolio_gauntlet_candidate_20260723.json`
- `logs/portfolio_gauntlet_candidate_20260723.md`
- `logs/portfolio_gauntlet_candidate_20260723.json.checkpoint.jsonl`
- `logs/portfolio_gauntlet_forecasts.sqlite3`

## Verification

- `PYTHONPATH=src/backend .venv/bin/python -m pytest tests/test_portfolio_backtest.py -q`
- cached live candidate replay completed with 216 persistent hits and 0 misses
