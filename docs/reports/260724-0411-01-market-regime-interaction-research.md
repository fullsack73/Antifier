# Market-Regime Interaction Research

## 결정

- 공식 French 12-industry daily panel에서 market trend/volatility interaction은 nested ridge baseline을 개선하지 못했습니다.
- candidate의 absolute signal gate, baseline 대비 paired gate, Holm familywise gate가 모두 실패했습니다.
- exact candidate를 폐기하고 production/default alpha를 변경하지 않습니다.
- reserved 1953~1961 validation과 1962~1970 locked holdout은 열지 않습니다.
- 같은 split에서 regime lookback, volatility threshold, interaction subset, ridge grid를 재튜닝하지 않습니다.

## 데이터와 split

- source: Kenneth R. French Data Library 12 Industry Portfolios
- source URL: `https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/12_Industry_Portfolios_daily_CSV.zip`
- archive size: `1,090,526` bytes
- archive SHA-256: `7b8ee059073c70cbdf17241d1623e73016b8f24c45c3d1d2092617c50aa290c4`
- derived panel: 1926-07-01~1971-03-11, 12,332 days × 12 portfolios
- price SHA-256: `03c7df05951286a72177e10ca63880b6639c351b0d75ac22048d83fc7ed3805c`
- market total-return SHA-256: `af5df62ecef99c3e3db207e5dd82e56060ba8d3ee979ff774590a6e83e418778`
- universe manifest SHA-256: `479b72b382c9a9d6378b121b19f8c69933a0335f4f3f0c6b2170c0822fe1db8b`
- split: `fama-french-12-industry-market-regime-research-1933-1952-v1`
- namespace: `alpha-v14-market-regime-interactions`
- research: 1933-01-01~1952-12-31
- reserved validation: 1953-01-01~1961-12-31
- reserved locked holdout: 1962-01-01~1970-12-31
- split manifest SHA-256: `cce4527e1726ae5ec2140881616e74209bcd63bb7ebbf5031b01822516b2805f`
- lineage: verified
- survivorship policy: official portfolios dynamically reconstitute eligible underlying firms; promotion-safe

## 후보 사양

- baseline: `relative_nested_ridge`
- candidate: `relative_market_regime_nested_ridge`
- horizon/rebalance: 63/63 trading days
- completed training periods: minimum 8, maximum 24
- nested penalties: `[1, 5, 20, 100]`
- inner validation periods: 3
- trend regime: completed prior 252-day cumulative market return sign
- volatility regime: current completed 63-day annualized volatility versus prior rolling median
- volatility threshold history: maximum 756 observations, minimum 252
- interaction: eight price predictors × trend regime and × volatility regime
- unavailable regime encoding: 0

모든 feature, regime, inner target은 outer signal date까지 완료된 데이터만 사용합니다. 현재 volatility 관측은 자신의 threshold history에서 제외합니다.

## 결과

| Model | OOS periods | Rank IC | Positive IC | Spread | P(IC>0) | P(spread>0) |
|---|---:|---:|---:|---:|---:|---:|
| nested baseline | 93 | 0.0193 | 51.61% | 0.00445 | 69.65% | 75.00% |
| regime candidate | 93 | 0.0050 | 49.46% | 0.00286 | 55.20% | 63.45% |

Candidate minus baseline:

- delta rank IC: `-0.01436`
- delta spread: `-0.001590`
- P(higher rank IC): `35.75%`
- P(higher spread): `40.25%`
- candidate Holm-adjusted p-value: `0.6070`
- candidate signal gate: rejected
- paired gate: rejected
- selection: `no_signal_candidate`
- promotion eligible: false

Regime availability는 93/93 period에서 100%였습니다. Trend는 down/up `30/63`, volatility는 low/high `61/32` period였습니다. Candidate 실패를 missing regime이나 단일 상태 집중으로 설명할 수 없습니다.

## 비용과 진단

| Model | Fits | Predictions | Seconds | Peak MiB | Predictions/s |
|---|---:|---:|---:|---:|---:|
| nested baseline | 93 | 1,116 | 32.68 | 15.13 | 34.15 |
| regime candidate | 93 | 1,116 | 50.64 | 23.52 | 22.04 |

- candidate runtime: baseline 대비 약 `1.55x`
- candidate peak memory: baseline 대비 약 `1.55x`
- coverage: 두 모델 모두 100%
- boundary saturation: 두 모델 모두 0%
- tie rate: 두 모델 모두 0%

복잡도와 비용은 증가했지만 rank ordering과 spread는 하락했습니다. Transformer capacity 확대보다 feature/target의 독립적인 predictive content 확보가 계속 선행조건입니다.

## 구현 및 검증

- PIT market-regime interaction feature와 research-only nested objective 추가
- future market return이 과거 interaction을 바꾸지 않는 회귀 테스트 추가
- regime state, availability, threshold diagnostics 기록
- French industry label uppercase canonicalization과 duplicate guard 추가
- immutable split에서 universe, price, market-factor SHA lineage 검증
- backend pytest `258`개 통과
- result JSON SHA-256: `3a57c73733c3908c8ca959e666c7ab52cf02789b022c8f32fbc3eec4cd56fce2`

## 후속

- exact market-regime interaction family는 폐기합니다.
- 1953+ reserved data를 이 후보 평가에 사용하지 않습니다.
- 다음 연구는 동일 price feature의 interaction 변형이 아니라 독립 정보원 또는 target family가 필요합니다.
- Transformer hyperparameter 조정은 여전히 근거가 없습니다.
