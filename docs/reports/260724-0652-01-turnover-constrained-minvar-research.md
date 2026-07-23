# Exact Turnover-Constrained Minimum-Variance Research

- 작업 일시: 2026-07-24 06:52 (KST)
- 상태: locked research 탈락
- split: `fama-french-12-industry-turnover-constrained-research-2000-2011-v1`
- namespace: `allocator-v4-turnover-constrained-minvar-industry-portfolios`

## 목적

Unconstrained target를 만든 뒤 거래를 비례 축소하는 post-hoc 방식 대신 turnover를 optimizer 내부의 exact constraint로 반영해 realized net risk-adjusted performance를 개선하는지 검증했습니다.

## 고정 사양

- candidate: `turnover_constrained_minimum_variance`
- statistical baselines: `min_variance`, `risk_parity`, `lightweight_bl`
- deterministic guards: `equal_weight`, `historical_bl`
- covariance: Ledoit-Wolf constant-variance shrinkage
- objective: long-only global minimum variance
- exact constraint: `||w_t - prior_target||₁ ≤ 0.35`
- initial allocation: unconstrained minimum variance
- solver: CLARABEL convex quadratic program
- expected return/forecast model: 사용하지 않음
- 504일 train, 63일 horizon/rebalance, 10bp cost
- 20% asset cap, 2% execution band, 35% execution turnover cap
- 21일 circular block bootstrap 2,000회
- 세 baseline의 lower-volatility/higher-Sharpe 6개 가설에 95% gate와 Holm correction

## 엔진 변경

- Previous target를 rebalance별 순차 전달합니다.
- Candidate target의 L1 turnover를 convex optimization에서 직접 제한합니다.
- Target turnover setting을 precomputed rebalance-target signature에 포함합니다.
- Cached target와 실행 max-turnover가 다르면 backtest를 거부합니다.
- 기존 post-hoc control은 실제 drifted holdings와 band/cash 처리를 위해 그대로 유지합니다.

## 데이터

- source: Kenneth R. French Data Library 12 Industry Portfolios Daily
- price panel: 1998-01-02~2011-12-30, 3,523행 × 12 industries
- evaluation: 2000-01-03~2011-12-30
- risk-free: official FRED DGS3MO backward-asof daily equivalent
- raw archives: 기존 로컬 공식 파일 재사용, 외부 다운로드 없음
- split manifest digest: `b14ac3d7…1bbcd0`
- price, factor, provenance, ordered basket, manifest SHA 검증 통과

## 결과

| Model | CAGR | Volatility | Sharpe | Max DD | Turnover |
|---|---:|---:|---:|---:|---:|
| Equal weight | 4.29% | 20.23% | 0.1968 | -52.20% | 3.54% |
| Historical BL | 4.18% | 19.40% | 0.1914 | -49.99% | 2.84% |
| Minimum variance | 6.60% | 17.11% | 0.3265 | -42.77% | 11.44% |
| Risk parity | 4.79% | 19.44% | 0.2216 | -51.43% | 3.40% |
| Lightweight BL | 3.71% | 20.19% | 0.1695 | -52.98% | 5.81% |
| Turnover-constrained minvar | 6.60% | 17.09% | 0.3272 | -42.62% | 11.71% |

| Baseline | P(lower vol) | P(higher Sharpe) | Holm higher-Sharpe p |
|---|---:|---:|---:|
| Minimum variance | 100.00% | 60.25% | 0.3975 |
| Risk parity | 100.00% | 96.10% | 0.0780 |
| Lightweight BL | 100.00% | 98.05% | 0.0585 |

- deterministic gate: passed
- six-hypothesis statistical gate: rejected
- promotion eligible: false

## Constraint diagnostics

- rebalance records: `48`
- constrained records after initial allocation: `47`
- solver success rate: `100%`
- mean target L1 turnover: `11.15%`
- maximum target L1 turnover: `34.9994%`
- constraint binding rate: `2.13%`
- fallback rate: `0%`

## 결정

- Exact constraint와 cache identity는 엔진 correctness를 개선했습니다.
- 고정 35% limit는 이 universe에서 대부분 inactive였고 actual controlled turnover를 줄이지 못했습니다.
- Closest minvar 대비 Sharpe uplift도 통계적으로 없습니다.
- Candidate를 production/default로 승격하지 않습니다.
- 같은 split에서 10%/20% turnover limit를 사후 탐색하지 않습니다.
- Validation과 locked holdout을 열지 않습니다.
- 구현은 research-only execution-aware allocator로 유지합니다.

## 구현 및 결과

- `src/backend/portfolio_risk_models.py`
- `src/backend/portfolio_backtest.py`
- `tools/research_minvar_promotion.py`
- `tests/test_portfolio_risk_models.py`
- `tests/test_research_minvar_promotion.py`
- result:
  `data/research/derived/fama_french_12_industry_turnover_constrained_research_result_v1.json`
