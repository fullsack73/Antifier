# 전략 비교 CSV 인식 및 업로드 화면 수정

- 일시: 2026-11-12 22:12 KST
- 에이전트: Codex
- 작업 유형: 버그 수정

## 확인한 원인

새 CSV parser가 소문자 ticker 열만 허용해 기존 저장소 CSV의 Symbol 열을
거부했다. S&P 500 파일은 503종목으로 기존 500종목 제한에도 걸렸다.
실행 중인 이전 백엔드는 새 업로드 API에 404를 반환했다.

## 수정

- Symbol/Ticker 대소문자·공백·BOM, 헤더 없는 줄바꿈/쉼표 목록,
  세미콜론/탭 구분과 한국어 종목코드 헤더를 공통 parser에서 처리한다.
- 다중 열에서는 종목 열만 사용하며 이름/가격 열은 종목으로 해석하지 않는다.
- 입력 한도를 2,000종목으로 조정해 snp.csv·dow.csv·nyse.csv를 그대로 인식한다.
  CSV 1MB 및 예측 계산 50,000회 상한은 유지한다.
- `/api/strategy-backtests/universe`로 날짜·모델 조건과 독립적으로 CSV를 검증한다.
  UI에서 선택 직후 파일명·인식 종목 수·예시·중복을 표시한다.
- UTF-16 BOM과 EUC-KR 파일을 읽으며 구버전 API 404를 재시작 안내로 구분한다.
- native 파일 입력을 숨기고 선택 버튼과 파일명을 분리한다. 선택된 동일 파일도 다시 선택할 수 있다.
- 입력/선택 컨트롤의 너비를 작업 영역에 제한하고 작은 화면에서는 파일 선택 및
  비교 행을 세로 배치한다. 기존 고정 포트폴리오 벤치마크는 유지한다.

## 실행 중인 앱 반영

이전 백엔드 PID 18244를 확인 후 종료하고 수정본으로 재시작했다.
현재 PID 87207이 127.0.0.1:5000에서 실행 중이며 log/PID는 아래 경로에 있다.
새 API의 Symbol 요청 HTTP 200을 확인했고 기존 5173 Vite 화면에서 실제 snp.csv를
업로드해 503개 종목 인식 → 작업량 503/2/0 → 실행 가능 표시까지 확인했다.
대규모 백테스트 실행 버튼은 누르지 않았다.

## 검증

- Backend focused: 40 passed (1.36s).
- Frontend focused: 7 passed (1.24s), lint 통과.
- 저장소 snp/dow/nyse 파일 및 헤더/구분자 변형, 독립 CSV API,
  Excel UTF-16 decoding, 구버전 HTML 404 안내를 회귀 테스트했다.
- 실제 앱 화면의 390px 및 1280px에서 수평 overflow 대상 컨트롤 0개를 확인했다.
- 실제 Symbol 형식 S&P 500 업로드 및 preview를 확인했다.
- `git diff --check` 통과.
- 최종 전체 검증: 실행 중. 로그·checks·종료 상태 파일에 실제 결과를 기록한다.

## 산출물과 한계

- `logs/strategy-csv-ui-fix-20261112/backend.log`, `backend.pid`
- `logs/strategy-csv-ui-fix-20261112/verification.log`, `verification.status`, `verification-checks.json`
- `logs/strategy-csv-ui-fix-20261112/browser-artifacts/`
- 실제 503/1,924종목의 학습·최적화 부하는 실행하지 않았다. 인식 성공을 계산 성능이나 투자 성과 검증으로 표현하지 않는다.
- 커밋·푸시는 하지 않았다.
