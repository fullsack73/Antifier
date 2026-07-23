# Lightweight OOS-Uncertainty Research

- 일시: 2026-07-24 03:20 (KST)
- 작성자: Codex
- 에이전트: Codex
- 작업 유형: forecast uncertainty / portfolio construction research
- 상태: 후보 폐기

## 요약

- 현재 lightweight ensemble의 point forecast와 고정 ensemble weight는 변경하지 않았습니다.
- fixed `20%` uncertainty를 training window 안에서 완료된 OOS residual RMSE로 교체하는 후보를 구현했습니다.
- realized volatility, drawdown, turnover는 개선됐지만 return, Sharpe, signal-quality gate를 통과하지 못했습니다.
- 후보를 폐기하고 validation과 public default를 변경하지 않습니다.

## 데이터

- source: Kenneth R. French Data Library
- official URL: `https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/17_Industry_Portfolios_daily_CSV.zip`
- construction: annual SIC assignment, NYSE/AMEX/NASDAQ stocks, value-weighted daily returns
- raw ZIP: `1,505,679 bytes`
- raw SHA-256: `ba836c55…80ab8`
- price panel: `1969-01-02~1999-12-31`, `7,832행 × 17 portfolios`
- price SHA-256: `c0815e9d…2ee49`
- historical RF: official French daily one-month Treasury-bill return
- RF SHA-256: `fffb3740…823b5`
- evaluation: `1971-01-04~1999-12-31`
- split manifest digest: `fe71a75f…d8ae0`
- physical split SHA-256: `290fd369…366b`
- `2000~2011` validation과 `2012+` holdout은 열지 않았습니다.

## 고정 후보

- candidate: `calibrated_lightweight_bl`
- baseline: `lightweight_bl`
- train window: `504 trading days`
- rebalance/horizon: `63/63 trading days`
- point forecast: existing lightweight ensemble, unchanged
- calibration origin: completed non-overlap horizons only
- minimum origin history: `126 trading days`
- maximum completed origins: `6`
- uncertainty estimator: annualized OOS residual RMSE
- shrinkage: `50% × 20%² prior variance + 50% × OOS RMSE²`
- transaction cost: `10 bps`
- rebalance band / turnover cap: `2% / 35%`
- max asset weight: `20%`
- bootstrap: `2,000`, circular `21-day` blocks

## 결과

| Model | CAGR | Volatility | Sharpe | Max DD | Avg turnover |
|---|---:|---:|---:|---:|---:|
| Current lightweight BL | 13.10% | 13.36% | 0.5100 | -43.97% | 6.53% |
| OOS-calibrated lightweight BL | 13.09% | 13.09% | 0.5169 | -43.27% | 2.15% |
| Equal weight | 12.95% | 13.04% | 0.5093 | -42.46% | 1.76% |
| Risk parity | 13.26% | 12.88% | 0.5347 | -43.81% | 2.11% |

- P(lower volatility): `100.00%`
- P(higher return): `39.40%`
- P(higher Sharpe): `71.05%`
- Holm-adjusted return p-value: `0.6060`
- Holm-adjusted Sharpe p-value: `0.5790`
- candidate mean rank IC: `0.02231`
- candidate positive rank-IC rate: `54.70%`
- candidate mean top-bottom spread: `-0.000407`
- deterministic gate: rejected
- statistical gate: rejected
- promotion eligible: false

## Calibration 진단

- ticker × rebalance calibration count: `1,989`
- completed observations per calibration: `6`
- mean raw annualized OOS RMSE: `0.5751`
- median raw annualized OOS RMSE: `0.5332`
- 90th percentile raw annualized OOS RMSE: `0.9130`
- constant `20%` uncertainty가 실제 forecast error를 크게 과소평가한다는 진단은 확인됐습니다.

## Audit 수정

- BL raw absolute view를 backtest `signal_scores`로 전달합니다.
- 이전에는 lightweight/BL raw signal이 존재해도 rank IC와 top-bottom spread가 `NA`였습니다.
- 수정 후 posterior/weight가 아니라 raw view와 realized forward return을 비교합니다.
- 이 수정은 point forecast, uncertainty, BL posterior, weight를 변경하지 않습니다.

## 결정

- OOS uncertainty calibration 구현은 유지합니다.
- `calibrated_lightweight_bl`은 research-only model로 유지하고 default 승격하지 않습니다.
- 같은 split에서 uncertainty prior, shrinkage, origin count, horizon을 재튜닝하지 않습니다.
- validation과 holdout을 실행하지 않습니다.
- Transformer hyperparameter 확장 근거로 사용하지 않습니다.

## 검증

- future-row mutation no-lookahead test: passed
- completed-origin boundary test: passed
- BL raw-view signal diagnostics regression test: passed
- focused backend tests: `49 passed`
