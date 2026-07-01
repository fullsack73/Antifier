# TODO - 포트폴리오 최적화 short-history ticker 처리

- 등록 일시: 2026-07-01 16:53 KST
- 작성자: austinjung
- 에이전트: Codex
- 진행 시점: 포트폴리오 최적화 데이터 검증 개선 시

> 완료된 TODO는 이 파일을 삭제하고, `docs/reports/`에 작업 기록을 남깁니다.

## 목표

- 포트폴리오 최적화 입력에서 거래일 수가 252일 미만인 ticker를 어떻게 처리할지 정책을 확정하고 구현합니다.

## 요구사항

- 데이터 길이가 부족한 ticker를 drop할지, 경고와 함께 제외할지, fallback 계산을 허용할지 결정합니다.
- 제외된 ticker가 있으면 API 응답과 UI에서 사용자가 이유를 이해할 수 있어야 합니다.
- 최적화 계산이 빈 universe 또는 과도하게 축소된 universe로 진행되지 않도록 방어합니다.

## 작업 요약

- `src/backend/portfolio_optimization.py`의 data fetch 및 optimization pipeline에서 최소 history 기준을 확인합니다.
- 관련 endpoint 응답 shape와 UI 표시 필요 여부를 검토합니다.
- 회귀 테스트를 추가합니다.

## 선행조건

- 최소 기준을 252 trading days로 유지할지 제품/모델 관점에서 확정합니다.

## 참고

- 관련 문서: `docs/02-specs.md`, `docs/03-product-plan.md`
- 기존 루트 TODO: `drop tickers with n<252 when optimize`
- todo-list 한 줄 요약: `drop-short-history-tickers.md` | 시점: 포트폴리오 최적화 데이터 검증 개선 시 | 목표: 최적화 입력에서 거래일 수 252일 미만 ticker 처리 정책 확정
