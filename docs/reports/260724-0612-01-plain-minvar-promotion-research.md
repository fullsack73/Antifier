# Plain Minimum-Variance Promotion Research

- 작업 일시: 2026-07-24 06:12 (KST)
- 상태: locked research 탈락
- split: `fama-french-10-industry-minvar-promotion-research-2000-2011-v1`
- namespace: `allocator-v1-minvar-default-industry-portfolios`

## 목적

선행 minvar/momentum 연구에서 가장 강했던 plain Ledoit-Wolf minimum variance가 current lightweight/default와 risk parity를 모두 이겨 default allocator 후보가 되는지 fresh period에서 검증했습니다.

## 고정 사양

- candidate: `min_variance`
- statistical baselines: `lightweight_bl`, `risk_parity`
- deterministic guards: `equal_weight`, `historical_bl`
- policy: long-only global minimum variance
- covariance: Ledoit-Wolf constant-variance shrinkage
- expected return/forecast model: 사용하지 않음
- 504일 train, 63일 horizon/rebalance, 10bp cost
- 20% asset cap, 2% rebalance band, 35% turnover cap
- 21일 circular block bootstrap 2,000회
- 네 paired lower-volatility/higher-Sharpe 가설에 95% gate와 Holm correction

## 데이터

- source: Kenneth R. French Data Library 10 Industry Portfolios Daily
- price panel: 1998-01-02~2011-12-30, 3,523행 × 10 industries
- evaluation: 2000-01-03~2011-12-30
- risk-free: official French daily factor와 FRED DGS3MO를 결합한 historical daily panel
- raw archive는 기존 로컬 공식 자료를 재사용했으며 외부 다운로드 없음
- price, factor, provenance, ordered basket, split manifest SHA 검증 통과
- split manifest digest: `89b49879…57d4b`

## Portfolio 결과

| Model | CAGR | Volatility | Sharpe | Max DD | Turnover |
|---|---:|---:|---:|---:|---:|
| Equal weight | 4.35% | 20.06% | 0.1997 | -51.22% | 3.50% |
| Historical BL | 4.27% | 19.80% | 0.1961 | -50.60% | 2.94% |
| Lightweight BL | 4.01% | 20.00% | 0.1834 | -51.69% | 5.30% |
| Risk parity | 5.42% | 18.65% | 0.2551 | -48.34% | 3.99% |
| Minimum variance | 6.61% | 17.34% | 0.3254 | -43.19% | 11.17% |

- deterministic gate: passed
- vs lightweight P(lower volatility/higher Sharpe): `100.00% / 97.95%`
- vs risk parity P(lower volatility/higher Sharpe): `100.00% / 91.50%`
- risk-parity higher-Sharpe Holm-adjusted p-value: `0.0850`
- statistical gate: rejected
- promotion eligible: false

## 결정

- Plain minimum variance는 평균 성과와 위험 지표에서 모든 guard를 이겼습니다.
- 그러나 risk parity 대비 Sharpe 개선의 통계적 확신이 사전 고정 기준에 미달했습니다.
- 강한 연구 baseline으로 유지하되 production/default allocator로 승격하지 않습니다.
- 같은 split에서 train window, asset cap, covariance estimator를 결과에 맞춰 변경하지 않습니다.
- Validation과 locked holdout을 열지 않습니다.

## 검증

- runner/manifest/no-lookahead 회귀 테스트: `2 passed`
- split self-hash와 data provenance SHA 검증 통과
- 결과 artifact:
  `data/research/derived/fama_french_10_industry_minvar_promotion_research_result_v1.json`
