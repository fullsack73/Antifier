# TODO - Portfolio Risk Model Research

- 등록 일시: 2026-07-23 20:40 (KST)
- 작성자: Codex
- 에이전트: Codex
- 현재 상태: constant-correlation shrinkage가 독립 복제에서도 closest minvar 통계 gate 탈락

> 완료된 TODO는 이 파일을 삭제하고, `docs/reports/`에 작업 기록을 남깁니다.

## 배경

- 기존 backtest와 optimizer는 Ledoit-Wolf shrinkage covariance를 사용해 sample covariance보다 안정적인 기본선을 이미 갖고 있습니다.
- 2005-2013 sector ETF research split에서 Ledoit-Wolf 50%, OAS 30%, 180일 exponential covariance 20% blend minimum variance가 기존 minimum variance보다 CAGR, volatility, Sharpe, max drawdown을 모두 소폭 개선했습니다.
- specification을 freeze해 기존 4-case validation에 보냈지만 defensive case만 통과하고 전체 1/4로 탈락했습니다.
- validation 결과를 이용해 blend weight/span을 재튜닝하지 않습니다.

## 완료 기반

- exact capped-simplex long-only weight projection
- covariance PSD/condition number/effective-rank diagnostics
- robust shrinkage/exponential covariance blend research candidate
- exact equal-risk-contribution SLSQP allocator
- hierarchical risk parity allocator
- research-only risk comparison CLI
- frozen candidate 4-case validation CLI

## 다음 연구

- validation과 겹치지 않는 새 research universe/period에서 covariance estimator error와 realized risk forecast error를 직접 측정합니다.
- covariance half-life와 estimator blend는 nested research walk-forward 안에서만 선택합니다.
- 현재 구현한 hard regime switch는 fresh research에서 baseline을 이기지 못했으므로 폐기하거나 continuous shrinkage로 재설계합니다.
- nested estimator selection은 volatility와 drawdown을 낮췄지만 Sharpe 하락과 turnover 증가로 탈락했습니다. estimator 선택보다 covariance ensemble과 weight stability penalty를 우선 연구합니다.
- volatility targeting, drawdown budget, correlation shock stress를 risk-only gate에 추가합니다.
- 새 specification을 freeze한 뒤에만 4-case validation을 다시 실행합니다.
- 모든 validation을 통과하기 전 locked holdout은 실행하지 않습니다.

## 2026-07-23 추가 연구

- style/value/growth/small/mid/credit/REIT ETF 10종, 2008-2013 fresh research split을 사용했습니다.
- robust minimum variance는 Ledoit-Wolf보다 volatility `0.1091 < 0.1092`, Sharpe `0.9998 > 0.9974`, max drawdown `-0.1274 > -0.1278`로 미세 우위였지만 기존 frozen validation 탈락 결정을 뒤집지 않습니다.
- regime minimum variance와 historical minimum-CVaR는 가장 가까운 minimum-variance baseline을 통과하지 못했습니다.
- train-window 내부 252/63 nested walk-forward로 Ledoit-Wolf/OAS/exponential 60/180/static blend를 고르는 후보는 volatility `0.1065`, max drawdown `-0.1260`으로 개선했지만 Sharpe `0.9186`으로 하락했고 average controlled turnover가 `0.2296`으로 증가해 탈락했습니다.
- Transformer hyperparameter 확장보다 risk-estimation error, portfolio construction stability, signal target/data quality를 먼저 개선합니다.

## 2026-07-23 통계/PIT 추가

