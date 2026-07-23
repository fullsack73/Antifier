# TODO - Portfolio Optimizer Quant Standard

- 등록 일시: 2026-07-23 21:21 (KST)
- 작성자: Codex
- 에이전트: Codex
- 현재 상태: online reversal Hedge가 dual-baseline paired/Holm research gate에서 탈락

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
- 최소 거래일, liveness, FX, sanitization, forecast, alignment 단계별 ticker eligibility 진단

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
- quarterly TTM PIT로 filing freshness는 약 5배 개선됐지만 Nasdaq 2020~2021 research에서 annual predictor보다 IC `-0.0081`, spread `-0.0112` 낮아 폐기했습니다.
- 7개 OOS period로 통계 power도 부족합니다. 같은 기간의 TTM/penalty 재튜닝 대신 새 universe와 feature family가 필요합니다.
- scenario worst-case covariance 후보는 2008~2016 global multi-asset research에서 Ledoit-Wolf보다 volatility와 Sharpe가 모두 나빠 폐기했습니다.
- backtest가 최초 배치까지 turnover cap으로 막던 결함을 수정하고, 부분 위험노출과 point-in-time 현금 이자 적립을 구현했습니다.
- fresh 2017~2025 global multi-asset research에서 volatility-target minimum variance는 volatility, drawdown, CVaR을 개선했지만 Sharpe `0.5083→0.4449`, P(higher Sharpe) `19.80%`로 탈락했습니다.
- risk engine truth는 개선됐지만 default candidate 승격, validation, untouched holdout 조건은 여전히 미충족입니다.
- fresh country-ETF research에서 compact nonlinear pooled model도 ridge 대비 paired IC/spread improvement gate를 통과하지 못했습니다.
- baseline 개별 gate가 candidate 승격으로 오인되지 않도록 candidate-specific paired gate를 promotion 판정에 강제했습니다.
- 최소 거래일 미달 ticker는 제외하되 성공/오류 응답에 관측 수, 커버리지, 관측일과 단계별 제외 사유를 노출해 조용한 universe 축소를 차단했습니다.
- fresh Nasdaq 2018~2019 research의 1년 fundamental-momentum 후보도 baseline 대비 paired IC/spread gate에서 탈락해 default alpha는 변경하지 않습니다.
- 공식 French 49-industry 2000~2010 research의 RMT covariance 후보도 Ledoit-Wolf 대비 volatility/Sharpe/drawdown이 모두 악화되어 default risk model을 변경하지 않습니다.
- 공식 French 49-industry 2011~2017 research의 고정 6m/12-1 dual-horizon momentum도 6m baseline보다 Sharpe, volatility, drawdown이 모두 악화되어 default alpha를 변경하지 않습니다.
- 공식 French 49-industry 1983~1999의 12개월 trend-filtered minimum variance는 평균 risk/Sharpe를 개선했지만 P(higher Sharpe) `73.45%`로 statistical gate에서 탈락했습니다.
- 공식 French 49-industry 1973~1981의 trend-filtered risk parity도 평균 Sharpe와 drawdown은 크게 개선했지만 P(higher Sharpe) `75.55%`로 statistical gate에서 탈락했습니다.
- 동일 frozen trend-risk-parity를 기간·universe가 겹치지 않는 French 30-industry 1928~1971에서 독립 복제했습니다.
- 복제에서는 Sharpe `0.4909→0.7237`, volatility `15.24%→9.74%`, drawdown `-82.70%→-37.77%`, P(higher Sharpe) `98.60%`, Holm p `0.0140`으로 모든 research gate를 통과했습니다.
- 후보 사양을 freeze했으며 다음 단계는 untouched 2018~2021 4-case validation입니다. 통과 전 2022+ holdout은 열지 않습니다.
- frozen 후보는 2018~2021 validation 전체에서 Sharpe `0.6752→0.4969`, P(higher Sharpe) `2.05%`로 탈락했고 4개 산업 case도 `0/4`였습니다.
- validation 결과로 trend family를 재튜닝하지 않으며 2022+ locked holdout은 계속 봉인합니다.
- official French 25 size×value portfolio의 FF3 residual momentum은 raw 12-1 momentum보다 paired IC/spread가 명확히 낮아 signal-only 단계에서 폐기했습니다.
- official French 25 size×value portfolio의 maximum-diversification allocator는 risk parity보다 volatility, Sharpe, drawdown을 평균적으로 개선했습니다.
- 그러나 P(higher Sharpe) `75.55%`, Holm-adjusted p-value `0.2445`로 95% statistical gate에서 탈락했습니다. 같은 split 재튜닝과 validation을 금지합니다.
- official French 25 size×operating-profitability의 50/50 profitability-momentum은 자체 signal gate를 통과했지만 raw momentum 대비 paired IC/spread 개선 확률이 `22.40%`/`45.05%`라 탈락했습니다.
- official French 25 operating-profitability×investment의 frozen quality-momentum은 raw momentum 대비 IC `0.0668→0.1085`, spread `0.00697→0.01303`으로 개선했습니다.
- paired P(higher IC/spread) `97.95%`/`98.55%`, Holm-adjusted p-value `0.0205`로 research gate를 통과했습니다. untouched 4-case validation 전 사양 변경을 금지합니다.
- frozen quality-momentum은 untouched 2000~2011에서 4/4 case와 paired P(higher IC/spread) `98.50%`/`99.90%`를 통과했습니다.
- candidate absolute P(IC>0)가 `91.60%`라 95% validation gate에서 탈락했습니다. 이 결과를 근거로 사양을 변경하지 않고 2012+ holdout을 봉인합니다.
- official French 25 B/M×OP의 value-quality-momentum은 raw momentum 대비 IC `0.0780→0.1238`, spread `0.01408→0.02047`로 개선했습니다.
- paired P(higher IC/spread) `98.20%`/`95.75%`, Holm-adjusted p-value `0.0425`로 research gate를 통과했습니다. untouched validation 전 사양 변경을 금지합니다.
- frozen value-quality-momentum은 untouched validation에서 absolute signal gate를 통과했지만 paired P(higher IC/spread) `93.85%`/`94.20%`, Holm p-value `0.0615`, 4-case `2/4`로 탈락했습니다.
- validation 결과에 맞춘 사양 변경 없이 2012+ holdout을 봉인합니다.
- completed-period IC를 prior `50/25/25`에 75% shrink하는 adaptive value-investment-momentum도 absolute gate는 통과했지만 paired P(higher IC/spread) `64.00%`/`87.40%`로 탈락했습니다.
- online weight history, cap, no-lookahead 검증은 추가됐지만 default alpha와 quant-standard 상태는 변경하지 않습니다.
- current lightweight point forecast를 유지하고 completed OOS residual RMSE로 uncertainty만 보정한 후보는 fresh French 17-industry research에서 volatility와 turnover를 낮췄습니다.
- calibrated 후보 Sharpe는 `0.5100→0.5169`였지만 P(higher Sharpe) `71.05%`, P(higher return) `39.40%`, negative top-bottom spread로 statistical/signal gate를 통과하지 못했습니다.
- validation을 열지 않고 public default를 변경하지 않습니다. uncertainty calibration hyperparameter와 Transformer capacity를 같은 결과에 맞춰 재탐색하지 않습니다.
- fresh 35-industry research에서 lightweight forecast magnitude를 제거한 fixed 20% rank tilt도 mean IC `-0.0125`, spread `-0.00034`, Sharpe `0.6533`으로 탈락했습니다.
- candidate P(higher Sharpe)는 current lightweight/equal-weight 대비 `28.40%`/`28.80%`였습니다. point ordering 자체가 약하므로 rank-view strength나 active share를 같은 split에서 재튜닝하지 않습니다.
- official French 25 size×accrual에서 fixed 50/50 accrual-quality-momentum은 absolute gate를 통과했지만 raw momentum 대비 paired spread probability `84.75%`, Holm-adjusted p-value `0.1525`로 탈락했습니다.
- local companyfacts 기반 SEC cash-accrual `(operating_cash_flow-net_income)/assets`를 opt-in PIT feature로 구현했지만 fresh Nasdaq 2017 nested candidate IC `-0.0451`, spread `-0.00742`로 baseline보다 악화됐습니다.
- usable OOS period가 6개뿐이라 bootstrap도 불가능했습니다. production optimizer/default alpha는 변경하지 않고 exact cash-accrual candidate를 폐기합니다.
- official French 12-industry 1933~1952의 market trend/volatility interaction 후보는 baseline 대비 IC `-0.01436`, spread `-0.00159` 낮았습니다.
- paired P(higher IC/spread)는 `35.75%`/`40.25%`, Holm-adjusted p-value는 `0.6070`이어서 폐기합니다. production/default alpha는 변경하지 않고 1953+ validation/holdout을 봉인합니다.
- official French 10-industry 1928~1969에서 네 기존 allocator를 completed-fold Hedge로 결합한 online ensemble은 momentum 대비 volatility와 turnover를 낮췄습니다.
- ensemble Sharpe는 `0.5434<0.5585`, P(higher Sharpe)는 `19.80%`, Holm-adjusted p-value는 `0.8020`이어서 폐기합니다. risk/default allocator는 변경하지 않고 1970+ validation/holdout을 봉인합니다.
- official French 35 size×net-share-issues의 frozen 50/50 issuance-quality-momentum은 raw momentum 대비 IC `0.1590→0.2476`, spread `0.03743→0.05858`로 개선했습니다.
- paired P(higher IC/spread) `97.60%`/`98.35%`, Holm-adjusted p-value `0.0240`으로 research gate를 통과했습니다. Production/default 변경 전 untouched 2000~2011 4-case validation이 필요하며 2012+ holdout은 봉인합니다.
- Untouched validation에서 aggregate paired P(higher IC/spread)는 `100.00%`/`98.05%`였지만 candidate absolute P(IC>0/spread>0)는 `84.55%`/`87.35%`에 그쳤습니다.
- Low-net-issuance case가 baseline보다 낮아 `3/4` case만 통과했습니다. Candidate를 폐기하고 같은 validation에 맞춘 재튜닝과 2012+ holdout 실행을 금지합니다.
- official French 25 size×FF3 residual-variance의 fixed 50/50 low-residual-variance-momentum은 absolute IC `0.2800`, spread `0.03599`로 강했습니다.
- 그러나 raw momentum 대비 paired P(higher IC/spread) `80.75%`/`77.15%`, Holm-adjusted p-value `0.2285`로 incremental uplift를 증명하지 못했습니다. Default alpha/risk model은 변경하지 않고 validation/holdout을 봉인합니다.
- official French size×prior-month-return의 fixed reversal-momentum은 locked research와 untouched validation 4/4를 통과했습니다.
- 최종 locked holdout에서 candidate IC `0.2120`, spread `0.01309`는 양수였지만 raw momentum 대비 paired P(higher IC/spread) `70.45%`/`84.75%`, Holm `0.2955`, cases `3/4`였습니다.
- Validation-result SHA chain과 locked-holdout role 검증은 강화됐지만 default alpha/optimizer는 변경하지 않습니다. Holdout 재튜닝·재실행을 금지합니다.
- Completed-feedback online Hedge는 no-tune learning rate와 completed-only expert loss를 사용했지만 fixed reversal blend보다 IC가 낮았습니다.
- Raw momentum 대비 spread는 개선됐어도 IC improvement probability `74.40%`, familywise Holm `0.5120`으로 승격하지 않습니다. Validation/holdout을 열지 않고 default optimizer를 유지합니다.

## 금지

- current market cap/fundamental을 historical rebalance에 사용
- failed forecast에 임의 양의 expected return 주입
- validation/holdout 결과를 보고 hyperparameter 재탐색
- 평균 Sharpe만으로 승격
- Transformer 크기 확장을 데이터/target 개선보다 먼저 수행
- 소진된 Nasdaq holdout 또는 반복 사용한 DOW research에 맞춘 tail-weight/penalty 연속 탐색
