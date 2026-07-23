# Lightweight Rank-Tilt Research

- 일시: 2026-07-24 03:32 (KST)
- 작성자: Codex
- 에이전트: Codex
- 작업 유형: forecast signal / portfolio construction research
- 상태: 후보 폐기

## 요약

- existing lightweight forecast의 cross-sectional order만 사용하고 forecast magnitude는 완전히 제거했습니다.
- fixed 20% active-share rank tilt를 fresh industry universe에서 평가했습니다.
- signal IC, spread, portfolio Sharpe가 모두 gate를 실패했습니다.
- magnitude와 uncertainty가 아니라 lightweight point ordering 자체가 현재 병목입니다.

## 데이터

- source: Kenneth R. French Data Library
- official URL: `https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/38_Industry_Portfolios_daily_CSV.zip`
- raw ZIP: `3,204,389 bytes`
- raw SHA-256: `371ddb13…b2900`
- source portfolios: `38`
- explicit exclusions:
  - `Govt`: missing `2,135`, available `2,500` rows
  - `Steam`: missing `1,615`, available `3,020` rows
  - `Water`: missing `4,383`, available `252` rows
- selected complete universe: `35 portfolios`
- price panel: `1981-09-01~1999-12-31`, `4,635행 × 35 portfolios`
- price SHA-256: `3a45de79…1642`
- historical RF: official French daily one-month Treasury-bill return
- RF file SHA-256: `03a069ca…85b0`
- evaluation: `1983-08-29~1999-12-31`
- split manifest digest: `07d8e1cf…07723`
- physical split SHA-256: `803e51c9…494fe`
- `2000+` validation/holdout은 열지 않았습니다.

## 고정 후보

- candidate: `lightweight_rank_tilt`
- primary baseline: `lightweight_bl`
- statistical guard: `equal_weight`
- other deterministic guards: `risk_parity`, `historical_bl`
- point forecast: existing lightweight ensemble, unchanged
- magnitude policy: cross-sectional rank only
- allocator: equal-weight active-share tilt
- target active share: `20%`
- train window: `504 trading days`
- rebalance/horizon: `63/63 trading days`
- transaction cost: `10 bps`
- rebalance band / turnover cap: `2% / 35%`
- max asset weight: `20%`
- portfolio bootstrap: `2,000`, circular `21-day` blocks
- signal bootstrap: `2,000`, circular `4-period` blocks

## Signal 결과

- completed periods: `66`
- mean rank IC: `-0.01253`
- positive rank-IC rate: `43.94%`
- mean top-bottom spread: `-0.000341`
- P(positive mean rank IC): `26.10%`
- P(positive mean spread): `47.30%`
- signal gate: rejected

## Portfolio 결과

| Model | CAGR | Volatility | Sharpe | Max DD | Avg turnover |
|---|---:|---:|---:|---:|---:|
| Lightweight rank tilt | 14.37% | 13.34% | 0.6533 | -34.87% | 19.45% |
| Current lightweight BL | 14.20% | 12.68% | 0.6688 | -32.97% | 18.61% |
| Equal weight | 14.15% | 12.58% | 0.6698 | -34.27% | 2.02% |
| Risk parity | 14.22% | 12.41% | 0.6817 | -33.70% | 2.21% |
| Historical BL | 15.14% | 13.45% | 0.6993 | -35.43% | 1.97% |

- vs current lightweight P(higher return): `74.45%`
- vs current lightweight P(higher Sharpe): `28.40%`
- vs equal weight P(higher return): `75.35%`
- vs equal weight P(higher Sharpe): `28.80%`
- all four Holm-adjusted p-values: `0.9860~1.0000`
- portfolio gate: rejected
- promotion eligible: false

## 결정

- `lightweight_rank_tilt`을 폐기합니다.
- 같은 split에서 active share, horizon, rank mapping, transaction controls를 재튜닝하지 않습니다.
- validation과 holdout을 실행하지 않습니다.
- public default를 변경하지 않습니다.
- Transformer HPO 근거로 사용하지 않습니다.

## 검증

- future-row mutation and fixed-active-share test: passed
- explicit source-column exclusion provenance test: passed
- locked split normalization: passed
- focused backend tests: `53 passed`
