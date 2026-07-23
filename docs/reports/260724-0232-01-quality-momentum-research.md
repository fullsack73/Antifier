# Quality-Momentum Research

- 일시: 2026-07-24 02:32 (KST)
- 작성자: Codex
- 에이전트: Codex
- 작업 유형: 알파 신호 연구
- 상태: research 통과, 후보 동결

## 요약

- operating profitability와 conservative investment를 raw 12-1 momentum에 결합한 고정 quality-momentum 신호를 시험했습니다.
- candidate 자체, baseline 대비 paired improvement, Holm familywise gate를 모두 통과했습니다.
- 후보 사양을 동결하고 untouched validation 전에는 변경하지 않습니다.

## 데이터

- source: Kenneth R. French Data Library
- official URL: `https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/25_Portfolios_OP_INV_5x5_daily_CSV.zip`
- raw ZIP: 2,654,513 bytes, SHA-256 `08c182a9…7f65c`
- construction: annually reconstituted independent 5×5 operating-profitability/investment portfolios
- return weighting: value weighted
- price panel: 1963-07-01~1999-12-31, 9,192행 × 25 portfolios
- evaluation: 1965-07-02~1999-10-01, 137 completed 63-day periods
- price SHA-256: `d8e7da2b…eeaa0`
- split manifest SHA-256: `7af92f60…fe150`
- 2000+ data는 연구 결과 확인 전에 열지 않았습니다.

## Frozen 후보

- baseline: raw 12-1 cross-sectional momentum rank
- candidate weights:
  - raw 12-1 momentum rank: 50%
  - official annual operating-profitability quintile: 25%
  - inverse official annual investment quintile: 25%
- momentum lookback/skip: 252/21 trading days
- horizon/step: 63/63 trading days
- statistics: circular block bootstrap 2,000회, 4-period block, 95% threshold

## 결과

| Signal | Mean rank IC | Positive IC | Mean top-bottom | P(IC>0) | P(spread>0) |
|---|---:|---:|---:|---:|---:|
| Quality + momentum | 0.1085 | 61.31% | 0.01303 | 99.95% | 99.85% |
| Raw 12-1 momentum | 0.0668 | 58.39% | 0.00697 | 99.65% | 98.10% |

- candidate minus baseline IC: `0.04166`
- candidate minus baseline spread: `0.00606`
- P(candidate higher IC): `97.95%`
- P(candidate higher spread): `98.55%`
- paired Holm-adjusted p-value: `0.0205`
- candidate gate: passed
- paired improvement gate: passed
- promotion eligible: true

## 결정

- quality-momentum 후보를 freeze합니다.
- momentum/OP/investment weight, lookback, skip, horizon을 validation 결과에 맞춰 변경하지 않습니다.
- 다음 단계는 untouched 2000~2011 full-universe 통계 gate와 low/high OP, low/high investment 4-case validation입니다.
- validation 통과 전 2012+ holdout을 열지 않습니다.

## 검증

- 기존 profitability-only mode artifact exact reproduction: passed
- locked split normalization and SHA validation: passed
- research result JSON/Markdown generated successfully

## 주요 변경 파일

- `tools/research_profitability_momentum.py`
- `data/research/derived/fama_french_25_profitability_investment_prices_1963_1999.*`
- `data/research/derived/fama_french_25_quality_momentum_research_*`