- predicted-versus-realized period volatility의 bias, MAE, ratio를 추가했습니다.
- paired 21일 circular block bootstrap 2,000회에서 volatility와 Sharpe 개선 확률 95%를 요구합니다.
- 동일 split의 동시 후보 비교는 Holm-Bonferroni family-wise correction을 적용합니다.
- country ETF research에서 deterministic gate를 통과했던 robust/ERC/regime/minimum-CVaR도 Sharpe 개선 확률이 각각 `74.10%`, `82.60%`, `83.65%`, `80.25%`에 그쳐 모두 탈락했습니다.
- stability-regularized, resampled minimum variance와 inverse-vol scaled momentum도 별도 fresh research에서 탈락했습니다.
- continuous regime covariance v2는 절대 상관 임계치를 제거하고 normal Ledoit-Wolf에서 stress covariance로 연속 혼합했지만 fresh industrial-stock research에서 baseline을 이기지 못했습니다.
- OOS covariance ensemble은 252/63 inner fold에서 Ledoit-Wolf, OAS, exponential 60/180, static blend의 covariance/correlation/variance-calibration loss를 점수화하고 soft weight로 결합합니다.
- fixed-income ETF 8종 2008-2013 fresh research에서 504일 outer train을 사용했을 때 volatility `0.0273 < 0.0280`, Sharpe `0.5265 > 0.5119`, max drawdown `-0.0545 > -0.0548`로 deterministic 개선했습니다.
- 그러나 paired bootstrap에서 lower-volatility 확률은 `99.50%`, higher-Sharpe 확률은 `62.60%`에 그쳐 95% joint gate와 Holm correction을 통과하지 못했습니다. validation은 실행하지 않습니다.
- 252일 outer train은 252/63 inner fold를 만들 수 없어 Ledoit-Wolf fallback과 동일해집니다. research CLI는 이 후보에 `train_window >= 315`를 강제합니다.

## 2026-07-23 nested weight shrinkage

- 새 global multi-asset basket `SPY/EFA/EEM/IEF/TLT/LQD/HYG/GLD/DBC/VNQ`
  2008-2016 가격 2,267행을 SHA provenance와 함께 생성했습니다.
- research basket, 가격 SHA, 실행 설정, 단일 candidate를 split digest
  `cb0ca2c7…c091`로 실행 전에 잠갔습니다.
- `nested_blended_min_variance`는 최소분산과 inverse-vol weight의 blend
  `[0, .25, .5, .75, 1]`을 252/63 completed inner realized variance로
  선택합니다.
- Ledoit-Wolf minimum variance 대비 annual volatility는
  `0.05010→0.04939`, max drawdown은 `-0.09377→-0.09211`,
  risk forecast MAE는 `0.01767→0.01728`로 개선했습니다.
- lower-volatility bootstrap probability는 `99.75%`였습니다.
- 그러나 Sharpe는 `0.6857→0.6561`, higher-Sharpe probability는
  `13.95%`로 하락했습니다. deterministic/statistical/Holm gate에서
  모두 탈락했고 validation은 실행하지 않습니다.
- 고정 2% Sharpe 평가를 FRED DGS3MO daily-equivalent curve로 교체했습니다. 2009-2016 실현 risk-free는 연율 `0.1058%`, date coverage는 `100%`입니다.
- historical-RF corrected Sharpe는 baseline `1.0605`, nested `1.0376`, paired higher-Sharpe probability `19.20%`로 결론은 동일합니다.

## 2026-07-24 stress/cash research

- baseline/recent/correlation-volatility-shock covariance의 최악 분산을 직접 최소화하는 scenario-robust allocator를 추가했습니다.
- 2008~2016 locked research에서 scenario 후보는 Ledoit baseline보다 volatility `5.0096%→5.0833%`, Sharpe `1.0605→1.0126`, drawdown `-9.3766%→-9.8683%`로 모두 열위여서 폐기했습니다.
- 부분 위험노출 보존과 point-in-time FRED cash accrual을 backtest에 추가했습니다.
- 최초 현금 배치를 turnover cap이 막던 truth bug를 수정했습니다. 초기 매수 비용은 부과하지만 rebalance band/turnover cap은 적용하지 않습니다.
- fresh 2017~2025 global multi-asset 10종 2,262행을 다운로드하고 corrected split digest `090da876…2509`로 잠갔습니다.
- training-only volatility target은 volatility `7.7361%→6.7285%`, max drawdown `-17.5973%→-14.7976%`, CVaR `1.1366%→0.9909%`로 개선했습니다.
- 그러나 Sharpe는 `0.5083→0.4449`, P(higher Sharpe)는 `19.80%`라 탈락했습니다. target ratio/floor/lookback을 같은 split에서 재튜닝하지 않습니다.

## 참고

- 결과 보고서: `docs/reports/260723-2040-01-risk-allocator-research.md`
- cash/volatility-target 보고서: `docs/reports/260724-0039-01-risk-cash-volatility-target.md`
- RMT denoising 보고서: `docs/reports/260724-0121-01-rmt-covariance-research.md`

## 2026-07-24 risk-momentum construction

