# Nasdaq-100 Frozen Nested Holdout

- 작업 일시: 2026-07-24 00:00 (KST)
- 범위: 포트폴리오 alpha signal layer 독립 유니버스 검증
- 결론: `factor_residual_nested_ridge` 일반화 gate 탈락

## 목적

Historical-DOW research에서 가장 좋았던 nested ridge 후보를 설정 변경 없이
Nasdaq-100 historical universe에 적용했다. Dow 결과를 본 뒤 선택한 penalty grid,
inner validation 길이, horizon을 Nasdaq 결과에 맞춰 변경하지 않았다.

## 입력

- 구성 이력: Wikipedia `List of NASDAQ-100 companies` pinned revision
  `oldid=1365378481`, CC BY-SA 4.0
- 평가 universe: 2016-12-31~2025-12-31 membership event 271개,
  고유 ticker 179개
- 가격: Yahoo adjusted daily, 2017-01-03~2025-12-30,
  2,261일 × 179 ticker, CSV 5.9MB
- 가격 완전 누락: delisted symbol 22개
- issuer identity: SEC `company_tickers.json` 155개 + local companyfacts로
  확인한 historical override 24개
- sector: SEC submissions SIC 173/174 issuer, security-master `Unknown` 1개
- PIT features: 1,244행, 152 ticker
- holdout active-universe PIT coverage: 2022년 91.1%, 2025년 96.0%

원시 다운로드는 Nasdaq 구성 HTML 2개 822KB, SEC ticker index 798KB,
SEC submissions 174개 24.8MiB였다. 기존 local companyfacts 18GB는 다시
다운로드하지 않았다.

## Parser 보강

- SEC annual forms에 `20-F`, `20-F/A`, `40-F`, `40-F/A`를 추가했다.
- IFRS net income, revenue, gross profit, operating cash flow, assets,
  current assets/liabilities, share tags를 추가했다.
- instant shares-outstanding가 없는 복수 class issuer는 annual weighted-average
  basic/diluted shares를 filing-date-safe fallback으로 사용한다.
- 비USD reporting issuer는 FX 변환 없이 valuation을 섞지 않기 위해 계속
  제외했다.

이 변경으로 PIT ticker 수는 130개에서 152개로 증가했고 2025 active coverage는
87.1%에서 96.0%로 증가했다.

## Locked holdout

- split ID: `nasdaq100-frozen-nested-holdout-2022-2025-v1`
- role: `locked_holdout`
- evaluation: 2022-01-01~2025-09-30
- horizon/rebalance: 63/63 거래일
- fixed penalty: 5
- nested grid: `[1, 5, 20, 100]`
- nested inner validation: 완료된 최근 3개 period
- manifest digest: `d43422d4c3f5f58fe5c2580df31a4608bf5199e7a6fe85f9312f263870971d79`
- OOS periods: 15
- aggregate active-universe coverage: 92.89%

| Objective | Mean rank IC | Positive IC | Top-bottom | P(IC > 0) | P(spread > 0) |
|---|---:|---:|---:|---:|---:|
| Fixed ridge | 0.0255 | 53.33% | -0.0030 | 86.15% | 39.05% |
| Frozen nested ridge | 0.0260 | 46.67% | -0.0022 | 88.70% | 41.90% |

Nested minus fixed paired result:

- rank IC difference: `+0.00043`, P(higher) `60.55%`
- spread difference: `+0.00074`, P(higher) `61.35%`
- required probability: 95%

두 objective 모두 signal-only gate에서 탈락했다. Nested penalty selection은
Dow research 안에서는 수치를 개선했지만 독립 Nasdaq-100 universe에서는 fixed
ridge 대비 유의한 개선을 재현하지 못했고 long-short tail spread도 음수였다.

## 판정

- 현재 엔진을 quant-standard alpha model로 승격하지 않는다.
- 이 Nasdaq holdout은 결과를 확인했으므로 소진된 것으로 취급하고 재튜닝에
  사용하지 않는다.
- Transformer size나 hyperparameter 탐색으로 바로 이동하지 않는다. 현재 병목은
  모델 용량보다 feature breadth, cross-universe stability, tail ranking이다.
- 다음 model family는 별도 research namespace에서 개발하고, 새로운 untouched
  universe/period를 최종 holdout으로 사전 잠근다.
