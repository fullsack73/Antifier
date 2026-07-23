# TODO - Portfolio Forecast Model Redesign

- 등록 일시: 2026-07-23 19:21 (KST)
- 작성자: Codex
- 에이전트: Codex
- 진행 시점: ARIMA/Transformer 계열을 portfolio alpha feature로 다시 검토하기 전
- 현재 상태: lightweight는 약하지만 raw momentum도 replacement signal gate에서 탈락

> 완료된 TODO는 이 파일을 삭제하고, `docs/reports/`에 작업 기록을 남깁니다.

## 배경

- live candidate gauntlet에서 `arima_transformer_rank_bl`과 `transformer_rank_bl` 모두 0/4 survival로 탈락했습니다.
- ARIMA+Transformer의 basket/regime별 평균 rank IC는 약 `0.0152`, `-0.0060`, `0.1161`, `0.0212`였고 Transformer는 약 `-0.0023`, `-0.0991`, `0.1280`, `-0.1726`이었습니다.
- defensive 구간 외에는 일관된 cross-sectional 예측력이 없었으며, live run의 주된 실패는 no-view가 아니라 정상 생성된 forecast의 방향성과 상대순위 품질 부족이었습니다.
- Transformer 예측이 `±0.6900` 경계에 반복적으로 포화되어 종목 간 신호 강도 구분과 rank 안정성이 약해졌습니다.
- ticker × rebalance 단위 재학습으로 candidate 4-case에도 forecast 216개와 약 20~30분이 필요했습니다. persistent cache는 재실행 비용만 줄이며 모델 품질과 학습 안정성은 해결하지 않습니다.

## 목표

- 종목별 절대 미래수익률을 독립적으로 예측한 뒤 순위화하는 현재 목표를 재검토합니다.
- portfolio research용 모델은 다음 horizon의 cross-sectional relative return 또는 market/sector/factor residual return을 직접 예측하도록 분리합니다.
- 시장 전체 방향, sector, beta 등 공통요인과 종목 고유 alpha를 구분합니다.
- 출력 clipping과 `±0.6900` 포화의 원인을 추적하고 예측 분포와 rank tie를 진단합니다.
- forecast uncertainty를 실제 walk-forward out-of-sample 오차로 calibration합니다.
- ticker별 반복 학습을 줄일 cross-sectional joint model, batched inference, warm-start 또는 공통 representation을 비교합니다.

## 요구사항

- research/train, validation, locked holdout을 분리하고 validation 결과를 모델 재튜닝에 재사용하지 않습니다.
- absolute-return loss, relative/residual-return regression, pairwise/listwise ranking objective를 같은 split에서 비교합니다.
- 모델별로 rank IC, positive IC rate, top-minus-bottom spread, calibration error, coverage/no-view rate를 기록합니다.
- 예측 clipping 전후 분포, 경계 포화율, cross-sectional unique-rank 비율을 기록합니다.
- uncertainty는 임의 상수나 signal-strength 조절값이 아니라 실제 OOS residual 또는 conformal/quantile coverage로 검증합니다.
- training time, peak memory, forecast당 비용, cache hit/miss와 재현성을 함께 보고합니다.
- 새 target 또는 architecture마다 cache schema와 `--forecast-cache-namespace`를 분리합니다.
- portfolio construction과 분리된 signal-only gate를 먼저 통과한 모델만 `portfolio-alpha-v2-research.md`의 후보 feature로 전달합니다.

## 산출물

- forecast target/출력 포화/uncertainty 진단 JSON과 Markdown 보고서
- relative 또는 factor-residual target 구현과 no-lookahead 테스트
- OOS calibration 및 rank-quality 회귀 테스트
- ticker-independent 모델과 cross-sectional/batched 후보의 비용·성능 비교
- signal-only 승격 또는 폐기 결정 기록

## 2026-07-23 진행

