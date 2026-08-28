# FF3 Factor-Risk Shadow-Forward Validation

- 작업 일시: 2026-08-28 03:59 KST
- 범위: 고정 FF3 factor-risk GMV의 미사용 historical shadow-forward validation
- 결론: statistical/Holm gate 탈락, production Ledoit-Wolf GMV 유지

## 검증 설계

Smoke 결과를 본 뒤 window, half-life, shrinkage, floor 또는 cap을 재선택하지 않았습니다. 기존 12-industry 연구 split이 사용한 1933-1952, 1970-1999, 2000-2011, 2021-2025 구간 사이에서 비어 있던 2012-2018 구간을 결과 확인 전에 immutable locked-holdout manifest로 고정했습니다.

이 실행은 2025년 이후 새로 쌓인 live calendar-forward 데이터가 아니라, 사양 동결 뒤 처음 개봉한 과거 미사용 contiguous holdout입니다. 이를 숨기지 않도록 split manifest에 `calendar_forward=false`와 해석을 기록했습니다. 2010-01-04~2018-10-05 가격 panel의 첫 504일은 training에만 쓰고 2012-01-03~2018-10-05의 완전한 63거래일 OOS origin 27개를 평가했습니다.

고정 비교 조건:

- 동일 Kenneth French 12 SIC industry value-weighted PIT portfolio universe
- 504일 training window, 63일 rebalance 및 forecast horizon
- long-only 20% cap, 10 bps 거래비용, 2% rebalance band, 35% turnover cap
- 동일 `us_market_factors_2007_2025.csv`의 FF3와 backward-asof FRED DGS3MO daily-equivalent risk-free
- FF3 exposure/covariance/specific-risk/PSD/fallback 사양은 smoke manifest와 byte-for-byte 같은 settings

## 데이터와 잠금

- price raw archive SHA-256: `7b8ee059073c70cbdf17241d1623e73016b8f24c45c3d1d2092617c50aa290c4`
- price file SHA-256: `e31de9a029237fdfd994c93c2e1ca8187dfd4e518522c8adbe9298dde14b4c1`
- ordered basket SHA-256: `bfe0abb165831f8b4b1a838c5facc93f990e3a484c0c6e7566b3e87644797e17`
- universe manifest digest: `4a6dc465e68bd1e743728a63e67b7b8548919b2ecb5677f08c6b67cddf8d068d`
- factor/risk-free file SHA-256: `015a593a033b3dab0662ef40017956acb85589ce2abd1d8014e4f16e550decd3`
- split manifest self-hash: `01c2c810197f7dce23713a5d8fd14c345f2263e767514f021bd3cd8adbf110ed`
- split manifest file SHA-256: `6118413996beeb741210e133df50dcf8b3f2328ebda41c8d81f6515f4643edc2`
- frozen smoke manifest self-hash: `8061eee3562ad2988d1e76984bc2388841ec17d295755c199f7776e910732e3f`
- `locked=true`, `role=locked_holdout`, parameter reselection `false`

## 결과

| Metric | Ledoit-Wolf GMV | FF3 factor-risk GMV |
|---|---:|---:|
| Annual realized volatility | 10.5515% | 10.5426% |
| CAGR | 13.0492% | 13.0019% |
| Sharpe | 1.1748 | 1.1718 |
| Sortino | 1.6863 | 1.6842 |
| Maximum drawdown | -10.4374% | -10.3572% |
| Net cumulative return | 128.8520% | 128.2064% |
| Average controlled turnover | 10.4046% | 9.4403% |
| Average concentration HHI | 0.1864 | 0.1932 |
| HHI effective holdings | 5.36 | 5.18 |
| Average predicted annual volatility | 11.9743% | 11.1452% |
| Average realized period annual volatility | 10.0353% | 10.0408% |
| Realized/predicted volatility ratio | 0.8733 | 0.9601 |
| Risk forecast MAE | 3.7529% | 3.2602% |

FF3는 point estimate 변동성을 0.89 bp 낮추고 maximum drawdown, turnover, risk forecast MAE와 calibration ratio를 개선했습니다. 그러나 CAGR과 Sharpe는 낮아졌고 HHI는 높아져 effective holdings가 5.36에서 5.18로 줄었습니다.

## Paired 95% 및 Holm gate

- circular block bootstrap: 2,000 samples, 21거래일 block, seed 42
- paired daily observations: 1,701
- P(FF3 lower realized volatility): 66.50%
- P(FF3 higher Sharpe): 43.20%
- realized-volatility difference 95% interval: -4.52 bp~+2.44 bp
- Sharpe difference 95% interval: -0.0506~+0.0462
- Holm raw/adjusted p-value: 0.5680 / 0.5680
- significant: `false`
- 판정: realized volatility와 Sharpe 각각 95%를 요구하는 gate 및 Holm gate 탈락

## Factor, fallback, exposure drift

- factor covariance 성공: 27/27 origins
- exact Ledoit-Wolf fallback: 0/27, fallback reason 없음
- 평균 covariance condition number: 88.1256
- 평균 covariance effective rank: 3.0596
- successive ticker exposure pair: 312
- factor beta 평균/중앙 L2 change: 0.05094 / 0.04403
- mean absolute beta change: market 0.01554, SMB 0.02370, HML 0.03586
- turnover cap hit: baseline 0, FF3 0

## 결정

Smoke에서 보인 큰 point-estimate 개선은 미사용 holdout에서 재현되지 않았습니다. FF3 candidate는 `risk_gate_passed=false`, `promotion_eligible=false`이며 이 결과로 파라미터를 재튜닝하지 않습니다. Production `MIN_VARIANCE`, API, UI와 기본 optimizer의 Ledoit-Wolf GMV는 변경하지 않았습니다.

TODO의 데이터 수, paired bootstrap/Holm, drawdown/turnover/집중도/fallback/predicted-realized/exposure-drift 보고 조건을 모두 충족했으므로 `docs/todo/ff3-factor-risk-shadow-forward-validation.md`를 삭제하고 index에서 제거했습니다.

## 산출물과 검증

- split: `data/research/derived/fama_french_12_industry_ff3_factor_risk_shadow_forward_validation_split_v1.json`
- result: `data/research/derived/fama_french_12_industry_ff3_factor_risk_shadow_forward_validation_result_v1.json`
  - SHA-256: `ac8a06ec62a899fcbbc1d6f41cfa7974a2cc16e569b6cc497765d876473a1416`
- summary: `data/research/derived/fama_french_12_industry_ff3_factor_risk_shadow_forward_validation_result_v1.md`
- price/universe provenance, 27개 완전 horizon과 split self-hash 검증: 통과
- deterministic CLI 재실행: result SHA-256 동일
- 관련 backend: `144 passed in 23.30s`
- 전체 backend: `418 passed in 97.37s`
- `git diff --check`: 통과
