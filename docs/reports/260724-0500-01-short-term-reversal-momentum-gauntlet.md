# Short-Term Reversal-Momentum Gauntlet

## 결정

- 공식 French size×prior-month-return portfolios로 fixed short-term-reversal-momentum 후보를 시험했습니다.
- 후보는 locked research와 untouched validation을 모두 통과했습니다.
- 최종 locked holdout에서 aggregate paired/Holm gate와 prior-losers case를 실패했습니다.
- 후보를 폐기합니다. Production/default alpha와 optimizer는 변경하지 않습니다.
- Holdout 결과로 blend, horizon, cadence, case를 재튜닝하거나 holdout을 재실행하지 않습니다.

## 공식 데이터

- source: Kenneth R. French Data Library
- archive: `25_Portfolios_ME_Prior_1_0_CSV.zip`
- source URL: `https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/25_Portfolios_ME_Prior_1_0_CSV.zip`
- archive size: `410,720` bytes
- archive SHA-256: `35f3c3ae57f65a6ad50148a9c38ad44a75eda1e8b54cea628069b17154c6da33`
- construction: monthly 5 size × 5 prior `(1-1)` return intersections
- breakpoints: NYSE monthly size and prior-return quintiles
- universe: eligible NYSE, AMEX, NASDAQ stocks
- source period: 1926-02~2026-05
- raw ZIP integrity: passed

Candidate specification:

- short-term reversal score: `LoPRIOR > PRIOR2 > PRIOR3 > PRIOR4 > HiPRIOR`
- 50% inverse prior-month-return bucket + 50% 12-1 momentum
- monthly horizon and rebalance
- 12-month circular block bootstrap
- baseline: raw 12-1 momentum

## Locked research

- split: `fama-french-25-short-term-reversal-momentum-research-1932-1955-v1`
- namespace: `alpha-v17-short-term-reversal-momentum`
- manifest digest: `bd05add70ab67f80ae2f74389443e22843b02e69829e18d9a1e6e5e3231bee45`
- evaluation: 1932-02-29~1955-12-31, 287 monthly periods
- price SHA-256: `ae41a21e32ed22a40d681179ba9dcb0d997d04548c0d3841330232937dca14a9`
- result SHA-256: `41f695f29c9654e59c166f3ccdfabd4fb654532b2e2518792d035b97d362d486`

| Signal | Mean rank IC | Positive IC | Top-bottom |
|---|---:|---:|---:|
| short-term-reversal-momentum | 0.2251 | 74.56% | 2.19% |
| short-term reversal | 0.2311 | 72.47% | 2.15% |
| 12-1 momentum | 0.1644 | 68.99% | 1.64% |

Candidate minus momentum:

- delta rank IC: `+0.0606`
- delta spread: `+0.00543`
- P(higher rank IC): `100.00%`
- P(higher spread): `100.00%`
- Holm-adjusted p-value: `0.0000`
- decision: research passed and candidate frozen

## Untouched validation

- split: `fama-french-25-short-term-reversal-momentum-validation-1958-1969-v1`
- namespace: `alpha-v17-short-term-reversal-momentum-validation`
- manifest digest: `afaad0ff9bbb1540e3147a61f9bbebf80377b97b941b80ce0bd2ad107ed4c6fe`
- evaluation: 1958-02-28~1969-12-31, 143 monthly periods
- price SHA-256: `de55bc13190d6b2f4f7a5fa107ab7329782d9d288909fff4ad0861868b6ea90b`
- result SHA-256: `a37ffa55f7b22e86b76dac20a8b81f8d4e996659a75b22fb578c070c2b895dc4`
- cases: small size, large size, prior losers, prior winners

| Signal | Mean rank IC | Positive IC | Top-bottom |
|---|---:|---:|---:|
| frozen candidate | 0.1703 | 71.33% | 0.91% |
| 12-1 momentum | 0.0918 | 58.04% | 0.50% |

- delta rank IC: `+0.0785`
- delta spread: `+0.00417`
- P(higher rank IC): `99.90%`
- P(higher spread): `99.80%`
- Holm-adjusted p-value: `0.0020`
- deterministic cases: `4/4`
- decision: validation passed

## Final locked holdout

- split: `fama-french-25-short-term-reversal-momentum-holdout-1971-1982-v1`
- namespace: `alpha-v17-short-term-reversal-momentum-locked-holdout`
- manifest digest: `ead2ce55d1591669a8bde4f473655bc06a517eb7fd69a3378fb205a6e1a54920`
- evaluation: 1971-02-28~1982-12-31, 143 monthly periods
- price SHA-256: `29259140bc7f8bc43e5d3860e1c70fc14ba866cd8ff4a3b25733879ea3b44016`
- result SHA-256: `5449bba9ca1b1bfed90de5216445065596574ec3ba3fca008cb18d449875da83`
- chain: frozen research result SHA + passing validation result SHA

| Signal | Mean rank IC | Positive IC | Top-bottom |
|---|---:|---:|---:|
| frozen candidate | 0.2120 | 71.33% | 1.31% |
| 12-1 momentum | 0.1978 | 67.83% | 1.11% |

Candidate absolute P(IC>0/spread>0)는 모두 `100%`였습니다. 그러나 최종 승격에는 baseline 대비 신뢰할 수 있는 incremental uplift가 필요합니다.

- delta rank IC: `+0.0142`
- delta spread: `+0.00196`
- P(higher rank IC): `70.45%`
- P(higher spread): `84.75%`
- Holm-adjusted p-value: `0.2955`
- deterministic cases: `3/4`
- failed case: prior losers, candidate IC `0.1778 < 0.1861`
- decision: locked holdout rejected

## 구현·검증

- research runner에 short-term-reversal bucket과 frozen setting 추가
- validation runner에 4-case short-term-reversal mode 추가
- locked holdout role, passing validation-result SHA chain, immutable holdout setting 추가
- legacy validation CLI/output 호환 유지
- bucket ordering, frozen cases, validation SHA-chain 회귀 테스트 추가
- holdout은 manifest 생성 후 최종 1회만 실행
- backend pytest `266 passed`
