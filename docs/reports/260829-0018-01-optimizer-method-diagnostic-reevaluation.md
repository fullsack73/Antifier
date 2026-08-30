# 기존 Optimizer 방법 재평가

- 일시: 2026-08-29 00:18 KST
- 범위: 기존 production/opt-in optimizer와 직접 risk comparator의 diagnostic reproduction
- 결론: production Ledoit-Wolf GMV의 risk-only 목적은 재확인했지만, 종합 성과 우위나 새로운 승격 근거는 확인하지 못함

## 사전 고정 범위

결과를 보기 전에 `optimizer_method_diagnostic_reevaluation_spec_v1.json`에 다음을 고정했습니다.

- 방법: `equal_weight`, `min_variance`, `historical_mpt`, `historical_bl`, `risk_parity`, `low_volatility`
- 설정: 504일 train, 63일 rebalance/forecast horizon, 10 bps 비용, 2% rebalance band, 35% turnover cap, 20% 종목 cap, 연 2% risk-free rate
- Endpoint: CAGR, 연율 변동성, Sharpe, max drawdown, controlled turnover, transaction cost, risk forecast MAE, concentration HHI
- 용도: diagnostic/reproduction only
- 금지: candidate 선택, validation, production 승격, calendar-forward 성과 주장

Momentum/forecast alpha와 experimental covariance/optimizer candidate는 이번 비교에 포함하지 않았습니다. Point-in-time market cap이 없으므로 `market_cap_weight`도 제외했습니다.

## 데이터

### Country ETF

- 15개 explicit ETF basket, 2007-01-03~2025-12-31
- Yahoo adjusted public price, complete panel
- 4,275개 OOS 일수익률, 68회 rebalance
- Public adjusted price이며 delisted-inclusive/vintage PIT 증거가 아님

### French 12 Industry

- 12개 value-weighted aggregate industry portfolio, 2019-01-02~2025-12-31
- 1,255개 OOS 일수익률, 20회 rebalance
- 이미 소비된 split임을 acknowledgement한 diagnostic reproduction
- 개별주 alpha나 실제 execution 증거가 아님

## 결과

### Country ETF

| 방법 | CAGR | 변동성 | Sharpe | Max DD | Controlled turnover | 비용 | Risk MAE | HHI |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Equal weight | 7.94% | 20.61% | 0.378 | -41.90% | 1.664 | 23.91 | 0.0835 | 0.0667 |
| **GMV** | 6.89% | **17.84%** | 0.352 | **-38.26%** | 9.941 | 180.24 | **0.0689** | 0.1799 |
| Historical MPT | 5.03% | 19.29% | 0.249 | -43.43% | 21.118 | 343.16 | 0.0753 | 0.1911 |
| Historical BL | 7.67% | 20.47% | 0.367 | -41.78% | **1.261** | **15.43** | 0.0833 | 0.0671 |
| Risk parity | 7.80% | 20.03% | 0.377 | -40.44% | 1.663 | 23.67 | 0.0815 | 0.0694 |
| Low volatility | 7.69% | 18.80% | **0.383** | -38.34% | 7.327 | 132.82 | 0.0775 | 0.0921 |

Country panel의 max-Sharpe 경로에서는 expected return이 risk-free rate를 넘지 못하거나 solver가 infeasible해 총 12회의 fallback warning이 발생했습니다. 최종 artifact는 동일 실행에서 결정적으로 재현됐지만, 이 불안정성은 MPT/BL 계열의 운영상 약점으로 남습니다.

### French 12 Industry

| 방법 | CAGR | 변동성 | Sharpe | Max DD | Controlled turnover | 비용 | Risk MAE | HHI |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Equal weight | **11.92%** | 15.90% | **0.664** | -19.47% | 1.609 | 18.25 | 0.0722 | **0.0833** |
| **GMV** | 3.43% | **13.19%** | 0.172 | -21.44% | 2.915 | 30.48 | **0.0581** | 0.1791 |
| Historical MPT | 5.13% | 17.39% | 0.261 | -27.90% | 7.040 | 74.08 | 0.0626 | 0.1876 |
| Historical BL | 10.69% | 16.18% | 0.586 | -20.17% | **1.128** | **11.43** | 0.0716 | 0.0844 |
| Risk parity | 9.46% | 14.81% | 0.551 | -20.19% | 1.310 | 13.83 | 0.0698 | 0.0886 |
| Low volatility | 7.17% | 13.70% | 0.429 | **-19.37%** | 2.831 | 31.33 | 0.0645 | 0.1162 |

