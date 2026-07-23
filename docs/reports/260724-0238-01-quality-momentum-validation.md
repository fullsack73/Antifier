# Frozen Quality-Momentum Validation

- 일시: 2026-07-24 02:38 (KST)
- 작성자: Codex
- 에이전트: Codex
- 작업 유형: frozen 후보 검증
- 상태: validation 탈락

## 요약

- research에서 동결한 50/25/25 quality-momentum을 untouched 2000~2011에 변경 없이 적용했습니다.
- 4개 deterministic case와 baseline 대비 paired statistical gate는 모두 통과했습니다.
- candidate 자체의 positive mean rank-IC 확률이 91.60%로 사전 95% 기준에 미달해 validation을 탈락 처리합니다.

## 데이터와 잠금

- source: Kenneth R. French Data Library, 25 OP × Investment portfolios daily
- raw ZIP SHA-256: `08c182a9…7f65c`
- validation panel: 1998-01-02~2011-12-30, 3,523행 × 25 portfolios
- evaluation: 2000-01-04~2011-09-30, 47 completed 63-day periods
- price SHA-256: `d5893b52…e6eace`
- validation manifest SHA-256: `01da860c…9ce66`
- frozen result SHA-256: `df7c5e9d…6e872`
- 2012+ data는 열지 않았습니다.

## Frozen 사양

- raw 12-1 momentum rank: 50%
- annual operating-profitability quintile: 25%
- inverse annual investment quintile: 25%
- lookback/skip: 252/21 trading days
- horizon/step: 63/63 trading days
- bootstrap: 2,000회, 4-period circular blocks, 95% threshold

## Aggregate 결과

| Signal | Mean rank IC | Positive IC | Mean top-bottom |
|---|---:|---:|---:|
| Quality + momentum | 0.0697 | 59.57% | 0.01644 |
| Raw 12-1 momentum | 0.0089 | 55.32% | 0.00155 |

- candidate minus baseline IC: `0.06078`
- candidate minus baseline spread: `0.01488`
- P(candidate higher IC): `98.50%`
- P(candidate higher spread): `99.90%`
- paired Holm-adjusted p-value: `0.0150`
- P(candidate IC>0): `91.60%`
- P(candidate spread>0): `97.55%`
- candidate IC 95% interval: `[-0.0340, 0.1717]`

## 4-case 결과

| Case | Candidate IC | Baseline IC | Candidate spread | Baseline spread | Gate |
|---|---:|---:|---:|---:|---|
| Low profitability | 0.0459 | -0.0182 | 0.01372 | 0.00068 | passed |
| High profitability | 0.0463 | 0.0205 | 0.01735 | 0.00746 | passed |
| Low investment | 0.0650 | -0.0262 | 0.00752 | -0.00507 | passed |
| High investment | 0.0679 | 0.0313 | 0.01761 | 0.01149 | passed |

## 결정

- 사전 선언한 aggregate absolute signal gate가 실패했으므로 validation을 탈락 처리합니다.
- baseline 대비 개선 증거와 4-case 안정성은 확인됐지만 quant-standard 승격을 주장하지 않습니다.
- validation 결과로 weight, lookback, skip, horizon, case를 재튜닝하지 않습니다.
- 2012+ locked holdout을 실행하지 않습니다.

## 주요 변경 파일

- `tools/validate_frozen_quality_momentum.py`
- `data/research/derived/fama_french_25_profitability_investment_prices_1998_2011.*`
- `data/research/derived/fama_french_25_quality_momentum_validation_*`
