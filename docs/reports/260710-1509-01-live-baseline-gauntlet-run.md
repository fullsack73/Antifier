# Live Baseline Gauntlet Run

## Summary

Ran the live portfolio gauntlet against yfinance data on 2026-07-10.

- First attempted the default `--gauntlet-preset standard --fetch-market-caps` run.
- The exact default run was stopped during case 1/180 because `arima_transformer_rank_bl` and `transformer_rank_bl` repeatedly trained TensorFlow models for each ticker/rebalance window.
- Then completed the full 180-case basket/regime/sensitivity matrix with the baseline and signal-stack model set, excluding the two ML rank models.

## Command Completed

```bash
PYTHONPATH=src/backend .venv/bin/python tools/backtest_portfolio_models.py \
  --gauntlet-preset standard \
  --fetch-market-caps \
  --models equal_weight min_variance risk_parity momentum_6m low_volatility market_cap_weight momentum_12_1 historical_bl momentum_bl signal_stack_bl historical_mpt lightweight_bl \
  --output logs/portfolio_gauntlet_standard_20260710_baselines.json
```

## Outputs

- `logs/portfolio_gauntlet_standard_20260710_baselines.json`
- `logs/portfolio_gauntlet_standard_20260710_baselines.md`

## Result Summary

- Completed cases: 180 / 180
- Completed cases by basket:
  - SP500 sample: 36
  - DOW: 36
  - tech basket: 36
  - defensive basket: 36
  - mixed ETF-like basket: 36
- Errors: 0 completed-run errors
- Promotion status: `not_promoted`
- Promotion caveat: candidate `arima_transformer_rank_bl` was intentionally excluded from this completed baseline run, so promotion summary reports the candidate as missing.

## Sharpe Win Counts

- `market_cap_weight`: 68
- `momentum_6m`: 37
- `historical_mpt`: 17
- `momentum_12_1`: 15
- `lightweight_bl`: 14
- `min_variance`: 13
- `low_volatility`: 5
- `risk_parity`: 4
- `equal_weight`: 4
- `signal_stack_bl`: 2
- `momentum_bl`: 1

## Average Metrics

| Model | Avg Sharpe | Avg CAGR | Avg Max DD | Avg Controlled Turnover |
|---|---:|---:|---:|---:|
| `market_cap_weight` | 1.0949 | 0.2349 | -0.1740 | 0.0609 |
| `momentum_6m` | 1.0204 | 0.2321 | -0.1727 | 0.1880 |
| `lightweight_bl` | 0.9826 | 0.2043 | -0.1720 | 0.1043 |
| `signal_stack_bl` | 0.9473 | 0.1747 | -0.1496 | 0.0559 |
| `equal_weight` | 0.9449 | 0.1744 | -0.1498 | 0.0560 |
| `momentum_12_1` | 0.9084 | 0.2158 | -0.1787 | 0.1528 |
| `momentum_bl` | 0.8647 | 0.1788 | -0.1576 | 0.0567 |
| `historical_bl` | 0.8449 | 0.1773 | -0.1571 | 0.0565 |
| `historical_mpt` | 0.7728 | 0.1750 | -0.1796 | 0.1733 |
| `min_variance` | 0.7312 | 0.1295 | -0.1506 | 0.0878 |
| `risk_parity` | 0.7301 | 0.1495 | -0.1407 | 0.0572 |
| `low_volatility` | 0.7189 | 0.1322 | -0.1433 | 0.0848 |

## Notes

- DOW basket had expected yfinance missing-data messages for `WBA`; DOW Inc. also lacks 2014-2016 data for the sideways regime. The backtest continued with valid price columns.
- Several max-Sharpe optimizations fell back when expected returns did not exceed the risk-free rate or solver constraints were infeasible.
- The next engineering step is to keep ML rank models out of the default standard gauntlet unless forecast caching/reuse is added.