- 기존 validation cache 432개를 재학습 없이 진단했습니다.
- standalone Transformer 216개 중 37개, `17.13%`가 `±0.69` annual boundary에 포화됐고 unique-value ratio는 `83.80%`, tie rate는 `16.20%`였습니다.
- hybrid 최종 평균은 boundary에 직접 포화되지 않았지만 내부 Transformer component는 동일한 `17.13%` 포화를 보였습니다.
- Transformer forecast에 raw/pre-clip/post-clip, daily clip hit, uncertainty source 진단을 추가했습니다.
- cache schema를 `2026-07-23-v2-diagnostics`로 분리했습니다.
- forecast distribution, empirical OOS uncertainty, cross-sectional rank quality, signal-only gate helper와 cache 진단 CLI를 추가했습니다.
- training cutoff 안에서 완료된 horizon만 사용하는 absolute/relative/factor-residual target builder를 추가했습니다.
- 기존 uncertainty가 in-sample training RMSE 또는 fixed fallback이라는 점을 응답에 명시했습니다.
- 기존 validation 결과는 failure diagnosis에만 사용했고 replacement model parameter tuning은 하지 않았습니다.
- 별도 research universe가 없어 absolute/relative/residual/pairwise/listwise 비교와 OOS uncertainty calibration은 실행하지 않았습니다.
- candidate validation과 locked holdout은 계속 보류합니다.
- 2005-2013 sector ETF 9종, 2,264일 research-only split에서 63일 horizon pooled objective를 비교했습니다.
- absolute/relative ridge의 mean rank IC는 `-0.0848`, pairwise는 `-0.0652`, listwise는 `-0.0232`였습니다.
- 4개 objective 모두 mean top-minus-bottom spread가 음수였고 signal-only gate에서 탈락했습니다.
- pooled 학습은 objective별 23회 fit, 207 prediction을 약 `1.20~1.40초`, peak Python memory 약 `1.88~2.10 MiB`로 처리해 ticker별 Transformer보다 계산비용은 크게 낮았습니다.
- price-only pooled linear/ranking 결과가 음수이므로 같은 feature에서 Transformer hyperparameter만 늘리는 작업은 보류합니다.
- 다음 후보는 PIT quality/value/liquidity와 macro/regime feature를 포함한 뒤 research 내부에서 compact joint model과 regularized baseline을 비교해야 합니다.
- SEC filing-date PIT fundamental loader와 날짜별 universe manifest contract를 추가했습니다. future amendment와 future constituent가 과거 signal row에 들어가지 않는 회귀 테스트를 통과했습니다.
- 실제 SEC 수집은 연락처가 포함된 `SEC_USER_AGENT`와 historical constituent source가 준비되면 실행합니다.
- 사용자가 제공한 로컬 SEC companyfacts archive로 2009-2025 PIT feature 449개를 생성했고, 재무 feature를 pooled predictor에 실제 연결했습니다.
- 같은 factor-residual target에서 price-only와 PIT joint model을 직접 비교했으나 mean rank IC가 각각 `0.0015`, `-0.0046`으로 둘 다 실패했습니다.
- price-only relative ridge는 59개 OOS period에서 mean rank IC `0.0539`, top-minus-bottom `0.0165`와 개별 95% block-bootstrap gate를 통과했습니다.
- 그러나 compact quality 후보까지 포함한 4개 동시 objective의 Holm-adjusted p-value는 `0.1340`이었고 static current-DOW universe도 survivorship-safe하지 않아 후보를 freeze하지 않았습니다.
- 현 단계에서는 Transformer hyperparameter 조정보다 historical constituent membership, sector metadata, immutable research split 확보가 먼저입니다.
- historical DJIA 2008-2025 membership을 적용하자 relative ridge IC는 static-DOW `0.0539`에서 `0.0289`로 감소했습니다.
- 63개 OOS period bootstrap에서 positive mean IC 확률 `84.80%`, positive spread 확률 `77.80%`로 95% gate를 통과하지 못했습니다.
- 동일 feature/target family를 Transformer hyperparameter로 확장할 근거가 없으므로 relative ridge도 freeze하지 않습니다.
- historical issuer CIK interval을 적용한 47-ticker PIT joint model은 동일 residual target의 price-only IC `0.0252`보다 높은 `0.0581`을 기록했습니다.
- 다만 top-minus-bottom positive probability가 `94.55%`, 3-objective Holm-adjusted p-value가 `0.1635`여서 signal-only gate를 통과하지 못했습니다.
- feature/data 방향의 가능성은 생겼지만 architecture 또는 Transformer hyperparameter 탐색 전 canonical PIT identity/sector provenance와 fresh immutable research split이 필요합니다.
- historical-DOW factor research split은 objective와 입력 SHA까지 포함한 manifest로 잠갔습니다. 새 architecture나 hyperparameter family는 같은 namespace를 수정하지 말고 별도 split/namespace를 선언해야 합니다.
- Transformer 대신 먼저 nested time-fold ridge regularization을 구현했습니다. nested model은 IC `0.0627`, spread `0.0153`으로 고정 penalty를 개선하고 개별 95% signal gate를 통과했습니다.
- 하지만 Holm-adjusted p-value `0.1020`과 fixed baseline 대비 paired IC improvement `81.70%` 때문에 아직 복잡한 architecture로 확장하지 않습니다.
- official French market beta target도 IC `0.0618`로 내부 beta nested ridge `0.0627`을 넘지 못했습니다. target data를 바꿔도 Transformer 확장 근거는 생기지 않았습니다.
- Nasdaq-100 historical membership 2016-2025, 179 ticker와 SEC SIC 173/174 issuer를 고정해 독립 locked holdout을 구성했습니다.
- SEC parser에 20-F/40-F, IFRS taxonomy, weighted-average shares fallback을 추가해 2025 active PIT coverage를 `87.1%→96.0%`으로 높였습니다.
- frozen nested ridge의 Nasdaq holdout IC는 `0.0260`, spread는 `-0.0022`였고 fixed ridge 대비 paired improvement 확률은 IC `60.55%`, spread `61.35%`로 탈락했습니다.
- 이 holdout 결과로 penalty, grid, 기간을 재튜닝하지 않습니다. 현재 증거는 Transformer hyperparameter 확대보다 새로운 feature/model family와 새 untouched holdout이 필요함을 지지합니다.
- 새 v4 research namespace에서 cross-sectional percentile-rank target을 직접 학습하는 nested ridge를 사전 잠그고 비교했습니다.
- rank-target은 raw nested 대비 IC `0.0538<0.0627`, spread `0.0078<0.0153`이었고 paired improvement 확률도 `18.75%`/`1.75%`여서 폐기했습니다.
- 분기 filing anchor와 YTD 차감으로 quarterly TTM PIT feature 2,170행/123 ticker를 생성했습니다. median feature age는 annual 약 306~309일에서 quarterly 약 58~62일로 감소했습니다.
- annual/quarterly predictor 비교에서 realized residual target을 같은 quarterly PIT frame으로 고정해 target 변경 혼입을 제거했습니다.
- Nasdaq 2020~2021 research의 annual predictor는 IC `-0.0424`, spread `-0.0151`, quarterly predictor는 IC `-0.0505`, spread `-0.0263`으로 둘 다 탈락했습니다.
- 7개 OOS period는 block bootstrap 최소 표본에도 미달합니다. 같은 기간에서 TTM window, 시작일, penalty를 재튜닝하지 않습니다.
- fresh country-ETF 15종의 2010~2016 research에서 고정 shallow histogram gradient boosting을 relative ridge와 비교했습니다.
- nonlinear candidate는 IC `-0.0139`, spread `0.0001`로 ridge IC `0.0164`, spread `-0.0030`을 안정적으로 개선하지 못했습니다.
- paired P(higher IC/spread)는 `25.65%`/`57.35%`였고 속도는 ridge보다 약 2.25배 느려 폐기했습니다. 2017+ validation/holdout은 열지 않습니다.
- fresh Nasdaq 2018~2019 research에서 공시 level에 1년 변화 feature를 더한 fundamental-momentum nested ridge는 baseline보다 IC `-0.0220`, spread `-0.01549` 낮았습니다.
- paired P(higher IC/spread)는 `12.35%`/`1.20%`여서 폐기했고, Transformer 확장 근거는 생기지 않았습니다.
- fresh French size×value portfolio research에서 FF3 residual momentum도 raw 12-1 momentum보다 IC `-0.0494`, spread `-0.00784` 열위였습니다.
- factor exposure 제거 자체가 Transformer hyperparameter 확대 근거를 만들지 못했으므로 residual window/factor set을 같은 결과에 맞춰 재튜닝하지 않습니다.
- fresh French size×operating-profitability research에서 50/50 profitability-momentum은 자체 signal gate를 통과했지만 raw momentum보다 IC `-0.0226`, spread `-0.00036` 열위였습니다.
- 새 fundamental feature도 paired uplift를 만들지 못했으므로 이 결과는 Transformer HPO 근거가 아닙니다.
- OP×investment quality composite를 raw 12-1 momentum과 결합한 고정 선형 신호는 IC/spread paired improvement와 Holm gate를 통과했습니다.
- 복잡한 Transformer HPO 없이 데이터/feature family 변경으로 uplift를 얻었습니다. frozen 4-case validation 전 architecture와 weight를 변경하지 않습니다.
- untouched 2000~2011 validation에서도 quality-momentum은 raw momentum 대비 paired IC/spread gate와 4/4 case를 통과했습니다.
- 다만 absolute P(IC>0)가 `91.60%`로 95%에 못 미쳐 최종 validation은 탈락입니다. Transformer HPO 또는 blend 재튜닝으로 이 결과에 맞추지 않습니다.
- 별도 B/M×OP universe의 value-quality-momentum은 raw momentum 대비 paired IC/spread 개선 확률 `98.20%`/`95.75%`로 research gate를 통과했습니다.
- 새 candidate도 고정 선형 신호이므로 Transformer HPO는 계속 보류하고 untouched validation부터 실행합니다.
- untouched validation에서 value-quality-momentum 자체 IC/spread는 95% absolute gate를 통과했지만 baseline 대비 paired 확률은 `93.85%`/`94.20%`, 4-case는 `2/4`였습니다.
- low-value/low-profitability 약점을 validation 결과로 보정하거나 Transformer로 fitting하지 않습니다.
- fresh B/M×investment universe에서 completed-period IC 기반 online factor-weight calibration도 raw momentum 대비 paired IC/spread uplift가 `64.00%`/`87.40%`에 그쳤습니다.
- 단순 weight adaptation도 generalizable uplift를 만들지 못했으므로 calibration hyperparameter나 Transformer capacity를 같은 결과에 맞춰 확대하지 않습니다.
- fresh official French 17-industry `1969~1999` panel에서 현재 lightweight point forecast는 그대로 두고 completed OOS residual RMSE로 uncertainty만 보정하는 후보를 사전 고정했습니다.
- 최대 6개 non-overlap origin, 최소 126일 history, fixed 20% prior에 대한 50% variance shrinkage를 사용했고 모든 calibration target은 현재 training end 전에 완료됐습니다.
- calibrated BL은 current lightweight BL 대비 volatility `13.36%→13.09%`, max drawdown `-43.97%→-43.27%`, average turnover `6.53%→2.15%`로 개선했습니다.
- 하지만 CAGR은 `13.10%→13.09%`로 감소했고 Sharpe `0.5100→0.5169`의 paired improvement probability는 `71.05%`, higher-return probability는 `39.40%`였습니다. Holm-adjusted p-value는 각각 `0.5790`/`0.6060`입니다.
- raw lightweight signal의 mean rank IC는 `0.0223`이지만 top-bottom spread가 `-0.00041`이라 signal gate도 실패했습니다. 후보를 폐기하고 `2000~2011` validation을 열지 않습니다.
- BL raw view가 backtest `signal_scores`로 전달되지 않아 rank diagnostics가 항상 비던 결함을 수정했습니다. 이는 model weight를 바꾸지 않는 audit fix입니다.
- OOS uncertainty 방향은 구현 검증됐지만 alpha 품질을 만들지 못했습니다. 같은 split에서 prior weight, origin 수, horizon을 재튜닝하거나 Transformer HPO 근거로 사용하지 않습니다.
- fresh official French 38-industry source에서 장기 결측인 `Govt`, `Steam`, `Water`를 exact-name provenance로 제외하고 35개 complete portfolio `1981~1999` research panel을 잠갔습니다.
- existing lightweight point forecast의 magnitude를 버리고 cross-sectional rank만 fixed 20% active-share tilt로 쓰는 후보를 사전 고정했습니다.
- rank signal은 mean IC `-0.0125`, positive IC rate `43.94%`, top-bottom spread `-0.00034`로 absolute signal gate를 명확히 실패했습니다.
- rank tilt Sharpe `0.6533`은 current lightweight BL `0.6688`, equal weight `0.6698`, historical BL `0.6993`보다 낮았습니다. P(higher Sharpe)는 current/equal 대비 `28.40%`/`28.80%`였습니다.
- magnitude 제거로도 실패했으므로 병목은 lightweight point forecast의 cross-sectional ordering입니다. 같은 split에서 forecast horizon, active share, rank transform을 재튜닝하지 않고 `2000+` validation/holdout을 봉인합니다.
- official French size×accrual benchmark에서 accrual-quality-momentum의 absolute signal은 강했지만 raw momentum 대비 paired spread gate가 실패했습니다.
- local companyfacts에서 opt-in cash-accrual `(operating_cash_flow-net_income)/assets`를 생성해 fresh Nasdaq 2017 nested ridge에 추가했으나 후보 IC `-0.0451`, spread `-0.00742`로 baseline보다 악화됐습니다.
- usable OOS period도 6개뿐이어서 statistical gate가 불가능했습니다. 같은 Nasdaq 기간에서 accrual 정의나 ridge 설정을 재튜닝하지 않으며 Transformer HPO 근거로 사용하지 않습니다.
- official French net-share-issues와 12-1 momentum의 고정 50/50 blend가 raw momentum 대비 paired IC/spread 개선 확률 `97.60%`/`98.35%`로 research gate를 통과했습니다.
- 이 uplift는 Transformer hyperparameter가 아니라 독립 issuer-action feature에서 발생했습니다. Frozen 2000~2011 validation 전 architecture 또는 blend weight를 변경하지 않습니다.
- Untouched validation의 paired uplift는 통과했지만 candidate absolute P(IC>0/spread>0)가 `84.55%`/`87.35%`, 4-case가 `3/4`여서 승격하지 않습니다.
- 이 실패는 Transformer capacity/HPO 근거가 아니며 2012+ holdout을 열지 않습니다.
- Official French FF3 residual-variance feature를 추가한 fixed blend는 absolute signal이 강했지만 momentum 대비 paired IC/spread 개선 확률이 `80.75%`/`77.15%`에 그쳤습니다.
- Residual-risk 정보도 incremental forecast ordering을 증명하지 못했으므로 Transformer HPO나 capacity 확대 근거로 사용하지 않습니다.
- Fixed short-term-reversal-momentum은 복잡한 모델 없이 research와 untouched validation을 통과했지만 final locked holdout의 paired uplift가 `70.45%`/`84.75%`에 그쳤습니다.
- Feature horizon diversification이 유망하다는 증거는 생겼지만 default 승격 또는 Transformer HPO 근거는 아닙니다.
- Parameter-free online Hedge는 expert weight를 실제로 `41.18%~79.26%`로 이동했지만 fixed blend보다 IC가 낮고 raw momentum 대비 IC uplift 확률도 `74.40%`에 그쳤습니다.
- Dynamic weighting 실패도 Transformer capacity 확대 근거가 아니며 target/feature ordering 병목이 계속됩니다.
- fresh official French 12-industry 1933~1952 split에서 고정 market trend/volatility interaction을 nested ridge에 추가했지만 IC `0.0193→0.0050`, spread `0.00445→0.00286`으로 악화됐습니다.
- Fresh official French 30-industry `1973~1999`에서 52-week-high/momentum fixed blend도 raw 12-1 momentum보다 IC와 spread가 각각 `0.01135`, `0.00522` 낮았습니다.
- Candidate가 nonlinear model 없이도 absolute predictiveness는 보였지만 incremental ordering은 실패했습니다. 단순 raw momentum이 engineered blend보다 강한 상태에서 Transformer capacity/HPO를 확대하지 않습니다.
- Fresh French 17-industry `2000~2011`에서 current lightweight point forecast IC/spread는 `-0.0120/-0.00421`, raw momentum은 `0.0042/-0.00250`이었습니다.
- Raw momentum portfolio는 lightweight 대비 return/Sharpe uplift 확률 `96.35%/95.40%`였지만 absolute/paired signal 및 risk-parity guard를 통과하지 못했습니다. 약한 current model을 확인했다는 이유만으로 불완전한 replacement를 승격하지 않습니다.
- candidate의 paired P(higher IC/spread)는 `35.75%`/`40.25%`였고 계산시간은 baseline `32.68s`에서 `50.64s`로 증가했습니다. macro/regime interaction도 Transformer HPO 근거를 만들지 못했습니다.
- 1953+ validation/holdout을 열지 않고 같은 split에서 lookback, threshold, interaction subset을 재튜닝하지 않습니다.

