# DFL Covariance Reproduction Closure

- 작업 일시: 2026-08-12 01:38 KST
- 범위: Decision-Focused Learning covariance estimation, unconstrained GMV paper reproduction, conditional Antifier long-only transfer
- 최종 결정: **REJECT**
- Production 기본값: 기존 Ledoit-Wolf `MIN_VARIANCE` 유지
- 증거 성격: paper reproduction/diagnostic only, promotion safe 아님

## 결정 요약

Checkpoint 1에서 DFL은 동일 backbone PFL보다 실현 변동성을 크게 낮췄지만 가장 강한 shrinkage baseline인 OAS를 이기지 못했다. 사전 등록한 stop rule에 따라 Checkpoint 2의 long-only constrained solver, transaction cost, turnover control, paired bootstrap는 실행하지 않았다. 탈락한 후보를 같은 test 결과에 맞춰 다시 튜닝하지 않았고 fresh-validation TODO도 만들지 않았다.

## Checkpoint 0: 고정 계약과 데이터 감사

- source: Kenneth R. French Data Library, `Average Value Weighted Returns -- Daily`
- raw archive: `data/research/raw/market_factors/49_Industry_Portfolios_daily_CSV.zip`
- raw archive coverage: 1926-07-01~2026-05-29, 26,253 rows, 49 ordered industries
- paper interval 내 missing value: 0
- ordered universe hash: `cad36f71a324c4cf9a24bde8f184f792bc2c499b6be218b9de1ec943848b4ad9`
- locked train/validation/test samples: 2,029 / 641 / 11
- labels: signal date 다음 거래일부터 63일, 각 partition end 이내
- lookahead violation: 0

같은 49-industry archive를 사용한 기존 consumed split은 다음과 같다.

- 2000-2010 RMT research
- 2011-2017 dual-momentum research
- 2018-2021 trend-risk-parity validation

특히 published test interval 일부가 기존 2018-2021 validation과 겹치므로 이 실행은 fresh promotion evidence가 아니다.

## 재현한 paper 요소

- fixed ordered French 49-industry universe
- input window 21 trading days
- forecast/holding horizon 63 trading days
- paper가 명시한 train 2010-01-05~2018-05-24, validation 2018-05-25~2021-03-12, test 2021-03-15~2023-12-29 partition
- train/validation 1-day rolling, test 63-day step
- moving-average kernel 7, hidden dimension 128의 최소 DLinear-style backbone
- lower-triangular `L` output과 `L @ L.T + 1e-5 * I` covariance
- Adam, learning rate `1e-4`, batch 32, 최대 50 epochs, patience 7
- 동일 samples/backbone/seeds를 쓰는 covariance-MSE PFL과 GMV decision-variance DFL
- unconstrained analytic GMV를 explicit inverse가 아닌 linear solve로 계산
- five predefined deterministic seeds: 7, 19, 42, 73, 101
- equal weight, historical sample covariance, Ledoit-Wolf constant variance, Ledoit-Wolf constant correlation, OAS baseline

## Paper와의 차이

학습 전에 manifest에 다음 차이를 고정했다.

1. 저자들이 사용한 원본 archive vintage와 source code를 확보하지 못했다. 2026-07-23에 저장한 공식 French archive를 사용했다.
2. Paper 본문은 returns가 2024년까지라고 설명하지만 명시된 test partition은 2023-12-29에 끝난다. 명시된 partition을 우선해 2024년은 사용하지 않았다.
3. Paper는 DLinear에서 Cholesky output으로 이어지는 head 전체를 설명하지 않는다. Trend/seasonal decomposition을 concatenate/flatten한 뒤 128-unit ReLU hidden layer와 triangular output을 쓰는 최소 head를 두 arm에 동일하게 고정했다.
4. Validation/test feature는 오직 과거인 이전 partition row를 context로 사용할 수 있지만 label은 항상 signal 뒤에 있고 해당 partition 안에서 끝나도록 했다.
5. 목표 계약에 따라 `1e-5 I`를 inversion 시점뿐 아니라 predicted covariance 자체에 포함했다.
6. Paper의 정확한 random seeds가 공개되지 않아 실행 전에 별도 deterministic seeds를 고정했다.

따라서 아래 결과는 paper claim의 exact reproduction이 아니라 가장 가까운 provenance-safe diagnostic reproduction이다.

## Checkpoint 1 결과

Primary metric은 11개 non-overlapping test holding period의 annualized realized volatility 평균이다.

| Model | Mean realized volatility |
|---|---:|
| Equal weight | 17.3487% |
| Historical sample covariance GMV | 16.2324% |
| Ledoit-Wolf constant correlation GMV | 14.0167% |
| Ledoit-Wolf constant variance GMV | 13.2244% |
| OAS GMV | **13.1749%** |
| PFL, five-seed mean ± std | 27.8908% ± 2.0025% |
| DFL, five-seed mean ± std | 13.8941% ± 0.3695% |

Seed별 결과:

| Seed | PFL volatility | DFL volatility |
|---:|---:|---:|
| 7 | 27.1132% | 14.0025% |
| 19 | 24.9333% | 13.5228% |
| 42 | 28.2407% | 14.4821% |
| 73 | 31.1400% | 13.9907% |
| 101 | 28.0269% | 13.4723% |

DFL은 PFL보다 13.9967 percentage points 낮았지만 OAS보다 0.7192 percentage points 높았다. 다섯 seed가 모두 완료됐고 model numerical fallback은 0이었다. Predicted covariance의 최소 eigenvalue도 전 실행에서 양수였다.

