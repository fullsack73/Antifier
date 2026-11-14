# 검색 모드별 작업량 표시 보정

기존 미리보기는 모든 모드에서 종목 수 × 예상 재조정 횟수 × 중복 제외 모델 수를
확정 계산량처럼 표시했다. 해당 값은 50,000회 예산 검증과 구버전 API 호환을 위해
유지하되 화면에서는 전체 갱신 가정의 예산 상한으로 명시한다.

`forecast_workloads`에 전략별 검색 모드·초기 최대 예측 수·예상 전체/부분 예측 시점 수·
예측 규칙을 제공한다. 동일 모델을 공유한 초기 계산 상한도 별도로 제공한다.

- 전체 갱신: 예상 재조정 횟수 기준 전체 계산 슬롯(캐시 적용 전).
- 예측 벡터: 설정 주기 이후 첫 재조정의 전체 갱신과 나머지 부분 갱신을 구분.
- 고정 지도: 초기 전체 지도 1회, 이후 선정 종목만 현재 예측. 전체 지도 정기 갱신 없음.
- 가격 특징: 지도에는 ML 불필요, 비중 계산용 선정 종목 예측은 새로 수행.
- GMV: 어떤 검색 정책에서도 모델 예측 0회.

부분 갱신은 min(유효 후보 풀, 실제 양수 보유 + 유사 + 탐색) 이하이며 후보 중복과
큐 잔여 수로 더 작아진다. 보유 수가 확정되기 전 총횟수는 미정으로 표시한다.
초기/전체 수는 가격 가용성 확인 전 상한이며 실제 거래 달력 확보 전 시점 수는
추정이다. 같은 모델/입력/날짜의 캐시는 공유되므로 조합별 수를 합산하지 않는다.
전체 갱신 모드에서는 탐색 순환 예상 횟수를 표시하지 않는다.

예측·선정·거래 실행 정책은 변경하지 않았다. 기존 실행/500종목 작업/서버는 그대로다.

검증:

- 백엔드 focused: `tests/test_strategy_backtest.py` 47개 통과.
- 화면 focused: `tests/StrategyBacktest.test.jsx` 7개 통과.
- 프론트엔드 전체 lint·46개 테스트·빌드 통과.
- 백엔드 전체: 602개 통과(187.04초), 종료 코드 0. `logs/workload-display-validation/backend.log`, `backend.exit`.
  PID는 `backend.pid`에 기록. 완료 전에는 통과로 취급하지 않는다.


전체 백엔드 검증 실행 정보(완료 여부는 종료 파일로 확인):

```sh
nohup sh -c 'cd /Applications/react/my-app/portfolio-project && PYTHONPATH=src/backend OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 /Applications/react/my-app/portfolio-project/.venv/bin/python -m pytest tests; status=$?; echo "$status" > /Applications/react/my-app/portfolio-project/logs/workload-display-validation/backend.exit; exit "$status"' > '/Applications/react/my-app/portfolio-project/logs/workload-display-validation/backend.log' 2>&1 < /dev/null & echo $! > '/Applications/react/my-app/portfolio-project/logs/workload-display-validation/backend.pid'
```

PID: `28418`。상태 확인:

```sh
ps -p 28418 -o pid,etime,command
cat /Applications/react/my-app/portfolio-project/logs/workload-display-validation/backend.exit
```

종료 파일이 없으면 실행 중이며, 0은 통과, 그 외는 실패다. 중단 명령:

```sh
pkill -TERM -P 28418; kill -TERM 28418
```
