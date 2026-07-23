# Quarterly TTM PIT Factor Research

- 실행 시각: 2026-07-24 00:24 KST
- 역할: research-only feature-family audit
- 기간: 2020-01-01 ~ 2021-09-30 signal dates
- horizon/rebalance: 63/63 trading days
- objective: `factor_residual_nested_ridge`
- 결론: quarterly TTM predictor 폐기

## 변경

- SEC `10-Q`, `10-Q/A`, `10-K`, `10-K/A`, `20-F` filing anchor를 시간순으로 처리합니다.
- direct quarter flow를 우선하고, Q2/Q3 YTD와 annual flow는 이미 알려진 이전 분기를 차감해 현재 분기를 계산합니다.
- 순차 4개 분기가 존재할 때만 revenue, operating income, net income, operating cash flow의 TTM 값을 만듭니다.
- 미래 정정공시는 이미 방출한 과거 row를 다시 쓰지 않습니다.
- annual predictor와 quarterly predictor가 동일한 realized residual target을 사용하도록 predictor factor와 target factor 입력을 분리했습니다.

## 데이터

- 로컬 `companyfacts/`를 사용했으며 외부 다운로드는 없었습니다.
- quarterly TTM: 2,170 rows / 123 tickers
- annual PIT, 2021년 이하: 650 rows / 140 tickers
- active-universe feature coverage:
  - 2018: annual 84.5%, quarterly 85.4%
  - 2019: annual 88.3%, quarterly 87.4%
  - 2020: 둘 다 85.3%
  - 2021: annual 87.1%, quarterly 90.1%
- median feature age는 annual 약 306~309일에서 quarterly 약 58~62일로 감소했습니다.

## 잠금

- annual split digest: `0549f3409d91cf9074f28baa54ed532c5ab2b3a5cf06a85734d223c822e5e67e`
- quarterly split digest: `a82a5fc06f6362a47635333d52434ebf9846d5ed65e0fd561772a614c01f13a9`
- 동일 target factor SHA: `44565520849f6cf2583faa06999769de29f109a206183c1d05bae0ff6d71c669`
- 2022~2025 Nasdaq holdout 결과는 이번 연구의 선택이나 설정 변경에 사용하지 않았습니다.

## 결과

| Predictor | OOS periods | Mean rank IC | Positive IC | Top-bottom spread | Active coverage | Seconds |
|---|---:|---:|---:|---:|---:|---:|
| Annual PIT | 7 | -0.0424 | 42.86% | -0.0151 | 86.49% | 10.97 |
| Quarterly TTM PIT | 7 | -0.0505 | 42.86% | -0.0263 | 86.49% | 10.96 |

- 두 실행의 signal dates와 realized-return dictionaries는 완전히 동일합니다.
- quarterly minus annual은 rank IC `-0.0081`, spread `-0.0112`입니다.
- 7개 OOS period라 dependent block bootstrap 최소 표본에도 미달합니다.
- 두 후보 모두 IC와 spread가 음수이므로 signal-only gate에서 탈락했습니다.

## 판정

- filing freshness와 2021 coverage는 개선됐습니다.
- 예측력과 포트폴리오 승격 근거는 개선되지 않았습니다.
- 같은 Nasdaq 2020~2021 결과를 보고 TTM window, penalty, 시작일 또는 minimum-training gate를 재조정하지 않습니다.
- 다음 후보는 동일 분기 TTM 변형이 아니라 새 research universe의 다른 feature family여야 합니다.
