# TODO - Stock Screener custom CSV 지원

- 등록 일시: 2026-07-01 16:53 KST
- 작성자: austinjung
- 에이전트: Codex
- 진행 시점: Stock Screener universe 기능 확장 시

> 완료된 TODO는 이 파일을 삭제하고, `docs/reports/`에 작업 기록을 남깁니다.

## 목표

- Stock Screener가 predefined CSV뿐 아니라 사용자가 지정한 custom CSV 파일을 universe로 사용할 수 있게 개선합니다.

## 요구사항

- CSV schema를 정의합니다. 최소 ticker column 이름과 optional display name column을 명시해야 합니다.
- 파일 경로 입력 또는 업로드 방식 중 제품 UX를 결정합니다.
- 경로 traversal, 대용량 파일, 중복 ticker, 빈 ticker, 잘못된 ticker 문자를 방어합니다.
- backend screening 함수와 frontend UI가 같은 validation/error message를 공유하도록 합니다.

## 작업 요약

- `src/backend/ticker_lists.py`와 `src/backend/stock_screener.py`의 universe loading 흐름을 확장합니다.
- `src/frontend/StockScreener.jsx`에서 custom CSV 입력 UI를 추가합니다.
- custom CSV 파싱과 filtering 테스트를 추가합니다.

## 선행조건

- custom CSV를 브라우저 업로드로 처리할지, 서버 로컬 경로로 처리할지 결정이 필요합니다.

## 참고

- 관련 문서: `docs/01-folder-architecture.md`, `docs/02-specs.md`, `docs/03-product-plan.md`
- 기존 루트 TODO: `fix stock screener to accept custom .csv files`
- todo-list 한 줄 요약: `custom-csv-stock-screener.md` | 시점: Stock Screener universe 기능 확장 시 | 목표: 사용자가 제공한 custom CSV 파일을 screening universe로 사용할 수 있게 개선
