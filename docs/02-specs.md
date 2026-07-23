# 2) Specs

본 문서는 Antifier 구현에 사용하는 기술 스택과 운영 규칙을 정의합니다.

## A. Runtime / Core

- 제품 형태: React SPA + Flask REST API 기반 로컬 웹앱
- 프론트엔드 언어: JavaScript ES modules, JSX
- 프론트엔드 프레임워크: React 19
- 빌드 도구: Vite 6
- 패키지 매니저: npm
- 백엔드 언어: Python
- 백엔드 프레임워크: Flask 3.x, Flask-CORS
- Python 호환성: README는 3.8+ 또는 3.9+를 언급하고, CI는 3.11, installer build는 3.12를 사용합니다. 최소 버전을 공식 변경하기 전에는 3.8+ 호환성을 깨지 않는 방향을 기본으로 합니다.
- Node.js 호환성: README는 Node.js 16+를 요구하고, CI는 Node.js 22를 사용합니다.

## B. Frontend Stack

- React: `react`, `react-dom`
- Charting: `plotly.js`, `plotly.js-dist`, `react-plotly.js`
- i18n: `i18next`, `react-i18next`
- HTTP: 기본 `fetch`와 `AbortController`, 일부 보조 용도 `axios`
- Test: Vitest, jsdom, Testing Library
- Lint: ESLint 9, React/React Hooks/React Refresh plugins

프론트엔드 규칙:

- API URL은 `src/frontend/apiClient.js`의 `apiUrl(path, params)`를 우선 사용합니다.
- 개발 환경에서는 Vite proxy가 `/api`를 `http://localhost:5000`으로 전달합니다.
- 외부 backend base URL이 필요하면 `VITE_API_BASE_URL`을 사용합니다.
- stock analysis처럼 중복 요청 가능성이 큰 흐름은 `AbortController`와 debounce 패턴을 유지합니다.
- locale key를 추가하면 영어와 한국어 번역 파일을 함께 업데이트합니다.
- 렌더링 성능이 중요한 chart는 lazy/loading 상태와 skeleton을 고려합니다.
- 스타일은 현재 `App.css` 중심 구조를 유지합니다. Tailwind, CSS-in-JS, UI framework는 별도 결정 없이 추가하지 않습니다.

## C. Backend Stack

- API framework: Flask, Flask-CORS
- 데이터 처리: pandas, numpy, scipy
- ML/통계: scikit-learn, statsmodels, pmdarima, TensorFlow, Keras, XGBoost, LightGBM
- 금융 데이터: yfinance, finvizfinance
  - `finvizfinance.group.valuation.Valuation`은 Financial Statement의 Finviz sector/industry valuation benchmark 1차 소스로 사용합니다.
  - Finviz benchmark가 제공하는 valuation 지표는 우선 사용하고, Finviz에 없는 수익성/성장성/안정성/위험 지표는 yfinance로 산업별 대표 대형주 10개 내외의 단순 평균을 계산해 보완합니다.
  - Finviz benchmark가 실패하거나 해당 산업/섹터 행을 찾지 못하면 전체 benchmark를 yfinance 대표 종목 평균으로 fallback합니다.
  - 산업별 대표 ticker dataset이 없으면 섹터 대표 대형주 평균을 마지막 benchmark fallback으로 사용합니다.
  - Financial Statement 대시보드의 시가총액과 valuation 계산에 쓰는 가격/주당 재무 값은 가능한 경우 최신 FX rate로 USD 기준 정규화하고, 원 통화와 표시 통화를 응답에 함께 포함합니다.
- 포트폴리오 최적화: PyPortfolioOpt
- 캐시/운영 보조: joblib, tenacity, rich, psutil, custom cache manager
- 패키징: PyInstaller

백엔드 규칙:

