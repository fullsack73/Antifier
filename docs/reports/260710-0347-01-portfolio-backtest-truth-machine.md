# 작업 기록 - Portfolio Backtest Truth Machine

- 일시: 2026-07-10 03:47 (Asia/Seoul)
- 작성자: Codex
- 에이전트: Codex
- 작업 유형: 기능 추가/버그 수정/문서

## 요약

- ARIMA + Transformer와 Transformer forecast 실패 시 임의의 `+8%` 기대수익률 대신 no-view를 반환하도록 변경했습니다.
- forecast 모델을 기본 optimizer 신호로 승격하기 전 검증할 수 있는 rolling rebalance backtest 엔진과 CLI를 추가했습니다.

## 변경 범위

- Backend-only research workflow입니다.
- public Flask API와 frontend UI는 추가하지 않았습니다.

## 주요 변경 파일

- `src/backend/forecast_models.py`
- `src/backend/portfolio_optimization.py`
- `src/backend/portfolio_backtest.py`
- `tools/backtest_portfolio_models.py`
- `tests/test_portfolio_backtest.py`
- `docs/01-folder-architecture.md`
- `docs/02-specs.md`
- `docs/03-product-plan.md`

## 검증

- `PYTHONPATH=src/backend .venv/bin/python -m pytest tests/test_portfolio_backtest.py tests/test_high_priority_fixes.py::test_ml_pipeline_converts_annual_log_return_to_annual_simple_return tests/test_high_priority_fixes.py::test_mpt_uses_confidence_adjusted_expected_returns tests/test_high_priority_fixes.py::test_black_litterman_uses_confidence_adjusted_views_and_omega tests/test_forecast_model_comparison.py -q`

## 리스크/이슈

- ARIMA + Transformer와 Transformer backtest는 TensorFlow 기반 forecast를 ticker별로 실행하므로 큰 universe에서는 오래 걸릴 수 있습니다.
- v1 promotion decision은 단일 실행에서 기본값 승격을 확정하지 않고, 여러 universe 확인 필요 상태를 반환합니다.

## 다음 작업

- 실제 SP500 sample, DOW, custom basket 결과를 저장해 promotion gate 기준을 보정합니다.
- 필요하면 backtest 결과를 UI/API로 노출하는 별도 후속 작업을 계획합니다.

## 참고

- 관련 문서: `docs/02-specs.md`, `docs/03-product-plan.md`
