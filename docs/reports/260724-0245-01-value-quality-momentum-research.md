# Value-Quality-Momentum Research

- 일시: 2026-07-24 02:45 (KST)
- 작성자: Codex
- 에이전트: Codex
- 작업 유형: 알파 신호 연구
- 상태: research 통과, 후보 동결

## 요약

- book-to-market value와 operating profitability를 raw 12-1 momentum에 결합한 고정 신호를 시험했습니다.
- candidate 자체, baseline 대비 paired improvement, Holm gate를 모두 통과했습니다.
- 후보를 동결하고 untouched validation 전 사양을 변경하지 않습니다.

## 데이터

- source: Kenneth R. French Data Library
- official URL: `https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/25_Portfolios_BEME_OP_5x5_daily_CSV.zip`
- raw ZIP: 2,652,562 bytes, SHA-256 `2a8608e3…ba2a62`
- construction: annually reconstituted independent 5×5 book-to-market/operating-profitability portfolios
- return weighting: value weighted
- price panel: 1963-07-01~1999-12-31, 9,192행 × 25 portfolios
- evaluation: 1965-07-02~1999-10-01, 137 completed 63-day periods
- price SHA-256: `41c451a6…213b4d`
- split manifest SHA-256: `bfedfb02…c73be8`
- 2000+ data는 연구 결과 확인 전에 열지 않았습니다.

## Frozen 후보

- baseline: raw 12-1 cross-sectional momentum rank
- candidate weights:
  - raw 12-1 momentum rank: 50%
  - official annual book-to-market quintile: 25%
  - official annual operating-profitability quintile: 25%
- momentum lookback/skip: 252/21 trading days
- horizon/step: 63/63 trading days
- statistics: circular block bootstrap 2,000회, 4-period block, 95% threshold

## 결과

| Signal | Mean rank IC | Positive IC | Mean top-bottom | P(IC>0) | P(spread>0) |
|---|---:|---:|---:|---:|---:|
| Value + quality + momentum | 0.1238 | 63.50% | 0.02047 | 100.00% | 100.00% |
| Raw 12-1 momentum | 0.0780 | 58.39% | 0.01408 | 99.95% | 99.80% |

- candidate minus baseline IC: `0.04581`
- candidate minus baseline spread: `0.00639`
- P(candidate higher IC): `98.20%`
- P(candidate higher spread): `95.75%`
- paired Holm-adjusted p-value: `0.0425`
- candidate gate: passed
- paired improvement gate: passed
- promotion eligible: true

## 결정

- value-quality-momentum 후보를 freeze합니다.
- momentum/value/profitability weight, lookback, skip, horizon을 validation 결과에 맞춰 변경하지 않습니다.
- 다음 단계는 untouched 2000~2011 full-universe 통계 gate와 low/high value, low/high profitability 4-case validation입니다.
- validation 통과 전 2012+ holdout을 열지 않습니다.

## 검증

- 기존 quality mode artifact exact reproduction: passed
- locked split normalization and SHA validation: passed
- parser/weight freeze regression tests included

## 주요 변경 파일

- `tools/research_profitability_momentum.py`
- `tests/test_research_profitability_momentum.py`
- `data/research/derived/fama_french_25_value_profitability_prices_1963_1999.*`
- `data/research/derived/fama_french_25_value_quality_momentum_research_*`
