# Nested Clustered Minimum-Variance Research

- 작업 일시: 2026-07-24 06:23 (KST)
- 상태: locked research 탈락
- split: `fama-french-38-source-30-complete-nco-research-1929-1969-v1`
- namespace: `allocator-v2-nested-clustered-minvar-industry-portfolios`

## 목적

고차원 covariance matrix를 한 번에 최적화하는 plain minimum variance의 estimation error를 줄이기 위해 Nested Clustered Optimization이 current default와 강한 risk baselines를 개선하는지 검증했습니다.

## 고정 사양

- candidate: `nested_clustered_minimum_variance`
- statistical baselines: `min_variance`, `risk_parity`, `lightweight_bl`
- deterministic guards: `equal_weight`, `historical_bl`
- covariance/correlation: Ledoit-Wolf constant-variance shrinkage
- distance: `sqrt((1-correlation)/2)`
- linkage: average
- cluster count: training data에서 `2..min(10,n-1)` silhouette 최대, 동률이면 작은 수
- intra-cluster allocator: long-only minimum variance
- inter-cluster allocator: long-only minimum variance
- expected return/forecast model: 사용하지 않음
- 504일 train, 63일 horizon/rebalance, 10bp cost
- 20% asset cap, 2% rebalance band, 35% turnover cap
- 21일 circular block bootstrap 2,000회
- 세 baseline의 lower-volatility/higher-Sharpe 6개 가설에 95% gate와 Holm correction

## 데이터

- source: Kenneth R. French Data Library 38 Industry Portfolios Daily
- raw archive: 기존 로컬 공식 ZIP 재사용, 외부 다운로드 없음
- source portfolios: 38개
- exact-name exclusions: `Agric`, `Wood`, `TV`, `Garbg`, `Steam`, `Water`, `Govt`, `Other`
- exclusions reason: requested research interval의 결측 존재
- complete portfolios: 30개
- price panel: 1928-01-03~1969-12-31, 11,579행
- evaluation: 1929-09-14~1969-12-31
- risk-free: same-date official French daily one-month Treasury-bill return
- split manifest digest: `0f8a7fc8…0362ae`
- price, factor, provenance, ordered basket, manifest SHA 검증 통과

## 결과

| Model | CAGR | Volatility | Sharpe | Max DD | Turnover |
|---|---:|---:|---:|---:|---:|
| Equal weight | 7.67% | 16.24% | 0.4525 | -81.32% | 1.16% |
| Historical BL | 7.95% | 17.52% | 0.4467 | -83.68% | 1.29% |
| Minimum variance | 7.99% | 11.83% | 0.5933 | -78.10% | 10.17% |
| Risk parity | 7.72% | 14.57% | 0.4900 | -78.65% | 1.70% |
| Lightweight BL | 8.66% | 17.35% | 0.4870 | -81.76% | 13.18% |
| NCO minimum variance | 7.62% | 11.76% | 0.5671 | -78.95% | 13.65% |

| Baseline | P(lower vol) | P(higher Sharpe) |
|---|---:|---:|
| Minimum variance | 86.65% | 13.90% |
| Risk parity | 100.00% | 85.00% |
| Lightweight BL | 100.00% | 84.55% |

- deterministic gate: rejected
- minvar lower-volatility Holm-adjusted p-value: `0.5340`
- minvar higher-Sharpe Holm-adjusted p-value: `0.8610`
- six-hypothesis statistical gate: rejected
- promotion eligible: false

## Cluster diagnostics

- rebalance records: `176`
- optimizer success rate: `100%`
- fallback rate: `0%`
- selected cluster count: 모든 rebalance에서 `2`
- mean selected silhouette: `0.2155`
- mean pre-cap maximum weight: `49.05%`
- mean final-cap projection L1 distance: `67.54%`
- 첫 partition은 `Cnstr`, 마지막 partition은 `Phone`을 나머지 산업과 분리한 singleton cluster였습니다.

## 결정

- Clustering은 volatility를 minvar보다 `0.07%p` 낮췄지만 return efficiency와 drawdown을 악화시켰습니다.
- Silhouette partition과 unconstrained cluster-level allocation이 20% asset cap과 크게 충돌해 NCO hierarchy 상당 부분이 final projection에서 변형됐습니다.
- NCO를 production/default allocator로 승격하지 않습니다.
- 같은 split에서 cluster count, linkage, covariance estimator, cap을 변경하지 않습니다.
- Validation과 locked holdout을 열지 않습니다.
- 구현은 비교 가능한 research-only allocator로 유지합니다.

## 구현 및 검증

- `src/backend/portfolio_risk_models.py`
- `src/backend/portfolio_backtest.py`
- `tools/research_minvar_promotion.py`
- `tests/test_portfolio_risk_models.py`
- `tests/test_research_minvar_promotion.py`
- result:
  `data/research/derived/fama_french_30_industry_nco_research_result_v1.json`
