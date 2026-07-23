# Low Residual-Variance Momentum Research

## 결정

- 공식 French size×FF3 residual-variance 자료로 독립 idiosyncratic-risk signal을 시험했습니다.
- 고정 50/50 low-residual-variance와 12-1 momentum 후보는 absolute signal gate를 통과했습니다.
- 그러나 raw momentum 대비 paired IC/spread improvement와 Holm gate를 통과하지 못했습니다.
- 후보를 research 단계에서 폐기합니다. Production/default alpha 또는 risk model은 변경하지 않습니다.
- 1991~1998 validation과 2000~2011 locked holdout은 실행하지 않습니다.
- 같은 split에서 blend weight, horizon, rebalance cadence를 재튜닝하지 않습니다.

## 공식 데이터

- source: Kenneth R. French Data Library
- archive: `25_Portfolios_ME_RESVAR_5x5_CSV.zip`
- source URL: `https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/25_Portfolios_ME_RESVAR_5x5_CSV.zip`
- archive size: `488,246` bytes
- archive SHA-256: `d91ee3ec791532e1d4861653a4fc710c36ff212abd462bde3befd8903dbbe83d`
- construction: monthly intersections of 5 size and 5 FF3 residual-variance groups
- residual variance: 60 lagged daily returns, minimum 20 observations
- breakpoints: NYSE size and residual-variance quintiles
- universe: eligible NYSE, AMEX, NASDAQ stocks
- raw ZIP integrity: passed

Derived data:

- research panel: 1963-07-31~1990-01-31, 319 months × 25 portfolios
- research price SHA-256: `063a7b218e0927e7d2ef16c7a4b6b2097088a9fe6938393942976e08cf8b7260`
- reserved validation panel: 1985-01-31~1999-01-31, 169 months × 25 portfolios
- validation price SHA-256: `0a36ce2bf4c62df000dcab073f0e2a9b082aa14d07bc36bbabea51c92ade246c`
- ordered basket SHA-256: `70d82fff6ded341b48e05d6b40c4a78d1924db3f3de9de75cae170a28b8d9c42`

## Locked research

- split: `fama-french-25-low-residual-variance-momentum-research-1969-1989-v1`
- namespace: `alpha-v16-low-residual-variance-momentum`
- manifest digest: `24f2619d2bcf5bfb9387b407456448e8afaa9abeed8ec94457779220f4b61715`
- evaluation: 1969-07-31~1989-10-31, 82 non-overlapping quarterly periods
- candidate: inverse residual-variance quintile 50% + 12-1 momentum 50%
- baseline: 12-1 momentum
- reserved validation: 1991-01-31~1998-10-31
- reserved locked holdout: 2000-01-31~2011-10-31

| Signal | Mean rank IC | Positive IC | Top-bottom | P(IC>0) | P(spread>0) |
|---|---:|---:|---:|---:|---:|
| low-residual-variance-momentum | 0.2800 | 73.17% | 3.60% | 100.00% | 100.00% |
| low residual variance | 0.2267 | 69.51% | 2.77% | 100.00% | 99.95% |
| 12-1 momentum | 0.2450 | 70.73% | 3.25% | 100.00% | 100.00% |

Candidate minus momentum:

- delta rank IC: `+0.0351`
- delta spread: `+0.00353`
- P(higher rank IC): `80.75%`
- P(higher spread): `77.15%`
- Holm-adjusted p-value: `0.2285`
- decision: paired gate rejected
- result SHA-256: `385385f7ede226404ba3e3a9a6c754359b8cb8ae0fcd4482c2a2020895497d6a`

Low residual variance 자체는 강한 characteristic이지만 이미 강한 momentum baseline에 통계적으로 신뢰할 수 있는 incremental ordering을 추가하지 못했습니다. 평균 IC만으로 승격하지 않습니다.

## 검증

- parser/ordering/no-lookahead targeted pytest 통과
- research split self-hash와 price provenance 검증 통과
- validation result/holdout artifact 생성 없음
- `git diff --check` 통과