- Official French 12-industry `1970~1999` fresh split에서 inverse-vol risk parity와 raw 12-1 momentum rank tilt를 fixed 50/50으로 결합했습니다.
- Blend volatility/Sharpe `13.36%/0.5610`은 risk parity `13.06%/0.5581`과 momentum `13.68%/0.5893` 사이에 머물렀습니다.
- P(lower volatility/higher Sharpe)는 risk parity 대비 `0%/59.00%`, momentum 대비 `100%/4.35%`였습니다.
- 두 component를 동시에 개선하지 못해 기각하며 blend weight를 같은 split에서 재튜닝하지 않습니다.

## 2026-07-24 minimum-variance/momentum construction

- Official French 10-industry `1970~1999` fresh split에서 Ledoit-Wolf minimum variance와 raw momentum rank tilt를 fixed 50/50으로 결합했습니다.
- Plain minimum variance volatility/Sharpe `11.95%/0.6829`가 blend `12.70%/0.6325`, momentum `13.67%/0.5878`보다 강했습니다.
- Blend의 P(higher Sharpe)는 minvar 대비 `6.45%`, momentum 대비 `94.10%`였고 six-hypothesis Holm gate를 통과하지 못했습니다.
- Blend를 폐기하고 plain Ledoit minimum variance를 current default 대비 fresh promotion research candidate로 검증합니다.

## 2026-07-24 plain minimum-variance promotion research

- Official French 10-industry `2000~2011` fresh split에서 long-only Ledoit-Wolf minimum variance를 current `lightweight_bl`, risk parity, equal weight, historical BL과 비교했습니다.
- Candidate volatility/Sharpe `17.34%/0.3254`는 lightweight `20.00%/0.1834`, risk parity `18.65%/0.2551`보다 우수했고 deterministic gate를 통과했습니다.
- Lightweight 대비 P(lower volatility/higher Sharpe)는 `100%/97.95%`로 통과했습니다.
- Risk parity 대비 P(lower volatility/higher Sharpe)는 `100%/91.50%`였고 higher-Sharpe Holm-adjusted p-value `0.0850`으로 statistical gate를 통과하지 못했습니다.
- Default allocator를 변경하지 않습니다. 동일 split에서 train window, cap, covariance estimator를 재튜닝하지 않고 validation/holdout을 봉인합니다.
- 보고서: `docs/reports/260724-0612-01-plain-minvar-promotion-research.md`

## 2026-07-24 nested clustered optimization research

- Nested Clustered Optimization을 research-only allocator로 추가했습니다.
- Training-only Ledoit-Wolf correlation distance에 average linkage를 적용하고, cluster 수는 `2..min(10,n-1)` 중 silhouette가 최대인 값을 선택합니다.
- 각 cluster 내부와 cluster portfolio 간에 long-only minimum variance를 순차 적용한 뒤 동일 asset cap과 execution control을 적용합니다.
- Official French 38-industry source의 장기 결측 8개를 exact-name으로 제외한 30개 portfolio `1929~1969` fresh research split을 SHA로 잠갔습니다.
- NCO volatility/Sharpe `11.76%/0.5671`은 minvar `11.83%/0.5933`보다 volatility만 미세하게 낮았습니다.
- Minvar 대비 P(lower volatility/higher Sharpe)는 `86.65%/13.90%`, risk parity 대비 `100%/85.00%`, lightweight 대비 `100%/84.55%`였습니다.
- 176회 전부 optimizer는 성공했지만 silhouette가 항상 2개 cluster를 골랐고 종종 단일 산업을 분리했습니다. 평균 pre-cap max weight `49.05%`, cap projection L1 distance `67.54%`로 hierarchy가 execution cap과 강하게 충돌했습니다.
- Deterministic 및 six-hypothesis Holm gate에서 탈락했습니다. Linkage, cluster-count range, covariance estimator를 같은 split에서 재튜닝하지 않습니다.
- Validation/holdout은 열지 않고 default allocator를 유지합니다.
- 보고서: `docs/reports/260724-0623-01-nco-minvar-research.md`

## 2026-07-24 constant-correlation shrinkage research

