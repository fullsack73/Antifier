# TODO - Portfolio Alpha v2 Research

- 등록 일시: 2026-07-23 18:24 (KST)
- 작성자: Codex
- 에이전트: Codex
- 진행 시점: point-in-time factor/fundamental 데이터와 validation과 분리된 research universe를 확보한 뒤
- 현재 상태: frozen value-quality-momentum이 validation paired/4-case gate에서 탈락

> 완료된 TODO는 이 파일을 삭제하고, `docs/reports/`에 작업 기록을 남깁니다.

## 배경

- `adaptive_signal_tilt` v1은 signal/construction/execution 분리 진단과 relative-return IC calibration을 구현했지만 live validation에서 0/4로 탈락했습니다.
- construction은 약 19.5~20% active share와 signal-weight rank correlation 1.0을 유지했고 execution도 평균 신호의 약 84~105%를 보존했습니다.
- 실패 원인은 4개 validation case 중 3개에서 평균 cross-sectional rank IC와 top-minus-bottom spread가 음수였던 signal layer입니다.
- rolling positive-IC weighting이 적은 관측에서 reversal 같은 단일 component에 집중되는 구조적 불안정성도 관찰됐습니다.
- 이 결과는 validation 후보 기각에만 사용하며 같은 4개 case에 맞춘 feature/weight 재튜닝에는 사용하지 않습니다.
- 2024-2025 locked holdout은 실행하지 않아 잠금 상태를 유지했습니다.

## 목표

- validation과 겹치지 않는 research/train universe와 기간을 먼저 확정합니다.
- 단순 cross-sectional median 제거를 넘어 market beta, sector, size 등 공통요인을 제거한 forward residual return을 target으로 사용합니다.
- point-in-time quality/profitability, valuation, liquidity feature를 survivorship/look-ahead 없이 결합합니다.
- component weight는 research split에서 regularization, weight cap, minimum observation gate를 적용해 단일 신호 집중을 방지합니다.
- pairwise/listwise ranking objective와 단순 regularized linear baseline을 복잡도 순으로 비교합니다.

## 검증 순서

1. research/train 내부 walk-forward에서 feature와 calibration 방식을 선택합니다.
2. 고정된 4-case validation은 선택된 단일 후보에만 실행합니다.
3. validation 통과 후보만 standard sensitivity gauntlet으로 보냅니다.
4. 모든 gate를 통과한 단일 후보에만 `--gauntlet-preset holdout`을 최종 1회 실행합니다.

## 산출물

- point-in-time dataset provenance와 survivorship 정책
- factor-residual target과 no-lookahead 회귀 테스트
- regularized component/ranking model 비교 보고서
- 새 cache namespace와 candidate validation 기록
- 통과 시에만 standard 및 locked-holdout 결과

## 2026-07-23 진행

