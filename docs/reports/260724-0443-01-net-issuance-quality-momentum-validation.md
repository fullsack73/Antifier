# Net-Issuance Quality-Momentum Validation

## 결정

- Frozen net-issuance-quality-momentum 후보를 untouched 2000~2011 validation에 사양 변경 없이 적용했습니다.
- Aggregate paired uplift gate는 통과했지만 candidate absolute bootstrap gate가 실패했습니다.
- 사전 고정 4-case 중 low-net-issuance case가 baseline을 이기지 못해 `3/4`만 통과했습니다.
- 후보를 기각합니다. Production/default alpha는 변경하지 않습니다.
- 같은 validation 결과에 맞춘 weight, horizon, bucket 재튜닝을 금지합니다.
- 2012+ locked holdout은 실행하지 않고 봉인합니다.

## Locked 계약

- validation split: `fama-french-35-net-issuance-quality-momentum-validation-2000-2011-v1`
- namespace: `alpha-v15-net-issuance-quality-momentum-validation`
- manifest digest: `0b4c505e963bb77fc5fb097ecbd6d4df3ecd2ee72bcb0551734ec30fe167733a`
- frozen research split: `fama-french-35-net-issuance-quality-momentum-research-1969-1998-v1`
- frozen result SHA-256: `b5249cdb832a3750a2d7a47e1ab9006a9141653f327259e483254940cb4083a8`
- validation price SHA-256: `ee0887e66882847a6c9a2d52a3694ace0d8ff8f4897fac40f44a78d7d6e2940c`
- evaluation: 2000-01-31~2010-12-31, 11 non-overlapping annual periods
- result SHA-256: `fe8d3bb9fe3eea953d52c747eadcbca676317cf63bcf8a8aa0362e2dcaa02228`

## Aggregate 결과

| Signal | Mean rank IC | Positive IC | Top-bottom |
|---|---:|---:|---:|
| net-issuance-quality-momentum | 0.1297 | 63.64% | 6.48% |
| 12-1 momentum | -0.0072 | 27.27% | 2.78% |

Candidate absolute bootstrap:

- P(IC > 0): `84.55%`
- P(spread > 0): `87.35%`
- required: `95%`
- decision: rejected

Candidate minus momentum:

- delta rank IC: `+0.1369`
- delta spread: `+0.03695`
- P(higher rank IC): `100.00%`
- P(higher spread): `98.05%`
- Holm-adjusted p-value: `0.0195`
- paired gate: passed

평균 uplift는 분명하지만 11개 validation period에서 absolute 95% 신뢰도를 증명하지 못했습니다. Paired gate만으로 승격하지 않습니다.

## 사전 고정 cases

| Case | Candidate IC | Baseline IC | Candidate spread | Baseline spread | Gate |
|---|---:|---:|---:|---:|---|
| small size | 0.1237 | 0.0422 | 7.09% | 6.30% | passed |
| large size | 0.1453 | -0.0290 | 5.21% | 1.36% | passed |
| low net issuance | 0.0185 | 0.0604 | 0.39% | 2.77% | rejected |
| high net issuance | 0.2506 | 0.0675 | 8.61% | 3.63% | passed |

Low-net-issuance subset에서 candidate IC와 spread가 모두 baseline보다 낮았습니다. 이는 고정 issuance score가 이미 낮은 issuance subset 내부를 추가로 잘 구분하지 못한다는 증거입니다. 이 validation을 보고 해당 subset용 weight를 재튜닝하지 않습니다.

## 결론

- Net issuance는 경제적으로 유효한 독립 feature 후보지만 현재 고정 blend는 quant-standard promotion gate를 충족하지 못했습니다.
- Transformer hyperparameter 확대 근거가 아닙니다.
- 다음 연구는 이 실패한 validation을 재사용하지 않고 fresh research namespace와 다른 정보 family를 사용해야 합니다.
