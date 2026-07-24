# Minimum-Variance Production Default

- 작업 일시: 2026-07-24 16:45 (KST)
- 목표: 제한된 데이터에서 포트폴리오 엔진을 퀀트 표준에 근접
- 결정: Ledoit-Wolf global minimum variance를 production 기본값으로 사용
- 범위: 기본 allocation policy 변경, full quant-standard alpha 승격 주장은 아님
- 커밋: 목표 완료 시 단일 커밋 예정

## 문제

Production은 `LIGHTWEIGHT + Black-Litterman + max-Sharpe`를 기본으로 사용했습니다. 그러나 locked research에서 lightweight forecast의 cross-sectional ordering과 여러 Transformer/feature 후보가 signal gate를 반복해서 통과하지 못했습니다.

Expected-return estimation이 검증되지 않은 상태에서 max-Sharpe를 기본으로 두면 작은 forecast 오차가 큰 weight 오차로 증폭됩니다. 제한 데이터에서는 추정해야 할 입력이 적고 검증 근거가 더 강한 risk-only allocation이 더 방어적인 기본값입니다.

## 근거

Official French 10-industry `2000~2011` locked research:

| Model | CAGR | Volatility | Sharpe | Max drawdown | Avg controlled turnover |
|---|---:|---:|---:|---:|---:|
| Previous lightweight/default | 4.01% | 20.00% | 0.1834 | -51.69% | 5.30% |
| Risk parity guard | 5.42% | 18.65% | 0.2551 | -48.34% | 3.99% |
| Ledoit-Wolf GMV | 6.61% | 17.34% | 0.3254 | -43.19% | 11.17% |

- Versus previous lightweight/default P(lower volatility/higher Sharpe): `100%/97.95%`
- Versus risk parity P(lower volatility/higher Sharpe): `100%/91.50%`
- Strict full promotion gate: rejected because the risk-parity Sharpe comparison was below 95%

Independent French 35-industry `2012~2017`:

- GMV Sharpe `1.2318`
- Previous lightweight/default Sharpe `1.2177`
- P(higher Sharpe) `52.05%`

Direction repeated but independent statistical confidence was weak. This supports a limited-data defensive default, not a universal superiority claim.

## Production policy

- Default `optimization_method`: `MIN_VARIANCE`
- Covariance: Ledoit-Wolf shrinkage
- Objective: long-only capped global minimum variance
- Return forecast: bypassed with effective method `RISK_ONLY`
- Expected-return role: historical diagnostic only, not optimization input
- Incompatible `target_return` and `risk_tolerance`: rejected
- Black-Litterman and classic MPT max-Sharpe: explicit opt-in
- Transformer and lightweight forecasts: retained for opt-in research/analysis

API responses and saved result metadata record:

- canonical optimization method
- requested and effective forecast method
- whether forecast was bypassed
- expected-return role
- exact solver objective

## Verification

- Focused backend production tests: `145 passed`
- Full backend regression: `351 passed`
- Full frontend regression: `14 passed`
- ESLint: passed
- Production build: passed
- `git diff --check`: passed

## Remaining limitation

This change reduces expected-return estimation risk and improves the default against the previous production baseline on one locked official panel. It does not provide licensed delisted-inclusive individual-stock evidence or prove a new alpha model through validation and locked holdout.
