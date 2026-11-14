# 미세 가격 차이 캐시 재사용과 ML 작업 격리 / 네 전략 비교

## 확인된 문제

동일한 설정에서도 Yahoo 재다운로드 가격의 미세한 차이로 원시 바이트 해시가 달라졌다.
두 다운로드의 같은 날짜 구간에서 350종목에 차이가 있었고 최대 절댓값 차이는
약 0.000305였다. 첫 457종목의 정확 캐시 적중은 확인 시점 118개였다.
서버의 1초 실행 샘플은 작업 스레드가 Python gc_collect에 머무는 것을 보였으며,
프로세스 memory footprint는 약 35.3GB였다. 단일 스냅샷이므로 메모리 누수 원인이나
전체 실행 시간 비율을 확정하지 않는다.

## 수정

- SQLite 공유 예측 캐시에 원가격과 동일 날짜 배열의 family 키를 추가한다.
- 정확 일치를 우선하고, 동일 종목/모델/예측 기간/날짜 배열의 모든 가격이
  원가격 대비 `1e-8 + 5e-7 * abs(원가격)` 이내일 때만 호환 적중으로 재사용한다.
- 재사용 시 원가격을 바꾸지 않아 허용 오차가 연쇄 누적되지 않는다.
- 날짜·모델·기간·유의한 가격 변경은 재계산하고 실제 학습 입력은 반올림하지 않는다.
- 정확 적중·신규 계산·호환 적중을 별도 집계한다. 원가격 없는 기존 캐시는 정확
  일치 시에만 원가격을 등록한다. 검증할 수 없는 기존 항목은 한 번 재계산해야 한다.
- 백테스트 캐시 미스의 ML은 별도 spawn 프로세스 하나에서 실행하고 10개 작업마다
  교체한다. 서버 본체에 ML 모델을 누적하지 않으며 취소 시 작업 프로세스를 종료한다.
- 모델 구조, epoch, 수익률 단위, 비중 계산은 변경하지 않는다. 기존 서버/작업은 유지한다.

## 검증

- 후보 캐시·백테스트·직접 예측·가격 복구 focused 100개 통과.
- 실제 spawn 작업 프로세스와 10-task 교체를 통계 예측만으로 검사한다. 대규모 ML 검사는 아니다.
- 미세 차이 재사용, 날짜/기간/모델/가격 변경 분리, 비연쇄 허용 오차, legacy 정확 일치
  등록, batch 미학습, 전부 적중 시 프로세스 미생성, 취소 정리를 검사한다.
- 전체 백엔드 611개 통과(105.30초), 종료 코드 0. `logs/forecast-cache-compatible-fix/backend_tests.log`와 `.exit`에서 확인했다.

## 사용자 요청 비교

직전 요청의 동일 513종목 풀, 2021-11-12~2026-11-12, 학습504일·예측63일·재조정63일,
초기 지도 고정, 유사10/탐색10/seed42. 네 전략은 일반 GMV, ARIMA+Transformer MPT,
ARIMA+Transformer BL, 기존 GMV+예측 신호(GMV_MODEL)다. 일반 GMV는 RISK_ONLY와
가격 특징 검색 계약을 유지한다.

가격 다운로드 캐시를 별도 snapshot으로 고정하고 hash를 manifest에 기록했다.
신규 다운로드 없이 모든 전략이 같은 자료를 쓴다. 초기 유효성 검사를 통과한 종목은
457개이고 재조정은 실제 거래 달력에서 20회다. 같은 시점의 동일 입력 예측은 공유하지만
실제 보유와 후보는 전략별로 달라지므로 미계산 항목은 추가 학습한다. 가격과 입력 근거가
없는 예전 예측을 강제로 연결하지 않는다.

전체 검증이 통과해 독립 작업으로 비교를 시작했다. 기존 앱 서버를 재시작하거나
5000번 서버를 추가로 실행하지 않는다. 실행 산출물은 다음 경로에 기록한다.

- `logs/forecast-cache-compatible-fix/manifest.json`: 코드/자료 hash와 고정 설정.
- `logs/forecast-cache-compatible-fix/status.json`: 검증/비교 단계 상태.
- `logs/forecast-cache-compatible-fix/comparison-status.json`: 비교 진행 상태.
- `logs/forecast-cache-compatible-fix/result.json`, `summary.json`, `comparison.md`: 완료 결과.
- `logs/forecast-cache-compatible-fix/comparison.log`: 실제 예측/진행 로그.

소비된 과거 자료의 비교로, 새로운 holdout 통과나 미래 성과 회복을 의미하지 않는다.


## 실행 및 중단 정보

감독 작업 PID: `24946`. 실행 명령:

```sh
nohup sh -c 'cd /Applications/react/my-app/portfolio-project && exec /Applications/react/my-app/portfolio-project/.venv/bin/python /Applications/react/my-app/portfolio-project/logs/forecast-cache-compatible-fix/run.py' > '/Applications/react/my-app/portfolio-project/logs/forecast-cache-compatible-fix/run.log' 2>&1 < /dev/null & echo $! > '/Applications/react/my-app/portfolio-project/logs/forecast-cache-compatible-fix/run.pid'
```

상태 확인:

```sh
cat /Applications/react/my-app/portfolio-project/logs/forecast-cache-compatible-fix/status.json
```

검증 통과 후 비교의 세부 진행:

```sh
cat /Applications/react/my-app/portfolio-project/logs/forecast-cache-compatible-fix/comparison-status.json
```

감독 작업 중단(하위 검증 또는 비교 프로세스 그룹에도 종료 신호 전달):

```sh
kill -TERM 24946
```

작업 ID: `backtest_7235bf5a590a47a5a7a386be33717d6b`. 완료 결과는 기존 portfolio result
저장소에도 기록해 앱의 전략 비교 저장 결과에서 조회할 수 있게 한다. 완료 전에
성과 수치나 전체 검증 통과를 주장하지 않는다.
