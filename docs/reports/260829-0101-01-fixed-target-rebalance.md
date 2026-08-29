# Portfolio Manager 고정 목표 리밸런싱

- 일시: 2026-08-29 01:01 KST
- 작성자: Codex
- 작업 유형: frontend/backend 기능 추가, execution correctness, 문서

## 요약

- Portfolio Manager에 기존 `REOPTIMIZE`와 JSON `weights`를 사용하는 `FIXED_TARGET` 모드를 추가했습니다.
- 고정 목표 모드는 optimizer, covariance와 solver를 호출하지 않고 현재 보유 수량과 실행 시점 최신 USD 가격으로 주문 제안만 계산합니다.
- Production `MIN_VARIANCE + RISK_ONLY` Ledoit-Wolf GMV와 연구/승격 정책은 변경하지 않았습니다.

## 계산 계약

- 서버가 ticker alias 충돌, finite/non-negative weight, 빈 weights와 합계 상한을 다시 검증합니다.
- 합계가 1 미만인 부분은 비용 전 목표 cash이며 canonical target SHA-256으로 imported target을 식별합니다.
- Imported JSON의 과거 holdings, prices, buy/sell list는 현재 상태에 적용하지 않습니다.
- 필수 최신 가격 coverage가 100%가 아니면 부분 주문을 만들지 않습니다.
- Gross turnover는 `Σ|executed value - current value| / total target value`이며 매수와 매도를 모두 합산합니다.
- 요청 목표와 비용 후 실행 wealth 회계를 별도로 반환합니다.

## 주요 변경 파일

- `src/backend/app.py`, `src/backend/portfolio_optimization.py`
- `src/frontend/PortfolioManager.jsx`, `src/frontend/portfolioManagerExports.js`
- Portfolio Manager backend/frontend tests와 영어/한국어 locale

## 검증

- Portfolio management targeted backend: `49 passed`
- 전체 backend: `428 passed in 97.87s`
- 전체 frontend: `26 passed`
- `npm run lint`: 통과
- `npm run build`: 통과, 기존 Plotly large-chunk warning만 유지
- `git diff --check`, Python compile: 통과
- Flask fixture smoke: 기존/default mode와 optimizer 미호출 fixed-target mode 통과
- In-app browser smoke: mode 전환, JSON import/요약, holdings 분리, disabled state, reoptimize 복귀와 console error 없음 확인

## 제한 및 비범위

- 별도 기존 현금 잔액 입력은 지원하지 않습니다. `cash_injection`만 새 외부 자금입니다.
- 가격은 yfinance adjusted close와 기존 USD 변환 정책을 사용하므로 provider 지연/실패 가능성이 있습니다.
- 실제 주문, broker 연동, 미래 성과 검증과 production 자동 승격은 수행하지 않습니다.
