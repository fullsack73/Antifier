# Constant-Correlation Minimum-Variance Research

- 작업 일시: 2026-07-24 06:36 (KST)
- 상태: locked research 탈락
- split: `fama-french-38-source-33-complete-constant-correlation-research-1971-1980-v1`
- namespace: `allocator-v3-constant-correlation-minvar-industry-portfolios`

## 목적

기존 Ledoit-Wolf constant-variance shrinkage보다 산업 자산의 공통상관 구조를 직접 반영하는 constant-correlation target이 OOS risk-adjusted performance를 개선하는지 검증했습니다.

## 고정 사양

- candidate: `constant_correlation_minimum_variance`
- statistical baselines: `min_variance`, `risk_parity`, `lightweight_bl`
- deterministic guards: `equal_weight`, `historical_bl`
- covariance: Ledoit-Wolf constant-correlation shrinkage
- objective: long-only global minimum variance
- expected return/forecast model: 사용하지 않음
- shrinkage target grid/HPO: 없음
- 504일 train, 63일 horizon/rebalance, 10bp cost
- 20% asset cap, 2% rebalance band, 35% turnover cap
- 21일 circular block bootstrap 2,000회
- 세 baseline의 lower-volatility/higher-Sharpe 6개 가설에 95% gate와 Holm correction

## 데이터

- source: Kenneth R. French Data Library 38 Industry Portfolios Daily
- raw archive: 기존 로컬 공식 ZIP 재사용, 외부 다운로드 없음
- exact-name exclusions: `Garbg`, `Steam`, `Water`, `Govt`, `Other`
- complete portfolios: 33개
- price panel: 1970-01-02~1980-12-31, 2,779행
- evaluation: 1971-12-29~1980-12-31
- risk-free: same-date official French daily one-month Treasury-bill return
- split manifest digest: `e7cf7a58…d4a8fbf`
- price, factor, provenance, ordered basket, manifest SHA 검증 통과

## 결과

| Model | CAGR | Volatility | Sharpe | Max DD | Turnover |
|---|---:|---:|---:|---:|---:|
| Equal weight | 8.96% | 12.71% | 0.2080 | -45.16% | 3.11% |
| Historical BL | 9.17% | 13.43% | 0.2180 | -47.28% | 3.28% |
| Minimum variance | 10.34% | 10.33% | 0.3514 | -34.65% | 19.03% |
| Risk parity | 8.86% | 12.17% | 0.2038 | -44.19% | 3.54% |
| Lightweight BL | 9.68% | 13.33% | 0.2535 | -44.32% | 18.68% |
| Constant-correlation minvar | 10.56% | 10.24% | 0.3729 | -34.59% | 20.06% |

| Baseline | P(lower vol) | P(higher Sharpe) |
|---|---:|---:|
| Minimum variance | 100.00% | 89.85% |
| Risk parity | 100.00% | 85.65% |
| Lightweight BL | 100.00% | 76.90% |

- deterministic gate: passed
- minvar higher-Sharpe Holm-adjusted p-value: `0.3045`
- six-hypothesis statistical gate: rejected
- promotion eligible: false

## Estimator diagnostics

- rebalance records: `37`
- estimator/optimizer success rate: `100%`
- mean shrinkage intensity: `9.10%`
- minimum/maximum shrinkage intensity: `5.45% / 16.65%`
- fallback rate: `0%`

## 결정

- Candidate는 모든 평균 portfolio 지표와 모든 baseline 대비 volatility를 개선했습니다.
- Sharpe 개선 확률과 familywise significance가 사전 기준에 미달했습니다.
- 평균 개선만으로 production/default allocator를 변경하지 않습니다.
- 같은 split에서 constant-variance, constant-correlation, single-factor target을 사후 비교하지 않습니다.
- Validation과 locked holdout을 열지 않습니다.
- 구현은 research-only comparison allocator로 유지합니다.
- Unchanged independent replication도 closest minvar 대비 P(higher Sharpe) `83.00%`로 탈락했습니다. 최종 결정은 폐기입니다.
- Replication 보고서: `docs/reports/260724-0643-01-constant-correlation-replication.md`

## 구현 및 검증

- `src/backend/portfolio_risk_models.py`
- `src/backend/portfolio_backtest.py`
- `tools/research_minvar_promotion.py`
- `tests/test_portfolio_risk_models.py`
- `tests/test_research_minvar_promotion.py`
- result:
  `data/research/derived/fama_french_33_industry_constant_correlation_research_result_v1.json`
