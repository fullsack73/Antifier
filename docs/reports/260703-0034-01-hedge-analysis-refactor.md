# 작업 기록 - Hedge Analysis 리팩터링

- 일시: 2026-07-03 00:34 (KST)
- 작성자: 사용자 요청
- 에이전트: Codex
- 작업 유형: 리팩터/문서/테스트

## 요약

- Hedge Analysis를 삭제하지 않고 Pairs / Correlation Analysis 성격으로 개편했습니다.
- 단순 `correlation < -0.5` 기반 `is_hedge` Yes/No 판정을 제거하고, 상관계수, p-value, 회귀 alpha/beta/R-squared, 관측치 수, 비단정적 correlation signal을 반환하도록 변경했습니다.
- 입력/기간/데이터 부족/yfinance 실패 경로를 명시적 예외와 HTTP status로 정리했습니다.

## 변경 범위

- Backend: `src/backend/hedge_analysis.py`, `src/backend/app.py`
- Frontend: `src/frontend/Hedge.jsx`, `src/frontend/App.css`, locale 파일
- Tests: `tests/test_hedge_analysis.py`, `tests/Hedge.test.jsx`
- Docs: `docs/01-folder-architecture.md`, `docs/02-specs.md`, `docs/03-product-plan.md`, `docs/todo/00-todo-list.md`

## 주요 변경 파일

- `src/backend/hedge_analysis.py`
- `src/backend/app.py`
- `src/frontend/Hedge.jsx`
- `src/frontend/locales/en/translation.json`
- `src/frontend/locales/ko/translation.json`
- `tests/test_hedge_analysis.py`
- `tests/Hedge.test.jsx`
- `docs/02-specs.md`
- `docs/03-product-plan.md`

## 검증

- `PYTHONPATH=src/backend .venv/bin/python -m pytest tests/test_hedge_analysis.py`
- `npx vitest run tests/Hedge.test.jsx`
- `npm run lint`
- `npm test`
- `PYTHONPATH=src/backend .venv/bin/python -m pytest tests`
- `npm run build`

`npm run build`는 성공했으며, 기존 Plotly 번들 크기 경고가 표시되었습니다.

## 리스크/이슈

- `/api/analyze-hedge` 경로는 유지하지만 응답에서 `is_hedge` 단정 필드가 사라졌습니다.
- 기존 외부 사용자가 legacy 응답 shape에 의존한다면 마이그레이션 안내가 필요합니다.

## 다음 작업

- `/api/analyze-hedge` legacy 응답 shape에 의존하는 외부 사용자가 있으면 새 pairs 분석 응답으로 마이그레이션합니다.

## 참고

- 관련 문서:
  - `docs/todo/hedge-analysis-refactor.md` 완료 후 삭제
  - `docs/02-specs.md`
  - `docs/03-product-plan.md`
