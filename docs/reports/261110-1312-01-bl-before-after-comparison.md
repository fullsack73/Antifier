# Black–Litterman 기존/개선 예측 비교 결과

- 검토: 2026-11-10 13:12 KST
- 사용자 요청: 개선 예측의 BL 성과 개선 여부 확인
- 도구: `tools/compare_forecast_bl_before_after.py`
- 출력: `logs/forecast_bl_before_after_20261110/`, 본 실행 exit 0

## 계약과 provenance

- 기존 MPT 전후 비교에서 저장된 기존·개선 Transformer 예측을 재사용했다.
  새 학습/다운로드/seed 탐색/모델 선택/Production 변경은 없다.
- 두 부모 manifest 자체 SHA와 52개 checkpoint의 계약·입력 파일·동일 학습
  가격 SHA를 검증했다. 새 manifest는 사용한 부모 산출물의 파일 hash를 고정한다.
  현재 모델 소스가 과거와 같다고 가장하거나 기존 source guard를 완화하지 않았다.
- 기존 값은 `predict()`의 연율 제한 후 실제 API 출력과 저장된 uncertainty다.
  개선 값은 저장된 raw 63일 직접 예측과 best validation MSE를 사용한다.
- 개선 uncertainty는 동일한 504일 입력에서 purged target partition을 재생성하고,
  `sqrt(min(validation_loss))*target_scaler.scale*252/63`으로 재구성했다.
  학습/검증 행 수를 저장값과 대조했으며 floor 0.01을 적용했다.
  이는 validation 진단치이며 calibrated OOS prediction interval이 아니다.
- 같은 covariance·절대 view·confidence shrinkage·omega를 사용하는 기존
  `_black_litterman_weights`를 호출했다. Delta 2.5, tau 0.05, 동일비중 시장 prior,
  20% cap, risk-free 2%다. 기존/개선별 평균과 uncertainty만 다르다.
- 과거 시가총액이 없는 production 경로는 BL 대신 MPT로 대체된다.
  이번에는 기존 historical BL 백테스트의 동일비중 prior를 명시적으로 고정해
  실제 BL 계산을 비교했다. 최신 시가총액을 과거에 소급하지 않았다.
- 12종목/504일 학습/63일 재조정/비용 10bp/band 2%/turnover cap 35%를
  동일 적용했다. 2019-04-03~2025-10-08, origin 26개, 일수익률 1,638개다.

## 결과

| 지표 | 기존 예측 BL | 개선 예측 BL | 개선 − 기존 |
|---|---:|---:|---:|
| CAGR | 23.8309% | 24.3569% | +0.5260%p |
| 변동성 | 25.7023% | 25.6834% | -0.0188%p |
| Sharpe | 0.8835 | 0.9005 | +0.0170 |
| 최대낙폭 | -38.6863% | -38.3134% | 0.3729%p 완화 |
| 누적수익률 | 301.2248% | 312.4335% | +11.2087%p |
| 최초 10,000의 최종 자산 | 40,122.48 | 41,243.35 | +1,120.87 |

최종 자산은 약 2.7936% 증가했다. MPT 전후 CAGR +3.3436%p보다 BL의
실현 개선 폭은 작았다. 이것을 모든 기간/종목에서의 BL 개선 한계로 일반화하지 않는다.

- BL 실패/MPT solver fallback은 양쪽 모두 0/26회다.
- 거래비용: 57.26→101.62, 평균 gross turnover: 11.91%→19.91%.
- 평균 confidence: 0.2826→0.2265, confidence 조정 후 view retention:
  0.2690→0.1895다. Posterior의 raw view 대비 prior 이탈 비율은 평균
  0.00475→0.03710이다. 이는 포트폴리오 비중이나 설명력 비율이 아니며
  prior와 uncertainty가 view를 강하게 수축한다는 계산 진단이다.
- 평균 rank IC는 기존 +0.0315, 개선 -0.0178이었다. 수익률 소폭 증가를
  독립 alpha signal gate 통과나 일관된 종목 순위 예측력으로 표현하지 않는다.

## 불확실성과 검증

- Paired 21일 block bootstrap, 2,000회, seed 42.
- 개선 방향 부호 비율: 수익률 78.90%, Sharpe 80.45%, 변동성 감소 61.75%.
- 세 endpoint 모두 Holm 보정 p=0.5865로 유의하지 않다.
- 연환산 평균수익률 차이 95% 구간 [-0.5807%p, +1.5369%p],
  Sharpe 차이 [-0.02257, +0.06143]은 0을 포함한다.
  Bootstrap 반환 endpoint는 CAGR이 아니며 부호 비율은 미래 승률이 아니다.
- 관련 회귀 10 passed. Frozen 입력/부모 hash, 52개 거래의 비용·자산·turnover
  항등식과 1,638개 순 일수익률 복리를 검산했다.
- 전체 backend 검증은 `logs/forecast_bl_before_after_20261110/backend-tests.log`
  및 종료 파일을 확인한다. 아래 완료 기록 전에는 전체 통과를 주장하지 않는다.

## 해석 범위

두 예측 경로와 uncertainty가 함께 바뀐 비교이므로 direct target만의 단독
효과는 아니다. 생산 환경의 실제 historical BL 실행 성과와도 구분한다.
고정 basket·소비된 공개 자료·하나의 seed·이론적 종가 체결 기반 diagnostic이다.
Production 모델·tau·confidence mapping·기본값·원격 브랜치는 변경하지 않았다.

## 전체 회귀 검증 완료

- `backend-tests.exit=0`, `527 passed in 172.28s`.
- 비교 계산 exit 0 및 비용/순자산 검산과 함께 전체 회귀 통과를 확인했다.
- 검증 종료 확인 TODO와 인덱스 항목을 제거했다. 성과 수치와 통계적 판정은
  앞서 보고한 결과 그대로이며 추가 모델 학습/튜닝/production 반영은 하지 않았다.
