# 1) 폴더 아키텍처

본 문서는 Antifier 저장소의 실제 폴더 구조와 책임을 정의합니다. 목표는 금융 분석 웹앱의 프론트엔드, Flask API, ML/포트폴리오 계산 로직, 테스트, 설치 도구, 에이전트 문서를 분명히 나누는 것입니다.

## A. Top-level 구조

```txt
antifier/
├─ AGENTS.md                         # 에이전트 공통 작업 규칙
├─ docs/                             # docs-driven 실행 컨텍스트
│  ├─ 01-folder-architecture.md
│  ├─ 02-specs.md
│  ├─ 03-product-plan.md
│  ├─ reports/
│  └─ todo/
├─ src/
│  ├─ backend/                       # Flask API, 금융 데이터, ML, 포트폴리오 로직
│  └─ frontend/                      # React/Vite SPA
├─ tests/                            # pytest와 Vitest/Testing Library 테스트
├─ tools/                            # 설치 프로그램, 빌드 스크립트, 분석/튜닝 도구
├─ .github/workflows/                # CI, installer build, release automation
├─ public/                           # Vite 정적 파일
├─ *.csv                             # 기본 ticker universe 데이터
├─ README.md / README.ko.md          # 사용자용 프로젝트 소개와 설치 안내
├─ requirements-pypi.txt             # 런타임 Python 의존성
├─ requirements-ci.txt               # CI용 경량 Python 테스트 의존성
├─ package.json / package-lock.json  # 프론트엔드 의존성 및 npm scripts
├─ vite.config.js                    # Vite dev server, proxy, test 설정
└─ eslint.config.js                  # 프론트엔드 lint 설정
```

생성물과 로컬 환경 폴더인 `node_modules/`, `.venv/`, `.cache/`, `.pytest_cache/`, `dist/`, `build/`, `__pycache__/`는 수동 편집 대상이 아닙니다. 빌드나 테스트 결과를 확인할 때만 읽습니다.

## B. docs 구조

```txt
docs/
├─ 01-folder-architecture.md         # 저장소 구조와 책임
├─ 02-specs.md                       # 기술 스택, API, 구현 규칙
├─ 03-product-plan.md                # 제품 범위, 사용자, 로드맵
├─ reports/
│  ├─ _template.md                   # 작업 기록 템플릿
│  └─ yymmdd-HHMM-NN-keyword.md      # 완료/결정 기록
└─ todo/
   ├─ 00-todo-list.md                # 후속 작업 단일 인덱스
   ├─ _template.md                   # TODO 템플릿
   └─ *.md                           # 개별 TODO 상세
```

`docs/todo/00-todo-list.md`가 TODO의 단일 발견 지점입니다. 루트 `TODO.md`는 호환용 안내 파일로만 유지합니다.

## C. 백엔드 구조

```txt
src/backend/
├─ app.py                            # Flask 앱, REST endpoint, request/response orchestration
├─ portfolio_optimization.py         # 데이터 수집, 예측 수익률, MPT/Black-Litterman 최적화
├─ portfolio_backtest.py             # walk-forward backtest, forecast cache/process pool, promotion gate
├─ portfolio_signals.py              # risk parity, momentum rank, confidence-gated GMV overlay helper
├─ portfolio_alpha_v2.py             # point-in-time factor 계약, factor-residual target, regularized alpha
├─ forecast_signal_research.py        # forecast 분포와 completed-OOS sequential confidence gate
├─ cross_sectional_forecast.py        # pooled linear/ranking/nonlinear walk-forward research
├─ pooled_patch_transformer.py        # research-only pooled Patch Transformer, Kronos context, direct-horizon gate
├─ portfolio_risk_models.py           # robust risk model과 conditional-volatility covariance 연구
├─ portfolio_statistics.py            # paired block bootstrap와 multiple-testing gate
├─ sec_point_in_time.py               # SEC filing-date 기준 PIT 재무 factor 생성
├─ research_split.py                   # split hash와 baseline/candidate 공통 실행 계약 검증
├─ universe_manifest.py               # 날짜별 universe membership와 생존편향 정책 검증
├─ forecast_models.py                # LSTM, LightGBM, ARIMA, Transformer 계열 모델
├─ lightweight_forecast.py           # 경량 통계 forecast fallback
├─ portfolio_benchmark.py            # 포트폴리오 벤치마크 계산
├─ hedge_analysis.py                 # pairs 상관/회귀 분석
├─ financial_statement.py            # 재무제표와 주요 ratio 조회
├─ stock_screener.py                 # universe 조회, Financial Statement 종합 점수 기반 필터 적용, screening
├─ ticker_lists.py                   # CSV 기반 ticker group 로딩
├─ cache_manager.py                  # multi-level cache 구현
├─ cache_init.py                     # cache 초기화 보조
└─ native_threading.py               # native/ML thread 제한과 worker cap
```

백엔드 책임 분리 규칙:

- `app.py`는 HTTP 요청 파싱, 입력 검증, endpoint 조합, 응답 shaping을 담당합니다.
- 계산 로직은 가능한 한 도메인 모듈에 둡니다.
- 외부 데이터 호출은 빈 데이터와 네트워크 실패를 정상적인 실패 경로로 취급합니다.
- portfolio optimization 경로는 진행률 callback/SSE 구조를 유지합니다.
- ticker, 날짜, 숫자 파라미터는 기존 normalize/parse/validate 함수를 우선 사용합니다.

