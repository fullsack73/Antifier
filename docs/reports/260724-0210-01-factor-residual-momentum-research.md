# Factor-Residual Momentum Research

- 작업 일시: 2026-07-24 02:10 (KST)
- 상태: 후보 폐기
- split: `fama-french-25-size-value-residual-momentum-research-1935-1970-v1`
- namespace: `alpha-v8-ff3-residual-momentum-size-value`

## 데이터

- source: Kenneth R. French Data Library, 25 Size × Book-to-Market Portfolios Daily
- official ZIP: 4,028,823 bytes, SHA-256 `c0127a35…eb2b89`
- portfolios: independent 5×5 size and book-to-market sorts, annually reconstituted
- derived price index: 1933-08-07~1971-03-11, 10,227행 × 25 portfolios
- research evaluation: 1935-04-16~1970-12-09, 154 completed 63-day periods
- 1933-08-04의 단일 `SMALL LoBM` 결측 이후부터 완전 패널을 시작했습니다.
- factors: official daily MKT-RF, SMB, HML, one-month T-bill RF

## 후보

- baseline: raw 12-1 cross-sectional momentum rank
- candidate: trailing 504 daily excess returns로 MKT/SMB/HML + intercept OLS
- signal: 최근 252일 중 최신 21일을 제외한 residual Sharpe rank
- horizon/step: 63일
- candidate 자체 IC/spread bootstrap 95%와 baseline 대비 paired 95%, Holm gate를 요구했습니다.
- factor set과 lookback은 결과 확인 전에 split manifest에 고정했습니다.

## 결과

| Signal | Mean rank IC | Positive IC | Mean top-bottom | P(IC>0) | P(spread>0) |
|---|---:|---:|---:|---:|---:|
| Raw 12-1 momentum | 0.0613 | 56.49% | 0.00704 | 97.60% | 94.20% |
| FF3 residual momentum | 0.0119 | 52.60% | -0.00080 | 73.70% | 37.25% |

- candidate minus baseline IC: `-0.0494`
- candidate minus baseline spread: `-0.00784`
- P(candidate higher IC): `5.40%`
- P(candidate higher spread): `5.65%`
- paired Holm-adjusted p-value: `0.9460`
- promotion eligible: false

## 결정

- factor-residual momentum 후보를 폐기합니다.
- 이 universe에서는 공통요인 제거가 유효한 raw momentum 정보를 제거했습니다.
- 같은 결과에 맞춘 factor set, beta window, residual window, skip 재튜닝을 금지합니다.
- portfolio construction과 validation을 실행하지 않습니다.
