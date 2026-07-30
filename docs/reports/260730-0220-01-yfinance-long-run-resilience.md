# yfinance 장시간 실행 복원력 개선

- 작업 일시: 2026-07-30 02:20 (KST)
- 범위: full portfolio gauntlet의 Yahoo 가격 수집
- 상태: 완료

## 현상

- 2026-07-28~30 사이 동일 gauntlet 프로세스에서 `DNSError`, SQLite `OperationalError: unable to open database file`, curl `SSLError(77)`가 반복됐습니다.
- yfinance는 실패 ticker도 all-NaN 열로 반환할 수 있어 기존 `Final shape: (..., 30)` 로그가 실제 가격 coverage를 과장했습니다.
- 실행 중 프로세스에는 Yahoo `CLOSE_WAIT` socket 수십 개와 pipe 백여 개가 남아 있었습니다.

## 원인

- yfinance 0.2.66 `download()`에 session을 넘기지 않으면 호출마다 새 curl session을 만들며, 장시간 프로세스에서 이전 연결 자원이 누적될 수 있습니다.
- 기존 batch는 yfinance 내부 ticker thread 최대 30개와 취소 불가능한 외부 timeout executor를 함께 사용했습니다.
- 자원 압박 시 DNS resolver thread 생성, yfinance SQLite cache open, CA file open이 같은 fetch에서 연쇄 실패했습니다.
- 기존 정리는 row 기준 all-NaN 제거만 수행해 실패 ticker의 all-NaN column을 성공 열로 남겼습니다.

## 변경

- fetch마다 명시적 curl session을 생성하고 `finally`에서 닫습니다.
- certifi CA bundle을 session에 직접 전달합니다.
- yfinance cache를 writable user cache에 고정하고 `ANTIFIER_YFINANCE_CACHE_DIR` override를 지원합니다.
- Yahoo batch와 fallback의 30/32-thread burst 및 취소 불가능한 timeout executor를 제거하고 serial download로 제한합니다.
- batch 반환에서 all-NaN ticker 열을 제거하고 누락 ticker만 최대 2회 개별 재시도합니다.
- 최종 로그에 `coverage=성공/요청`과 누락 ticker를 기록합니다.
- stock-data cache schema를 `v3`로 올려 이전 partial 결과를 재사용하지 않습니다.

## 검증

- `PYTHONPATH=src/backend .venv/bin/python -m pytest tests/test_yfinance_resilience.py tests/test_high_priority_fixes.py::test_optimization_cancel_event_stops_before_fetch -q`
  - `6 passed`
- 실제 Yahoo smoke: AAPL/MSFT 2024-01-01~10
  - shape `(6, 2)`, coverage `2/2`, all-NaN column `0`
- `py_compile` 통과

## 실행 영향

- 이미 실행 중인 PID는 import된 기존 코드를 계속 사용하므로 변경 효과는 다음 프로세스부터 적용됩니다.
- 가격 download는 직렬화되어 수 초 느려질 수 있지만, 수일 걸리는 ML gauntlet에서 연결 자원 누적과 숨은 ticker 누락을 방지하는 쪽을 우선합니다.
