# Transformer·ARIMA 예측 실패 원인 분리 실험 구현

- 일시: 2026-11-09 15:43 KST
- 유형: research-only diagnostic 구현 및 실행 준비
- production forecast/API/GMV 기본값 변경 없음

## 구현

- `src/backend/forecast_failure_diagnostics.py`: 기존 모델 추적, 출력 제한 전후,
  순서 정보/직접 예측 통제, purged train-only scaling, 고정 ridge와 혼합 오차 분해.
- `tools/diagnose_forecast_failures.py`: 로컬 입력만 사용하는 immutable manifest,
  합성 대조군, 날짜별 작업, 단계 예산, 별도 worker, checkpoint 재시작과 보고서.
- `tests/test_forecast_failure_diagnostics.py`: 단위/날짜/미래 입력/대체 경로/
  혼합 항등식/통계 군집/예산·재시작·보고서 회귀 검증.

## 실험 계약

- 주 대상 63일, 12개 고정 종목, 2019~2025년 63거래일 간격 origin.
- 무거운 통제는 6개 종목, 사전 균등 선택 12 origin, seed 42/43/44.
- 합성 data seed 101/102/103. 위치 정보를 포함한 교정 모델의 AR(1)/순서
  양성 대조군 평균 MSE가 historical mean의 90% 미만이어야 시장 실험을 연다.
  네 합성 과정의 세 seed가 모두 완료되고 외부 정보의 ridge 회복도 확인해야 한다.
- 기존 Transformer의 합성 오차도 별도로 기록한다. 교정 모델의 gate 통과를
  기존 모델이 정상이라는 증거로 취급하지 않는다.
- 학습 예산은 A/B/C/D 각각 45/45/210/120분, 전체 8시간 중 1시간은 집계용.
  단계 제한/중단은 `budget_not_run`, gate 미통과는 `blocked_synthetic_gate`로 기록한다.
- 2,000회 날짜 block bootstrap, seed 42, block 2 origin. 같은 날짜의 종목과
  학습 seed는 함께 재표집한다. 미실행 가설도 Holm family에서 제거하지 않는다.
- 기존 Nasdaq consumed split을 acknowledged diagnostic으로 검사하며, 모든
  결과는 `diagnostic_only`, `promotion_eligible=false`다.

## 사전 검증

- Focused 회귀: 33 passed (신규 진단 17개와 기존 비교/split 테스트 포함).
- 실제 TensorFlow recursive/position+direct 각 1 epoch, 실제 ARIMA,
  12종목 PIT 정보 비교 36개 예측을 짧게 실행해 exit 0 확인.
- 추론 입력 순서 반전 차이: 기존 구조 약 1.49e-8, 위치 정보 추가 약 0.0172.
  이는 구조적 순서 손실의 증거이며 실제 수익률 오차 기여도 증거는 아니다.
- AR(1), data seed 101의 짧은 합성 실행도 exit 0. Historical mean 대비 MSE
  비율은 ARIMA 0.1506, 이론적 예측 0.1482, 기존 Transformer 0.8837,
  교정 Transformer seed 42/43/44 각각 0.1580/0.1589/0.1603이었다.
  단일 합성 과정의 smoke 결과이며 전체 gate 통과나 시장 성능 증거가 아니다.
- 백엔드 전체 검증과 8시간 본 실험의 완료 여부는 아래 실행 로그와 종료 파일을
  확인해야 하며 이 문서만으로 통과/완료를 주장하지 않는다.

## 실행 및 결과

- 출력: `logs/forecast_failure_20261109/`
- 실행 전 고정: `manifest.json`
- 상태/세부 증거: `run_state.json`, `checkpoints/*.json`, `worker.log`
- 결과: `result.json`, `report.md`
- 전체 백엔드 검증: `backend-tests.log`, `backend-tests.exit`
- 본 실행: `run.log`, `run.pid`, `run.exit`
- `prepare`는 기존 manifest 덮어쓰기를 거부한다. `run`은 입력/소스/의존성
  drift를 거부하고 lock을 잡아 중복 실행을 막는다. `report`는 checkpoint에서 재생한다.

## 한계

- 과거 소비된 공개 조정 가격이며 PIT security identity/상장폐지 coverage는 불완전하다.
- 합성 대조군 실패/예산 미완료는 시장에 예측 정보가 없다는 의미가 아니다.
- Teacher forcing은 실제 미래 입력을 사용하는 진단이며 배포 가능한 성과가 아니다.
- 구조·학습·입력 변경의 상호작용과 부족한 독립 시장 표본 때문에 단일 원인을
  확정하지 못할 수 있다. 모델 승격이나 포트폴리오 성과 실험은 수행하지 않는다.

## 실행 중단 및 복구 — 2026-11-09

- 전체 backend 검증: `499 passed in 180.66s`, `backend-tests.exit=0`.
- 첫 본 실행은 A 1개와 B 6개, 총 7개 작업을 저장한 뒤 중단됐다.
  완료된 AR(1) seed group의 gate가 NumPy boolean이어서 Markdown 보고서의
  `json.dumps`가 직렬화하지 못했다. `run.exit=1`이며 실험 완료가 아니다.
- Gate 판정을 Python builtin `bool`로 반환하도록 한 줄 수정했다. Gate 전체의
  JSON 직렬화 회귀를 추가했고 focused 비교/split 포함 `33 passed`를 확인했다.
- 원 manifest/checkpoint/로그와 원 runner 소스 snapshot은 그대로 보존한다.
  새 출력은 `logs/forecast_failure_20261109_resume_01/`이며 복구 manifest에
  부모 manifest SHA, 수정 이유, 기존 checkpoint SHA와 상속 관계를 남긴다.
- 이전 runner 대비 boolean cast 한 줄만 달라졌고 모델/입력/seed/task/threshold는
  같음을 검증한 뒤 완료된 7개 작업을 상속한다. 데이터/모델 재학습은 하지 않는다.
- `started_at`과 단계별 사용 시간을 보존해 원래 8시간 예산을 늘리지 않는다.
  복구 실행 역시 종료 파일과 결과를 확인하기 전에는 완료로 취급하지 않는다.

## 최종 검토

복구 실행은 exit 0으로 종료했다. 성공 548개, C 단계 예산 미실행 7개,
대기 0개다. 실제 원인별 판정과 보고서의 혼합 회계 수정은
[최종 결과 기록](261109-2024-01-forecast-failure-attribution-results.md)에 남겼다.
원래 결과 검토 TODO는 완료 처리했고, 미실행 비교와 미해결 질문만
`docs/todo/forecast-failure-missing-controls.md`에 보존했다.
