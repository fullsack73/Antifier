# GMV·개선 예측 MPT·GMV+개선 예측 비교

- 요청: 사용자 지정 세 포트폴리오 historical diagnostic 비교
- 일시: 2026-11-09 20:34 KST
- 도구: `tools/compare_improved_forecast_portfolios.py`
- Production API/default/기존 예측 코드 변경 없음

## 사전 고정 계약

- 개선 모델은 원인 분리 효과가 확인된 위치 정보 없는 63일 직접 예측으로 고정.
  Seed 42, 5 epoch, 60일 입력. 낮은 MSE를 보고 위치 정보/seed를 다시 고르지 않는다.
- 사용자 선택에 따라 standalone은 예측 기반 MPT max-Sharpe다. 동일 Ledoit-Wolf
  covariance를 쓰므로 위험 모델까지 제거한다는 의미의 standalone은 아니다.
- 63일 로그수익률을 `expm1(prediction*252/63)`로 변환한 기하 연환산 수익률
  proxy를 MPT에 제공한다. 이 값은 보정된 조건부 산술 기대수익률이 아니다.
- Plain GMV, model MPT, GMV+gamma 0.025 rank overlay 세 target을 비교한다.
  Gamma는 기존 연구값을 재사용하며 이번 수익률에 맞춰 탐색하지 않는다.
- 모든 방법에 504일 학습, 63일 재조정/예측, 자산 cap 20%, 비용 10bp,
  band 2%, gross turnover cap 35%, 연 risk-free 2%를 동일 적용한다.
- AAPL/MSFT/AMZN/GOOGL/META/NVDA/ADBE/AMGN/COST/INTC/CSCO/QCOM 고정
  12종목. 원래 2019년 grid에서 학습 길이가 충분하고 63일 outcome이 완료된
  26개 origin을 사용한다. 전체 기간의 연속 일수익률을 동일 엔진으로 평가한다.
- 기존 엔진 계약에 따라 학습은 재조정일 직전 종가까지다. 과거 원인 진단의
  학습 끝과 같다고 간주해 prediction을 재사용하지 않고 전체 origin을 재생성한다.
- MPT가 해를 구하지 못하면 같은 origin의 GMV target으로 대체하고 횟수와
  이유를 모두 저장한다. 이를 성공한 순수 MPT target으로 숨기지 않는다.
- 사용자 명시 비교이므로 signal gate와 무관한 diagnostic replay로 한정한다.
  Consumed split 사용을 acknowledge하며, 후보 선택/holdout/승격 근거가 아니다.
- 2시간 실행 상한. 모든 origin이 완료되지 않으면 일부 구간만으로 성과를
  비교하지 않고 incomplete로 중단한다. 추가 예산은 자동으로 부여하지 않는다.

## 구현 및 검증

- 기존 GMV/overlay helper, target signature, 비용·현금 회계와 backtest 엔진을 재사용.
- 예측 단위 변환, MPT의 정확한 GMV 대체, 누락 신호 차단, 공통 실행 달력,
  학습 종료일의 미래정보 차단, manifest drift 회귀 테스트: 6 passed.
- 전체 backend 검증은 별도 background 단계에서 실행하고 통과한 경우에만
  본 비교를 시작한다. 완료 전에는 전체 통과나 성과 결과를 주장하지 않는다.

## 산출물과 해석

- 출력: `logs/improved_forecast_three_portfolios_20261109/`
- 사전 계약: `manifest.json`, origin별 예측/비중: `checkpoints/*.json`
- 검증: `backend-tests.log`, `backend-tests.exit`
- 본 실행: `run.log`, `run.pid`, `run.exit`, `worker.log`, `run_state.json`
- 결과: `report.md`, `result.json` (CAGR/volatility/Sharpe/drawdown/turnover/cost,
  일수익률·매매 회계·MPT 대체 횟수 포함)
- Bootstrap은 동일 일수익률에 21일 block/2,000회/seed 42. GMV 대비 두 비교의
  수익률·Sharpe·변동성 총 여섯 가설에 Holm 보정한다. 수익률 bootstrap endpoint는
  연환산 평균수익률이며 CAGR 차이 검정으로 표현하지 않는다.
- 공개 조정 가격, 고정 basket, 한 seed 및 종가 기준 이론적 체결 조건이다.
  Survivorship-safe stock alpha, 실거래 slippage, 독립 미래 성과는 미검증이다.

관련 원인 진단 미실행 7개 TODO는 이 비교와 별개로 보존한다.

## 완료 결과 — 2026-11-09

- Backend 전체: `506 passed in 159.18s`, 검증/본 실행 모두 exit 0.
- 26개 origin의 12종목 예측 완료. 2019-04-03~2025-10-08의 연속 일수익률
  1,638개를 동일한 실행 엔진에서 비교했다. 세 방법의 실행 record는 총 78개다.