## 선행조건

- validation과 겹치지 않는 research universe와 기간을 확정합니다.
- point-in-time factor 또는 benchmark 데이터를 사용할 경우 provenance와 survivorship 정책을 먼저 문서화합니다.
- 기존 live gauntlet 결과는 문제 확인 근거로만 사용하고 같은 4개 case에 맞춘 튜닝은 금지합니다.

## 참고

- ARIMA+Transformer live 결과: `docs/reports/260723-1703-01-live-candidate-gauntlet.md`
- Transformer live 결과: `docs/reports/260723-1749-01-live-transformer-candidate-gauntlet.md`
- 연계 TODO: `docs/todo/portfolio-alpha-v2-research.md`
- todo-list 한 줄 요약: redesign ARIMA/Transformer forecast targets, calibration, and training efficiency before reusing them as portfolio alpha features.
- 기반 보고서: `docs/reports/260723-1932-01-forecast-signal-diagnostics.md`
- pooled research 결과: `docs/reports/260723-2032-01-pooled-cross-sectional-research.md`
- Nasdaq locked holdout: `docs/reports/260724-0000-01-nasdaq100-frozen-holdout.md`
- Rank-target research: `docs/reports/260724-0009-01-rank-target-research.md`
- Quarterly TTM research: `docs/reports/260724-0024-01-quarterly-ttm-research.md`
- Country ETF nonlinear research: `docs/reports/260724-0049-01-country-etf-nonlinear-research.md`
- Fundamental momentum research: `docs/reports/260724-0111-01-fundamental-momentum-research.md`
- Factor-residual momentum research: `docs/reports/260724-0210-01-factor-residual-momentum-research.md`
- Profitability-momentum research: `docs/reports/260724-0226-01-profitability-momentum-research.md`
- Quality-momentum research: `docs/reports/260724-0232-01-quality-momentum-research.md`
- Quality-momentum validation: `docs/reports/260724-0238-01-quality-momentum-validation.md`
- Value-quality-momentum research: `docs/reports/260724-0245-01-value-quality-momentum-research.md`
- Value-quality-momentum validation: `docs/reports/260724-0250-01-value-quality-momentum-validation.md`
- Adaptive value-investment research: `docs/reports/260724-0301-01-adaptive-value-investment-momentum-research.md`
- Lightweight OOS uncertainty research: `docs/reports/260724-0320-01-lightweight-oos-uncertainty-research.md`
- Lightweight rank-tilt research: `docs/reports/260724-0332-01-lightweight-rank-tilt-research.md`
- Cash-accrual research: `docs/reports/260724-0350-01-cash-accrual-research.md`
- Market-regime interaction research: `docs/reports/260724-0411-01-market-regime-interaction-research.md`
- Net-issuance quality-momentum research: `docs/reports/260724-0438-01-net-issuance-quality-momentum-research.md`
- Net-issuance quality-momentum validation: `docs/reports/260724-0443-01-net-issuance-quality-momentum-validation.md`
- Low residual-variance momentum research: `docs/reports/260724-0448-01-low-residual-variance-momentum-research.md`
- Short-term reversal-momentum gauntlet: `docs/reports/260724-0500-01-short-term-reversal-momentum-gauntlet.md`
- Online reversal Hedge research: `docs/reports/260724-0507-01-online-reversal-hedge-research.md`
