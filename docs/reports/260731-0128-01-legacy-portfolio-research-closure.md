# 작업 기록 - Legacy Portfolio Research 종료

- 일시: 2026-07-31 01:28 (KST)
- 작성자: Codex
- 에이전트: Codex
- 작업 유형: 연구 종료/문서

## 요약

- `portfolio-risk-model-research.md`, `portfolio-forecast-model-redesign.md`, `portfolio-optimizer-quant-standard.md`의 요구사항을 현재 구현·테스트·연구 결과와 대조했습니다.
- 세 TODO의 구현 및 연구 절차는 완료됐고 production 승격 gate를 통과하지 못한 후보는 폐기됐습니다.
- 제한된 데이터의 production 기본값은 검증되지 않은 expected-return max-Sharpe 대신 Ledoit-Wolf global minimum variance로 교체된 상태입니다.
- licensed delisted-inclusive PIT 자료가 필요한 새 가설은 별도 residual/risk/GMV TODO에서 추적하므로 legacy TODO를 종료합니다.

## TODO별 판정

### Portfolio Risk Model Research

- covariance PSD/condition/effective-rank 진단, robust/ensemble/nested estimator, ERC, HRP, CVaR/CDaR, RMT, NCO, constant-correlation, trend, semivariance, exact turnover constraint를 구현·비교했습니다.
- deterministic gate를 통과한 후보도 closest baseline 대비 paired 95% Sharpe gate 또는 untouched validation에서 탈락했습니다.
- production covariance는 Ledoit-Wolf를 유지합니다.
- 판정: `완료(후보 미승격)`.

### Portfolio Forecast Model Redesign

- forecast saturation/tie/coverage 진단, completed-OOS uncertainty, absolute/relative/factor-residual target, pooled pairwise/listwise/nested objective를 구현했습니다.
- ARIMA+Transformer, Transformer, Kronos-small을 동일 4-case signal-only 조건으로 비교했습니다.
- Kronos-small은 absolute gate를 통과했지만 closest forecast baseline 대비 paired uplift가 95%에 미달해 production integration을 기각했습니다.
- 판정: `완료(후보 미승격)`.

### Portfolio Optimizer Quant Standard

- no-lookahead price/FX/PIT universe, explicit no-view, eligibility diagnostics, actual controlled-weight performance, cost/turnover/cash accounting, bootstrap/Holm gate를 구현했습니다.
- production 기본은 `MIN_VARIANCE` + `RISK_ONLY` + Ledoit-Wolf covariance이며 BL/MPT/forecast는 opt-in입니다.
- full stock-alpha 승격은 근거 부족으로 주장하지 않으며 후속 가설은 별도 TODO로 분리했습니다.
- 판정: `완료(제한-data quant standard)`.

## 변경 범위

- 완료된 legacy TODO 3개 삭제
- TODO index 3개 항목 제거
- successor TODO의 삭제 대상 참조를 이 종료 보고서로 교체
- runtime 코드 변경 없음

## 검증

- `PYTHONPATH=src/backend .venv/bin/python -m pytest -q tests/test_portfolio_risk_models.py tests/test_research_risk_allocators.py tests/test_research_minvar_promotion.py tests/test_forecast_model_comparison.py tests/test_kronos_benchmark.py tests/test_import_crsp_monthly_research_data.py tests/test_high_priority_fixes.py`: `102 passed`
- 기존 alpha/PIT focused suite: `147 passed`
- 최종 전체 suite와 문서 consistency는 모든 TODO 종료 단계에서 다시 검증합니다.

## 리스크/이슈

- Licensed CRSP/CCM 원본이 없어 promotion-safe 개별주 alpha 일반화는 입증하지 않았습니다.
- 소진된 DOW/Nasdaq/French 결과를 같은 family 재튜닝에 재사용하지 않습니다.
- 후속 candidate가 gate를 통과하기 전 production Ledoit-Wolf GMV를 변경하지 않습니다.

## 다음 작업

- validation contract를 먼저 잠근 뒤 conditional-risk와 residual forecast를 독립 검증합니다.
- forecast candidate가 통과한 경우에만 confidence gate와 GMV overlay를 검증합니다.

## 참고

- `docs/reports/260724-1121-01-allocator-feature-gate-audit.md`
- `docs/reports/260724-1645-01-minimum-variance-production-default.md`
- `docs/reports/260730-1638-01-kronos-signal-benchmark.md`
