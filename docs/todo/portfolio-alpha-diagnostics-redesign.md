# TODO - Portfolio Alpha Diagnostics and Redesign

- 등록 일시: 2026-07-23 17:11 (KST)
- 작성자: Codex
- 에이전트: Codex
- 진행 시점: 다음 portfolio forecast candidate 개발 전

> 완료된 TODO는 이 파일을 삭제하고, `docs/reports/`에 작업 기록을 남깁니다.

## 목표

- forecast 신호 자체의 예측력, 신호를 target weight로 변환하는 portfolio construction, 거래 제약 적용 후 성과를 분리 측정합니다.
- 진단 결과를 근거로 cross-sectional alpha model과 portfolio construction을 재설계합니다.
- 단순 gauntlet 하이퍼파라미터 튜닝과 동일 기간 반복 최적화로 인한 과적합을 방지합니다.

## 1단계 - Signal / Portfolio Construction 분리 진단

- 각 rebalance 시점의 raw forecast, cross-sectional rank, uncertainty, target weight, controlled weight와 실제 forward return을 함께 보관합니다.
- 모델 신호 계층에서 아래 항목을 basket/regime별로 측정합니다.
  - Spearman rank IC, mean/median IC, positive IC rate
  - top-minus-bottom spread와 방향 적중률
  - horizon별 IC decay와 signal persistence
  - ticker coverage, no-view/failed forecast 비율
- portfolio construction 계층에서 아래 항목을 측정합니다.
  - forecast rank와 pre-control target weight의 rank correlation
  - equal weight 대비 L1 distance와 active share
  - BL prior → adjusted view → posterior return → target weight 단계별 신호 축소율
  - concentration, volatility, sector/factor exposure
- execution 계층에서 아래 항목을 분리합니다.
  - gross 성과와 transaction cost 차감 net 성과
  - raw turnover와 controlled turnover
  - rebalance band/max turnover로 인한 신호 손실
- 모든 측정은 해당 rebalance 시점 이전 데이터만 사용하고 forward return은 평가에만 사용해 look-ahead를 금지합니다.

## 2단계 - Alpha Model 재설계

- 절대 미래 가격/수익률 예측을 그대로 순위화하는 현재 경로를 우선 재검토합니다.
- 다음 rebalance horizon의 cross-sectional relative return 또는 benchmark/factor residual return을 직접 target으로 사용하는 후보를 설계합니다.
- regression loss뿐 아니라 pairwise/listwise ranking objective를 비교합니다.
- 단일 Transformer 의존 대신 서로 다른 정보원의 약한 신호를 조합하는 후보를 검토합니다.
  - 6/12개월 momentum과 short-term reversal
  - volatility, downside risk, drawdown
  - quality/profitability와 valuation
  - liquidity와 market regime
  - Transformer/ARIMA rank
- 결합 방식은 단순 평균, rolling IC weighting, regularized linear model, LightGBM 등부터 복잡도 순으로 검증합니다.
- forecast uncertainty는 실제 out-of-sample calibration 결과로 산정하고 임의로 신호 강도만 높이지 않습니다.
- alpha가 유효한데 portfolio 단계에서 소멸하는 경우 BL view/omega, covariance, objective와 constraint를 별도 개선합니다.

## 검증 및 승격 기준

- research/train, validation gauntlet, locked holdout을 분리합니다.
- feature, target, hyperparameter 선택은 research/train 내부 walk-forward 구간에서만 수행합니다.
- validation gauntlet은 후보 선택에 사용하고 locked holdout은 최종 1회 평가에만 사용합니다.
- cache schema와 `--forecast-cache-namespace`를 모델/target 버전별로 분리합니다.
- 최소 승격 조건:
  - 여러 basket/regime에서 일관된 positive rank IC
  - equal weight와 강한 baseline 대비 비용 차감 Sharpe 개선
  - max drawdown과 turnover가 허용 범위 이내
  - 특정 단일 기간이나 ticker에 성과가 집중되지 않음
- candidate 4-case gate를 통과한 모델만 standard 180-case로 보냅니다.

## 산출물

- signal/weight/realized-return 진단 JSON과 Markdown summary
- rank IC, top-bottom spread, active share, signal shrinkage 회귀 테스트
- 새 alpha candidate 구현과 no-lookahead 테스트
- validation/locked holdout 분리 실행 기록
- default forecast method 변경 여부에 대한 별도 수동 판단

## 선행조건

- staged gauntlet의 persistent forecast cache와 case checkpoint/resume 흐름을 유지합니다.
- live primary candidate 실패 결과를 초기 진단 기준으로 사용하되 같은 4개 case에 맞춘 과적합은 금지합니다.

## 참고

- 관련 TODO: `portfolio-gauntlet-live-run.md`
- 관련 보고서: `docs/reports/260723-1703-01-live-candidate-gauntlet.md`
- todo-list 한 줄 요약: separate alpha-signal quality from portfolio construction, then redesign and validate the cross-sectional alpha model.
