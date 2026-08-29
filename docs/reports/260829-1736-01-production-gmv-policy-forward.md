# Production GMV 운용 정책 calendar-forward 등록

## 목적과 결론

이미 결과를 확인한 DOW, Nasdaq, French, Country ETF 구간과 다른 가설에
예약된 holdout을 재사용하지 않고 production GMV의 운용 방식만 비교하는
calendar-forward campaign을 등록했습니다. Historical 성과는 실행하지 않았고,
현재 결과 상태는 `forward_pending`입니다. Production optimizer와 frontend의
동작은 변경하지 않았으며 자동 승격은 허용하지 않습니다.

## Evidence와 immutable 사양

- Country ETF 결과를 diagnostic/reproduction-only consumed record로 registry에
  append했습니다. Registry는 9개 record이며 마지막 hash는
  `b994400594e6d7a77fe4d43c49c329fa9575d5115c594c5017aa516b98944ea0`입니다.
- 사양은 code revision `506404f79d27d392dccbccb0b1a47c7418b48362`와
  현재 `snp.csv` 503종목 snapshot을 고정합니다. Spec hash는
  `388e1b8a83de5030b83d471919872fdb1f57eee5f7df4c2f367835b770ebe256`입니다.
- 504일 train, 63일 rebalance/outcome, 10,000 USD, fractional synthetic units,
  10 bps 비용, 2% band, gross L1 35% cap, 종목 20% cap, 연 2% risk-free를
  고정했습니다. Group/asset override와 소급 historical classification은 쓰지
  않습니다.

## 구현 계약

`gmv_policy_comparison`은 production `MIN_VARIANCE + RISK_ONLY + Ledoit-Wolf`
결과를 두 번 계산해 data/result hash와 weight 결정성을 확인합니다. 최초
post-cost quantities/cash는 buy-and-hold, fixed-target, rolling-reoptimization에
동일하게 복제합니다. 이후 buy-and-hold는 무거래, fixed는 최초 raw
weight/cash/hash, rolling은 해당 as-of 이전 504개 관측의 새 GMV를 사용합니다.
Fixed와 rolling은 기존 `apply_trade_controls`와 `_fund_transaction_cost`를
공유합니다.

Shadow ledger contract v3는 기존 v1/v2 physical schema와 hash chain을 유지하면서
세 정책의 pre/post quantities·notionals·cash, 공통 price/covariance, target,
turnover·cost, risk, HHI, deviation, constraint/fallback/coverage를 보존합니다.
실패 관측은 no-trade provenance를 append하고 마지막 complete state에서 재시도하며,
63개 미래 거래 관측이 모두 있는 paired outcome만 terminal record가 됩니다.

평가는 21일 circular block bootstrap 2,000회, seed 42와 volatility one-sided
Holm 보정을 사용합니다. 8개 mature paired observation 전에는 항상
`forward_pending`이고, 그 이후에도 volatility/CI, Sharpe 95%, drawdown,
calibration, turnover, concentration, correctness guard를 모두 통과해야만 수동
superiority 검토가 가능합니다. 여러 panel은 모두 같은 정책·방향이어야 합니다.

## 최초 live formation

- Campaign hash: `67349b5a53b2bd8a450c7c797430ba7b48137f2942e6115e32384a4470944ee3`
- As-of: `2026-08-29T08:34:14+00:00`; data available through `2026-08-28`
- Requested/eligible: 503/497; 제외 `AVB`, `EA`, `EQR`, `FDXF`, `Q`, `SNDK`
- Common data hash: `4ea309bbc76d5ffab59c46bcce779cf64ee203651516b158328ea832058037a2`
- 두 optimizer result hash는
  `a6231b89116f51d78ff59d9ef561f5802bd6e4c6e6bf443ea728ac6cbe8440ce`로
  동일하고 최대 weight 차이는 0입니다.
- 세 정책의 초기 quantities/cash는 동일합니다. 초기 turnover는
  `0.9990009990`, 비용은 `9.9900099900 USD`, fallback count는 0입니다.
- Observation payload/record hash는 각각
  `64d50d09a7fde828ceef9e3deafff64ff20094f3dfef5cabb3298c6a067eba01`,
  `58c775de201b98f4afea54f5b032999182f220373987467fb583b56957fb38dd`입니다.
- Ledger audit는 campaign 1, complete observation 1, outcome 0, attempt 0으로
  정상입니다. Mature paired observation은 0이며 correctness/turnover cap 위반도
  0입니다.

## 검증

- Targeted backend regression: 125 passed
- Full backend regression: 462 passed
- 모든 CLI subcommand help와 Python compile smoke: 정상
- Evidence registry audit, spec self-hash, ledger hash-chain: 정상
- Live exact-504 deterministic rerun: 정상
- `git diff --check`: 정상
- Frontend 코드는 변경하지 않아 npm 검증은 생략합니다.

Offline fixture canonical rerun은 targeted/full regression에서 동일 hash로
확인했습니다. 등록 artifact와 모든 향후 결과는
`no_automatic_promotion: true`입니다. 원격 CI와 release 상태는 push 후 별도로
확인합니다.
