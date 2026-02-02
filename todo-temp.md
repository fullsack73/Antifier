# Implementation Plan: Decouple Forecast and Optimization Methods

This plan outlines the steps to separate the forecasting logic (how returns are predicted) from the optimization logic (how the portfolio is constructed) in the Portfolio Optimizer.

## 1. Frontend Implementation (`src/frontend/Optimizer.jsx`)
- [ ] **Remove Legacy State**: Remove `modelStrategy` state and its single dropdown.
- [ ] **Add New State**:
  - `forecastMethod`: Default to `'Lightweight'` (Options: `'Lightweight'`, `'Deep Learning'`).
  - `optimizationMethod`: Default to `'BL'` (Options: `'Black-Litterman'`, `'MPT'`).
- [ ] **Update UI Layout**: Create two distinct form groups/dropdowns for the users to make their selections.
- [ ] **Update API Data**: Modify `handleSubmit` to include `forecast_method` and `optimization_method` in the payload instead of `model_strategy`.

## 2. Backend Implementation (`src/backend/portfolio_optimization.py`)
- [ ] **Update Function Signature**: Modify `optimize_portfolio` to accept `forecast_method` and `optimization_method`.
- [ ] **Refactor Forecasting Phase**:
  - IF `forecast_method` == 'Deep Learning': Call `ml_forecast_returns`.
  - IF `forecast_method` == 'Lightweight': Call `lightweight_ensemble_forecast`.
  - Result: Common format matching `expected_returns` (and `uncertainties` for BL).
- [ ] **Refactor Optimization Phase**:
  - **Case Black-Litterman (`BL`)**:
    - Use the results from the Forecasting Phase as the "Investor Views".
    - Continue using the existing "predetermined" view logic (no user-facing view fine-tuning).
    - Combine Market Equilibrium + Views -> Posterior Returns -> Efficient Frontier.
  - **Case Mean-Variance (`MPT`)**:
    - Use the results from the Forecasting Phase *directly* as the Expected Returns (`mu`).
    - Pass `mu` and Covariance `S` directly to `EfficientFrontier`.

## 3. Backend API Layer (`src/backend/app.py`)
- [ ] **Parameter Extraction**: Update the `/api/optimize-portfolio` route handler to extract `forecast_method` and `optimization_method` from the request JSON and pass them to the optimizer.

## 4. Testing & Verification
- [ ] **Update Unit Tests** (`tests/test_portfolio_optimization_strategies.py`):
  - Create test cases for the 4 distinct combinations:
    1. `BL` + `Lightweight`
    2. `BL` + `Deep Learning`
    3. `MPT` + `Lightweight`
    4. `MPT` + `Deep Learning`
  - Verify that the correct internal functions (`ml_forecast_returns` vs `lightweight...`) are called based on inputs.
- [ ] **Verification**:
  - Run the full test suite.
  - Verify that the frontend UI elements render correctly.
