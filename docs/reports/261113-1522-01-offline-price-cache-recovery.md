# 오프라인 가격 실패 캐시와 재개 UI 보정

## 확인된 원인

네트워크 복귀 후 전략 백테스트가 즉시 `No price history available`로 끝났다.
`.cache/stock_data_d6680712733fff92d9a2a6b91b8eccb6.cache`는 빈 DataFrame이며
2026-11-13 14:29:43에 저장됐다. 최근 513종목 백테스트 요청 5개의 종목/기간/
raw-price 키가 모두 이 항목과 일치했다. get_stock_data의 데코레이터가 빈 결과도
L1 15분/L2 4시간 캐시해 새 네트워크 요청 없이 실패를 반복할 수 있었다.

## 변경

- 공통 `cached`에 선택적 `cache_if`를 추가해 조회와 저장 모두 검사한다.
- 가격 조회는 비어 있지 않은 DataFrame만 재사용/저장한다. 기존 빈 항목도 우회한다.
- 전처리 pipeline은 정상 dict 결과만 캐시하고 `error` 결과를 우회한다.
- 다른 캐시 사용처의 기본 동작, 정상 가격 캐시 키/TTL은 유지한다.
- 화면은 서버 `error`도 재개 가능한 실패로 처리한다. 재개 후 진행/완료 응답에서
  이전 오류 알림을 지운다. 온라인 복귀 시 대규모 작업을 자동 재실행하지 않는다.

## 검증

- 가격 연결/전략 백테스트 focused 62개 통과.
- 화면 focused 8개 통과. 프론트엔드 lint/전체 47개 테스트/빌드 통과.
- 백엔드 전체 604개 통과(103.13초), 종료 코드 0.
  `logs/offline-cache-recovery/backend.log`, `backend.exit`에서 확인했다.

## 적용 범위

서버 재시작, 실행 중인 500종목 작업 조작, 전체 캐시 삭제, 실제 Yahoo 호출은 하지
않았다. 기존 프로세스가 새 캐시 정책을 사용하려면 백엔드 코드 재시작 후 실패한
작업을 재개해야 한다. 재시작만으로 기존 잘못된 디스크 캐시가 사라지는 것은 아니며,
이번 검증 조건이 그 항목을 우회한다.


## 백그라운드 검증 정보

검증 PID `52144`(완료, 종료 코드 0). 실행:

```sh
nohup sh -c 'cd /Applications/react/my-app/portfolio-project && PYTHONPATH=src/backend OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 /Applications/react/my-app/portfolio-project/.venv/bin/python -m pytest tests; status=$?; echo "$status" > /Applications/react/my-app/portfolio-project/logs/offline-cache-recovery/backend.exit; exit "$status"' > '/Applications/react/my-app/portfolio-project/logs/offline-cache-recovery/backend.log' 2>&1 < /dev/null & echo $! > '/Applications/react/my-app/portfolio-project/logs/offline-cache-recovery/backend.pid'
```

상태 확인:

```sh
ps -p 52144 -o pid,etime,command
cat /Applications/react/my-app/portfolio-project/logs/offline-cache-recovery/backend.exit
```

중단(해당 검증이 실행 중일 때만):

```sh
pkill -TERM -P 52144; kill -TERM 52144
```
