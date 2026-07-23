# Online Reversal-Momentum Hedge Research

## 결정

- Completed-feedback online Hedge로 12-1 momentum과 short-term reversal을 parameter-free 결합했습니다.
- 후보 absolute signal은 양수였지만 fixed 50/50 blend와 raw momentum 두 baseline에 대한 paired/Holm gate를 통과하지 못했습니다.
- 후보를 research 단계에서 폐기합니다.
- 2006~2014 validation과 2016~2025 locked holdout은 실행하지 않습니다.
- 이 결과로 learning-rate, loss, cap, lookback을 재튜닝하지 않습니다.

## 후보 사양

- experts: `momentum_12_1`, `short_term_reversal`
- initial weights: 50% / 50%
- expert loss: `(1 - completed Spearman rank IC) / 2`
- learning rate: `sqrt(8 * log(expert_count) / completed_count)`
- update: completed one-month forward outcomes only
- candidate baseline 1: fixed 50/50 reversal-momentum
- candidate baseline 2: raw 12-1 momentum
- promotion: candidate absolute gate와 두 paired comparisons의 95%/Holm gate 모두 필요

학습률은 expert count와 completed observation count의 이론식으로 고정했습니다. Research 결과에 맞춘 hyperparameter search는 없습니다.

## 데이터와 split

- source archive: official French `25_Portfolios_ME_Prior_1_0_CSV.zip`
- source SHA-256: `35f3c3ae57f65a6ad50148a9c38ad44a75eda1e8b54cea628069b17154c6da33`
- panel: 1980-02-29~2005-01-31, 300 months × 25 portfolios
- price SHA-256: `ae1cd2445c9edf96e556cc81f2c16cb66e99fc366c2ea5cbae98e8df717faa83`
- basket SHA-256: `271bc40259c9bdb51e042ec776c46310d3cacb0c1deded4fbbe330b0e32cb494`
- split: `fama-french-25-online-reversal-hedge-research-1986-2004-v1`
- namespace: `alpha-v18-online-reversal-hedge`
- manifest digest: `92a6b3f884b6fdfc1717f3e4f29fcd141dc8fbc9d96b7cd88953646f92feecea`
- evaluation: 1986-02-28~2004-12-31, 227 monthly periods
- reserved validation: 2006-02-28~2014-12-31
- reserved locked holdout: 2016-02-29~2025-12-31
- result SHA-256: `b3cd26d40773325d92cfc3e8ed544b233bb0388717db09f51d2736e1f030a4fd`

## 결과

| Signal | Mean rank IC | Positive IC | Top-bottom |
|---|---:|---:|---:|
| online Hedge | 0.0887 | 57.71% | 0.68% |
| fixed 50/50 | 0.0943 | 58.15% | 0.60% |
| raw momentum | 0.0789 | 58.15% | 0.37% |
| reversal diagnostic | 0.0774 | 57.27% | 0.53% |

Candidate absolute P(IC>0/spread>0)는 `100.00%`/`99.95%`로 통과했습니다.

Versus fixed 50/50:

- delta rank IC: `-0.0056`
- delta spread: `+0.00085`
- P(higher rank IC): `24.55%`
- P(higher spread): `89.55%`
- Holm-adjusted p-value: `0.7545`

Versus raw momentum:

- delta rank IC: `+0.0098`
- delta spread: `+0.00307`
- P(higher rank IC): `74.40%`
- P(higher spread): `98.60%`
- Holm-adjusted p-value: `0.5120`

Momentum expert weight는 `41.18%~79.26%` 사이에서 움직였고 최종 `50.96%`였습니다. Online adaptation은 실제로 작동했지만 fixed blend보다 IC가 낮고 raw momentum 대비 IC uplift도 통계적으로 불충분했습니다.

## 검증

- initial equal weight와 lower-completed-loss 선호 테스트
- current score가 completed periods만 사용하는 회귀 테스트
- dual-baseline familywise Holm gate
- split self-hash와 price provenance 검증
- validation/holdout artifact 없음
- backend pytest `268 passed`
