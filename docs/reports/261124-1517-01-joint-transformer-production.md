# 공동 종목 attention Transformer 프로덕션 적용

- 사용자 요청: 2년 비교의 Sharpe 1.533 대 GMV 0.722 결과를 수용하고 프로덕션 적용을 명시적으로 승인했다.
- 사용자 승인 적용이며 독립 holdout/통계 gate를 새로 통과했다는 해석은 하지 않는다.
- 기존 포트폴리오 Transformer의 최종 예측을 시간/종목 attention, 0.5 표준화 MSE +
  0.5 (1-Pearson 횡단면 상관), seed 42/43/44 동일가중 평균으로 변경했다.
- 기본 예측 기간 63일을 유지하고 요청 horizon의 target/purge/연율 변환을 사용한다.
  504개 공통 가격, 60일 입력, train-only scaler, 5 epoch, batch 최대 8개 날짜다.
  22종목을 넘는 큰 풀은 batch를 줄여 메모리 사용을 제한한다. 500종목의 운용 성능은 미측정이다.
- 연구 도구를 runtime에서 import하지 않는 backend 전용 모듈을 추가했다. 진행 중인
  horizon 실험의 파일과 source hash는 그대로 보존한다. 연구 builder/전처리/loss와
  수치 일치 검사를 두어 고정 연구 버전과 프로덕션 구현의 차이를 검출한다.
- 실제 Optimizer/Manager의 Transformer 최종 비중 입력과 전략 백테스트를 연결했다.
  후보 탐색 단일종목 지도는 기존 방식이며 최종 선정 풀은 항상 공동 재예측한다.
  GMV 기본값, 단일종목 차트, ARIMA+Transformer 경로는 유지한다.
- 공동 Transformer MPT에서는 실험과 같이 raw 예측을 confidence 수축 없이 입력한다.
  BL의 불확실성 처리는 유지한다. 기본 max-Sharpe 계산 실패/모든 no-view는
  동일 제약의 min-variance로 대체하고 solver objective를 응답에 표시한다.
- 모델 버전/seed/cohort/horizon/loss를 API 결과에 기록한다. 공동 캐시는 전체
  풀과 순서/공통 날짜/모든 가격/horizon/모델 버전을 포함한다. 공동 pipeline의
  실패 예측을 캐시하지 않는다. 잘못된 history 종목은 no-view로 분리한다.
- spawn 프로세스 하나에 학습을 격리하고 pipe로 진행률/결과를 전달한다. 취소 또는
  오류에는 worker를 종료하며 실패를 캐시하지 않는다. 기존 전략 job checkpoint의
  실행 버전도 분리해 예전 단일종목 결과와 새 공동 결과의 혼합 재개를 거부한다.
- 변경 경로만 검증하며 전체 테스트는 사용자 지시에 따라 실행하지 않는다.
- 검증 출력: `logs/cross-stock-production-20261124-ppujuok8/`. 상태: 관련 회귀 검사 및 실제 API 학습 검증 완료.

## 검증 완료

- 변경 경로 관련 테스트 총 127개 통과. 최초 묶음의 124개 통과 후, 공동 예측과
  후보 지도 호출을 분리한 테스트 수정 및 no-view/checkpoint 검사 추가를 포함해
  변경한 두 파일 63개를 재실행해 모두 통과했다. 전체 테스트는 실행하지 않았다.
- 실제 Flask `/api/optimize-portfolio` 작업을 통해 저장된 22종목 가격에서
  spawn worker의 3개 seed/5 epoch 학습과 MPT 비중 계산을 끝냈다. 외부 가격/
  메타데이터 조회만 fixture로 대체했으며 ML·프로세스·API job·최적화는 실제 경로다.
- 실제 API 검증 28.58초, 연구 결과 대비 연 단순 예측 최대 차이 0.0,
  최종 비중 합 1.0/최대 비중 0.2, 실패 종목 없음, 풀 캐시 재적중을 확인했다.
- 모델/전처리/loss 일치, 전체 풀·다른 종목 가격·날짜·순서·horizon·버전 캐시 분리,
  잘못된 입력, 취소 worker 종료/실패 미캐시, 후보 점수 대신 최종 풀 재예측,
  confidence 추가 수축 없는 MPT, 자산/그룹 hard constraint 유지,
  all-no-view의 constrained GMV 대체, 구버전 checkpoint 거부를 확인했다.
- 진행 중이던 96 fit 예측 기간 비교도 종료 코드 0으로 완료됐다.
  ensemble 순 Sharpe 21/42/63/126일 = 1.355892/1.462161/1.533296/1.041143.
  기본 63일을 유지한다. 해당 결과와 검증은 `261124-1433-01-transformer-horizon-comparison.md`에 기록했다.
- 현재 작업 환경에서 별도로 실행 중인 운영 백엔드 프로세스는 확인되지 않았다.
  운영 서버 배포/설치 파일 재빌드는 수행하지 않았다. 수정된 백엔드를 시작하거나
  기존 배포의 코드를 업데이트하고 재시작해야 새 모델이 로딩된다.
- 증거: 같은 출력 폴더의 `verification.json`, `api-result.json`, `verify.py`, `run.log`,
  `run.exit`(0). 서비스 경로에 적용했으며 실계좌 운용/미래 성과를 검증했다는 뜻은 아니다.
