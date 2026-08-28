# FF3 Factor Risk Experiment

- 작업 일시: 2026-08-28 03:07 KST
- 범위: 공개 FF3 factor covariance, research-only GMV, Ledoit-Wolf GMV paired smoke comparison
- 결론: production 유지, 미사용 shadow-forward 추가 검증 필요

## 가설과 production 원칙

종목 excess return을 `r_t = B_t f_t + epsilon_t`로 추정하고 `Sigma_t = B_t F_t B_t' + D_t`를 사용하면 기존 Ledoit-Wolf covariance보다 OOS realized volatility 추정과 GMV 성과가 개선된다는 가설을 검증했습니다. 구현은 backend research model과 CLI에만 추가했습니다. Production `MIN_VARIANCE`, API, UI와 기본 optimizer는 변경하지 않았습니다.

## 데이터와 provenance

- universe: Kenneth French 12 SIC industry value-weighted portfolios, source가 시점별 eligible NYSE/AMEX/Nasdaq 구성종목을 재구성
- 가격 기간: 2019-01-02~2025-12-31, 1,760행 × 12 portfolios
- 평가 기간: 2020-12-31~2025-12-31, 20개 63거래일 rebalance origin
- 가격: `data/research/derived/fama_french_12_industry_prices_2019_2025_forecast_research.csv`
  - SHA-256: `26d3efcbd6711e072d3ba89959dea45aa92d122f7c92808479e66594d33a392d`
- universe manifest: `data/research/derived/fama_french_12_industry_universe_2019_2025_forecast_research.csv`
  - file SHA-256: `358d3342a32952eae64505ebd6b62a19cc66703937140e8efd2fd828e79fd95b`
  - ordered eligible-universe SHA-256: `409362fc5d4e9cd778d93684172cf5b36bd9323518090d3bc8d12d1c131e343f`
- factor/risk-free: Kenneth French daily U.S. `Mkt-RF`, `SMB`, `HML`, `RF`와 backward-asof FRED DGS3MO
- factor file: `data/research/derived/us_market_factors_2007_2025.csv`
  - SHA-256: `015a593a033b3dab0662ef40017956acb85589ce2abd1d8014e4f16e550decd3`
- split: `fama-french-12-industry-ff3-factor-risk-smoke-2021-2025-v1`
  - manifest self-hash: `8061eee3562ad2988d1e76984bc2388841ec17d295755c199f7776e910732e3f`
  - manifest file SHA-256: `9e9e6ebf932c85f005397e52bbf068472483cd114955074ec163b726ffdbbb6d`
  - locked: `true`; promotion-safe: `false`
  - 이유: 같은 origin은 `fama-french-12-industry-conditional-volatility-research-2021-2025-v1`에서 이미 소비됐습니다. 기존 Nasdaq-100 2022–2025 locked holdout은 읽거나 실행하지 않았습니다.

## 고정 사양

- exposure `B`: signal date 이전 504거래일의 asset return에서 French `RF`를 뺀 excess return을 intercept + `Mkt-RF`, `SMB`, `HML`에 OLS; 최소 252개 정렬 관측
- factor covariance `F`: 가장 최근 관측에 더 큰 가중치를 두는 63거래일 half-life EWMA, 25% diagonal shrinkage, 연 252일 환산
- specific risk `D`: 종목별 OLS residual sample variance, cross-sectional median으로 50% shrinkage, daily variance `1e-8` floor, 연 252일 환산
- 최종 covariance: `B F B' + D`, 대칭화, eigenvalue `1e-12` spectral floor, PSD/condition/effective-rank 진단
- fallback: factor 열/관측 부족, rank deficiency, regression/specific variance/covariance 비정상 또는 solver 실패 시 동일 origin Ledoit-Wolf GMV target weight를 그대로 반환하고 reason 기록
- 후보 탐색: 없음. 위 단일 사양을 결과 확인 전에 split manifest에 고정했습니다.

## 공정 비교 계약

Baseline과 candidate는 동일한 12-portfolio universe, 504일 training window, 63일 rebalance/horizon, long-only 20% target cap, 10 bps transaction cost, 2% rebalance band, 35% turnover cap, FRED DGS3MO daily-equivalent risk-free series를 사용했습니다. 각 origin의 training price와 factor는 train end date 이하만 사용했습니다.

## 결과