- public endpoint는 `/api/*` 경로를 기본으로 합니다. 기존 호환 endpoint는 명시적 이유가 있을 때만 유지합니다.
- 요청 파라미터는 endpoint 초입에서 검증하고, domain function에 검증되지 않은 값을 넘기지 않습니다.
- ticker는 `SAFE_TICKER_PATTERN` 수준의 제한을 적용합니다.
- 날짜는 `YYYY-MM-DD` 형식을 사용하고 시작일이 종료일보다 앞서야 합니다.
- JSON 응답에는 NaN, inf, pandas/numpy 타입이 그대로 노출되지 않도록 직렬화합니다.
- 외부 데이터 부족은 4xx/5xx 의미에 맞게 메시지를 내려주고 서버 traceback을 노출하지 않습니다.
- 장시간 최적화는 `request_id` 기반 job lifecycle을 사용하고 `/api/progress-stream/<request_id>` SSE 흐름을 유지합니다.
- Optimizer job은 `running`, `completed`, `failed`, `cancelled` 상태를 가지며, 페이지 새로고침/화면 이동 뒤에도 상태 조회와 SSE 재연결이 가능해야 합니다.
- 클라이언트가 명시 취소하거나 일정 시간 동안 heartbeat/SSE 재연결이 없으면 backend는 cancellation event를 설정하고 계산 루프의 체크포인트에서 협력적으로 중단합니다.
- 계산 비용이 큰 ML 모델은 cache, batch size, worker/thread 제한을 고려합니다.
- ARIMA + Transformer와 Transformer forecast가 학습 실패, 미학습, 데이터 부족 등으로 유효한 예측을 만들지 못하면 `expected_return: null`, 최대 uncertainty, `source: "no_view"`를 반환하고 optimizer는 해당 ticker를 prior-only view로 취급합니다.
- `requirements-ci.txt`는 CI용 경량 의존성입니다. 무거운 런타임 의존성을 CI에 추가할 때는 필요성을 분명히 합니다.

## D. 금융/분석 도메인 규칙

- Antifier는 투자 의사결정을 보조하는 분석 도구이며 투자 자문이나 수익 보장을 제공하지 않습니다.
- 통화가 다른 자산은 USD 기준 변환 흐름을 유지하고, 원 통화와 표시 통화를 응답에 명확히 포함합니다.
- 수익률은 log return, simple return, annualized return의 의미가 섞이지 않도록 함수명과 응답 필드명을 분명히 합니다.
- 거래일 기준 연율화는 기존 `TRADING_DAYS_PER_YEAR = 252` 관례를 따릅니다.
- 포트폴리오 최적화는 입력 데이터 길이, 결측치, 상장 기간 부족, 무효 weight를 방어해야 합니다. `min_history` 미만 ticker는 최적화 universe에서 제외하되 성공/오류 응답의 `data_eligibility`에 요청·적격·제외 ticker, 관측 수/커버리지/최초·최종 관측일, 제외 stage/reason을 남겨 universe 축소를 숨기지 않습니다.
- Black-Litterman, MPT, forecast 기반 expected return은 모델 가정과 fallback 경로를 테스트 또는 문서로 남깁니다.
- forecast 모델을 optimizer 기본값으로 승격하기 전에는 walk-forward 포트폴리오 backtest에서 equal weight, minimum variance, historical MPT/BL, inverse-vol risk parity, 6-month momentum, low-volatility tilt, market-cap weight(가능한 경우), standalone 12-1 momentum, momentum BL, signal-stack BL baseline과 거래비용/turnover-control 반영 성과를 비교합니다.

## E. API Surface

주요 endpoint와 책임:

- `GET /api/get-data`: ticker price, regression, future prediction, currency metadata
- `GET /api/analyze-hedge`: 두 ticker의 pairs/correlation/regression 분석. 단정적인 hedge 성립 여부를 반환하지 않고, 상관계수, p-value, 회귀 alpha/beta/R-squared, 관측치 수, 비단정적 correlation signal을 반환합니다.
- `GET /api/financial-statement`: 기본 요청은 재무 지표 대시보드, Finviz/yfinance benchmark 비교, 규칙 기반 투자 신호, 전체 재무제표 묶음을 조회하고, `type=income|balance|cash` 요청은 기존 단일 표 조회를 유지
- `POST /api/optimize-portfolio`: 포트폴리오 최적화 job 시작. 같은 `request_id` 재요청은 기존 job 상태를 반환합니다. 완료/데이터 오류 결과의 `data_eligibility`는 `minimum_observations`, 14일 staleness, no-leading-fill alignment 정책과 ticker별 `no_price_data`, `insufficient_history`, `stale_price`, `fx_unavailable`, `invalid_price`, `forecast_output_missing`, `alignment_missing` 사유를 제공합니다. 선택 입력 `rebalance_band`, `max_turnover`, `current_weights`가 함께 있으면 raw optimizer 응답에 `rebalance_controls`, `pre_control_weights`, `controlled_weights`를 포함할 수 있습니다. 선택 입력 `turnover_penalty`는 `current_weights`가 있을 때 optimizer objective에 L1 turnover penalty를 더하고, `min_holding_weight`는 최적화 후 작은 long-only position을 제거한 뒤 재정규화합니다.
- `GET /api/optimization-jobs/<request_id>`: 최적화 job 상태, 진행률, 완료 결과 또는 오류 조회
- `POST /api/optimization-jobs/<request_id>/cancel`: 실행 중인 최적화 job 취소 요청
- `GET /api/progress-stream/<request_id>`: 최적화 진행률 SSE. 연결 시 현재 상태를 먼저 전송하고 이후 이벤트를 구독합니다.
- `GET /api/portfolio-results`: 저장된 최적화 결과 목록
- `GET /api/portfolio-results/<portfolio_id>`: 특정 최적화 결과 조회
- `POST /api/stock-screener`: ticker universe와 Financial Statement 대시보드의 0-100 종합 점수 기반 screening
- `POST /api/asset-names`: ticker display name 조회
- `POST /api/benchmark-portfolio`: 포트폴리오 benchmark 계산
- `POST /api/manage-portfolio`: 현 보유/현금 주입 기준 리밸런싱 주문 계산. 입력에서 생략하면 `rebalance_band=0.02`, `max_turnover=0.35`를 적용해 작은 거래를 건너뛰고 gross turnover를 제한합니다. Band가 매수/매도 한쪽만 제거해 target의 의도된 현금 비중을 바꾸지 않도록 필요한 최소 반대편 거래를 재도입한 뒤 turnover cap을 적용합니다. 선택 입력 `turnover_penalty`, `min_holding_weight`는 내부 최적화 호출에 전달됩니다.

