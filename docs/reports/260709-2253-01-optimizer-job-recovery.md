# 작업 기록 - Optimizer Job 복구/취소

- 일시: 2026-07-09 22:53 (KST)
- 작성자: Codex
- 에이전트: Codex
- 작업 유형: 기능 추가/버그 수정/문서

## 요약

- 포트폴리오 최적화가 오래 걸릴 때 화면 이동, 새로고침, SSE 재연결 실패로 계산 결과를 잃거나 불필요하게 계속 계산하는 문제를 줄였습니다.
- `request_id` 기반 최적화 job 상태 조회, SSE 재연결, 명시 취소, orphan timeout 취소 흐름을 추가했습니다.

## 변경 범위

- Backend: 최적화 job registry, 다중 SSE subscriber, status/cancel API, 협력적 cancellation checkpoint 추가
- Frontend: Optimizer localStorage job 복구, App-level heartbeat, 취소 버튼, 진행률 재연결 처리 추가
- Docs/Tests: API/제품 문서 갱신, backend/frontend 회귀 테스트 추가

## 주요 변경 파일

- `src/backend/app.py`
- `src/backend/portfolio_optimization.py`
- `src/frontend/Optimizer.jsx`
- `src/frontend/App.jsx`
- `tests/test_high_priority_fixes.py`
- `tests/Optimizer.test.jsx`

## 검증

- `npm run lint`
- `npm test`
- `npm test -- Optimizer.test.jsx`
- `npm run build`
- `PYTHONPATH=src/backend .venv/bin/python -m pytest tests/test_high_priority_fixes.py -q`
- `PYTHONPATH=src/backend .venv/bin/python -m pytest tests -q`

## 리스크/이슈

- 외부 데이터 호출이나 ML worker 내부 실행은 즉시 강제 중단되지 않고 다음 cancellation checkpoint에서 중단됩니다.
- 서버 재시작 중 실행 중이던 job 복구는 지원하지 않으며, 저장된 완료 결과만 복구할 수 있습니다.

## 다음 작업

- 실제 장시간 최적화 입력으로 취소 체크포인트가 사용자 기대 시간 안에 반응하는지 수동 확인합니다.

## 참고

- 관련 문서: `docs/02-specs.md`, `docs/03-product-plan.md`