## Paired block bootstrap

Production GMV를 각 비교법과 동일 일수익률에서 21일 circular block, 2,000 samples, seed 42로 비교했습니다.

| Panel | 비교법 | P(GMV lower vol) | P(GMV higher return) | P(GMV higher Sharpe) |
|---|---|---:|---:|---:|
| Country ETF | Equal weight | 100.00% | 10.35% | 32.95% |
| Country ETF | Historical MPT | 100.00% | 92.75% | 97.25% |
| Country ETF | Historical BL | 100.00% | 13.80% | 39.70% |
| Country ETF | Risk parity | 100.00% | 10.20% | 31.40% |
| Country ETF | Low volatility | 100.00% | 8.05% | 20.55% |
| French 12 | Equal weight | 100.00% | 0.15% | 0.75% |
| French 12 | Historical MPT | 100.00% | 25.45% | 32.10% |
| French 12 | Historical BL | 100.00% | 0.70% | 1.85% |
| French 12 | Risk parity | 100.00% | 0.10% | 0.25% |
| French 12 | Low volatility | 100.00% | 0.10% | 0.20% |

GMV의 변동성 차이 95% interval은 모든 panel/비교에서 0 아래였습니다. 그러나 Sharpe 우위 95%를 보인 것은 country ETF의 MPT 비교뿐이며 French panel에서는 GMV Sharpe가 모든 비교법보다 낮았습니다.

## 해석

- GMV는 두 panel에서 연율 변동성과 risk forecast MAE가 모두 가장 낮았습니다. `MIN_VARIANCE + RISK_ONLY`라는 production objective와 일치합니다.
- GMV는 수익률, Sharpe, drawdown, turnover, 비용과 concentration에서 일관된 우위가 없습니다. “가장 좋은 종합 성과 optimizer”라고 주장할 수 없습니다.
- Historical MPT는 두 panel 모두 높은 turnover/cost와 낮은 Sharpe를 보였고 country panel에서는 max-Sharpe fallback warning도 발생했습니다.
- Historical BL, equal weight와 risk parity는 수익률·Sharpe·회전율에서 더 나은 구간이 있었지만 항상 더 높은 변동성을 보였습니다.
- Low volatility는 GMV와 가장 가까운 위험 결과를 보이면서 Sharpe/drawdown이 나은 구간이 있었지만, 이번 결과는 consumed/public aggregate diagnostic이므로 candidate 선택이나 production 변경 근거가 아닙니다.

따라서 production GMV를 유지합니다. 이는 새 성과 검증이나 승격 결정이 아니라 기존 risk-only 선택의 diagnostic 재확인입니다.

## 검증 및 artifact

- 두 raw result를 같은 명령으로 재실행해 byte-for-byte 동일함을 확인했습니다.
- 528개 rebalance record에서 weight+cash, pre/post-cost wealth, turnover×cost rate, turnover cap 항등식 위반은 0건입니다.
- Evidence registry audit: consumed 8개, hash chain `ok`
- Spec SHA-256: `7c69595557c5849a7739b1eec098e69e7ec889da0c93ffca40e590e7657704bc`
- Country result SHA-256: `3bb3029ac973cffb3866cae015506085aec78d040dbc5f8455cc4e4c1ea927b2`
- French result SHA-256: `cf3e4f74985b93fe067fd76b29c8abbaa2bc21ed856e166b4c67e684f4efbcb7`
- Combined summary SHA-256: `d48172464bbc2114e910bec18f1accca81990a910eca6e7a300803206cf272ea`
- 실제 미래 calendar-forward observation은 사용하지 않았습니다.
