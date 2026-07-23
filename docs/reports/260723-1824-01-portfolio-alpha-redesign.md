# Portfolio Alpha Diagnostics and Redesign

## Summary

portfolio research backtest를 signal, portfolio construction, execution 3계층으로 분리하고 training-window IC calibration 기반 `adaptive_signal_tilt` 후보를 구현했습니다.

- public API와 optimizer UI/default forecast는 변경하지 않았습니다.
- 새 후보는 live 4-case validation에서 0/4로 탈락했습니다.
- validation 탈락에 따라 standard와 2024-2025 locked holdout은 실행하지 않았습니다.
- default forecast method는 변경하지 않습니다.

## Prior Failure Diagnosis

기존 `arima_transformer_rank_bl`과 `transformer_rank_bl` live run에서 확인된 문제를 설계 입력으로 사용했습니다.

- 종목별 절대 미래수익률 예측 후 사후 순위화하는 목표가 portfolio의 relative-return alpha와 어긋났습니다.
- Transformer prediction이 `±0.6900` 경계에 반복적으로 포화되어 cross-sectional rank 안정성이 약했습니다.
- uncertainty가 실제 out-of-sample 오차, regime, ticker별로 calibration되지 않았습니다.
- ticker별 단변량 학습은 시장/sector/beta 공통요인과 종목 고유 alpha를 분리하지 못했습니다.
- ticker × rebalance 재학습은 candidate 4-case에서도 forecast 216개와 약 20~30분이 필요했습니다.
- 주된 실패는 no-view가 아니라 정상 생성된 forecast의 방향성과 상대순위 품질 부족이었습니다.

## Implementation

### Signal

- 12-1 momentum, 6-month momentum, 1-month reversal, low-volatility, drawdown rank를 결합합니다.
- 각 rebalance의 training window 내부에서 완료된 forward relative-return 구간만 사용해 component rank IC를 calibration합니다.
- raw/component signal, calibration row, coverage, realized forward return, 21일/forecast-horizon IC, persistence, top-minus-bottom spread를 저장합니다.

### Portfolio construction

- BL confidence shrinkage 대신 equal-weight 주변의 목표 active share 20% long-only tilt를 사용합니다.
- signal-weight rank correlation, equal-weight L1, active share, concentration, predicted volatility를 기록합니다.
- 기존 BL 후보에는 prior, raw view, adjusted view, posterior return과 view retention을 기록합니다.

### Execution

- pre-control/controlled weight, raw/controlled turnover, execution weight L1, signal retention을 기록합니다.
- gross/net period return과 transaction-cost return drag를 분리합니다.

### Experiment isolation

- `candidate`/`standard`는 validation, `smoke`는 research로 표시합니다.
- `holdout` preset은 2022-2025 price window로 504일 train 후 2024-2025만 평가하며 별도 cache namespace를 사용합니다.
- validation 탈락 후보에는 holdout을 실행하지 않습니다.

## Live Validation

설정: 504일 train, 63일 forecast/rebalance, 거래비용 10 bps, rebalance band 2%, max turnover 35%.

| Basket / Regime | Candidate Sharpe | Equal-weight Sharpe | Mean Rank IC | Positive IC | Top-bottom | Active Share | Execution Retention |
|---|---:|---:|---:|---:|---:|---:|---:|
| SP500 sample / bull | 0.6140 | 0.8321 | -0.0197 | 50.0% | -0.0397 | 20.0% | 86.0% |
| tech / crash | 2.1534 | 2.1282 | 0.2024 | 50.0% | 0.1095 | 19.5% | 83.5% |
| defensive / inflation-rate shock | -0.1242 | 0.1154 | -0.2398 | 37.5% | -0.0622 | 19.6% | 91.1% |
| mixed ETF-like / sideways | 0.1248 | 0.7136 | -0.3212 | 25.0% | -0.0505 | 20.0% | 105.1% |

## Decision

- construction이 신호를 유지했고 execution loss도 주된 실패 원인이 아니었습니다.
- price-only weak-signal stack은 여러 basket/regime에서 일관된 alpha를 만들지 못했습니다.
- `adaptive_signal_tilt` v1은 reproducible research candidate로 유지하되 승격하지 않습니다.
- 같은 validation 결과에 맞춘 재튜닝을 금지하고 point-in-time/factor-neutral v2 연구를 새 TODO로 분리했습니다.
- 기존 `portfolio-alpha-diagnostics-redesign.md` TODO는 구현과 validation 완료로 종료했습니다.

## Outputs

- `logs/portfolio_gauntlet_candidate_adaptive_20260723.json`
- `logs/portfolio_gauntlet_candidate_adaptive_20260723.md`
- `logs/portfolio_gauntlet_candidate_adaptive_20260723.json.checkpoint.jsonl`
- `docs/todo/portfolio-alpha-v2-research.md`

## Verification

- `PYTHONPATH=src/backend .venv/bin/python -m pytest tests/test_portfolio_backtest.py -q`: 31 passed
- `PYTHONPATH=src/backend .venv/bin/python -m pytest tests`: 115 passed
- Python compile verification passed for changed backend/tool modules
- live validation process exited with code 0 and wrote 4/4 checkpoint cases