- 기존 `constant_variance` Ledoit-Wolf baseline과 다른 `constant_correlation` shrinkage target을 parameter-free risk-only candidate로 추가했습니다.
- Official French 38-industry source에서 결측 5개를 exact-name 제외한 33개 portfolio `1971~1980` fresh split을 SHA로 잠갔습니다.
- Candidate volatility/Sharpe `10.24%/0.3729`는 minvar `10.33%/0.3514`, risk parity `12.17%/0.2038`, lightweight `13.33%/0.2535`보다 우수해 deterministic gate를 통과했습니다.
- P(lower volatility)는 세 baseline 모두 `100%`였지만 P(higher Sharpe)는 `89.85%/85.65%/76.90%`였습니다.
- Minvar higher-Sharpe Holm-adjusted p-value는 `0.3045`로 statistical gate를 통과하지 못했습니다.
- 평균 shrinkage intensity는 `9.10%`, 범위는 `5.45%~16.65%`, optimizer 성공률은 `100%`였습니다.
- Default를 변경하지 않고 shrinkage target 재탐색과 validation/holdout 실행을 금지합니다.
- 보고서: `docs/reports/260724-0636-01-constant-correlation-minvar-research.md`

## 2026-07-24 constant-correlation independent replication

- Prior result SHA, candidate policy, deterministic pass를 새 manifest auxiliary lineage로 강제하는 replication guard를 promotion runner에 추가했습니다.
- Candidate specification을 변경하지 않고 official French 25 size×B/M portfolio `2000~2011`에서 독립 복제했습니다.
- Candidate volatility/Sharpe `20.46%/0.4860`은 minvar `20.53%/0.4811`, risk parity `23.20%/0.3401`, lightweight `23.43%/0.2941`보다 평균적으로 우수했습니다.
- Risk parity/lightweight 대비 P(lower volatility/higher Sharpe)는 `100%/99.95%`로 통과했습니다.
- Closest minvar 대비 P(lower volatility/higher Sharpe)는 `96.85%/83.00%`, Holm-adjusted p-value는 `0.0630/0.1700`이었습니다.
- 두 independent universe에서 deterministic 방향은 반복됐지만 closest-baseline Sharpe uplift를 95%로 증명하지 못했습니다.
- Candidate를 최종 폐기하고 validation/holdout을 봉인합니다.
- 보고서: `docs/reports/260724-0643-01-constant-correlation-replication.md`

## 2026-07-24 RMT research

- 공식 Kenneth French 49-industry value-weighted daily portfolio를 survivorship-safe fresh research source로 사용했습니다.
- 1998~2010 가격 index 3,271행과 historical FRED risk-free를 source/hash lock하고 2000~2010만 평가했습니다.
- Marchenko-Pastur threshold로 매 rebalance에서 49개 중 46~47개 correlation eigenvalue를 noise로 분류해 평균화하고 Ledoit-Wolf variance diagonal과 재조합했습니다.
- RMT 후보는 Ledoit-Wolf minimum variance보다 volatility `15.22%→15.33%`, Sharpe `0.4227→0.3882`, drawdown `-43.55%→-43.70%`로 모두 열위였습니다.
- paired P(lower volatility/higher Sharpe)는 `3.15%`/`21.0%`여서 폐기합니다. 같은 2000~2010 구간에서 threshold 또는 blend를 재튜닝하지 않습니다.

## 2026-07-24 trend-filter research

- 공식 French 49-industry 1983~1999 fresh research에서 252일 positive absolute-trend filter를 Ledoit-Wolf minimum variance에 고정 적용했습니다.
- historical DGS3MO cash를 포함해 volatility `10.70%→8.79%`, Sharpe `0.4301→0.4957`, drawdown `-31.77%→-28.48%`로 deterministic 개선했습니다.
- P(lower volatility)는 `100%`였지만 P(higher Sharpe)는 `73.45%`로 95% gate와 Holm correction을 통과하지 못했습니다.
- 같은 기간에서 lookback, threshold, cash floor를 재튜닝하지 않고 validation을 열지 않습니다.
- 보고서: `docs/reports/260724-0138-01-trend-filtered-minvar-research.md`

## 2026-07-24 trend-filtered risk parity research

- DGS3MO 이전 구간을 위해 official French daily one-month Treasury-bill RF를 명시적으로 선택하는 research path를 추가했습니다.
- French 49-industry 1973~1981 fresh research에서 252일 positive-trend filter를 inverse-volatility risk parity에 고정 적용했습니다.
- volatility `13.53%→7.43%`, Sharpe `0.1738→0.3544`, drawdown `-43.34%→-14.54%`로 deterministic 개선했습니다.
- P(lower volatility)는 `100%`였지만 P(higher Sharpe)는 `75.55%`로 95% gate와 Holm correction을 통과하지 못했습니다.
- 같은 기간에서 lookback, threshold, exposure floor를 재튜닝하지 않고 validation을 열지 않습니다.
- 보고서: `docs/reports/260724-0145-01-trend-filtered-risk-parity-research.md`

