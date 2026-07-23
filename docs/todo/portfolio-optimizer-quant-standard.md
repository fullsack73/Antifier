# TODO - Portfolio Optimizer Quant Standard

- 등록 일시: 2026-07-23 21:21 (KST)
- 작성자: Codex
- 에이전트: Codex
- 현재 상태: frozen nested PIT signal이 독립 Nasdaq-100 locked holdout에서 탈락

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
- official Fama/French daily market factors와 FRED DGS3MO historical risk-free panel
- historical daily risk-free 기반 Sharpe/Sortino와 paired bootstrap

## 미완료 조건

- canonical/licensed historical constituent source와 issuer identity provenance
- 새 최종 후보용 untouched validation/locked-holdout split
- factor residual/joint model familywise 및 paired-improvement gate 통과
- default candidate가 4-case validation 전부와 corrected standard gauntlet을 통과
- 최종 단일 frozen candidate의 untouched locked holdout 통과

## 다음 순서

1. Nasdaq holdout을 재튜닝에서 제외하고 새 research namespace를 선언합니다.
2. 분기 PIT, analyst-independent revisions, macro/regime 등 새 feature family를 research split에서 비교합니다.
3. positive rank IC, positive top-bottom spread, calibration, cost, 95% bootstrap와 Holm gate를 모두 통과한 모델 하나만 freeze합니다.
4. 새 validation manifest를 사용하고 실패 결과로 같은 family를 재튜닝하지 않습니다.
5. validation 통과 후 새로운 untouched locked holdout을 한 번 실행합니다.

## 2026-07-23 추가 진단

- 로컬 SEC companyfacts archive로 2009-2025 PIT feature 449개, 29 ticker를 생성했습니다.
- signal period circular block bootstrap 95% gate와 objective별 Holm-Bonferroni 보정을 구현했습니다.
- relative ridge는 개별 bootstrap을 통과했지만 4개 objective 보정 후 유의하지 않았습니다(adjusted p-value `0.1340`).
- factor-residual price baseline과 PIT fundamental joint model은 모두 signal gate에서 탈락했습니다.
- static current-DOW universe와 전부 `Unknown`인 sector 때문에 promotion/default uplift는 주장하지 않습니다.
- pinned historical DJIA snapshot, corporate ticker alias, SHA-verified price panel을 추가해 static-universe 결과를 재검증했습니다.
- relative ridge의 mean rank IC는 `0.0289`였지만 positive IC/spread bootstrap 확률이 `84.80%`/`77.80%`에 그쳐 후보가 없습니다.
- active membership 30개를 coverage 분모로 강제해 delisted/missing symbol의 조용한 제외를 차단했습니다.
- historical security master와 로컬 SEC archive를 결합해 PIT feature `712`행, `47/49` ticker를 생성했습니다.
- full PIT joint는 price-only residual ridge보다 IC가 `0.0252→0.0581`, spread가 `0.0044→0.0114`로 개선됐습니다.
- 하지만 spread positive probability `94.55%`와 Holm-adjusted p-value `0.1635`로 통계 gate를 통과하지 못했습니다.
- static broad-sector proxy의 `promotion_safe=false`가 최종 research eligibility에 반영되도록 provenance 판정을 수정했습니다.
- historical-DOW research split의 날짜, objective family, namespace, universe/price/factor SHA를 digest `a9212fed…dc8a`로 잠갔습니다.
- data provenance, locked split, statistical signal gate를 분리해 모두 통과할 때만 `promotion_eligible=true`가 되도록 강화했습니다.
- universe→price→factor lineage mismatch는 실행 전에 거부합니다.
- 완료 target만 쓰는 nested time-fold penalty 선택으로 factor IC를 `0.0581→0.0627`, spread를 `0.0114→0.0153`으로 개선했습니다.
- nested candidate는 개별 95% signal gate를 통과했지만 Holm-adjusted p-value `0.1020`, fixed baseline 대비 paired IC/spread improvement `81.70%`/`93.50%`로 승격하지 않습니다.
- risk layer에서 minimum-variance/inverse-vol blend를 completed inner variance로 선택하는 nested allocator를 추가했습니다.
- fresh global multi-asset research에서 volatility와 drawdown은 개선됐지만 Sharpe가 `0.6857→0.6561`로 하락해 폐기했습니다. lower-vol `99.75%`만으로 승격하지 않습니다.
- FRED historical risk-free로 재평가한 corrected Sharpe도 baseline `1.0605` 대비 nested `1.0376`으로 열위입니다.
- French market factor beta residual target은 authoritative data를 사용했지만 내부 beta nested 후보보다 IC/spread가 낮아 폐기했습니다.
- Nasdaq-100 historical membership 2016-2025와 SEC issuer/SIC provenance를 구성해 독립 locked holdout을 실행했습니다.
- SEC 20-F/40-F, IFRS taxonomy, weighted-average shares fallback으로 holdout PIT coverage를 최대 96.0%까지 높였습니다.
- frozen nested ridge는 Nasdaq holdout에서 IC `0.0260`, spread `-0.0022`였고 fixed 대비 paired improvement 확률도 `60.55%`/`61.35%`에 그쳐 탈락했습니다.
- 이 실패로 current alpha engine은 quant-standard 승격 조건을 충족하지 못합니다.
- 후속 rank-target nested ridge도 raw nested보다 IC `-0.0090`, spread `-0.0075` 열위여서 폐기했습니다.

## 금지

- current market cap/fundamental을 historical rebalance에 사용
- failed forecast에 임의 양의 expected return 주입
- validation/holdout 결과를 보고 hyperparameter 재탐색
- 평균 Sharpe만으로 승격
- Transformer 크기 확장을 데이터/target 개선보다 먼저 수행
- 소진된 Nasdaq holdout 또는 반복 사용한 DOW research에 맞춘 tail-weight/penalty 연속 탐색
