# Net-Issuance Quality-Momentum Research

## 결정

- 공식 French size×net-share-issues 자료로 독립 issuer-action signal을 시험했습니다.
- 고정 50/50 net-issuance-quality와 12-1 momentum 후보가 research absolute/paired/Holm gate를 모두 통과했습니다.
- 후보 사양과 research 결과를 freeze했습니다.
- untouched 2000~2011 validation 도구와 입력 panel만 준비했습니다. validation은 아직 실행하지 않았습니다.
- validation 전 후보 weight, horizon, bucket 순서를 변경하지 않습니다. 2012+ holdout은 봉인합니다.

## 공식 데이터

- source: Kenneth R. French Data Library
- archive: `25_Portfolios_ME_NI_5x5_CSV.zip`
- source URL: `https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/25_Portfolios_ME_NI_5x5_CSV.zip`
- archive size: `689,183` bytes
- archive SHA-256: `6f0bffd72c315d336dc0bac531b404b2bb8f541a4a03143476c23622870c79a1`
- source definition: fiscal `t-2`에서 `t-1`까지 split-adjusted shares outstanding의 log 변화
- universe: eligible NYSE, AMEX, NASDAQ firms
- portfolios: 5 size groups × `NegNI`, `ZeroNI`, 5 positive-NI buckets = 35 columns
- research panel: 1963-07-31~1999-12-31, 438 months × 35 portfolios
- research price SHA-256: `dc790a030ad0e20647cccd4fff45e32ad47b9dc7da280cc56de9d1981fcd9ea2`
- universe manifest SHA-256: `9e550f8e9a6c31b8341b5ced86f36898b8ec18cd7c88a99b11b30659c63adbd0`

## Locked research

- split: `fama-french-35-net-issuance-quality-momentum-research-1969-1998-v1`
- namespace: `alpha-v15-net-issuance-quality-momentum`
- manifest digest: `897cb5915c3c3b6c166ee772790ed0633ea1439601cf5321b069b3a2fdecb1b4`
- evaluation: 1969-07-31~1998-07-31, 30 non-overlapping annual periods
- candidate: inverse net-share-issues bucket 50% + 12-1 momentum 50%
- baseline: 12-1 momentum

| Signal | Mean rank IC | Positive IC | Top-bottom | P(IC>0) | P(spread>0) |
|---|---:|---:|---:|---:|---:|
| net-issuance-quality-momentum | 0.2476 | 76.67% | 5.86% | 100.00% | 100.00% |
| net-issuance-quality diagnostic | 0.2313 | — | 5.74% | — | — |
| 12-1 momentum | 0.1590 | — | 3.74% | 99.45% | 99.40% |

Candidate minus momentum:

- delta rank IC: `+0.0885`
- delta spread: `+0.02114`
- P(higher rank IC): `97.60%`
- P(higher spread): `98.35%`
- Holm-adjusted p-value: `0.0240`
- decision: research promotion gate passed

Frozen result SHA-256:
`b5249cdb832a3750a2d7a47e1ab9006a9141653f327259e483254940cb4083a8`

## Validation 준비

- validation panel: 1994-01-31~2011-12-31, 216 months × 35 portfolios
- validation price SHA-256: `ee0887e66882847a6c9a2d52a3694ace0d8ff8f4897fac40f44a78d7d6e2940c`
- reserved validation: 2000~2011, 11 completed annual signal periods
- cases: small size, large size, low net issuance, high net issuance
- minimum case periods: 10
- reserved locked holdout: 2012~2025

Validation runner는 frozen result SHA와 exact candidate specification을 확인합니다. Research 통과만으로 production/default alpha를 변경하지 않습니다.

## 검증

- `py_compile` 통과
- 표적 pytest `7 passed`
- raw ZIP `unzip -t` 통과
- `git diff --check` 통과
