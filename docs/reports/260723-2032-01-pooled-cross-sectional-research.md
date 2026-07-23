# Pooled Cross-sectional Forecast Research

## Summary

ticker별 Transformer hyperparameter를 조절하기 전에 계산비용이 낮고 해석 가능한 pooled cross-sectional baseline으로 target/objective 가설을 검증했습니다.

- research split: 2005-01-03 ~ 2013-12-30
- universe: XLB, XLE, XLF, XLI, XLK, XLP, XLU, XLV, XLY
- observations: 2,264 trading days, 9 assets
- forecast/rebalance horizon: 63 trading days
- validation은 2014년 이후 regime/ticker basket이며 이번 split과 기간/자산이 겹치지 않습니다.
- portfolio construction, candidate gauntlet, locked holdout은 실행하지 않았습니다.

## Architecture

- 12-1/6m/3m/1m momentum, 1m/3m low volatility, 6m drawdown, 6m market beta를 signal date 단면에서 winsorize/z-score합니다.
- date × ticker observation을 하나의 pooled model에 넣어 ticker별 재학습을 제거합니다.
- 각 evaluation date는 해당 시점까지 outcome이 완료된 최대 12개 training period만 사용합니다.
- objective는 absolute return ridge, relative return ridge, pairwise ridge, listwise rank ridge입니다.
- uncertainty는 현재 signal date 전에 완료된 이전 OOS residual만 사용합니다.

## Signal-only results

| Objective | Periods | Mean rank IC | Positive IC | Top-bottom | OOS 80% radius | Gate |
|---|---:|---:|---:|---:|---:|---|
| absolute ridge | 23 | -0.0848 | 43.48% | -0.0168 | 0.1394 | rejected |
| relative ridge | 23 | -0.0848 | 43.48% | -0.0168 | 0.0799 | rejected |
| pairwise ridge | 23 | -0.0652 | 43.48% | -0.0155 | 0.0797 | rejected |
| listwise rank ridge | 23 | -0.0232 | 52.17% | -0.0240 | 0.1385 | rejected |

absolute와 relative target은 날짜별 상수인 cross-sectional median 차이만 있어 ranking 결과가 같았습니다. pairwise와 listwise도 mean rank IC 또는 top-minus-bottom spread gate를 통과하지 못했습니다.

## Cost

| Objective | Fits | Predictions | Seconds | Peak Python memory |
|---|---:|---:|---:|---:|
| absolute ridge | 23 | 207 | 1.20 | 2.10 MiB |
| relative ridge | 23 | 207 | 1.20 | 1.90 MiB |
| pairwise ridge | 23 | 207 | 1.40 | 1.88 MiB |
| listwise rank ridge | 23 | 207 | 1.26 | 1.89 MiB |

기존 ticker × rebalance Transformer 216개가 약 20~30분 걸린 것과 비교해 pooled baseline은 objective당 약 1초대였습니다. 계산 구조는 개선됐지만 signal quality는 승격 기준을 충족하지 못했습니다.

## Decision

- price-only pooled 후보를 portfolio engine에 연결하지 않습니다.
- 같은 price-only feature에서 Transformer capacity/hyperparameter만 늘리지 않습니다.
- 다음 research candidate는 survivorship-safe PIT quality/value/liquidity와 macro/regime feature를 추가해야 합니다.
- 새 data feature와 compact joint model은 이 research split 내부 nested walk-forward에서 regularized baseline과 비교합니다.
- 단일 specification을 freeze하기 전 validation을 실행하지 않습니다.

## Outputs

- `logs/cross_sectional_research_sector_etfs_2005_2013.json`
- `logs/cross_sectional_research_sector_etfs_2005_2013.md`

## Verification

- `PYTHONPATH=src/backend .venv/bin/python -m pytest tests/test_cross_sectional_forecast.py -q`: 4 passed
- research CLI completed with 4 objective reports and `selection_status: no_signal_candidate`
