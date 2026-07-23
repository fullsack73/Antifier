# Trend Risk Parity Independent Replication

- 작업 일시: 2026-07-24 01:53 (KST)
- 상태: research 통과, candidate freeze
- split: `fama-french-30-industry-trend-risk-parity-replication-1928-1971-v1`
- namespace: `risk-v9-trend-filtered-risk-parity-replication`

## 사전 복제 규칙

- 선행 49-industry 1973~1981 split의 deterministic gate 통과를 요구했습니다.
- candidate specification은 변경하지 않았습니다.
- 독립 복제에서 deterministic, 95% paired bootstrap, Holm gate를 모두 요구했습니다.
- 선행 result SHA-256 `39fcfab8…36c46`을 split manifest에 잠갔습니다.

## 데이터

- source: Kenneth R. French Data Library, 30 Industry Portfolios Daily
- official ZIP: 2,590,771 bytes, SHA-256 `7140a2db…d61848`
- derived price index: 1926-07-01~1971-03-11, 12,332행 × 30 industries
- research evaluation: 1928-03-07~1971-03-11, 11,827 OOS returns
- historical risk-free: French daily one-month Treasury-bill return
- source portfolios are reconstituted through time; requested interval has no missing observations.

## Frozen candidate

- baseline: inverse-volatility risk parity
- candidate: 252일 trailing return이 양수인 sleeve만 보유
- 비활성 sleeve는 같은 날짜의 official French risk-free cash로 유지
- 504일 train, 63일 rebalance, 10bp cost, 10% asset cap, 2% band, 35% turnover cap

## 결과

| Model | CAGR | Volatility | Sharpe | Max DD | CVaR | Risk exposure | Turnover |
|---|---:|---:|---:|---:|---:|---:|---:|
| Risk parity | 8.19% | 15.24% | 0.4909 | -82.70% | 2.391% | 93.64% | 1.65% |
| Trend-filtered risk parity | 8.46% | 9.74% | 0.7237 | -37.77% | 1.530% | 67.78% | 10.70% |

- candidate minus baseline volatility: `-5.498%p`
- candidate minus baseline Sharpe: `+0.2329`
- P(lower volatility): `100.00%`
- P(higher Sharpe): `98.60%`
- Holm-adjusted p-value: `0.0140`
- deterministic gate: passed
- statistical gate: passed
- promotion eligible: true

## 결정

- trend-filtered risk parity specification을 frozen candidate로 고정합니다.
- 다음 단계는 untouched 2018~2021 validation입니다.
- validation 결과로 lookback, threshold, base allocator, exposure floor를 재튜닝하지 않습니다.
- validation 통과 전 2022~2025 locked holdout을 열지 않습니다.
