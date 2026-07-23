# Frozen Value-Quality-Momentum Validation

- 일시: 2026-07-24 02:50 (KST)
- 작성자: Codex
- 에이전트: Codex
- 작업 유형: frozen 후보 검증
- 상태: validation 탈락

## 요약

- research에서 동결한 50/25/25 value-quality-momentum을 untouched 2000~2011에 변경 없이 적용했습니다.
- candidate 자체 absolute IC/spread gate는 통과했지만 baseline 대비 paired 95%와 4-case gate를 통과하지 못했습니다.
- 후보를 폐기하고 2012+ holdout을 열지 않습니다.

## 데이터와 잠금

- source: Kenneth R. French Data Library, 25 B/M × OP portfolios daily
- raw ZIP SHA-256: `2a8608e3…ba2a62`
- validation panel: 1998-01-02~2011-12-30, 3,523행 × 25 portfolios
- evaluation: 2000-01-04~2011-09-30, 47 completed 63-day periods
- price SHA-256: `72b56af7…b732a3`
- validation manifest SHA-256: `1c83c74c…47b6c7`
- frozen result SHA-256: `820c76bc…8d0be9`
- 2012+ data는 열지 않았습니다.

## Frozen 사양

- raw 12-1 momentum rank: 50%
- annual book-to-market quintile: 25%
- annual operating-profitability quintile: 25%
- lookback/skip: 252/21 trading days
- horizon/step: 63/63 trading days
- bootstrap: 2,000회, 4-period circular blocks, 95% threshold

## Aggregate 결과

| Signal | Mean rank IC | Positive IC | Mean top-bottom |
|---|---:|---:|---:|
| Value + quality + momentum | 0.1072 | 59.57% | 0.02801 |
| Raw 12-1 momentum | 0.0614 | 57.45% | 0.01557 |

- candidate minus baseline IC: `0.04577`
- candidate minus baseline spread: `0.01244`
- P(candidate IC>0): `98.35%`
- P(candidate spread>0): `99.80%`
- P(candidate higher IC): `93.85%`
- P(candidate higher spread): `94.20%`
- paired Holm-adjusted p-value: `0.0615`

## 4-case 결과

| Case | Candidate IC | Baseline IC | Candidate spread | Baseline spread | Gate |
|---|---:|---:|---:|---:|---|
| Low value | -0.0380 | -0.1028 | 0.00560 | -0.01800 | rejected |
| High value | 0.1607 | 0.1172 | 0.04435 | 0.03204 | passed |
| Low profitability | -0.0161 | -0.0368 | 0.00726 | -0.00336 | rejected |
| High profitability | 0.1376 | 0.1273 | 0.03628 | 0.01969 | passed |

## 결정

- aggregate paired gate와 4-case 전부 통과 조건을 충족하지 못해 validation을 탈락 처리합니다.
- 평균 성능과 absolute predictiveness는 개선됐지만 quant-standard 승격을 주장하지 않습니다.
- validation 결과로 weight, lookback, skip, horizon, case를 재튜닝하지 않습니다.
- 2012+ locked holdout을 실행하지 않습니다.

## 주요 변경 파일

- `tools/validate_frozen_quality_momentum.py`
- `tests/test_validate_frozen_quality_momentum.py`
- `data/research/derived/fama_french_25_value_profitability_prices_1998_2011.*`
- `data/research/derived/fama_french_25_value_quality_momentum_validation_*`
