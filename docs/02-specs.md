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
- 포트폴리오 최적화는 입력 데이터 길이, 결측치, 상장 기간 부족, 무효 weight를 방어해야 합니다.
- Black-Litterman, MPT, forecast 기반 expected return은 모델 가정과 fallback 경로를 테스트 또는 문서로 남깁니다.
- forecast 모델을 optimizer 기본값으로 승격하기 전에는 walk-forward 포트폴리오 backtest에서 equal weight, minimum variance, historical MPT/BL baseline과 거래비용 반영 성과를 비교합니다.

## E. API Surface

주요 endpoint와 책임:

- `GET /api/get-data`: ticker price, regression, future prediction, currency metadata
- `GET /api/analyze-hedge`: 두 ticker의 pairs/correlation/regression 분석. 단정적인 hedge 성립 여부를 반환하지 않고, 상관계수, p-value, 회귀 alpha/beta/R-squared, 관측치 수, 비단정적 correlation signal을 반환합니다.
- `GET /api/financial-statement`: 기본 요청은 재무 지표 대시보드, Finviz/yfinance benchmark 비교, 규칙 기반 투자 신호, 전체 재무제표 묶음을 조회하고, `type=income|balance|cash` 요청은 기존 단일 표 조회를 유지
- `POST /api/optimize-portfolio`: 포트폴리오 최적화 job 시작. 같은 `request_id` 재요청은 기존 job 상태를 반환합니다.
- `GET /api/optimization-jobs/<request_id>`: 최적화 job 상태, 진행률, 완료 결과 또는 오류 조회
- `POST /api/optimization-jobs/<request_id>/cancel`: 실행 중인 최적화 job 취소 요청
- `GET /api/progress-stream/<request_id>`: 최적화 진행률 SSE. 연결 시 현재 상태를 먼저 전송하고 이후 이벤트를 구독합니다.
- `GET /api/portfolio-results`: 저장된 최적화 결과 목록
- `GET /api/portfolio-results/<portfolio_id>`: 특정 최적화 결과 조회
- `POST /api/stock-screener`: ticker universe와 Financial Statement 대시보드의 0-100 종합 점수 기반 screening
- `POST /api/asset-names`: ticker display name 조회
- `POST /api/benchmark-portfolio`: 포트폴리오 benchmark 계산
- `POST /api/manage-portfolio`: 현 보유/현금 주입 기준 리밸런싱 주문 계산

Backend-only research tool:

- `tools/backtest_portfolio_models.py`: CSV, ticker list, ticker group을 입력받아 rolling rebalance backtest를 실행하고 `settings`, `models`, `summary_by_model`, `rebalance_records`, `promotion_decision`, `warnings` JSON을 저장합니다. v1은 public API나 UI를 추가하지 않습니다.

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
