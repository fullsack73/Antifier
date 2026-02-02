# Implementation: Backend Logic & Strategy Implementation

## Overview
Implemented the backend logic for selecting different portfolio optimization strategies. The `optimize_portfolio` function now supports:
- **Black-Litterman (Default)**: Combines Market Prior with Ex-Ante ML Views.
- **Deep Learning Ensemble**: Uses ML forecast views directly as expected returns.
- **Lightweight Prediction**: Uses statistical exponential smoothing for fast estimates.
- **Classic MPT**: Uses historical CAGR and Covariance.

## Changes

### `src/backend/portfolio_optimization.py`
- Updated `optimize_portfolio` signature to accept `model_strategy`.
- Refactored the forecasting section to branch based on `model_strategy`.
- Implemented logic for each strategy:
  - **MPT**: Calculates historical CAGR.
  - **Lightweight**: iteratives over tickers and calls `lightweight_ensemble_forecast`.
  - **Ensemble**: Calls `ml_forecast_returns` and bypasses BL model.
  - **BL**: Existing logic preserved.
- Added legacy check for `is_ex_post` (backtesting) which forces MPT if date is too old, unless strategy is explicitly overridden (logic preferences explicit strategy).

### `src/backend/app.py`
- Updated `/api/optimize-portfolio` to parse `model_strategy` from request JSON.
- Passes `model_strategy` to the backend function.

## Verification
- Created `tests/test_portfolio_optimization_strategies.py`.
- Verified `MPT` strategy works (mocked).
- Verified `BL` strategy enters the correct logic block (logs confirm BL execution attempt).
- Note: Test mocking for `ml_forecast_returns` proved challenging due to decorator/import interactions, but execution flow is confirmed via logs.

## Next Steps
- Frontend integration (Task Group 2).
- Integration testing to ensure UI dropdown triggers correct backend path.
