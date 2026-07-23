# Forecast Signal Diagnostics Foundation

## Summary

ARIMA/Transformer portfolio forecast를 다시 튜닝하기 전에 기존 validation cache를 재학습 없이 진단하고, 새 research run이 반드시 남겨야 할 clip/uncertainty/signal-only evidence를 구현했습니다.

- optimizer API, UI, default forecast는 변경하지 않았습니다.
- replacement model을 기존 validation 4-case에 맞춰 튜닝하지 않았습니다.
- candidate/standard gauntlet과 locked holdout은 실행하지 않았습니다.

## Existing cache diagnosis

source: `logs/portfolio_gauntlet_forecasts.sqlite3`, schema v1, cached prediction 432개.

| Namespace | Output | Count | Coverage | Boundary saturation | Unique ratio | Tie rate | Mean uncertainty |
|---|---|---:|---:|---:|---:|---:|---:|
| `arima-transformer-rank-v1` | hybrid final | 216 | 100% | 0.00% | 94.44% | 5.56% | 0.1797 |
| `arima-transformer-rank-v1` | Transformer component | 216 | 100% | 17.13% | 83.80% | 16.20% | 0.1797 |
| `transformer-rank-v1` | Transformer final | 216 | 100% | 17.13% | 83.80% | 16.20% | 0.2375 |

Transformer boundary 37개는 positive `+0.69` 25~26개, negative `-0.69` 11~12개였습니다. hybrid 평균은 ARIMA와 결합해 final output의 정확한 boundary tie를 제거했지만 내부 Transformer 정보 손실은 그대로 남았습니다.

이 수치는 이미 소비한 validation forecast의 failure diagnosis이며 새 모델 선택 또는 parameter tuning score로 사용하지 않습니다.

## Implementation

### Forecast output evidence

`TransformerForecastModel.predict()`가 다음을 반환합니다.

- raw annualized log return
- daily clip 적용 후 annual clip 전 값
- clipped annual log return
- annual boundary hit
- daily clip hit count/rate
- uncertainty source와 training daily RMSE

ARIMA+Transformer는 component disagreement와 Transformer component diagnostics를 함께 기록합니다.

### Research diagnostics

`forecast_signal_research.py`는 다음을 제공합니다.

- forecast coverage/no-view, distribution, boundary saturation, unique/tie 진단
- training cutoff 내부 완료 window만 사용하는 absolute/relative/factor-residual target builder
- 동일 단위 완료 OOS residual 기반 empirical uncertainty radius와 reported coverage
- period별 cross-sectional rank IC, positive rate, top-minus-bottom spread, coverage
- portfolio construction 이전 signal-only rejection gate

### Cache isolation

forecast rank cache schema를 `2026-07-23-v2-diagnostics`로 올렸습니다. 새 evidence가 없는 v1 prediction을 미래 research run에서 자동 재사용하지 않습니다.

## Remaining work

- validation과 겹치지 않는 research universe/기간 확정
- absolute, relative, factor-residual target을 같은 split에서 비교
- regularized regression 뒤 pairwise/listwise ranking objective 비교
- ticker-independent pooled/joint model과 batched inference 비용 측정
- completed walk-forward residual로 uncertainty calibration
- signal-only gate를 통과한 단일 frozen candidate만 기존 4-case validation에 전달

## Verification

- existing cache 432 predictions parsed without retraining
- `PYTHONPATH=src/backend .venv/bin/python -m pytest tests/test_portfolio_backtest.py -q`: 39 passed
- Python compile verification passed for changed backend/tool modules