Backend-only research tool:

- `tools/backtest_portfolio_models.py`: CSV, ticker list, ticker group을 입력받아 rolling rebalance backtest를 실행하고 `settings`, `models`, `summary_by_model`, `alpha_diagnostics`, `rebalance_records`, `promotion_decision`, `warnings` JSON을 저장합니다. 모델에는 `risk_parity`, `momentum_6m`, `low_volatility`, `market_cap_weight`, `momentum_12_1`, `momentum_bl`, `signal_stack_bl`, `adaptive_signal_tilt`, `calibrated_lightweight_bl`, `arima_transformer_rank_bl`, `transformer_rank_bl`이 포함됩니다.
  - `adaptive_signal_tilt`은 12-1/6개월 momentum, 1개월 reversal, low-volatility, drawdown rank를 training window 내부의 완료된 forward-relative-return 구간으로 IC calibration하고 equal-weight 주변의 명시적 active-share tilt로 변환합니다. calibration과 target 생성은 rebalance date 이전 가격만 사용합니다.
  - research model `maximum_diversification`은 Ledoit-Wolf covariance와 long-only/max-weight 제약에서 diversification ratio를 최대화합니다. promotion gate 통과 전 기본 allocator로 사용하지 않습니다.
  - research signal `profitability_momentum_scores`는 12-1 momentum rank와 filing-date/PIT fundamental rank를 명시적 고정 비중으로 결합합니다. quality mode는 profitability와 conservative investment rank를, value-quality mode는 value와 profitability rank를 결합합니다. blend는 새 split에서 사전 고정하고 paired signal gate를 통과해야 합니다.
  - `adaptive_factor_momentum_scores`는 training window 안에서 완료된 forward period의 component IC만 사용하고 fixed prior로 shrink한 뒤 component cap을 적용합니다. 미래 가격/factor row는 calibration에 사용할 수 없습니다.
  - research model `calibrated_lightweight_bl`은 기존 lightweight ensemble의 point forecast와 ensemble weight를 변경하지 않고, training window 안에서 완료된 non-overlap horizon residual의 annualized RMSE로 ticker별 uncertainty만 보정합니다. 최대 6개 origin, 126일 최소 history, fixed 20% uncertainty prior에 대한 50% variance shrinkage는 split manifest로 고정합니다.
  - research model `lightweight_rank_tilt`은 lightweight point forecast의 크기를 폐기하고 cross-sectional rank만 equal-weight 주변 fixed 20% active-share tilt로 변환합니다. promotion gate 통과 전 production optimizer와 기본 모델 목록에 포함하지 않습니다.
  - BL 계열의 raw absolute view는 `signal_scores`로도 기록해 realized cross-sectional rank IC와 top-bottom spread를 계산합니다. posterior return이나 최종 weight를 raw signal 진단으로 대체하지 않습니다.
  - `alpha_diagnostics`는 signal의 rank IC/top-minus-bottom/horizon decay/persistence/coverage, construction의 signal-weight rank correlation/active share/BL view retention/concentration/예측 변동성, execution의 raw-controlled turnover/weight loss/비용 전후 수익을 분리합니다.
  - `--gauntlet-preset candidate`는 bull/crash/inflation-rate-shock/sideways를 대표하는 4개 validation basket/regime을 기본 63거래일 리밸런싱으로 빠르게 선별하며, 기본 후보는 `adaptive_signal_tilt`입니다.
  - `--gauntlet-preset standard`는 SP500 sample, DOW, tech, defensive, mixed ETF-like basket을 4개 regime과 rebalance band 2/3/5%, max turnover 20/35/50% sensitivity로 실행합니다.
  - `--gauntlet-preset holdout`은 validation을 통과한 단일 후보만 2024-2025 locked holdout에서 최종 1회 평가하기 위한 별도 split/namespace를 사용합니다. validation 탈락 후보에는 실행하지 않습니다.
  - 각 basket/regime의 forecast와 pre-control target weight는 한 번만 만들고 9개 거래 제약 조합에서 재사용합니다. ML prediction은 가격 window digest, 모델 방식, horizon, cache schema/experiment namespace를 key로 SQLite에 즉시 저장합니다.
  - signal candidate는 rebalance별 forward cross-sectional Spearman rank IC와 top-minus-bottom spread를 기록하고, positive rank IC와 positive spread가 없는 후보는 성과와 별개로 승격시키지 않습니다.
  - 각 완료 case는 JSONL checkpoint에 append하며 `--resume`으로 완료 case와 persistent forecast를 재사용합니다. 모델 설정이 달라지는 실험은 `--forecast-cache-namespace`를 분리해야 합니다.
  - 최종 JSON과 Markdown summary는 `logs/` 아래에 저장하며 public API나 UI는 추가하지 않습니다.
  - research-only `factor_neutral_alpha_tilt`은 기본 모델 목록과 gauntlet 기본 후보에 포함하지 않습니다. 실행하려면 `--models factor_neutral_alpha_tilt`, `--factor-data`, `--factor-provenance`를 명시해야 합니다.
  - point-in-time factor CSV는 long-form `available_date`, `ticker`, `sector`, `market_cap`, `quality`, `profitability`, `valuation`, `liquidity` 열을 요구합니다. 네 alpha feature는 값이 높을수록 선호되는 방향으로 사전 정규화해야 하며, `available_date` 이후에만 사용합니다.
  - factor provenance JSON은 `source`, `retrieved_at`, `universe_policy`, `survivorship_policy`를 요구합니다. 실행 결과에는 data/provenance SHA-256과 정책을 기록합니다.
  - v2 target은 완료된 training-window forward return에서 cross-sectional market beta, sector, log market-cap 노출을 제거합니다. alpha ridge coefficient는 최소 관측 수 gate와 feature별 절대 weight cap을 적용합니다.
  - forecast rank cache schema `2026-07-23-v2-diagnostics`부터 Transformer 응답은 daily clip hit, annual clip 전후 값, uncertainty source를 기록합니다. 기존 schema cache는 진단 메타데이터가 없으므로 새 research 실행에 재사용하지 않습니다.
  - `tools/diagnose_forecast_signals.py`는 SQLite forecast cache를 재학습 없이 읽어 coverage, `±0.69` boundary saturation, unique-value/tie 비율, component 분포를 JSON/Markdown으로 기록합니다.
  - `forecast_signal_research.py`의 empirical uncertainty calibration은 동일 단위의 완료된 OOS prediction/realized return 최소 20개를 요구합니다. in-sample training RMSE를 OOS-calibrated uncertainty로 표시하지 않습니다.
  - research target builder는 명시한 training cutoff 안에서 forward horizon이 완료된 row만 만들며 `absolute`, cross-sectional median-adjusted `relative`, PIT beta/sector/size `factor_residual` target을 지원합니다.
  - forecast 후보는 portfolio construction 전에 signal-only gate에서 OOS rank IC, positive IC rate, top-minus-bottom spread, coverage, saturation, tie 기준을 통과해야 합니다.
  - `tools/research_cross_sectional_forecasts.py`는 generic validation/holdout 이름을 거부하고 self-hash로 잠긴 research 또는 locked-holdout split에서 pooled `absolute_ridge`, `relative_ridge`, `pairwise_ridge`, `listwise_rank_ridge`, 고정 compact `relative_hist_gradient_boosting`, completed inner time-fold로 penalty를 선택하는 `relative_nested_ridge`, market trend/volatility regime과 price predictor의 interaction을 추가하는 research-only `relative_market_regime_nested_ridge`, 선택적 `factor_residual_price_ridge`, 전체 재무 predictor를 결합한 `factor_residual_ridge`, compact `factor_residual_quality_ridge`, inner time-fold에서만 penalty를 선택하는 `factor_residual_nested_ridge`, factor-residual의 signal-date percentile rank를 학습하는 `factor_residual_rank_nested_ridge`, 최소 300일 이전 공시 대비 재무 변화를 추가하는 research-only `factor_residual_fundamental_momentum_nested_ridge`, opt-in SEC cash-accrual을 추가하는 `factor_residual_cash_accrual_nested_ridge`를 비교합니다.
  - `tools/research_accrual_quality.py`는 official French accrual, net-share-issues, FF3 residual-variance, 또는 prior-month-return bucket과 12-1 momentum의 고정 blend를 locked research split에서 비교합니다. Net-share-issues 후보는 `NegNI > ZeroNI > LoNI > NI2 > NI3 > NI4 > HiNI`, residual-variance 후보는 `LoVAR > VAR2 > VAR3 > VAR4 > HiVAR`, short-term-reversal 후보는 `LoPRIOR > PRIOR2 > PRIOR3 > PRIOR4 > HiPRIOR` 순서를 사용합니다. Research gate를 통과한 후보만 `tools/validate_frozen_quality_momentum.py`가 frozen result SHA와 사양을 검증한 뒤 사전 고정 case validation을 수행합니다. Locked holdout 실행은 passing validation-result SHA를 추가로 요구하고 manifest settings와 auxiliary lineage에 함께 잠급니다.
  - `tools/research_online_reversal_ensemble.py`는 completed one-month rank IC를 expert loss로 변환하고 `sqrt(8 log N / t)` learning rate를 쓰는 no-tune Hedge로 momentum/reversal weight를 갱신합니다. Candidate는 fixed 50/50 blend와 raw momentum 모두에 대해 paired 95% bootstrap와 familywise Holm gate를 통과해야 합니다.
  - research-only `momentum_12_1_rank_tilt`과 `high_momentum_rank_tilt`은 같은 equal-weight 주변 20% active-share construction을 사용합니다. 후자는 12-1 momentum rank와 현재 가격/직전 252일 고점 proximity rank를 고정 50/50으로 결합합니다. `tools/research_high_momentum.py`는 candidate absolute IC/spread와 raw momentum 대비 paired IC/spread/return/Sharpe를 95% bootstrap 및 통합 Holm gate로 검증합니다.
  - `tools/research_raw_momentum.py`는 research-only `momentum_12_1_rank_tilt`을 current production-default 대응 `lightweight_bl`과 직접 비교합니다. Candidate absolute IC/spread, paired signal IC/spread, paired portfolio return/Sharpe, equal/risk-parity/historical-BL guard를 모두 통과해야 validation 대상이 됩니다.
  - research-only `risk_momentum_blend`는 inverse-volatility risk parity와 12-1 momentum rank tilt target을 고정 50/50으로 결합합니다. `tools/research_risk_momentum_blend.py`는 momentum absolute IC/spread와 두 component 각각 대비 lower-volatility/higher-Sharpe probability를 95% paired bootstrap 및 six-hypothesis Holm gate로 검증합니다.
  - research-only `minvar_momentum_blend`는 Ledoit-Wolf long-only minimum variance와 12-1 momentum rank tilt target을 고정 50/50으로 결합합니다. `tools/research_minvar_momentum_blend.py`는 동일 dual-component 및 six-hypothesis gate를 적용합니다.
  - research-only `james_stein_bl`은 historical daily sample mean을 global-minimum-variance expected return으로 Jorion/Bayes-Stein closed-form 수축한 뒤 기존 historical BL과 동일한 prior, covariance, uncertainty, 제약을 사용합니다. `tools/research_mean_shrinkage.py`는 locked research split에서 `historical_bl` 대비 volatility, Sharpe, drawdown, turnover, paired bootstrap와 Holm gate를 검증하며 기본 모델 목록에는 포함하지 않습니다.
  - research-only `hac_historical_bl`은 historical CAGR point view는 유지하고 고정 uncertainty를 training-only Newey-West/HAC annual mean standard error로 교체합니다. 자동 lag rule `floor(4*(T/100)^(2/9))`을 사용하며 `historical_bl` closest baseline과 inverse-vol guard를 통과하기 전 기본 모델에 포함하지 않습니다.
  - market regime interaction은 signal date까지 완료된 공식 market total return만 사용합니다. trend는 직전 252거래일 누적수익률의 부호, volatility는 직전 63거래일 연율 변동성과 현재 관측을 제외한 최대 756거래일 rolling-volatility median을 비교해 `-1/+1`로 고정하며, 필요한 history가 없으면 0으로 중립 처리합니다.
  - `tools/build_fama_french_industry_panel.py`는 source portfolio 제외가 필요하면 `--exclude-columns`에 exact name을 요구하고, source/selected ticker count와 ticker별 missing/available row count를 provenance에 기록합니다. `--uppercase-columns`는 source label을 기록한 뒤 canonical universe label만 대문자로 변환하며 중복 label을 거부합니다. 결측 portfolio를 자동 제거하거나 채우지 않습니다.
  - `tools/build_fama_french_monthly_panel.py`는 공식 French 월간 portfolio archive의 average value-weighted section을 월말 decimal return으로 파싱하고 누적 price index, 원본/파생 SHA, ordered basket hash를 기록합니다.
  - PIT 재무 predictor는 signal date까지 알려진 최신 filing만 사용합니다. quality, profitability, valuation, liquidity를 cross-sectional winsorized z-score로 만들고 결측은 중립값 0과 별도 missing indicator로 표현합니다.
  - factor CSV 사용 시 SHA-256을 포함한 `--factor-provenance`가 필수이며 불일치 파일을 거부합니다. universe, price, factor 파일 hash의 lineage도 서로 동일한 dataset 계보를 가리켜야 합니다.
  - promotion-safe pooled research와 locked holdout은 `--split-manifest`를 필수로 사용합니다. split role/ID, evaluation interval, namespace, objective family, universe/price/factor SHA-256을 self-hash contract로 잠그고 어느 하나라도 drift하면 실행을 거부합니다.
  - 최종 `promotion_eligible`은 data provenance safe, immutable research split locked, signal-only statistical gate passed 세 조건이 모두 true일 때만 true입니다. 단순히 데이터 hash가 맞다는 이유로 탈락 모델을 승격 가능으로 표시하지 않습니다.
  - signal-only gate는 시점 의존성을 보존한 circular block bootstrap에서 mean rank IC와 mean top-minus-bottom spread가 양수일 확률을 각각 95% 이상 요구합니다. 동시 비교 objective는 Holm-Bonferroni로 보정합니다.
  - 선택적 universe manifest는 `effective_date`, `ticker`, `in_universe` event 열을 요구합니다. 각 signal date에는 그 날짜까지 발생한 마지막 membership event만 적용하고 미래 편입 종목은 cross-sectional 표준화, target, prediction에서 제외합니다.
  - universe provenance는 `source`, `retrieved_at`, `universe_policy`, `survivorship_policy`를 요구합니다. promotion-safe 실행은 `historical_constituents`, `point_in_time_membership`, `survivorship_safe` 정책만 허용합니다.
  - full constituent snapshot은 `snapshots_to_membership_events`로 편입/퇴출 event를 재구성하고 모든 source date에서 원 snapshot과 동일한 membership인지 검증합니다.
  - promotion-safe universe 연구에 로컬 price CSV를 사용하면 `price_file_sha256`을 포함한 `--price-provenance`가 필수입니다. corporate ticker alias는 별도 파일과 hash로 기록합니다.
  - forecast coverage는 다운로드된 가격 열 내부가 아니라 signal date의 manifest active universe 전체를 분모로 계산합니다. 누락 active ticker와 period별 최소 coverage를 결과에 기록합니다.
  - `tools/build_sec_pit_features.py`는 SEC companyfacts/submissions API 또는 사용자가 제공한 로컬 공식 companyfacts archive의 공시일을 `available_date`로 사용해 quality, profitability, valuation, liquidity, filing-date market cap을 생성합니다. 이후 제출된 정정 공시는 이전 signal date row를 덮어쓰지 않습니다. `--feature-set core-cash-accrual`은 research-only `(operating_cash_flow-net_income)/assets`를 opt-in으로 추가하며 default `core` schema와 기존 artifact를 변경하지 않습니다.
  - SEC PIT parser는 10-K 외에 20-F/40-F와 IFRS standard taxonomy를 지원합니다. instant shares-outstanding가 없으면 동일 filing에서 공개된 annual weighted-average basic/diluted shares를 market-cap fallback으로 사용할 수 있으며 provenance에 정책을 기록합니다.
  - historical ticker가 registrant 변경을 거치면 `--security-master`의 `effective_start`, `effective_end`, `cik` interval을 사용합니다. interval overlap은 거부하며 `--security-master-provenance`의 SHA-256과 promotion-safe 여부를 결과에 전파합니다.
  - prebuilt historical price를 사용할 때는 `--price-csv`와 SHA-256을 가진 `--price-provenance`를 함께 요구합니다. 누락 ticker와 corporate alias도 factor provenance에 보존합니다.
  - 로컬 archive 모드는 선택적 `--submissions-dir`의 `CIK##########.json` 파일에서 SIC를 읽습니다. 이를 제공하지 않으면 sector는 `Unknown`이며 sector-neutral 성능을 주장하거나 후보를 승격할 수 없습니다.
  - SEC 수집은 연락처 email 또는 project URL을 포함한 `SEC_USER_AGENT`를 요구하고, 캐시와 최소 0.10초 요청 간격을 적용합니다. 결과 CSV와 provenance JSON에는 endpoint, 수집 시각, 실패 ticker, universe 정책, SHA-256을 기록합니다.
  - pooled candidate는 ticker별 모델을 반복 학습하지 않고 date × ticker observation을 한 모델로 학습합니다. 각 evaluation date의 training set은 그 날짜까지 forward horizon이 완료된 target만 포함합니다.
  - paired baseline이 있는 pooled candidate는 개별 bootstrap과 Holm correction뿐 아니라 baseline 대비 paired IC/spread 95% gate를 모두 통과해야 승격 대상이 됩니다.
  - nested ridge는 outer evaluation보다 먼저 완료된 target만 inner fold에 사용합니다. overlapping rebalance에서도 inner validation date까지 forward outcome이 완료되지 않은 row는 penalty 선택에서 제외합니다.
  - nested candidate와 fixed-penalty baseline의 period별 rank IC와 top-bottom spread 차이는 paired circular block bootstrap으로 별도 검증합니다.
  - historical 성과의 Sharpe/Sortino와 paired bootstrap은 가능하면 SHA-verified daily risk-free series를 사용합니다. FRED DGS3MO 연율은 해당 날짜 또는 그 이전 최신 관측만 backward-asof 정렬한 뒤 일수익률로 변환하며 미래 금리를 backward-fill하지 않습니다.
  - Fama/French `Mkt-RF + RF` daily return을 외부 market beta history로 사용하는 residual-target 후보를 지원합니다. 외부 factor가 내부 equal-weight market beta보다 낫다는 가정은 별도 paired gate로 검증합니다.
  - uncertainty는 이전 evaluation prediction 중 현재 signal date 전에 outcome이 완료된 residual만 사용해 순차적으로 계산합니다. 최종 보고서는 fit count, elapsed time, prediction throughput, peak Python memory를 함께 기록합니다.
  - risk allocator research는 기존 Ledoit-Wolf minimum variance와 별도로 Ledoit-Wolf 50%, Oracle Approximating 30%, 180일 exponential covariance 20% blend, exact equal-risk-contribution, hierarchical risk parity, regime-conditioned covariance, historical minimum-CVaR, completed-fold online allocator ensemble, historical BL 대비 HAC uncertainty 후보를 비교할 수 있습니다.
  - `online_allocator_ensemble`은 equal-weight, Ledoit-Wolf minimum variance, inverse-volatility risk parity, 6-month momentum 네 expert를 사용합니다. outer training window 안에서 완료된 252일 train/63일 validation fold의 cross-expert return rank만 Hedge loss로 누적하고 `sqrt(2 log(N) / completed_folds)` learning rate로 현재 expert target을 결합합니다. tuning grid나 미래 fold를 사용하지 않습니다.
  - research-only `random_matrix_minimum_variance`는 sample correlation의 Marchenko-Pastur noise band eigenvalue를 평균화하고 Ledoit-Wolf diagonal variance로 재조합합니다. RMT threshold, variance source, noise/signal eigenvalue 수를 diagnostics와 locked split에 기록합니다.
  - `nested_blended_min_variance`는 Ledoit-Wolf minimum-variance와 inverse-volatility weight 사이 shrinkage를 완료된 252/63 inner OOS realized variance만으로 선택합니다. `train_window < 315`이면 research CLI가 실행을 거부합니다.
  - risk allocator research도 price SHA, 명시적 universe manifest SHA 또는 legacy ordered basket hash, 모든 실행 설정과 candidate family를 split manifest로 잠급니다. 낮은 변동성만으로 승격하지 않고 closest baseline 대비 Sharpe, drawdown, turnover와 paired block bootstrap를 함께 통과해야 합니다.
  - cross-validated covariance 후보는 outer rebalance의 train window 안에서만 252일 inner train/63일 validation walk-forward를 수행하고 realized portfolio variance로 estimator를 선택합니다. 이 후보도 research-only이며 높은 turnover 또는 Sharpe 저하 시 승격하지 않습니다.
  - covariance forecast ensemble은 완료된 inner OOS window에서 relative Frobenius error, correlation RMSE, equal/inverse-vol portfolio log-variance calibration error를 측정합니다. estimator를 hard-select하지 않고 inverse-loss weight를 50% equal-weight prior로 shrink해 결합합니다.
  - covariance stress 진단은 PSD를 보존하는 correlation-to-one shock와 volatility shock에서 portfolio volatility amplification, effective asset count, maximum weight를 기록합니다.
  - covariance ensemble research는 최소 252일 inner train과 63일 completed validation을 확보하도록 outer `train_window >= 315`를 요구합니다. inner fold가 없는 fallback 결과를 후보 성능으로 승격하지 않습니다.
  - `tools/build_fama_french_industry_panel.py`는 공식 French 49-industry daily archive의 value-weighted section만 decimal return으로 파싱하고 누적 price index, 원본/파생 SHA, ordered industry basket hash를 생성합니다.
  - robust covariance는 spectral PSD repair와 eigenvalue condition/effective-rank 진단을 기록합니다. long-only asset cap은 capped simplex projection으로 합계 1과 cap을 동시에 만족해야 합니다.
  - risk candidate는 research split에서 equal weight를 통과한 뒤 단일 specification을 freeze합니다. 4-case validation에서는 가장 가까운 Ledoit-Wolf minimum-variance baseline보다 volatility, Sharpe, max drawdown을 모두 개선해야 하며 탈락 후보를 같은 validation 결과에 맞춰 재튜닝하지 않습니다.
  - portfolio risk metric은 annual volatility와 Sharpe 외에 downside deviation, Sortino, Calmar, Omega, daily 95% VaR/CVaR를 함께 기록합니다.
  - predicted/realized period volatility, forecast bias/MAE/ratio를 OOS로 기록하고 paired circular block bootstrap의 volatility/Sharpe improvement probability가 각각 95% 이상이어야 합니다.
  - 여러 candidate를 같은 research split에서 비교하면 Holm-Bonferroni correction으로 family-wise error를 제어합니다.
  - historical price/FX alignment는 forward-fill만 허용하며 미래 첫 관측값을 leading missing period에 backward-fill하지 않습니다.
  - forecast 실패는 임의 양의 expected return을 주입하지 않고 explicit no-view와 maximum uncertainty로 prior-only 처리합니다.
  - historical backtest에서 static market cap은 as-of date가 없으면 사용하지 않습니다. historical market-cap 모델은 date-indexed point-in-time snapshot만 사용합니다.
  - max-Sharpe에 L2/turnover penalty가 있으면 변환된 단일 max-Sharpe 문제에 objective를 직접 붙이지 않고 convex efficient-return target grid를 비교합니다.
  - optimizer 응답의 return/risk/Sharpe는 threshold와 turnover control 이후 실제 반환 weight 기준으로 계산합니다.
  - backtest 최초 현금 배치는 rebalance band/turnover cap을 적용하지 않되 transaction cost는 부과합니다.
  - 부분 위험노출 research model의 잔여 현금은 signal date에 이용 가능한 historical daily risk-free return으로 적립하며, risk forecast는 실제 위험자산 노출을 사용합니다.

