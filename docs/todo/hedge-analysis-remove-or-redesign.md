# TODO - Hedge Analysis 삭제 또는 개편 검토

- 등록 일시: 2026-07-02 19:50 (Asia/Seoul)
- 작성자: 사용자 요청
- 에이전트: Codex
- 진행 시점: Hedge Analysis 관련 화면/API를 수정하거나 제품 범위를 재정리할 때

> 완료된 TODO는 이 파일을 삭제하고, `docs/reports/`에 작업 기록을 남깁니다.

## 목표

- 현재 Hedge Analysis 기능을 유지할 가치가 있는지 검토하고, 삭제하거나 제품 의도에 맞게 개편합니다.

## 요구사항

- `src/frontend/Hedge.jsx`, sidebar navigation, locale 문구, `/api/analyze-hedge`, `src/backend/hedge_analysis.py`의 실제 사용 흐름을 함께 확인합니다.
- 단순 음의 상관관계를 hedge 여부로 단정하는 현재 표현이 분석 보조 도구 범위에 맞는지 검토합니다.
- 삭제를 선택하면 프론트엔드 navigation, API surface, 문서의 Hedge Analysis 언급을 함께 정리합니다.
- 개편을 선택하면 pairs/correlation/regression 분석으로 명확히 재정의하고, 실패/빈 데이터/기간 부족에 대한 방어 로직과 테스트를 보강합니다.
- UI 문구를 변경하면 영어/한국어 locale을 함께 갱신합니다.

## 작업 요약

- Hedge Analysis의 제품 가치, 계산 정확성, UI 표현을 재평가합니다.
- 결과에 따라 기능 제거 또는 분석 화면/API 개편 작업을 진행합니다.

## 선행조건

- Hedge Analysis를 Antifier의 핵심 범위에 계속 포함할지 제품 방향을 결정해야 합니다.
- 삭제 시 기존 사용자가 접근하던 sidebar 항목과 endpoint 호환성 처리 방식을 정해야 합니다.

## 참고

- 관련 문서:
  - `docs/01-folder-architecture.md`
  - `docs/02-specs.md`
  - `docs/03-product-plan.md`
- todo-list 한 줄 요약: 현재 hedge 분석 화면/API의 제품 가치와 정확성을 재검토하고, 삭제 또는 개편 방향을 결정합니다.