## 2026-07-24 independent trend replication

- official French 30-industry 1928~1971 장기표본을 새로 확보하고 기존 49-industry 결과와 기간·universe가 겹치지 않게 잠갔습니다.
- candidate specification은 252일 positive trend, inverse-vol sleeve, inactive historical RF cash로 변경하지 않았습니다.
- risk parity 대비 volatility `15.24%→9.74%`, Sharpe `0.4909→0.7237`, drawdown `-82.70%→-37.77%`로 개선했습니다.
- P(lower volatility/higher Sharpe)는 `100%`/`98.60%`, Holm-adjusted p-value는 `0.0140`으로 모든 research gate를 통과했습니다.
- candidate를 freeze하고 untouched 2018~2021 validation 전에는 사양을 변경하지 않습니다.
- 보고서: `docs/reports/260724-0153-01-trend-risk-parity-replication.md`

## 2026-07-24 frozen validation

- frozen candidate와 source result SHA를 고정하고 untouched French 49-industry 2018~2021 validation을 실행했습니다.
- 전체에서 volatility와 drawdown은 개선했지만 Sharpe `0.6752→0.4969`, P(higher Sharpe) `2.05%`로 명확히 악화됐습니다.
- defensive, cyclical, technology/services, real-assets/financials 4개 case가 모두 Sharpe gate에서 탈락해 `0/4`였습니다.
- candidate를 폐기하고 validation 결과로 trend lookback, threshold, exposure floor를 재튜닝하지 않습니다.
- 2022+ locked holdout은 열지 않았습니다.
- 보고서: `docs/reports/260724-0159-01-trend-risk-parity-validation.md`

## 2026-07-24 maximum-diversification research

- Ledoit-Wolf covariance에서 가중 개별 변동성/포트폴리오 변동성 비율을 최대화하는 long-only allocator를 추가했습니다.
- official French 25 size×book-to-market value-weighted daily portfolios의 1971~1999 평가 구간을 새 namespace와 SHA-locked split으로 고정했습니다.
- risk parity 대비 volatility `11.66%→11.50%`, Sharpe `0.7188→0.7387`, drawdown `-46.91%→-42.67%`로 deterministic gate는 통과했습니다.
- P(lower volatility)는 `99.95%`였지만 P(higher Sharpe)는 `75.55%`, Holm-adjusted p-value는 `0.2445`로 95% statistical gate를 통과하지 못했습니다.
- 후보를 폐기하고 같은 1971~1999 split에서 covariance, cap, train window, rebalance 설정을 재튜닝하지 않습니다.
- validation은 열지 않았고 기본 allocator는 변경하지 않습니다.
- 보고서: `docs/reports/260724-0217-01-maximum-diversification-research.md`

## 2026-07-24 online allocator ensemble research

- official French 10-industry의 fresh 1928~1969 research panel과 historical French RF를 SHA-locked split으로 고정했습니다.
- equal-weight, Ledoit-Wolf minimum variance, inverse-vol risk parity, 6-month momentum을 completed 252/63 inner fold의 return rank로만 결합하는 parameter-free Hedge allocator를 추가했습니다.
- candidate는 momentum baseline 대비 volatility `17.08%→15.79%`, average controlled turnover `32.10%→16.17%`, drawdown `-79.47%→-79.03%`로 개선했습니다.
- 그러나 Sharpe는 `0.5585→0.5434`, P(higher Sharpe)는 `19.80%`, Holm-adjusted p-value는 `0.8020`이어서 탈락했습니다.
- rolling 504일 outer window마다 completed inner fold가 3개뿐이었고 평균 posterior는 equal/min-var/risk-parity/momentum `21.96%/26.26%/18.24%/33.53%`였습니다.
- 같은 split에서 outer window, expert set, loss, learning rate를 재튜닝하지 않고 1970+ validation/holdout을 봉인합니다.
- 보고서: `docs/reports/260724-0424-01-online-allocator-ensemble-research.md`