주요 API endpoint:

- `GET /api/get-data`
- `GET /api/analyze-hedge`
- `GET /api/financial-statement`
- `GET /api/progress-stream/<request_id>`
- `POST /api/optimize-portfolio`
- `GET /api/portfolio-results`
- `GET /api/portfolio-results/<portfolio_id>`
- `POST /api/stock-screener`
- `POST /api/asset-names`
- `POST /api/benchmark-portfolio`
- `POST /api/manage-portfolio`

## D. 프론트엔드 구조

```txt
src/frontend/
├─ main.jsx                          # React root bootstrap
├─ App.jsx                           # view selection, top-level state, data fetch orchestration
├─ App.css                           # 전역 UI 스타일
├─ apiClient.js                      # API URL 생성, VITE_API_BASE_URL 처리
├─ config/
│  ├─ i18n.js                        # i18next 설정
│  └─ translationLoader.js           # locale loading
├─ locales/
│  ├─ en/translation.json
│  └─ ko/translation.json
├─ *Chart.jsx                        # Plotly 기반 차트 컴포넌트
├─ Optimizer.jsx                     # 포트폴리오 최적화 UI
├─ PortfolioBenchmark.jsx            # 벤치마크 UI
├─ PortfolioManager.jsx              # 보유 종목/리밸런싱 UI
├─ FinancialStatement.jsx            # 재무제표 UI
├─ StockScreener.jsx                 # 종목 스크리닝 UI
├─ Hedge.jsx                         # pairs/correlation 분석 UI
└─ *Input.jsx / *Selector.jsx        # 입력, 선택, 사이드바 컨트롤
```

프론트엔드 책임 분리 규칙:

- `App.jsx`는 현재처럼 최상위 view 선택과 stock analysis 기본 상태를 관리합니다.
- 기능별 UI는 독립 컴포넌트 파일에 유지합니다.
- API URL은 `apiClient.js`를 통해 생성합니다.
- chart 렌더링은 Plotly 래퍼 컴포넌트로 분리합니다.
- 신규 UI 문구는 영어/한국어 locale을 동시에 갱신합니다.
- 기존 CSS 기반 스타일 구조를 유지하고, 별도 UI 프레임워크를 도입하지 않습니다.

## E. 테스트와 도구

```txt
tests/
├─ conftest.py
├─ test_*.py                         # 백엔드 pytest
├─ *.test.js                         # 프론트엔드 Vitest
└─ ...

tools/
├─ installer.py                      # 대화형/비대화형 설치 orchestration
├─ installer.spec                    # PyInstaller spec
├─ build-macos.sh
├─ build-linux.sh
├─ build-windows.bat
├─ BUILD.md
├─ sanitize_requirements.py
├─ backtest_portfolio_models.py
├─ compare_forecast_models.py
├─ diagnose_forecast_signals.py       # persistent forecast cache 포화/tie/coverage 진단
├─ benchmark_kronos_forecasts.py       # pinned Kronos-small과 기존 ML rank signal 비교
├─ research_cross_sectional_forecasts.py # research-only pooled objective 비교
├─ research_pooled_patch_transformer.py # frozen origin 기반 Patch/ARIMA/Transformer signal과 GMV tilt 비교
├─ build_sec_pit_features.py          # SEC 공시일 기준 PIT factor/provenance 생성
├─ build_ticker_cik_map.py             # 제한된 ticker 집합의 Yahoo SEC metadata 기반 CIK map
├─ build_dow_universe_manifest.py       # pinned DJIA snapshot을 dated membership event로 변환
├─ build_nasdaq100_universe_manifest.py # pinned Nasdaq-100 change history를 dated membership event로 역복원
├─ build_nasdaq100_security_master.py   # SEC current/history CIK와 submissions SIC security master 생성
├─ download_sec_submissions.py          # security master issuer의 SEC submissions JSON 수집/검증
├─ build_historical_price_panel.py      # ticker alias와 SHA provenance를 갖는 historical price panel
├─ build_research_price_panel.py        # explicit research basket 가격과 SHA provenance 생성
├─ build_market_factor_panel.py         # French factors + FRED DGS3MO PIT-aligned panel
├─ research_risk_allocators.py        # research-only risk allocator 비교
├─ research_mean_shrinkage.py         # locked expected-return shrinkage 비교
├─ research_high_momentum.py          # 52-week-high/momentum signal gate
├─ research_raw_momentum.py           # raw momentum vs live-default gate
├─ research_risk_momentum_blend.py    # risk/momentum construction gate
├─ research_minvar_momentum_blend.py  # min-var/momentum construction gate
├─ research_online_reversal_ensemble.py # completed-feedback signal Hedge 연구
├─ validate_risk_allocator_candidate.py # frozen risk candidate 4-case validation
└─ tune_transformer_hpo.py
```

테스트는 변경 범위에 맞춰 선택적으로 실행하되, 공유 API나 포트폴리오 계산 로직을 건드리면 백엔드 테스트를 우선 실행합니다. 프론트엔드 렌더링/API client 변경은 lint, Vitest, build 중 최소 하나 이상으로 확인합니다.

## F. 레거시 에이전트 문서

이전 `agent-os/` 문서 아카이브는 더 이상 저장소에서 추적하지 않습니다. 새 작업의 기본 진입점은 `AGENTS.md`와 `docs/`이며, 과거 작업 기록은 `docs/reports/`, 후속 작업은 `docs/todo/`에서 관리합니다.
