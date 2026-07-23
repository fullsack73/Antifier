# Risk Cash and Volatility-Target Research

- 실행 시각: 2026-07-24 00:39 KST
- 역할: risk-engine truth fix and research-only candidate audit
- 결론: backtest cash fixes 유지, 신규 risk 후보 2개 폐기

## 구현

- baseline Ledoit-Wolf, recent exponential, correlation/volatility shock의 세 covariance scenario에서 최악 분산을 직접 최소화하는 epigraph optimizer를 추가했습니다.
- minimum-variance risky allocation을 252일 historical predicted-volatility state의 median에 맞추는 no-leverage volatility target을 추가했습니다.
- volatility target은 위험자산 비중을 `25~100%`로 제한하고 나머지를 현금으로 보유합니다.
- backtest target normalization이 명시적 부분 위험노출을 다시 100%로 확대하지 않도록 수정했습니다.
- 잔여 현금은 signal date에 이용 가능한 FRED DGS3MO daily-equivalent rate로 복리 적립합니다.
- execution risk forecast는 현금을 제외한 실제 위험자산 비중으로 계산합니다.

## Backtest truth fix

- 기존 backtest는 최초 현금 투입도 `max_turnover=35%`로 제한했습니다.
- 이 때문에 완전투자 baseline도 초기 여러 구간에 현금을 강제로 남겼고 2017~2025 v1 실행에서 평균 현금 비중이 약 `4~7%`였습니다.
- 최초 배치는 rebalancing turnover가 아니므로 rebalance band와 turnover cap을 면제했습니다.
- 최초 매수의 transaction cost는 그대로 부과합니다.
- v1 결과는 이 결함을 찾은 진단 기록으로만 보존하고 후보 판정에는 수정 후 v2만 사용합니다.

## Scenario worst-case research

- 데이터: global multi-asset ETF 10종, 2008~2016
- split digest: `f544c9097b019ff7c1dc96a47008b987a087e986cc9b8365de942afa2a20a834`

| Model | Volatility | Sharpe | Max drawdown | P(lower vol) | P(higher Sharpe) |
|---|---:|---:|---:|---:|---:|
| Ledoit minimum variance | 5.0096% | 1.0605 | -9.3766% | — | — |
| Scenario worst-case | 5.0833% | 1.0126 | -9.8683% | 0.15% | 10.30% |

- stress-aware allocation은 baseline보다 volatility, Sharpe, drawdown이 모두 나빠 폐기했습니다.
- 같은 split에서 shock size, recent span 또는 scenario weight를 재튜닝하지 않습니다.

## Fresh volatility-target research

- 다운로드: Yahoo Finance adjusted price, 10 tickers, 2017-01-01~2026-01-01
- 파일: `global_multi_asset_prices_2017_2025.csv`, 2,262×10, 428 KiB
- 전 종목 usable observation: 2,262
- price SHA: `17d070cc5f1e4c0211f8ddd405fed65ef4c38a1126af471a081e0394f93c0636`
- corrected v2 split digest: `090da8761fc2f523afe60be0f5a5fdf4fff7c6afd6f81a6188d61c637e502509`
- evaluation: 2019-01-04~2025-12-31, 63일 rebalance, 10 bps cost

| Model | CAGR | Volatility | Sharpe | Max drawdown | Daily CVaR | Avg risky exposure |
|---|---:|---:|---:|---:|---:|---:|
| Ledoit minimum variance | 6.5257% | 7.7361% | 0.5083 | -17.5973% | 1.1366% | 97.88% |
| Volatility-targeted minimum variance | 5.6073% | 6.7285% | 0.4449 | -14.7976% | 0.9909% | 87.37% |

- candidate minus baseline volatility는 `-1.0077%p`, Sharpe는 `-0.0634`입니다.
- paired 21일 block bootstrap 2,000회에서 P(lower volatility)는 `100%`, P(higher Sharpe)는 `19.80%`입니다.
- tail risk는 낮췄지만 return sacrifice가 커서 joint risk/return gate와 Holm gate에서 탈락했습니다.
- volatility target ratio, floor, lookback을 이 결과에 맞춰 재튜닝하지 않습니다.

## 판정

- scenario worst-case와 volatility-target 후보는 live/default optimizer로 승격하지 않습니다.
- 부분 위험노출, point-in-time cash accrual, initial deployment cap 면제는 candidate 성능과 독립적인 backtest 정확성 수정이므로 유지합니다.
- current default risk estimator는 Ledoit-Wolf입니다.
- quant-standard 완료에는 새 alpha 후보, 새 validation split, untouched holdout 통과가 여전히 필요합니다.
