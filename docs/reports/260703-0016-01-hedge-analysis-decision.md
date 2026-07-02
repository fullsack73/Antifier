# 작업 기록 - Hedge Analysis 존속 판단

- 일시: 2026-07-03 00:16 (Asia/Seoul)
- 작성자: 사용자 요청
- 에이전트: Codex
- 작업 유형: 문서/제품 판단

## 요약

- Hedge Analysis는 삭제하지 않고 유지하는 것으로 판단했습니다.
- 현재 기능의 문제는 제품 가치 부재가 아니라 단순 음의 상관관계를 hedge 여부로 단정하는 표현과 방어 로직/테스트 부족입니다.
- 기존 검토 TODO를 닫고, 구체적인 리팩터링 TODO로 교체했습니다.

## 변경 범위

- `docs/todo/hedge-analysis-remove-or-redesign.md` 삭제
- `docs/todo/hedge-analysis-refactor.md` 추가
- `docs/todo/00-todo-list.md`의 TODO 항목 갱신

## 주요 변경 파일

- `docs/todo/hedge-analysis-refactor.md`
- `docs/todo/00-todo-list.md`
- `docs/reports/260703-0016-01-hedge-analysis-decision.md`

## 검증

- 필수 문서와 기존 TODO를 확인했습니다.
- `src/frontend/Hedge.jsx`, `src/frontend/Selector.jsx`, `src/backend/app.py`, `src/backend/hedge_analysis.py`, locale 파일의 hedge 사용 흐름을 확인했습니다.
- 문서만 변경했으므로 코드 테스트는 실행하지 않았습니다.

## 리스크/이슈

- 현재 `/api/analyze-hedge`는 `correlation < -0.5`를 `is_hedge`로 반환하므로, 리팩터링 전까지는 UI가 hedge 성립 여부처럼 읽힐 수 있습니다.
- 새 응답 shape를 도입할 때 기존 endpoint 호환성을 유지할지 결정해야 합니다.

## 다음 작업

- `docs/todo/hedge-analysis-refactor.md`에 따라 기능명을 pairs/correlation/regression 분석으로 조정하고, 백엔드 방어 로직과 테스트를 보강합니다.

## 참고

- 관련 문서:
  - `docs/01-folder-architecture.md`
  - `docs/02-specs.md`
  - `docs/03-product-plan.md`
  - `docs/todo/00-todo-list.md`
