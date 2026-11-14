# 직접 예측의 서비스 코드 반영

- 일시: 2026-11-09 23:36 KST
- 사용자 요청: 개선 모델을 production 코드에 반영
- 배포/서버 재시작/실거래/GMV 기본값 변경 없음

## 변경

- 기존 실험에서 사용한 model builder, 기간 목표 생성과 purged split을
  `src/backend/direct_horizon_forecast.py`로 옮겨 production/research가 공유한다.
  위치 정보와 구조/seed/5 epoch 기본값을 임의로 변경하지 않는다.
- 서비스의 Transformer wrapper를 새 직접 head에 연결한다. `train`은 검증된
  가격 이력을 보관하고 `predict(horizon)`에서 해당 기간 head를 학습한다.
  같은 instance의 같은 horizon은 다시 학습하지 않는다. 새 이력/cleanup은 캐시를 비운다.
- 차트 API도 고정 252일 호출 대신 요청한 미래 기간(미지정 시 63일)을 사용한다.
  이 경로에 남아 있던 연율 clipping을 제거하고 예측 horizon과 diagnostics를
  응답 metadata에 추가한다. 표시용 결측 제거 전에 원래 날짜 이력을 예측에 전달한다.
- API 연율 로그수익률과 no-view 계약을 유지한다. 직접 head의 기간값은
  `252/horizon`으로 변환한다. ARIMA+Transformer도 동일한 연율 단위로 결합한다.
- 기존 일별 반복/포화 출력을 대신해 직접 기간값을 사용한다. 검증 RMSE는
  연율 단위로 변환하되 통계적 신뢰구간으로 오인하지 않도록 diagnostic flag를 남긴다.
- 충분한 완료 목표가 없는 기간은 no-view다. 결측 가격을 제거해 날짜 간격을
  압축하지 않는다. ARIMA 부분만 유효한 경우의 hybrid 동작은 기존 계약을 따른다.
- Forecast-rank cache schema를 올려 예전 예측이 새 서비스 결과로 섞이지 않게 한다.
- 종목별 Transformer/hybrid 예측과 pipeline 캐시도 모델 버전으로 분리한다.
  캐시 키 생성 함수 자체의 캐싱을 제거해 오래된 pipeline key 반환도 방지한다.
- Legacy Transformer/HPO는 과거 연구 진단을 위해 보존한다. 이전 immutable
  연구 manifest는 source 변경을 감지하므로 수정된 코드로 소급 재실행하지 않는다.

## 검증

- Production 선택 연결, 기간/연율 변환, no-view, 기간별 재사용/재학습,
  hybrid 단위와 metadata, 결측 날짜 보존과 기존 HPO/비교/backtest 회귀: 119 passed.
- 서비스 캐시 버전 회귀와 기존 high-priority 검사를 포함한 확장 검사: 151 passed.
- 차트 요청 기간/출력/결측 이력 검사와 기존 비교/high-priority 회귀: 51 passed.
- 실제 TensorFlow 연구/서비스 예측 일치 smoke와 backend 전체 검증은
  `logs/direct_horizon_production_20261109_release/`의 로그와 종료 파일로 확인한다.
  종료 전에는 전체 통과를 주장하지 않는다.
- 최초 실제 TensorFlow smoke는 연구/서비스 기간 예측 모두
  `0.007643590681254864`로 정확히 일치했다. 이후 전체 검증은 서비스 캐시
  버전 보완을 위해 중단(exit 143)했고 최종 코드로 검증을 다시 실행한다.

## 범위와 한계

63일 fixed-basket 비교를 다른 기간/종목의 성과 보장으로 확장하지 않는다.
API 예측을 기존 MPT/BL confidence 조정에 연결하므로 연구용 MPT의 수익률을
서비스에서 그대로 재현한다고 주장하지 않는다. GMV는 기본값으로 유지한다.
배포는 하지 않으며 코드와 문서/테스트 반영까지 수행한다.
기존 미실행 통제 7개와 공통 일수익률 export TODO는 이번 변경과 별개로 보존한다.

## 최종 완료

- 최종 코드의 실제 TensorFlow parity smoke: exit 0.
  연구/서비스의 63일 기간 로그수익률 모두 `0.007643590681254864`로 일치했다.
- Backend 전체: `524 passed in 98.07s`, `backend-tests.exit=0`, `run.exit=0`.
- 서비스 wrapper/차트 요청 기간, no-view/단위/자료 분리/캐시 버전 검사 포함.
- `git diff --check` 통과. 프론트엔드는 변경하지 않아 별도 lint/build를 실행하지 않았다.
- Production 코드 반영과 검증은 완료했으며 서버 배포/재시작은 실행하지 않았다.
  검증 확인 TODO는 완료 처리했다. 기존 다른 TODO와 과거 연구 산출물은 유지한다.
