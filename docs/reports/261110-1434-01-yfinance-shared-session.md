# 최적화 이후 Yahoo 조회 연결 단절 수정

- 일시: 2026-11-10 14:34 KST
- 에이전트: Codex
- 작업 유형: 버그 수정

## 원인

`logs/bl-session-fix-20261110/backend.log:327`의 14:03:19 AAPL 회귀 요청이
`Session is closed, cannot send request`와 HTTP 500을 기록했다. 최적화 가격
수집이 닫은 curl session이 yfinance YfData singleton에 남고 다른 화면도 이를
참조한다. BL 조회 두 곳에 새 session을 전달한 이전 수정만으로는 일반 차트·회귀를
보호하지 못했다. 실제 회귀 함수에서도 SessionClosed 및 그 오류가 숨겨진
ExternalDataError 경로를 재현했다.

## 변경

- 기존 managed session helper에서 프로세스 소유 session 하나를 lock으로 지연 생성하고 재사용한다.
- 개별 조회 성공·오류·취소 시 session을 닫지 않고 atexit에서 정리한다.
- 추가 dependency, API 변경, frontend 변경 없이 기존 CA bundle·가격 조회 timeout·concurrency 제한을 보존한다.
- spawn worker는 모듈 상태가 독립적이므로 session을 부모 프로세스와 공유하지 않는다.
- 이전 BL 빈 캐시 방지 및 조회 오류 로그 수정은 유지한다.

## 검증

- focused: yfinance resilience + high-priority fixes, 43 passed (2.42s).
- 실제 yfinance singleton과 curl session을 사용하는 회귀 테스트로 optimizer 가격 수집 후
  `/api/get-data` 차트·Transformer 회귀 응답의 200과 가격·예측 데이터를 확인한다.
- 취소 이후 재사용, 가격 다운로드 예외 이후 재사용, 동시 borrower 4개의 단일 session 생성,
  종료 cleanup을 확인한다.
- 실제 Yahoo smoke: AAPL 가격 수집 → MSFT 차트·회귀 → 시가총액을 두 번 반복해 성공.
  차트/회귀 4회 모두 HTTP 200, 각 105개 가격, 공유 session은 계속 유효했다.
  ML 출력만 stub이며 가격·메타데이터 조회는 실제 Yahoo 호출이다. 모델 성능 검증은 아니다.
- 백엔드 전체 테스트: 실행 중. 종료 코드와 상세 결과는 아래 status/log에 기록한다.
- `git diff --check`: 통과.

## 산출물과 한계

- `logs/yfinance-shared-session-20261110/live-smoke.py`, `live-smoke.log`
- `logs/yfinance-shared-session-20261110/backend-tests.log`, `backend-tests.pid`, `backend-tests.status`
- 테스트와 smoke는 별도 임시 캐시를 사용하며 저장된 포트폴리오 결과를 덮어쓰지 않는다.
- 실행 중인 사용자 서버는 재시작하지 않았다. 적용하려면 해당 프로세스를 재시작해야 한다.
- 전체 496개 종목 ML 재최적화, 실제 서비스 장시간 부하 및 Yahoo rate limit 상황은 재현하지 않았다.