API 변경 규칙:

- 기존 프론트엔드 요청 shape를 깨는 변경은 frontend와 tests를 함께 수정합니다.
- 새 endpoint는 입력 예시, 실패 케이스, 응답 shape를 코드 또는 문서에 남깁니다.
- CORS origin은 `ALLOWED_CORS_ORIGINS` 환경 변수를 우선하고 localhost 기본값을 유지합니다.

## F. Testing / Verification

일반 검증 명령:

```bash
npm run lint
npm test
npm run build
PYTHONPATH=src/backend python -m pytest tests
```

변경 범위별 기준:

- 프론트엔드 UI/상태/API client 변경: `npm run lint`, `npm test`, 필요 시 `npm run build`
- 백엔드 API/계산 로직 변경: `PYTHONPATH=src/backend python -m pytest tests`
- installer/tooling 변경: 관련 `tools/build-*.sh` 또는 `tools/installer.py --help` 경로 확인
- 문서만 변경: 링크, 파일명, TODO 인덱스, 예시 placeholder 제거 여부 확인

## G. Build / Distribution

- 개발 서버: frontend `npm run dev` on port 5173, backend `python src/backend/app.py` on port 5000
- CI: `.github/workflows/build-installer.yml`
- 프론트엔드 CI: `npm ci`, `npm run lint`, `npm test`, `npm run build`
- 백엔드 CI: Python 3.11, `requirements-ci.txt`, `python -m pytest tests`
- installer build: Linux/Windows/macOS matrix, PyInstaller, artifact upload, release creation
- 상세 빌드 문서: `tools/BUILD.md`
