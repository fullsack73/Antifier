# Fundamental Momentum Research

- 작업 일시: 2026-07-24 01:11 (KST)
- 상태: 후보 폐기
- split: `nasdaq100-fundamental-momentum-research-2018-2019-v1`
- namespace: `pit-factor-v6-fundamental-momentum-nasdaq100`

## 데이터

- historical Nasdaq-100 membership: 2016-2025 pinned manifest
- price panel: Yahoo Finance adjusted daily, 2015-2021, 1,762일 × 149 ticker
- SEC quarterly-TTM PIT: 로컬 `companyfacts/`, 2015-2019, 1,903행/104 completed ticker
- Yahoo가 제공하지 못한 delisted symbol 22개는 price provenance에 기록했습니다.
- evaluation은 2018-01-01~2019-09-30의 21개 monthly signal date만 사용했습니다. 2020+는 열지 않았습니다.

## 후보

- baseline: price + PIT fundamental level, nested ridge
- candidate: baseline + 최소 300일 이전 filing 대비 quality/profitability/valuation/liquidity 변화
- horizon 63일, penalty `[1, 5, 20, 100]`, completed inner time-fold 3개
- 미래 filing 변경이 과거 feature를 바꾸지 않는 회귀 테스트와 candidate-specific paired gate를 적용했습니다.

## 결과

| Model | Rank IC | Top-bottom | P(IC>0) | P(Spread>0) | Coverage |
|---|---:|---:|---:|---:|---:|
| baseline | 0.0681 | 0.02095 | 96.50% | 89.45% | 81.92% |
| fundamental momentum | 0.0461 | 0.00546 | 90.60% | 67.35% | 81.92% |

- candidate minus baseline: IC `-0.0220`, spread `-0.01549`
- paired P(higher IC): `12.35%`
- paired P(higher spread): `1.20%`
- candidate gate: rejected
- promotion eligible: false

## 결정

- fundamental-momentum 후보를 폐기합니다.
- 같은 구간 결과를 보고 lag, missing indicator, penalty를 다시 탐색하지 않습니다.
- Transformer hyperparameter 확대 근거로 사용하지 않습니다.