| Metric | Ledoit-Wolf GMV | FF3 factor-risk GMV |
|---|---:|---:|
| Annual realized volatility | 13.1933% | 12.9661% |
| CAGR | 3.4277% | 4.1087% |
| Sharpe | 0.0731 | 0.1224 |
| Maximum drawdown | -21.4438% | -19.5996% |
| Net cumulative return | 18.2982% | 22.2020% |
| Avg controlled turnover | 14.5745% | 10.8282% |
| Avg concentration HHI | 0.1791 | 0.1915 |
| HHI effective holdings | 5.58 | 5.22 |
| Risk forecast MAE | 5.8050% | 3.3515% |
| Avg realized/predicted vol ratio | 0.8715 | 0.9897 |

Candidate는 point estimate에서 realized volatility를 22.7 bp 낮추고 Sharpe, drawdown, turnover와 risk calibration을 개선했지만 집중도는 높아졌습니다.

### Paired statistical gate

- circular block bootstrap: 2,000 samples, 21거래일 block, seed 42
- P(candidate lower volatility): 92.90%
- P(candidate higher return): 81.90%
- P(candidate higher Sharpe): 81.00%
- 요구 기준: realized volatility와 Sharpe 각각 95%
- Holm-Bonferroni raw/adjusted p-value: 0.1900 / 0.1900; significant `false`
- 판정: statistical gate 탈락

### Factor/covariance diagnostics

- factor covariance 성공: 20/20 origins
- Ledoit-Wolf fallback: 0/20, 실패 원인 없음
- 평균 covariance condition number: 63.1785
- 평균 covariance effective rank: 3.9749
- successive ticker exposure pair: 228
- factor beta 평균 L2 change: 0.05292; median 0.04029
- mean absolute beta change: market 0.02603, SMB 0.02812, HML 0.02380

## 제한사항

- 이 비교는 이미 소비된 origin의 non-promotion smoke이며 fresh validation이 아닙니다. 개선 수치를 promotion이나 파라미터 선택 근거로 사용할 수 없습니다.
- French industry portfolios는 시점별 구성종목을 반영해 단순 current-constituent survivorship bias를 줄이지만 개별 상장폐지 종목의 identity, delisting return, 거래 가능성, 스프레드와 시장충격을 직접 모델링하지 않습니다.
- 공개 French/FRED 자료의 재배포·상업 사용 조건과 개별 가격 라이선스는 production 데이터 계약과 별도로 확인해야 합니다.
- SEC filing-date PIT fundamental을 사용하지 않았으므로 SEC 정정공시, issuer/ticker identity, taxonomy와 공시 품질 문제를 해결하는 모델이 아닙니다.
- 12개 industry portfolio 결과를 개별주 universe, 위기 tail 또는 해외자산에 일반화할 수 없습니다.
- factor exposure는 rolling OLS point estimate이며 coefficient uncertainty와 dynamic beta state model을 포함하지 않습니다.

## 최종 결정

FF3 factor-risk GMV는 point estimate에서는 기존 Ledoit-Wolf GMV를 개선했지만 paired 95% 및 Holm gate를 통과하지 못했고 split도 fresh하지 않습니다. 따라서 자동 승격하지 않고 production Ledoit-Wolf GMV를 유지합니다. 이후 사양을 변경하지 않은 shadow-forward 검증은 `docs/reports/260828-0359-01-ff3-factor-risk-shadow-forward-validation.md`에서 완료했으며 candidate는 다시 탈락했습니다.

## 산출물과 검증

- result: `data/research/derived/fama_french_12_industry_ff3_factor_risk_smoke_result_v1.json`
  - SHA-256: `3a5af72df0206582eb0c1a7a8f64e908f6ede20594e5961a61db43041fe0619b`
- summary: `data/research/derived/fama_french_12_industry_ff3_factor_risk_smoke_result_v1.md`
- targeted/related: `PYTHONPATH=src/backend .venv/bin/python -m pytest -q tests/test_ff3_factor_risk_model.py tests/test_portfolio_risk_models.py tests/test_research_risk_allocators.py tests/test_forecast_gmv_pipeline.py tests/test_research_split.py tests/test_portfolio_backtest.py` → `148 passed`
- 전체 backend: `PYTHONPATH=src/backend .venv/bin/python -m pytest -q tests` → `418 passed in 95.99s`
- deterministic CLI rerun: result SHA-256 동일
- 문서 링크/TODO index, manifest/result SHA-256과 `git diff --check`를 별도 확인했습니다.
