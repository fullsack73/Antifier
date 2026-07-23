# Constant-Correlation Minimum-Variance Replication

- 작업 일시: 2026-07-24 06:43 (KST)
- 상태: unchanged independent replication 탈락
- split: `fama-french-25-size-value-constant-correlation-replication-2000-2011-v1`
- namespace: `allocator-v3-constant-correlation-minvar-size-value-replication`
- prior split: `fama-french-38-source-33-complete-constant-correlation-research-1971-1980-v1`
- prior result SHA: `9c4ff299…f283fe`

## 목적

첫 research에서 모든 deterministic 지표를 개선했지만 statistical gate를 통과하지 못한 constant-correlation candidate를 다른 portfolio construction과 시대에서 사양 변경 없이 한 번 독립 복제했습니다.

## Replication contract

- candidate policy: prior result와 exact equality 강제
- candidate: `constant_correlation_minimum_variance`
- covariance: Ledoit-Wolf constant-correlation shrinkage
- objective: long-only global minimum variance
- expected return/forecast model: 사용하지 않음
- statistical baselines: `min_variance`, `risk_parity`, `lightweight_bl`
- deterministic guards: `equal_weight`, `historical_bl`
- prior requirement: deterministic gate passed
- replication requirement: deterministic, 95% paired, six-hypothesis Holm gate 모두 통과
- prior result SHA를 split manifest auxiliary file로 고정
- 504일 train, 63일 horizon/rebalance, 10bp cost
- 20% asset cap, 2% rebalance band, 35% turnover cap

## 데이터

- source: Kenneth R. French Data Library 25 Portfolios Formed on Size and Book-to-Market Daily
- construction: annual independent 5×5 size/BM sorts, value weighted
- portfolios: 25개, 기간 내 결측 없음
- price panel: 1998-01-02~2011-12-30, 3,523행
- evaluation: 2000-01-03~2011-12-30
- risk-free: official FRED DGS3MO backward-asof daily equivalent
- raw archives: 기존 로컬 공식 파일 재사용, 외부 다운로드 없음
- split manifest digest: `b5905269…b61cc7c`
- price, factor, provenance, ordered basket, prior-result SHA 검증 통과

## 결과

| Model | CAGR | Volatility | Sharpe | Max DD | Turnover |
|---|---:|---:|---:|---:|---:|
| Equal weight | 7.18% | 23.71% | 0.3158 | -59.14% | 2.51% |
| Historical BL | 6.84% | 23.71% | 0.3026 | -59.49% | 2.45% |
| Minimum variance | 10.55% | 20.53% | 0.4811 | -55.34% | 20.56% |
| Risk parity | 7.74% | 23.20% | 0.3401 | -59.49% | 3.09% |
| Lightweight BL | 6.61% | 23.43% | 0.2941 | -58.44% | 11.31% |
| Constant-correlation minvar | 10.64% | 20.46% | 0.4860 | -54.97% | 20.40% |

| Baseline | P(lower vol) | P(higher Sharpe) | Holm adjusted p |
|---|---:|---:|---:|
| Minimum variance | 96.85% | 83.00% | 0.0630 / 0.1700 |
| Risk parity | 100.00% | 99.95% | 0 / 0.0020 |
| Lightweight BL | 100.00% | 99.95% | 0 / 0.0020 |

- deterministic gate: passed
- six-hypothesis statistical gate: rejected
- promotion eligible: false

## Estimator diagnostics

- rebalance records: `48`
- estimator/optimizer success rate: `100%`
- mean shrinkage intensity: `14.02%`
- minimum/maximum shrinkage intensity: `5.75% / 35.24%`
- fallback rate: `0%`

## 결정

- Candidate는 두 independent universe에서 모든 평균 지표를 같은 방향으로 개선했습니다.
- 그러나 두 번 모두 closest Ledoit-Wolf minvar 대비 Sharpe uplift가 95%에 미달했습니다.
- Risk parity와 current lightweight보다 강하다는 증거만으로 closest risk baseline을 건너뛰지 않습니다.
- Candidate를 production/default로 승격하지 않고 최종 폐기합니다.
- Shrinkage target, train window, cap을 결과에 맞춰 변경하지 않습니다.
- Validation과 locked holdout을 열지 않습니다.

## 구현 및 결과

- replication SHA-chain guard: `tools/research_minvar_promotion.py`
- tests: `tests/test_research_minvar_promotion.py`
- result:
  `data/research/derived/fama_french_25_size_value_constant_correlation_replication_result_v1.json`
