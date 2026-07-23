# Adaptive Value-Investment-Momentum Research

- 일시: 2026-07-24 03:01 (KST)
- 작성자: Codex
- 에이전트: Codex
- 작업 유형: 알파 신호 연구
- 상태: 후보 폐기

## 요약

- value, conservative investment, 12-1 momentum의 weight를 완료된 과거 IC로만 보정하는 online calibration 후보를 구현했습니다.
- 후보 자체 predictiveness는 95% absolute gate를 통과했지만 raw momentum 대비 paired uplift는 통과하지 못했습니다.
- 후보를 폐기하고 validation을 열지 않습니다.

## 데이터

- source: Kenneth R. French Data Library
- official URL: `https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/25_Portfolios_BEME_INV_5x5_daily_CSV.zip`
- raw ZIP: 2,636,469 bytes, SHA-256 `01922719…d87179`
- construction: annually reconstituted independent 5×5 book-to-market/investment portfolios
- return weighting: value weighted
- price panel: 1963-07-01~1999-12-31, 9,192행 × 25 portfolios
- evaluation: 1968-07-11~1999-10-01, 125 completed 63-day periods
- price SHA-256: `fa2eeaf5…9955f3`
- split manifest SHA-256: `212e853c…150d0b`
- 2000+ data는 열지 않았습니다.

## 후보

- baseline: raw 12-1 momentum rank
- factor prior:
  - 12-1 momentum: 50%
  - book-to-market value: 25%
  - conservative investment: 25%
- outer train window: 1,260 trading days
- calibration: training window 안의 completed 63-day targets 최대 12개
- empirical IC weight: nonnegative only
- posterior: fixed prior 75% + empirical weight 25%
- component cap: 60%
- horizon/step: 63/63 trading days
- bootstrap: 2,000회, 4-period circular blocks, 95% threshold

## 결과

| Signal | Mean rank IC | Positive IC | Mean top-bottom | P(IC>0) | P(spread>0) |
|---|---:|---:|---:|---:|---:|
| Adaptive value-investment-momentum | 0.0698 | 59.20% | 0.01177 | 99.40% | 99.85% |
| Raw 12-1 momentum | 0.0627 | 63.20% | 0.00831 | 99.05% | 98.40% |

- candidate minus baseline IC: `0.00705`
- candidate minus baseline spread: `0.00346`
- P(candidate higher IC): `64.00%`
- P(candidate higher spread): `87.40%`
- paired Holm-adjusted p-value: `0.3600`
- candidate gate: passed
- paired improvement gate: rejected
- promotion eligible: false

## Weight 진단

- 평균 momentum weight: `46.11%`
- 평균 value weight: `27.90%`
- 평균 conservative-investment weight: `26.00%`
- 전체 observed component weight 범위: `18.75%~52.50%`
- 60% cap 위반: 없음

## 결정

- adaptive value-investment-momentum 후보를 폐기합니다.
- 같은 split에서 prior, shrinkage, component cap, calibration history를 재튜닝하지 않습니다.
- validation과 holdout을 실행하지 않습니다.
- Transformer HPO 근거로 사용하지 않습니다.

## 검증

- future price/factor row mutation no-lookahead test: passed
- existing value-quality artifact exact reproduction: passed
- locked split normalization and weight-history diagnostics: passed

## 주요 변경 파일

- `src/backend/portfolio_signals.py`
- `tools/research_profitability_momentum.py`
- `tests/test_portfolio_backtest.py`
- `tests/test_research_profitability_momentum.py`
- `data/research/derived/fama_french_25_value_investment_prices_1963_1999.*`
- `data/research/derived/fama_french_25_adaptive_value_investment_momentum_research_*`
