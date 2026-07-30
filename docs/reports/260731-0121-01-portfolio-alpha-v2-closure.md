# 작업 기록 - Portfolio Alpha v2 연구 종료

- 일시: 2026-07-31 01:21 (KST)
- 작성자: Codex
- 에이전트: Codex
- 작업 유형: 연구 종료/문서

## 요약

- `portfolio-alpha-v2-research.md`의 목표와 현재 구현·테스트·실험 결과를 대조했습니다.
- PIT 데이터 계약, factor-residual target, regularized/pairwise/listwise 비교, immutable split, staged validation 산출물이 모두 존재합니다.
- 여러 signal 후보가 research gate를 통과했지만 validation 또는 독립 locked holdout에서 일반화 gate를 통과한 후보는 없었습니다.
- 실패한 후보를 같은 결과에 맞춰 재튜닝하지 않고 alpha v2 연구를 `완료(미승격)`로 종료합니다.
- production 기본값은 Ledoit-Wolf global minimum variance를 유지합니다.

## 완료 근거

| TODO 목표 | 구현·산출물 | 판정 |
|---|---|---|
| Survivorship-safe PIT data/provenance | `sec_point_in_time.py`, `universe_manifest.py`, historical DOW/Nasdaq manifest와 SEC provenance | 완료 |
| Factor-residual target/no-lookahead | `portfolio_alpha_v2.py`, PIT snapshot·future filing·future membership 회귀 테스트 | 완료 |
| Regularized/ranking model 비교 | pooled absolute/relative/factor-residual ridge, pairwise/listwise, nested ridge 및 nonlinear 비교 보고서 | 완료 |
| Candidate freeze와 staged gate | quality/value/issuance/reversal 계열 research·validation, Nasdaq frozen nested locked holdout | 완료 |
| 승격 판정 | independent holdout 또는 component gate 통과 후보 없음 | 미승격으로 종료 |

## 최종 증거

- Historical DOW nested factor ridge는 개별 signal gate를 통과했지만 familywise Holm과 fixed-ridge 대비 paired uplift gate에서 탈락했습니다.
- Frozen nested ridge는 Nasdaq-100 2022-2025 locked holdout에서 top-minus-bottom spread가 음수였고 paired uplift도 95%에 미달했습니다.
- Raw momentum은 장기 표본에서 signal gate를 통과했지만 fixed risk/momentum과 minimum-variance/momentum construction 모두 strongest component 대비 Sharpe gate에서 탈락했습니다.
- 검증되지 않은 expected-return alpha를 production에 연결하지 않았습니다.

## 변경 범위

- 완료된 `docs/todo/portfolio-alpha-v2-research.md` 삭제
- `docs/todo/00-todo-list.md`에서 항목 제거
- `docs/03-product-plan.md` 로드맵을 GMV 중심 후속 연구로 갱신
- forecast redesign TODO의 삭제 대상 참조를 후속 TODO로 교체
- backend/frontend 동작 변경 없음

## 검증

- `PYTHONPATH=src/backend .venv/bin/python -m pytest -q tests/test_cross_sectional_forecast.py tests/test_portfolio_backtest.py tests/test_research_split.py tests/test_universe_manifest.py tests/test_sec_point_in_time.py tests/test_research_raw_momentum.py tests/test_research_risk_momentum_blend.py tests/test_research_minvar_momentum_blend.py`: `147 passed`
- 문서 링크, TODO index, 삭제 파일 참조, `git diff --check`를 별도 확인합니다.

## 리스크/이슈

- Licensed delisted-inclusive individual-stock PIT price/identity 자료가 없어 production-safe stock alpha를 입증하지 못했습니다.
- Nasdaq locked holdout은 이미 소진됐으므로 같은 결과를 사용한 feature/penalty 재탐색에 사용할 수 없습니다.

## 다음 작업

- 후속 split, stop rule, residual/conditional-risk 검증 결과는
  `docs/reports/260731-0157-01-gmv-forecast-research-closure.md`에 기록했습니다.
- signal-only candidate가 통과한 경우에만 confidence gate와 GMV alpha overlay를 진행합니다.

## 참고

- `docs/reports/260723-1921-01-portfolio-alpha-v2-foundation.md`
- `docs/reports/260723-2240-01-historical-dow-alpha-audit.md`
- `docs/reports/260724-0000-01-nasdaq100-frozen-holdout.md`
- `docs/reports/260724-0549-01-raw-momentum-research.md`
- `docs/reports/260724-0556-01-risk-momentum-blend-research.md`
- `docs/reports/260724-0605-01-minvar-momentum-blend-research.md`
- `docs/reports/260724-1645-01-minimum-variance-production-default.md`
