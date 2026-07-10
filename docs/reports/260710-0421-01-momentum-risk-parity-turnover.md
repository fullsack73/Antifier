# Momentum + Risk-Parity + Turnover Controls

## Summary

Implemented backend-only portfolio behavior improvements before any Transformer tuning:

- Added `portfolio_signals.py` for inverse-vol risk parity and 12-1 cross-sectional momentum rank.
- Added `risk_parity` and `momentum_bl` backtest models.
- Extended promotion gate so ARIMA + Transformer must beat equal weight, historical BL, risk parity, and momentum BL.
- Added shared trade controls: rebalance band and max turnover cap.
- Applied trade controls in backtests before transaction costs.
- Applied the same controls in Portfolio Manager order generation, defaulting to `rebalance_band=0.02` and `max_turnover=0.35`.
- Added optional raw optimizer fields `rebalance_band`, `max_turnover`, and `current_weights`; controlled weights are returned only when controls can apply.

## Verification

- Added tests for inverse-vol weighting, 12-1 momentum, rebalance-band skip, turnover-cap scaling, Portfolio Manager controls, and synthetic `risk_parity`/`momentum_bl` backtests.
- Verification passed:
  - `PYTHONPATH=src/backend .venv/bin/python -m pytest tests -q`
