# Profitability-Momentum Research

- 일시: 2026-07-24 02:26 (KST)
- 작성자: Codex
- 에이전트: Codex
- 작업 유형: 알파 신호 연구
- 상태: 후보 폐기

## 요약

- official operating-profitability portfolio를 이용해 profitability rank와 12-1 momentum의 고정 결합을 시험했습니다.
- 후보 자체의 IC와 spread는 통계적으로 양수였지만 raw momentum baseline보다 개선되지 않았습니다.
- 후보를 폐기하고 validation을 열지 않습니다.

## 데이터

- source: Kenneth R. French Data Library
- official URL: `https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/25_Portfolios_ME_OP_5x5_daily_CSV.zip`
- raw ZIP: 2,560,597 bytes, SHA-256 `a41d3376…74e8`
- construction: annually reconstituted independent 5×5 size/operating-profitability portfolios
- return weighting: value weighted
- price panel: 1963-07-01~1999-12-31, 9,192행 × 25 portfolios
- evaluation: 1965-07-02~1999-10-01, 137 completed 63-day periods
- price SHA-256: `8eeccf00…33874`
- split manifest SHA-256: `bfe4d470…df098`
- 2000+ data는 열지 않았습니다.

## 후보

- baseline: raw 12-1 cross-sectional momentum rank
- candidate: 50% raw 12-1 momentum rank + 50% official annual OP quintile rank
- momentum lookback/skip: 252/21 trading days
- horizon/step: 63/63 trading days
- statistics: circular block bootstrap 2,000회, 4-period block, 95% threshold
- blend와 기간은 결과 확인 전에 locked manifest로 고정했습니다.

## 결과

| Signal | Mean rank IC | Positive IC | Mean top-bottom | P(IC>0) | P(spread>0) |
|---|---:|---:|---:|---:|---:|
| Profitability + momentum | 0.0951 | 63.50% | 0.01221 | 99.90% | 100.00% |
| Raw 12-1 momentum | 0.1177 | 62.04% | 0.01257 | 99.90% | 99.60% |

- candidate minus baseline IC: `-0.02258`
- candidate minus baseline spread: `-0.00036`
- P(candidate higher IC): `22.40%`
- P(candidate higher spread): `45.05%`
- paired Holm-adjusted p-value: `0.7760`
- candidate individual gate: passed
- paired improvement gate: rejected
- promotion eligible: false

## 결정

- profitability-momentum 후보를 폐기합니다.
- 같은 1965~1999 split에서 blend weight, momentum lookback/skip, horizon을 재튜닝하지 않습니다.
- portfolio construction과 validation을 실행하지 않습니다.
- 이 결과는 Transformer hyperparameter 확대 근거가 아닙니다.

## 검증

- profitability blend/no-lookahead focused test: `1 passed`
- result JSON/Markdown and locked split generated successfully

## 주요 변경 파일

- `src/backend/portfolio_signals.py`
- `tools/research_profitability_momentum.py`
- `tests/test_portfolio_backtest.py`
- `data/research/derived/fama_french_25_size_profitability_*`