### Prediction loss와 decision loss의 차이

| Diagnostic, five-seed mean | PFL | DFL |
|---|---:|---:|
| Period variance, percent-return squared | 3.5473 | 0.8320 |
| Covariance Frobenius error | **67.1822** | 104.6624 |
| Weight concentration | 3.2539 | **0.2672** |
| Gross turnover sum | 88.1668 | **16.5267** |

DFL은 covariance Frobenius error가 더 나쁜데도 PFL보다 portfolio variance를 낮췄다. 이는 decision loss가 prediction loss와 다른 방향을 학습할 수 있다는 가설과 일치한다. 그러나 practical candidate gate는 PFL만 이기는 것으로 충분하지 않고 strongest shrinkage baseline도 이겨야 하므로 최종 후보는 탈락이다. PFL이 paper의 Industry 결과보다 크게 나쁜 점도 exact reproduction이 아니라는 제한으로 남긴다.

## Checkpoint 1 gate

- DFL < identical-backbone PFL: PASS
- DFL < strongest shrinkage baseline: **FAIL** (`13.8941% > 13.1749%` OAS)
- five seeds complete: PASS
- lookahead violation 0: PASS
- model numerical fallback 0: PASS
- Checkpoint 1 decision: **REJECT**

## Unconstrained와 long-only behavior

Unconstrained 결과만 관측했다. 이 결과에서 DFL은 PFL보다 낮은 concentration과 turnover를 보였지만 OAS보다 낮은 volatility를 만들지는 못했다.

Checkpoint 1 탈락으로 Antifier long-only capped solver에는 covariance를 공급하지 않았다. 따라서 다음 값은 0이 아니라 **미측정/미실행**이다.

- long-only 20% cap 이후 DFL behavior
- 2% rebalance band와 35% turnover cap 효과
- 10 bps transaction-cost drag
- net Sharpe, max drawdown, cumulative return
- predicted/realized volatility bias와 MAE
- Ledoit-Wolf 대비 paired 21-day circular block bootstrap
- 2,000-sample probability와 Holm-Bonferroni gate

Train/decision constraint mismatch는 이번 후보에서 평가할 단계까지 도달하지 못했다. Stop rule을 어기고 differentiable QP나 추가 architecture를 도입하지 않았다.

## Determinism, runtime, memory

같은 locked manifest/configuration으로 전체 command를 두 번 실행했다.

- prediction NPZ SHA-256: 두 실행 모두 `15ef48528497b9944b468074591e93ea943ba23a8816b92eea31285ad5c09777`
- prediction content SHA-256: 두 실행 모두 `00e2a3c2a8ab5a055425b4fdeeb01586597ba052544b0b1a5bfba4cebd441003`
- runtime/peak-memory와 첫 실행의 boolean serialization 표현만 정규화한 result SHA-256: 두 실행 모두 `097dfd38b756d2766e962c57c1d3919f08dc233078d51a361020341db366be3d`
- final rerun의 10 fits 총 runtime: 587.98 seconds
- 최대 peak Python allocation: 42,985,949 bytes

Runtime과 `tracemalloc` peak는 환경 상태에 따라 달라지는 측정치다. Covariance predictions, metrics, seed losses/epochs, gate, artifact content는 동일했다. Peak memory는 TensorFlow native allocator 전체가 아니라 Python allocations 기준이다.

## Artifacts와 hashes

| Artifact | SHA-256 |
|---|---|
| Paper PDF | `01e0e06461a881dae355d959ddee2c075a584d5b8f45a8e6513e8e02fd3d8d9c` |
| French raw data archive | `e214c54a41f058c03ed4a4e582b2126e04120d2a84bc19c023bd2a4251f77097` |
| Locked configuration | `f3b98bb184ee9ecf826d592aae68c35fae0e00e310226b179fb7a37f6a38df4b` |
| Locked manifest file | `fc630018440760b8fbf9a62235228a27133592c488a11613a1954032672c481a` |
| Manifest canonical self-digest | `5c45e052a05b1d72f7b8f22ebbf43af5499cacd3b5e0e355d7a5c7440f0423d8` |
| Frozen predictions | `15ef48528497b9944b468074591e93ea943ba23a8816b92eea31285ad5c09777` |
| Machine-readable result | `eadc987f3178b3746a5132f264a746db741685b4274775d4c887dcaf6c0d5806` |
| Human-readable result | `2f7d83e7da1c9222c1c40701efa413dc0918d74a4fc4541780e7d2105e55a364` |

## 구현과 검증

- research CLI: `tools/research_dfl_covariance.py`
- focused regression tests: `tests/test_research_dfl_covariance.py`
- DFL contract suite: 6 passed
- affected DFL/risk/backtest/statistics/split suite: 148 passed
- TensorFlow mock leakage order regression: 49 passed
- full backend: 390 passed in 257.03 seconds
- deterministic full research rerun: passed
- frontend checks: 미실행, frontend 변경 없음

## Production default 유지 이유

Candidate가 closest shrinkage baseline을 이기지 못했고 practical long-only gate도 열리지 않았다. 데이터도 reproduction split이며 fresh promotion evidence가 아니다. 따라서 production `MIN_VARIANCE`, public API, frontend, differentiable optimizer dependency를 모두 변경하지 않았다.

REJECT는 사전 등록된 성공적인 terminal outcome이다. 근거 있는 미해결 blocker가 없으므로 speculative follow-up TODO를 추가하지 않는다.
