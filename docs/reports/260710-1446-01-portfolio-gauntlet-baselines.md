# Portfolio Gauntlet Baselines

## Summary

Implemented the portfolio performance gauntlet infrastructure and stronger dumb baselines before further Transformer tuning:

- Added reusable signal helpers for 6-month momentum, low-volatility score, drawdown score, market-cap weights, cross-sectional signal stack, and weak BL rank views.
- Added backtest models for `momentum_6m`, `low_volatility`, `market_cap_weight`, `momentum_12_1`, `signal_stack_bl`, `arima_transformer_rank_bl`, and `transformer_rank_bl`.
- Changed promotion gating to prefer rank-based ARIMA + Transformer competition and require stronger baselines plus gauntlet confirmation.
- Added `aggregate_gauntlet_promotion` for multi-basket/regime/sensitivity survival reporting.
- Extended `tools/backtest_portfolio_models.py` with `--gauntlet-preset standard|smoke`, JSON output, and Markdown summary output.
- Added optional optimizer controls: `turnover_penalty` and `min_holding_weight`.

## Changed Files

- `src/backend/portfolio_signals.py`
- `src/backend/portfolio_backtest.py`
- `src/backend/portfolio_optimization.py`
- `src/backend/app.py`
- `tools/backtest_portfolio_models.py`
- `tests/test_portfolio_backtest.py`
- `docs/02-specs.md`
- `docs/03-product-plan.md`
- `docs/todo/00-todo-list.md`
- `docs/todo/portfolio-gauntlet-live-run.md`

## Verification

- `PYTHONPATH=src/backend .venv/bin/python -m pytest tests/test_portfolio_backtest.py -q`
- `PYTHONPATH=src/backend .venv/bin/python -m pytest tests/test_portfolio_management.py tests/test_portfolio_management_gaps.py tests/test_high_priority_fixes.py::test_mpt_uses_confidence_adjusted_expected_returns tests/test_high_priority_fixes.py::test_black_litterman_uses_confidence_adjusted_views_and_omega -q`
- `PYTHONPATH=src/backend .venv/bin/python -m pytest tests -q`

## Notes

- The full live `standard` gauntlet is intentionally left as a separate TODO because it depends on external yfinance access and can be long-running.
- Synthetic smoke coverage verifies signal math, no-lookahead windows, turnover sensitivity, min-holding threshold, optimizer turnover penalty wiring, and gauntlet CLI JSON/Markdown output.
