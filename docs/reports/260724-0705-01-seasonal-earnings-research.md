# Seasonal Earnings Change Research

## 결정

- SEC 계절성 분기 이익변화는 데이터 coverage는 높았지만 예측력이 없었습니다.
- 50% seasonal earnings + 50% 12-1 momentum 후보를 폐기합니다.
- Transformer hyperparameter 또는 blend weight를 이 결과에 맞춰 조정하지 않습니다.
- 2020+ Nasdaq validation/holdout은 열지 않았습니다.

## 기능과 lineage

- 정의: `(현재 분기 순이익 - 전년 동분기 순이익) / 현재 자산`
- 방향: 높을수록 긍정적
- 가용일: SEC filing date
- feature set: `core-seasonal-earnings-change` opt-in
- 입력: 사용자 로컬 `companyfacts/`, 기존 Nasdaq-100 PIT membership,
  security master, 2015-2021 가격 panel
- 추가 SEC/가격 다운로드: 없음
- feature interval: 2015-01-09~2019-12-23
- rows/tickers: 1,903 / 104
- valid seasonal earnings rows: 1,797 (`94.43%`)
- feature SHA-256:
  `31e545fb16c83a302ef43e83ab359b60c7dc0b1bfbd82dd89b48d1823e1cf36e`

## 고정 exploratory split

- split: `nasdaq100-seasonal-earnings-research-2018-2019-v1`
- namespace: `alpha-v24-seasonal-earnings`
- evaluation: 2018-01-03~2019-09-05
- periods: 21 monthly origins, 63 trading-day forward horizon
- candidate: 50% 12-1 momentum + 50% seasonal earnings
- baseline: 12-1 momentum
- bootstrap: 4,000 samples, circular block size 3
- split digest:
  `ea53cdf4b94462f5a3c1a19f947f10c41d00c6b2dba0113fedd2c29b8365213a`

이 기간은 과거 fundamental-momentum 연구에서 사용됐으므로 fresh split이
아닙니다. 결과와 무관하게 promotion 불가로 사전 고정했습니다.

| Signal | Mean rank IC | Positive IC | Top-bottom spread |
|---|---:|---:|---:|
| Seasonal earnings + momentum | -0.0376 | 47.62% | -1.11% |
| Seasonal earnings diagnostic | -0.0569 | 52.38% | -2.02% |
| 12-1 momentum | 0.0109 | 47.62% | -0.75% |

Candidate minus baseline:

- delta rank IC: `-0.04849`
- delta spread: `-0.00363`
- P(higher rank IC): `9.10%`
- P(higher spread): `37.38%`
- candidate signal gate: rejected
- paired gate: rejected
- promotion eligible: false
- result SHA-256:
  `707b7bd9964d71f10a0eaaecd0cd7362495a155ce61e50c3c4569997eadde8b3`

## 외부 데이터 audit

더 넓은 fresh universe 가능성을 확인하려고 raw membership CSV 두 개만
다운로드했습니다. 가격 대량 다운로드는 하지 않았습니다.

- `fja05680/sp500`, pinned commit
  `c31ac3cc56f28cf9a02b4e694eff7ceab596a0ff`
  - 7,791,584 bytes
  - SHA-256:
    `bd2745939a709f316a74a550253d21f3fd5b72aa223e3a0137c790d2e54b7d5e`
  - 실제 범위 1996-01-02~2019-01-11
  - 구성 수 499~517로 변동
- `hanshof/sp500_constituents`, pinned commit
  `a91ef88fad5ace83bed1f3452f451247295bcd18`
  - 6,773,869 bytes
  - SHA-256:
    `02f37a12c11f82218fce422ecf7d95fae1074bd96e664c262a5ea42c120d5fe9`
  - 실제 범위 1996-01-02~2025-08-23
  - 2008-2018 구성 수 442~497로 불완전

2019-2021 구간의 상장폐지 표본 `ETFC`, `TIF`, `RTN`, `CELG`는 Yahoo
가격이 4/4 실패했고 Stooq는 anti-bot challenge만 반환했습니다. 이 상태로
현재 생존 종목 가격만 사용하면 survivorship bias가 생기므로 565종목 가격
다운로드를 중단했습니다. 두 CSV는 git-ignored raw audit 자료이며 모델 입력이
아닙니다.

## 후속

- 다음 실증 연구에는 delisted-inclusive 가격과 dated security identity가
  함께 있는 point-in-time 데이터가 필요합니다.
- 그런 데이터 없이 S&P 500 현재 생존 종목만으로 alpha를 재평가하지 않습니다.
- Transformer HPO는 독립 signal gate를 통과한 feature/target이 생긴 뒤에만
  실행합니다.
