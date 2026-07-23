# Maximum-Diversification Research

- 일시: 2026-07-24 02:17 (KST)
- 작성자: Codex
- 에이전트: Codex
- 작업 유형: 리스크 모델 연구
- 상태: 후보 폐기

## 요약

- maximum-diversification allocator를 구현하고 새 official French 25 size×value research split에서 risk parity와 비교했습니다.
- 변동성 감소는 통계적으로 명확했지만 Sharpe 개선은 95% gate와 Holm correction을 통과하지 못했습니다.
- 후보를 폐기하고 validation 및 기본 allocator 변경을 하지 않습니다.

## 데이터

- source: Kenneth R. French Data Library, 25 Size × Book-to-Market Portfolios Daily
- official ZIP: 4,028,823 bytes, SHA-256 `c0127a35…eb2b89`
- portfolios: annually reconstituted independent 5×5 size/book-to-market, value weighted
- price panel: 1969-01-02~1999-12-31, 7,832행 × 25 portfolios
- evaluation: 1971-01-04~1999-12-31
- price SHA-256: `a56ebf6c…7591f`
- factor SHA-256: `fffb3740…823b5`
- risk-free: official French daily one-month Treasury-bill return
- split manifest SHA-256: `5e9b8af9…11ea`

## 후보

- baseline: inverse-volatility risk parity
- covariance: Ledoit-Wolf
- objective: weighted standalone volatility / portfolio volatility 최대화
- constraints: long-only, weights sum to 1, asset cap 10%
- train/rebalance: 504/63 trading days
- transaction cost: 10 bps
- rebalance band/max turnover: 2%/35%
- statistics: paired circular block bootstrap 2,000회, 21일 block, 95% threshold

## 결과

| Metric | Risk parity | Maximum diversification |
|---|---:|---:|
| Annual volatility | 11.66% | 11.50% |
| Sharpe | 0.7188 | 0.7387 |
| Sortino | 0.9692 | 1.0024 |
| Max drawdown | -46.91% | -42.67% |
| Daily CVaR 95% | 1.7616% | 1.7145% |
| Avg controlled turnover | 1.29% | 11.73% |

- P(lower volatility): `99.95%`
- P(higher Sharpe): `75.55%`
- Sharpe difference 95% interval: `[-0.0326, 0.0756]`
- Holm-adjusted p-value: `0.2445`
- deterministic gate: passed
- statistical/familywise gate: rejected
- promotion eligible: false

## 결정

- maximum-diversification 후보를 폐기합니다.
- 기본 allocator는 변경하지 않습니다.
- 1971~1999 결과에 맞춘 covariance estimator, cap, lookback, rebalance frequency 재튜닝을 금지합니다.
- 후보가 research gate를 통과하지 못했으므로 validation split을 열지 않습니다.

## 검증

- focused unit/integration tests: `2 passed`
- result JSON/Markdown and locked split generated successfully

## 주요 변경 파일

- `src/backend/portfolio_risk_models.py`
- `src/backend/portfolio_backtest.py`
- `tools/research_risk_allocators.py`
- `tests/test_portfolio_risk_models.py`
- `data/research/derived/fama_french_25_size_value_max_diversification_research_*`

## 다음 작업

- 실패한 allocation family의 hyperparameter 조정보다 독립된 새 data/target/model family를 연구합니다.
- quant-standard 승격에는 새 frozen candidate의 4-case validation과 untouched holdout 통과가 계속 필요합니다.
