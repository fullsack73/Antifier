# 작업 기록 - 재무 지표 benchmark 기반 점수화

- 일시: 2026-07-02 18:34 (Asia/Seoul)
- 작성자: Codex
- 에이전트: Codex
- 작업 유형: 버그 수정

## 요약

- Financial Statement 대시보드가 산업/섹터 benchmark를 표시하면서도 점수는 절대 임계값으로 산출하던 문제를 수정했습니다.
- benchmark가 있는 지표는 산업/섹터 평균 대비 상대 위치로 점수와 signal을 산출하고, benchmark가 없거나 유효하지 않을 때만 기존 절대 기준으로 fallback합니다.

## 변경 범위

- valuation, profitability, growth, stability, risk 주요 지표의 benchmark 우선 점수화 helper를 추가했습니다.
- UI 카드의 `Rule` 텍스트가 benchmark 기반 점수화 시 상대 기준을 표시하도록 backend metric payload의 threshold를 갱신했습니다.
- P/B가 산업 평균과 거의 같은 경우 절대 기준으로 10점 처리되지 않는 회귀 테스트를 추가했습니다.

## 주요 변경 파일

- `src/backend/financial_statement.py`
- `tests/test_financial_statement.py`

## 검증

- `PYTHONPATH=src/backend ./.venv/bin/python -m pytest tests/test_financial_statement.py`
- `PYTHONPATH=src/backend ./.venv/bin/python -m pytest tests`
- `python3 -m py_compile src/backend/financial_statement.py`
- `git diff --check`

## 리스크/이슈

- benchmark가 있는 지표는 동종 업계 평균 대비 상대 점수로 바뀌므로 기존 절대 기준보다 전체 decision score가 낮거나 높게 움직일 수 있습니다.

## 다음 작업

- 실제 사용자 티커에서 benchmark 평균이 과도하게 왜곡되는 산업이 발견되면 peer dataset 품질을 별도 개선합니다.

## 참고

- 관련 문서: `docs/02-specs.md`, `docs/03-product-plan.md`