- `factor_neutral_alpha_tilt` research-only 후보와 PIT long-table 계약을 구현했습니다.
- `available_date` 기준 snapshot, beta/sector/log-size residual target, ridge regularization, feature weight cap, minimum observation gate를 구현했습니다.
- CLI에 `--factor-data`, `--factor-provenance`와 `factor-neutral-alpha-v2-*` namespace를 추가했습니다.
- synthetic no-lookahead/미래 fundamental 격리 회귀 테스트를 추가했습니다.
- 실제 PIT dataset과 validation 비중복 research universe가 없어 pairwise/listwise 비교와 candidate validation은 실행하지 않았습니다.
- locked holdout은 계속 잠금 상태입니다.
- validation과 겹치지 않는 2005-2013 sector ETF research split에서 price-only pooled objective 4개를 비교했지만 모두 signal-only gate에서 탈락했습니다.
- PIT quality/value/liquidity 또는 macro/regime feature 없이 price-only alpha를 복잡한 Transformer로 확대하지 않습니다.
- 사용자가 제공한 로컬 SEC companyfacts archive에서 2009-2025 filing-date PIT row 449개, 29 ticker를 생성했습니다. 외부 SEC bulk 다운로드는 사용하지 않았습니다.
- `factor_residual_ridge`가 quality/profitability/valuation/liquidity와 missing indicator를 실제 predictor로 사용하도록 연결했고 미래 filing 변경 불변 테스트를 추가했습니다.
- 2008-2025 static-DOW 진단에서 price relative ridge는 mean rank IC `0.0539`, positive IC `57.63%`, top-minus-bottom `0.0165`였지만 4개 동시 objective의 Holm-adjusted p-value가 `0.1340`이어서 승격하지 않았습니다.
- 동일 factor-residual target의 price-only baseline은 rank IC `0.0015`, PIT 재무 결합 모델은 `-0.0046`으로 둘 다 탈락했습니다.
- feature별 진단에서 profitability와 quality의 raw rank IC는 각각 `0.0478`, `0.0254`였지만 16-feature Holm 보정 후 유의한 feature는 없었습니다. 이를 근거로 시험한 compact quality ridge도 rank IC `-0.0476`으로 탈락했습니다.
- 로컬 companyfacts에는 SIC/submissions metadata가 없어 sector가 전부 `Unknown`입니다. 현재 residual target은 beta/size만 제거하므로 sector-neutral 성능을 주장하지 않습니다.
- 현재 DOW 정적 ticker 표본은 survivorship-safe하지 않아 모든 결과의 `promotion_eligible`은 false입니다.
- pinned historical DJIA full-composition snapshot 14개를 70개 membership event로 재구성했고 각 source date에서 30종목을 검증했습니다.
- corporate ticker alias `KFT→MDLZ`, `UTX→RTX`, `DWDP→DD`를 적용한 49-column price panel과 SHA provenance를 생성했습니다.
- historical membership 연구에서 relative ridge mean rank IC는 `0.0289`, positive IC rate `58.73%`, top-minus-bottom `0.0076`이었습니다.
- block bootstrap의 positive IC/spread 확률은 `84.80%`, `77.80%`로 95% gate를 통과하지 못했습니다. static-current-DOW의 `0.0539` IC는 생존편향의 영향을 받은 것으로 판단합니다.
- active-universe coverage 분모에서 가격 없는 ticker가 제외되던 결함을 수정했습니다. 최종 aggregate coverage는 `98.57%`, period minimum은 `93.33%`, 남은 누락은 `WBA`입니다.
- historical ticker-to-CIK interval과 local companyfacts를 결합해 2009-2025 PIT feature `712`행, `47/49` ticker를 생성했습니다. `DIS`는 2019년 전후 registrant CIK를 분리했습니다.
- historical-DOW factor-residual 비교에서 price-only IC `0.0252` 대비 full PIT joint IC `0.0581`로 개선됐고 spread도 `0.0044`에서 `0.0114`로 증가했습니다.
- full PIT joint의 positive IC/spread 확률은 `98.00%`/`94.55%`였습니다. spread 95%와 Holm-adjusted p-value `0.1635` 때문에 승격하지 않습니다.
- broad sector는 manually audited static proxy이고 canonical dated SEC SIC가 아닙니다. security-master provenance를 `promotion_safe=false`로 기록하고 최종 research 판정에 전파했습니다.
- historical-DOW research split의 날짜, namespace, objective family, 학습 설정, universe/price/factor hash를 immutable manifest로 잠갔습니다.
- universe→price→factor lineage 교차검증을 추가해 개별 hash가 맞아도 서로 다른 dataset 계보를 섞는 실행을 거부합니다.
- 승격 판정은 data-safe, split-locked, signal-gate 세 축으로 분리했습니다. 이번 실행은 각각 false/true/false이므로 `promotion_eligible=false`입니다.
- inner completed time fold만 사용하는 nested ridge penalty 선택을 추가했습니다. `[1,5,20,100]` grid와 3개 inner validation period를 v2 split digest `8e10ff…1ae5`로 사전 잠갔습니다.
- nested ridge는 IC `0.0627`, spread `0.0153`, positive bootstrap `98.70%`/`97.45%`로 개별 signal gate를 통과했습니다.
- 네 objective Holm-adjusted p-value는 `0.1020`, fixed ridge 대비 paired improvement 확률은 IC `81.70%`, spread `93.50%`여서 후보 freeze는 보류합니다.
- official French market total return으로 beta를 추정한 v3 nested target은 IC `0.0618`, spread `0.0149`로 내부 equal-weight beta의 `0.0627`/`0.0153`보다 낮았습니다.
- external-market 후보의 기존 nested 대비 paired improvement는 IC `38.80%`, spread `6.85%`, 5-objective adjusted p-value는 `0.1275`여서 폐기합니다.
- pinned Nasdaq-100 change history를 2016-2025 PIT membership event로 역재구성하고 179 ticker 가격, 174 issuer security master, SEC SIC sector를 source-lock했습니다.
- 20-F/40-F와 IFRS facts, weighted-average shares fallback을 지원해 Nasdaq PIT feature를 1,244행/152 ticker로 확장했습니다.
- 2022-2025 locked holdout에서 nested IC `0.0260`, spread `-0.0022`, fixed 대비 paired improvement `60.55%`/`61.35%`로 signal gate를 통과하지 못했습니다.
- Nasdaq holdout은 소진됐으며 같은 결과를 사용한 feature/penalty 재탐색을 금지합니다.
- PIT factor-residual의 centered percentile rank를 직접 학습하는 nested objective도 raw nested보다 IC와 spread가 낮아 폐기했습니다.
- rank-target minus raw paired P(higher)는 IC `18.75%`, spread `1.75%`였습니다. 같은 DOW 기간에서 tail-weight 변형을 연속 탐색하지 않습니다.
- quarterly TTM PIT는 filing age를 약 306~309일에서 58~62일로 줄였지만 Nasdaq 2020~2021 research에서 annual predictor보다 IC `-0.0081`, spread `-0.0112` 열위였습니다.
- realized target을 동일하게 고정한 비교에서도 annual과 quarterly 후보 모두 signal gate를 통과하지 못했습니다. 같은 Nasdaq 기간에서 분기 feature 변형을 연속 탐색하지 않습니다.
- country ETF 15종 2010~2016 fresh research에서 fixed shallow histogram gradient boosting은 relative ridge보다 IC `-0.0303` 열위였고 paired P(higher IC/spread)는 `25.65%`/`57.35%`였습니다.
- candidate-specific paired gate를 승격 판정에 강제했습니다. nonlinear 후보가 탈락했으므로 2017+ validation/holdout을 실행하지 않습니다.
- Nasdaq-100 2018~2019의 새 locked research split에서 300일 이상 이전 공시 대비 quality/profitability/valuation/liquidity 변화를 추가했습니다.
- fundamental-momentum 후보는 baseline 대비 IC `0.0681→0.0461`, spread `0.02095→0.00546`으로 하락했고 paired P(higher IC/spread)는 `12.35%`/`1.20%`여서 폐기했습니다.
- 동일 구간에서 lag, missing flag, penalty를 재튜닝하지 않으며 2020+ 데이터는 이 후보 평가에 사용하지 않았습니다.
- 공식 French 49-industry 2011~2017 fresh research에서 6개월/12-1개월 순위를 50/50으로 고정한 dual-horizon momentum을 6개월 momentum과 비교했습니다.
- dual-horizon은 회전율을 `17.79%→10.44%`로 낮췄지만 Sharpe `0.8259→0.7987`, 변동성 `15.38%→15.64%`, drawdown `-24.16%→-25.37%`로 악화되어 폐기했습니다.
- paired P(lower volatility/higher Sharpe)는 `5.60%`/`22.00%`였습니다. 같은 기간에서 horizon weight를 재튜닝하지 않습니다.
- official French 25 size×book-to-market 1935~1970 research에서 MKT/SMB/HML residual momentum을 raw 12-1 momentum과 직접 비교했습니다.
- residual candidate는 IC `0.0119<0.0613`, spread `-0.00080<0.00704`였고 paired P(higher IC/spread)는 `5.40%`/`5.65%`로 폐기했습니다.
- 같은 결과에서 factor set, beta window, residual window를 재튜닝하지 않습니다.
- official French 25 size×operating-profitability 1965~1999 research에서 12-1 momentum과 annual OP quintile을 50/50으로 고정 결합했습니다.
- 후보 자체는 IC `0.0951`, spread `0.01221`로 개별 95% gate를 통과했지만 raw momentum의 IC `0.1177`, spread `0.01257`보다 낮았습니다.
- paired P(higher IC/spread)는 `22.40%`/`45.05%`여서 폐기합니다. 같은 split에서 blend weight, momentum window, skip, horizon을 재튜닝하지 않습니다.
- official French 25 operating-profitability×investment 1965~1999 research에서 momentum 50%, OP 25%, conservative investment 25%를 결과 확인 전에 고정했습니다.
- quality-momentum은 raw momentum 대비 IC `0.0668→0.1085`, spread `0.00697→0.01303`으로 개선했습니다.
- paired P(higher IC/spread)는 `97.95%`/`98.55%`, Holm-adjusted p-value는 `0.0205`로 candidate, paired, familywise gate를 모두 통과했습니다.
- 후보를 freeze합니다. validation 전 momentum/OP/investment weight, lookback, skip, horizon을 변경하지 않습니다.
- 다음 단계는 untouched 2000~2011의 full universe와 low/high OP, low/high investment 4-case validation입니다.
- frozen candidate를 untouched 2000~2011에 변경 없이 적용했습니다. low/high OP와 low/high investment 4개 case는 모두 deterministic gate를 통과했습니다.
- 전체 IC는 `0.0089→0.0697`, spread는 `0.00155→0.01644`로 개선됐고 paired P(higher IC/spread)는 `98.50%`/`99.90%`, Holm p-value는 `0.0150`이었습니다.
- 그러나 candidate absolute P(IC>0)가 `91.60%`로 사전 95% gate에 미달했습니다. P(spread>0)는 `97.55%`였습니다.
- validation을 탈락 처리하고 같은 2000~2011 결과로 weight/window를 재튜닝하지 않습니다. 2012+ holdout은 봉인합니다.
- official French 25 book-to-market×operating-profitability 1965~1999 research에서 momentum 50%, value 25%, profitability 25%를 결과 확인 전에 고정했습니다.
- value-quality-momentum은 raw momentum 대비 IC `0.0780→0.1238`, spread `0.01408→0.02047`로 개선했습니다.
- paired P(higher IC/spread)는 `98.20%`/`95.75%`, Holm-adjusted p-value는 `0.0425`로 모든 research gate를 통과했습니다.
- 후보를 freeze합니다. validation 전 momentum/value/profitability weight, lookback, skip, horizon을 변경하지 않습니다.
- frozen candidate를 untouched 2000~2011에 변경 없이 적용했습니다. 전체 IC `0.0614→0.1072`, spread `0.01557→0.02801`로 개선됐고 absolute P(IC>0/spread>0)는 `98.35%`/`99.80%`였습니다.
- paired P(higher IC/spread)는 `93.85%`/`94.20%`, Holm-adjusted p-value는 `0.0615`로 95% gate에 미달했습니다.
- high-value와 high-profitability case는 통과했지만 low-value와 low-profitability candidate IC가 음수여서 4-case는 `2/4`였습니다.
- validation을 탈락 처리하고 같은 결과로 weight/window/case를 재튜닝하지 않습니다. 2012+ holdout은 봉인합니다.
- official French 25 book-to-market×investment의 fresh 1968~1999 split에서 completed 63일 IC만 사용하는 online factor-weight calibration을 추가했습니다.
- prior `momentum/value/conservative-investment=50/25/25`, prior shrinkage 75%, component cap 60%, 최대 12 completed observations를 결과 전에 고정했습니다.
- adaptive 후보 자체 IC `0.0698`, spread `0.01177`은 absolute gate를 통과했지만 raw momentum 대비 ΔIC `0.00705`, Δspread `0.00346`에 그쳤습니다.
- paired P(higher IC/spread)는 `64.00%`/`87.40%`, Holm-adjusted p-value는 `0.3600`이라 폐기합니다. 같은 split에서 shrinkage, cap, prior, history를 재튜닝하지 않습니다.

