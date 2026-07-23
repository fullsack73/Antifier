# TODO - Portfolio Optimizer Quant Standard

- 등록 일시: 2026-07-23 21:21 (KST)
- 작성자: Codex
- 에이전트: Codex
- 현재 상태: 실제 로컬 PIT dataset과 signal bootstrap 완료, promotion-safe universe와 유의한 frozen candidate 미확보

> 완료된 TODO는 이 파일을 삭제하고, `docs/reports/`에 작업 기록을 남깁니다.

## 완료 기반

- price/FX leading history backward-fill 제거
- historical BL current-market-cap 차단
- static market cap as-of 강제와 PIT market-cap frame 지원
- forecast failure explicit no-view/prior-only
- post-control weight 기준 performance reporting
- regularized max-Sharpe convex target grid
- OOS risk forecast calibration과 downside/tail metrics
- paired block bootstrap 95% gate와 Holm multiple-testing correction
- current-cap 모델 제외 corrected 180-case baseline gauntlet
- SEC filing-date PIT fundamental loader와 정정공시 no-lookahead 테스트
- 날짜별 universe membership resolver와 promotion-safe provenance guard
- pooled research에서 signal date별 active universe 적용

## 미완료 조건

- 실제 survivorship-safe historical universe constituent snapshot 파일과 provenance
- 실제 SEC quality/value/liquidity/fundamental dataset 생성과 provenance 완료(정적 DOW 진단용, promotion-safe 아님)
- historical risk-free curve와 benchmark/factor return series
- research/validation/locked-holdout split manifest의 immutable hash
- factor residual/joint model signal-only gate 통과
- default candidate가 4-case validation 전부와 corrected standard gauntlet을 통과
- 최종 단일 frozen candidate의 untouched locked holdout 통과

## 다음 순서

1. historical constituent manifest와 declared `SEC_USER_AGENT`로 실제 PIT dataset을 생성합니다.
2. factor residual target의 compact regularized model을 fresh research split에서 평가합니다.
3. positive rank IC, top-bottom spread, calibration, cost, 95% bootstrap와 Holm gate를 모두 통과한 모델 하나만 freeze합니다.
4. 기존 validation 결과로 재튜닝하지 않고 새 validation manifest를 사용합니다.
5. validation 전부 통과 후에만 locked holdout을 한 번 실행합니다.

## 2026-07-23 추가 진단

- 로컬 SEC companyfacts archive로 2009-2025 PIT feature 449개, 29 ticker를 생성했습니다.
- signal period circular block bootstrap 95% gate와 objective별 Holm-Bonferroni 보정을 구현했습니다.
- relative ridge는 개별 bootstrap을 통과했지만 4개 objective 보정 후 유의하지 않았습니다(adjusted p-value `0.1340`).
- factor-residual price baseline과 PIT fundamental joint model은 모두 signal gate에서 탈락했습니다.
- static current-DOW universe와 전부 `Unknown`인 sector 때문에 promotion/default uplift는 주장하지 않습니다.

## 금지

- current market cap/fundamental을 historical rebalance에 사용
- failed forecast에 임의 양의 expected return 주입
- validation/holdout 결과를 보고 hyperparameter 재탐색
- 평균 Sharpe만으로 승격
- Transformer 크기 확장을 데이터/target 개선보다 먼저 수행
