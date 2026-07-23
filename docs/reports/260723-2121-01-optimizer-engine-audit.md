# Portfolio Optimizer Quant-Standard Audit

## Summary

portfolio optimizer와 backtest의 성능 근거를 감사하고 look-ahead, 임의 alpha fallback, solver/reporting 불일치를 수정했습니다.

- Transformer hyperparameter는 변경하지 않았습니다.
- public default model을 새 후보로 승격하지 않았습니다.
- locked holdout은 실행하지 않았습니다.
- 기존 current-market-cap historical gauntlet 결과는 point-in-time 위반으로 무효화했습니다.

## Correctness fixes

### Point-in-time data

- 신규 상장 종목의 leading missing price를 미래 첫 가격으로 backward-fill하지 않습니다.
- FX history도 미래 환율을 과거 날짜에 backward-fill하지 않습니다.
- production BL은 historical end date에서 현재 market cap을 사용하지 않고 historical-return prior로 fallback합니다.
- backtest static market cap은 `market_caps_as_of_date`가 없으면 사용하지 않습니다.
- historical market-cap research는 date-indexed `point_in_time_market_caps`만 사용하며 각 rebalance date 이전 snapshot만 선택합니다.

### Forecast fallback

- lightweight forecast 실패 또는 빈 입력에 임의 `+5%` expected return을 넣지 않습니다.
- 실패 ticker는 explicit no-view, maximum uncertainty, historical prior-only로 처리합니다.

### Optimization and reporting

- malformed max-Sharpe + L2 objective를 기본 경로에서 제거해 default `l2_gamma=0`으로 변경했습니다.
- L2 또는 turnover penalty를 요청하면 24개 target-return grid의 convex efficient-return 문제를 풀고 ex-post Sharpe가 가장 높은 feasible solution을 선택합니다.
- return/risk/Sharpe는 threshold와 turnover control 이후 실제 반환 weight로 다시 계산합니다.
- solver objective와 L2/turnover 설정을 응답 diagnostics에 기록합니다.

## Risk research additions

- OOS predicted-versus-realized volatility, risk forecast bias/MAE/ratio
- Sortino, Calmar, Omega, daily 95% VaR/CVaR
- paired circular block bootstrap
- 95% lower-volatility/higher-Sharpe probability gate
- simultaneous candidate research용 Holm-Bonferroni family-wise error correction
- nested covariance selection, continuous regime covariance v2, minimum-CVaR, stability-regularized, resampled minimum-variance, risk-managed momentum research candidates

모든 새 후보는 deterministic 또는 statistical gate에서 탈락했습니다. 복잡도 증가를 성능 개선으로 간주하지 않았고 Ledoit-Wolf minimum variance와 기존 public defaults를 유지했습니다.

## Corrected 180-case baseline gauntlet

현재 market cap을 사용하는 `market_cap_weight`를 제외하고 5 baskets × 4 regimes × 9 execution controls, 총 180 cases를 재실행했습니다.

| Model | Avg Sharpe | Avg CAGR | Avg Max DD | Avg controlled turnover | Sharpe wins |
|---|---:|---:|---:|---:|---:|
| momentum_6m | 1.0204 | 0.2321 | -0.1727 | 0.1880 | 48 |
| lightweight_bl | 0.9826 | 0.2043 | -0.1720 | 0.1043 | 19 |
| momentum_12_1 | 0.9084 | 0.2158 | -0.1787 | 0.1528 | 26 |
| signal_stack_bl | 0.8841 | 0.1747 | -0.1496 | 0.0559 | 4 |
| equal_weight | 0.8819 | 0.1744 | -0.1498 | 0.0560 | 13 |
| momentum_bl | 0.8647 | 0.1788 | -0.1576 | 0.0567 | 5 |
| historical_bl | 0.8449 | 0.1773 | -0.1571 | 0.0565 | 2 |
| historical_mpt | 0.7728 | 0.1750 | -0.1796 | 0.1733 | 29 |
| min_variance | 0.7312 | 0.1295 | -0.1506 | 0.0878 | 22 |
| risk_parity | 0.7301 | 0.1495 | -0.1407 | 0.0572 | 5 |
| low_volatility | 0.7189 | 0.1322 | -0.1433 | 0.0848 | 7 |

기본 execution setting 20개 basket/regime에서 momentum 6m은 equal weight 대비 10/20, lightweight BL은 13/20 Sharpe 승리였습니다. 평균 성과는 높지만 regime 전반 승격 근거는 부족합니다.

## Live runtime verification

2023-01-01~2026-07-23, SPY/QQQ/IWM/EFA/EEM/TLT/GLD/VNQ:

- default max-Sharpe: return `0.3050`, risk `0.1682`, Sharpe `1.6348`
- explicit L2 `0.05` regularized grid: return `0.2986`, risk `0.1650`, Sharpe `1.6276`
- forecast failures: `0`
- MPT market prior: `not_applicable`
- both runs returned valid capped weights and matching post-control performance metrics

이 live 실행은 runtime verification이며 out-of-sample promotion evidence가 아닙니다.

## Outputs

- `logs/portfolio_gauntlet_standard_20260723_pit_corrected.json`
- `logs/portfolio_gauntlet_standard_20260723_pit_corrected.md`
- `logs/risk_allocator_research_country_etfs_2004_2012_statistical.json`
- `logs/risk_allocator_research_ishares_industries_2003_2011_resampled.json`
- `logs/risk_allocator_research_style_size_2003_2011_risk_managed_momentum.json`
- `logs/risk_allocator_research_industrials_2004_2012_regime_v2.json`

## Verification

- `PYTHONPATH=src/backend .venv/bin/python -m pytest tests -q`: 159 passed
- corrected baseline gauntlet: 180/180 completed
- live default and explicit-L2 optimizer runs exited successfully
- `git diff --check`: required before handoff

## Decision

- 엔진의 truthfulness, PIT safety, statistical gate, risk diagnostics는 개선됐습니다.
- 검증된 default performance uplift는 아직 없습니다.
- Transformer tuning은 PIT factor/macro signal이 signal-only gate를 통과한 뒤에만 진행합니다.
- 다음 승격 후보는 survivorship-safe universe와 PIT fundamentals를 포함한 fresh research에서 95% bootstrap + Holm gate를 통과해야 합니다.