## 참고

- v1 완료 보고서: `docs/reports/260723-1824-01-portfolio-alpha-redesign.md`
- v1 validation 결과: `logs/portfolio_gauntlet_candidate_adaptive_20260723.json`
- v2 기반 보고서: `docs/reports/260723-1921-01-portfolio-alpha-v2-foundation.md`
- pooled price-only 결과: `docs/reports/260723-2032-01-pooled-cross-sectional-research.md`
- 독립 holdout 결과: `docs/reports/260724-0000-01-nasdaq100-frozen-holdout.md`
- Rank-target 폐기: `docs/reports/260724-0009-01-rank-target-research.md`
- Quarterly TTM 폐기: `docs/reports/260724-0024-01-quarterly-ttm-research.md`
- Country ETF nonlinear 폐기: `docs/reports/260724-0049-01-country-etf-nonlinear-research.md`
- Fundamental momentum 폐기: `docs/reports/260724-0111-01-fundamental-momentum-research.md`
- Dual-horizon momentum 폐기: `docs/reports/260724-0129-01-dual-horizon-momentum-research.md`
- Factor-residual momentum 폐기: `docs/reports/260724-0210-01-factor-residual-momentum-research.md`
- Profitability-momentum 폐기: `docs/reports/260724-0226-01-profitability-momentum-research.md`
- Quality-momentum freeze: `docs/reports/260724-0232-01-quality-momentum-research.md`
- Quality-momentum validation: `docs/reports/260724-0238-01-quality-momentum-validation.md`
- Value-quality-momentum freeze: `docs/reports/260724-0245-01-value-quality-momentum-research.md`
- Value-quality-momentum validation: `docs/reports/260724-0250-01-value-quality-momentum-validation.md`
- Adaptive value-investment-momentum 폐기: `docs/reports/260724-0301-01-adaptive-value-investment-momentum-research.md`
