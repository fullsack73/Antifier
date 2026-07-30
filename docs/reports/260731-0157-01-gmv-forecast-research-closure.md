# GMV Forecast Research Closure

- 작업 일시: 2026-07-31 01:57 KST
- 범위: conditional-risk forecast, cross-sectional forecast, confidence gate, GMV alpha overlay, 공통 validation 계약
- 결정: 두 research 후보를 폐기하고 production Ledoit-Wolf GMV를 유지

## 구현

- `forecast_signal_research.py`
  - 현재 signal date 전에 outcome이 완료된 OOS record만 읽는 deterministic confidence gate
  - coverage, sample count, uncertainty, saturation, tie, rank IC reason code
  - 실패 시 `active=false`, `strength=0`
- `portfolio_signals.py`
  - fixed rank sleeve를 사용하는 confidence-gated GMV overlay
  - gate 실패 또는 invalid signal의 exact-GMV fallback
- `portfolio_risk_models.py`
  - 21일 연율 실현 변동성 history와 기존 ARIMA+Transformer forecast adapter
  - `D_forecast @ R_ledoit_wolf @ D_forecast` conditional covariance
  - 종목별 invalid forecast의 Ledoit-Wolf historical-volatility fallback
  - PSD repair, covariance diagnostics, capped minimum-variance weight
- `portfolio_backtest.py`, `tools/research_risk_allocators.py`
  - conditional-volatility research model과 closest GMV baseline
  - experiment namespace가 있는 SQLite cache
  - cache miss만 기존 spawn process pool에서 병렬 계산
- `research_split.py`
  - universe, rebalance, horizon, cap, turnover, cost, risk-free 조건의 baseline/candidate 동일성 검사

Production `MIN_VARIANCE` 경로와 기본 모델은 변경하지 않았다.

## Fresh cross-sectional research

- 자료: Kenneth French 12 Industry Portfolios, 2019-01-02~2025-12-31
- 가격 SHA-256: `26d3efcbd6711e072d3ba89959dea45aa92d122f7c92808479e66594d33a392d`
- universe manifest: `409362fc5d4e9cd778d93684172cf5b36bd9323518090d3bc8d12d1c131e343f`
- locked split digest: `87ee1e67fc675dce7c43277727ee571d2ca7cd6f8c619f0ea5e89cf685c4093f`
- OOS period: 14

| Objective | Mean rank IC | Positive IC rate | Mean spread | 판정 |
|---|---:|---:|---:|---|
| `relative_ridge` | 0.0480 | 50.00% | 0.0157 | signal gate 탈락 |
| `relative_nested_ridge` | 0.0654 | 57.14% | 0.0174 | signal gate 탈락 |

Nested ridge의 closest-baseline paired uplift도 탈락했다.

- P(higher IC): 72.25%
- P(higher spread): 60.10%
- 요구 기준: 각 95%

따라서 사전 등록 stop rule에 따라 Transformer joint extension을 실행하지 않았다. Delisted-inclusive PIT security identity가 없는 상태에서 개별주 factor-residual 승격을 주장하지 않는다.

Artifacts:

- `data/research/derived/fama_french_12_industry_forecast_research_split_v1.json`
- `data/research/derived/fama_french_12_industry_forecast_research_result_v1.json`
- result SHA-256: `6e895e7c51f2568f12edfd75c45d8da9d1f6b8ae31f57a1173974d6f29e65bc0`

## Fresh conditional-risk research

- 같은 12-industry price/universe lineage
- evaluation: 2020-12-31~2025-12-31
- 504일 training, 63일 rebalance, 20회 OOS rebalance
- transaction cost 10 bps, weight cap 20%, band 2%, turnover cap 35%
- DGS3MO daily-equivalent risk-free SHA-256: `015a593a033b3dab0662ef40017956acb85589ce2abd1d8014e4f16e550decd3`
- locked split digest: `b790d0b67b864c536542c1f8fb933144754c24637c411359b92450b7bc3e07f4`

| Metric | Plain GMV | Conditional volatility GMV |
|---|---:|---:|
| Annual volatility | 13.1933% | 13.2271% |
| Sharpe | 0.0731 | 0.2781 |
| Max drawdown | -21.4438% | -19.3437% |
| Net cumulative return | 18.2982% | 35.3891% |
| Avg controlled turnover | 14.5745% | 38.2118% |
| Risk forecast MAE | 5.8050% | 6.3001% |

Primary realized-volatility gate가 실패했다. P(lower volatility)는 35.85%였고 95% 기준과 Holm correction을 통과하지 못했다. Sharpe와 drawdown 개선만으로 risk 후보를 승격하지 않았다.

동일 SQLite cache 재실행 전후 result SHA-256은 모두 `f9b4112cf1cb0370e1ab6a86e2d64fb1ae7e78324780ed98c8e7268dcabe2fa1`이었다.

Artifacts:

- `data/research/derived/fama_french_12_industry_conditional_volatility_research_split_v1.json`
- `data/research/derived/fama_french_12_industry_conditional_volatility_research_result_v1.json`
- `data/research/derived/conditional_volatility_forecasts_v1.sqlite3`

## Confidence gate, overlay, validation decision

Cross-sectional signal이 research gate를 통과하지 못했으므로 confidence gate는 활성 후보를 만들지 않았다. 테스트에서 future outcome 제외, stable reason code, deterministic result와 정확한 zero contribution을 확인했다.

Overlay는 gate 실패 시 plain GMV와 정확히 동일하고 통과 입력에서만 fixed sleeve를 적용하도록 구현했다. upstream signal이 없으므로 portfolio validation candidate로 freeze하지 않았다.

Research 단계의 두 후보가 모두 탈락했으므로 validation과 locked holdout은 열지 않았다. 이는 실패 후보를 같은 split에 맞추지 않고 중단한다는 사전 계약의 결과다.

## 검증

- legacy research 회귀: 102 passed
- foundational forecast/GMV/risk suite: 168 passed
- cross-sectional suite: 31 passed
- conditional-risk focused suite: 54 passed
- portfolio backtest 및 risk research focused checks: passed
- deterministic cached research rerun: identical SHA-256
- backend 전체: 375 passed
- frontend: lint 통과, Vitest 15 passed, production build 통과

## TODO 처리

다음 TODO는 구현, fresh research 실행, 폐기/유지 결정까지 완료해 삭제했다.

- `portfolio-conditional-risk-forecast.md`
- `portfolio-cross-sectional-residual-forecast.md`
- `portfolio-forecast-confidence-gate.md`
- `portfolio-gmv-alpha-overlay.md`
- `portfolio-gmv-forecast-validation.md`
