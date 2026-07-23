# TODO - Portfolio Forecast Model Redesign

- 등록 일시: 2026-07-23 19:21 (KST)
- 작성자: Codex
- 에이전트: Codex
- 진행 시점: ARIMA/Transformer 계열을 portfolio alpha feature로 다시 검토하기 전
- 현재 상태: frozen nested PIT ridge가 독립 Nasdaq-100 locked holdout에서 탈락

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
