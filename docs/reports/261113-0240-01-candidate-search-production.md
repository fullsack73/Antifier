# 보유·유사·랜덤 후보 갱신 프로덕션 반영

## 변경

공통 SQLite 후보 선정과 세 검색 모드, 252거래일 갱신, 보유 무제한/유사 10/탐색 10 기본값을 Optimizer·Manager·전략 백테스트에 연결했다. GMV는 가격 특징과 RISK_ONLY, FIXED_TARGET은 기존 계산을 유지한다.

백테스트는 기존 회계 실행 단계를 공유하면서 실제 실행 후 보유량을 다음 선정에 전달한다. 예측 캐시 공유와 전략별 큐 분리, 취소/실패 미확정, 동시 갱신 충돌 검출, 원자적 작업 checkpoint 및 재생 기반 resume를 추가했다.

## 검증

- 후보 선정·전략 비교·관리·최적화 제약·회계 회귀 테스트 234개를 통과했다. 전체 회귀 검증은 별도 로그에서 확인한다.
- 프론트엔드 lint·전체 테스트 45개·빌드를 통과했다. 백엔드 전체 596개도 통과했다(103.92초). 전체 검증은 약 121초에 완료했고 종료 상태는 0이다. 전체 갱신의 기존 기대수익률 보존/메타데이터 검사는 마지막 수정 후 별도 focused 테스트로 확인한다.
- 500종목/보유 20종목 fixture의 일반 갱신 40개 호출, 양수 보유 500개 유지, no-view 제외, 252일 갱신/고정 지도, 미래 자료 독립, 취소/CAS 원자성, 동일 구간 재개 시 추가 예측 없음 등을 검사한다.

## 소규모 동일 자료 정책 비교

합성 가격 530행·50종목, seed42, 학습126일/재조정63일, 기존 LIGHTWEIGHT+MPT. 실제 시장/대규모 ML 성과 검증이 아니다. 아래 시간은 순서대로 공유 예측 캐시를 사용했으므로 cold-cache 학습 속도 비교가 아니다.

| 정책 | 시간(초) | 신규 예측/캐시 | 시점별 선정 수 | 순수익률 | 최대 낙폭 | 실행 회전율 합 |
|---|---:|---:|---|---:|---:|---:|
| full | 0.350 | 350/0 | 50, 50, 50, 50, 50, 50, 50 | 15.44% | -4.49% | 3.0969 |
| forecast_profile | 0.164 | 0/345 | 50, 47, 48, 50, 50, 50, 50 | 15.30% | -4.52% | 3.0969 |
| price_features | 0.231 | 0/346 | 50, 47, 49, 50, 50, 50, 50 | 15.38% | -4.49% | 3.0969 |
| frozen_forecast | 0.162 | 0/345 | 50, 47, 48, 50, 50, 50, 50 | 15.30% | -4.52% | 3.0969 |

보유 종목이 많아 부분 선정도 47~50개가 된 fixture다. 상한 없는 보유 정책에서 절감이 보장되지 않는다는 사례이며 수익률 우위 주장은 하지 않는다.

원시 비교: `logs/candidate-policy-validation/fixture-comparison.json`.

## 검증 로그와 운용 주의

- 전체 검증: `logs/candidate-policy-validation/verification.log`, `verification-status.json`.
- 대규모 실제 ML과 실행 중인 500종목 작업은 실행·변경·중단하지 않았다. 별도 5000번 서버를 시작하지 않았다.
- 현재 실행 프로세스에는 코드가 자동 적용되지 않는다. 기존 작업이 끝난 뒤 백엔드 재시작과 새 프론트엔드 반영이 필요하다.
- SQLite 상태와 작업 checkpoint 경로를 결과 파일과 함께 보존한다. 학습 가중치 저장/공동 모델/현금 정책 변경은 범위 밖이다.
- 사전 작업량은 네트워크 없는 추정이며 실제 유효 풀·보유·제약·지도 갱신에 따라 늘 수 있다. 실제 결과에 선정 수/호출 수/캐시/실패/지도 나이를 제공한다.
- 공통 엔진의 최초 거래비용 daily export TODO는 유지한다. 전략 백테스트 어댑터의 기존 비용 검산을 보존했으며 해당 회계 문제를 별도로 소급 수정하지 않는다.

## 전체 검증 실행 정보

검증 PID: `40339`(완료). 전체 검증 상태 `passed`, 종료 코드 0. 기존 500종목 작업/서버와 별개로 실행했고 종료했다.

실행한 명령:

```sh
nohup sh -c 'cd /Applications/react/my-app/portfolio-project && exec /Applications/react/my-app/portfolio-project/.venv/bin/python /Applications/react/my-app/portfolio-project/logs/candidate-policy-validation/verify.py' > '/Applications/react/my-app/portfolio-project/logs/candidate-policy-validation/verification.log' 2>&1 < /dev/null & echo $! > '/Applications/react/my-app/portfolio-project/logs/candidate-policy-validation/verification.pid'
```

상태 확인:

```sh
cat /Applications/react/my-app/portfolio-project/logs/candidate-policy-validation/verification-status.json
```

실행 중에만 사용하는 중단 명령(현재 작업은 완료):

```sh
pkill -TERM -P 40339; kill -TERM 40339
```

전체 갱신의 기존 기대수익률 보존 및 신규 정책 메타데이터 focused 검사 2개도 마지막 코드 수정 후 통과했다(`logs/candidate-policy-validation/final_full_mode.log`).