- 모델 예측 기반 MPT가 수익률은 가장 높았으나 변동성·낙폭·거래비용도 가장 컸다.

| 방법 | CAGR | 변동성 | Sharpe | 최대낙폭 | 누적수익률 |
|---|---:|---:|---:|---:|---:|
| GMV | 18.9455% | 20.6278% | 0.8485 | -26.1722% | 208.8611% |
| 개선 예측 MPT | 28.7558% | 26.0111% | 1.0259 | -37.9628% | 416.9914% |
| GMV+개선 신호 | 19.3186% | 20.7616% | 0.8594 | -26.8250% | 215.2128% |

- MPT의 CAGR 차이는 GMV 대비 +9.8103%p지만 변동성 +5.3833%p,
  최대낙폭은 11.7906%p 더 깊었다. 예측 오차 개선이 안정적 알파나 위험 우위를
  입증했다는 뜻은 아니다.
- GMV+신호는 CAGR +0.3731%p, Sharpe +0.0109, 변동성 +0.1338%p였다.
- MPT는 2023-07-06에 solver infeasible로 같은 GMV target을 사용했다.
  총 26회 중 1회이며 나머지는 MPT target이었다.
- 초기 자금 10,000 기준 누적 거래비용: GMV 77.38, MPT 214.08, 혼합 72.72.
- 평균 gross 거래회전율은 GMV 18.34%, MPT 37.46%, 혼합 17.37%다.
  이 평균은 최초 100% 매수를 포함한다. 최초 배분을 제외한 모든 거래는
  35% cap 이내이며 평균이 cap보다 높다는 이유로 제약 위반은 아니다.

## 비교 불확실성

| GMV 대비 | 수익률 차이 양수 재표집 비율 | Sharpe 차이 양수 비율 | 수익률 Holm 보정 p |
|---|---:|---:|---:|
| 개선 예측 MPT | 98.45% | 84.15% | 0.0930 |
| GMV+개선 신호 | 92.45% | 81.60% | 0.3775 |

수익률 endpoint는 연환산 일평균 수익률이며 CAGR 검정이 아니다. 여섯 사전
비교의 Holm 보정 후 유의한 개선은 없다. MPT Sharpe 차이의 95% 구간은
약 [-0.1550, 0.4937], 혼합은 [-0.01235, 0.03506]으로 둘 다 0을 포함한다.
재표집 비율을 미래 승률로 표현하지 않는다.

이번 결과는 '모델이 GMV를 이기지 못한다'는 단정과 다르다. 이 표본에서는
모델 MPT가 더 높은 실현 수익률을 보였고, 그 대가로 더 큰 위험을 감수했다.
독립 미래 데이터·다른 seed/basket에서도 유지되는지는 검증하지 않았다.
Production 모델·기본값·gamma를 변경하지 않는다.

## 최종 회계 점검 및 분석 코드 기록

`run_portfolio_model_backtest`의 내보낸 일수익률이 최초 매수 비용을 포함하지
않는 점을 검산 중 발견했다. 누적수익률/CAGR/Sharpe 등 summary에는 이미
초기 비용이 포함돼 있었다. 내보낸 일수익률의 복리만 최종 순자산 대비
1.001배였으며 세 방법의 동일한 초기 비용에서 발생했다.

연구 비교 도구에 summary 순자산과 일치 여부를 확인하고 필요할 때 최초 일수익률을
비용 후/전 자산 비율로 보정하는 검사를 추가했다. 이미 일치하는 export에는
이중 차감하지 않으며 다른 차이는 오류로 중단한다. Production engine은 변경하지 않았다.
공유 export의 정리는 별도 TODO로 남겼다.

- 보정 전 `result-before-initial-cost-audit.json`, `report-before-initial-cost-audit.md`,
  runner source를 보존했다. 보정 후 `result.json`은 `analysis_source_hashes`와
  `daily_returns_include_initial_cost=true`로 계산 경로를 기록한다.
- 저장된 예측/비중만 재생했으며 모델을 다시 학습하거나 manifest를 바꾸지 않았다.
  모든 summary와 78개 거래 record가 보정 전과 동일함을 확인했다.
- 78개 거래의 비용·회전율·자산 항등식, 공통 달력과 일수익률 복리가 순자산에
  일치함을 검산했다. 보정 후 bootstrap 비율과 Holm 판정도 동일했다.
- 보정 후 관련 회귀: `7 passed`. 전체 506개는 본 실행 전 통과한 결과다.

이 비교의 결과 검토 TODO는 완료 처리했다. 추가 검증·튜닝·승격은 실행하지 않았다.
