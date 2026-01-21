# Task Breakdown: Portfolio Optimizer Log Return & Black-Litterman

## Overview
Total Tasks: 3 Groups
Assigned roles: api-engineer, testing-engineer

## Task List

### Backend Logic

#### Task Group 1: Forecasting Models Update
**Assigned implementer:** api-engineer
**Dependencies:** None

- [ ] 1.0 Update forecasting models to use log returns and implement ensemble
  - [ ] 1.1 Write 2-8 focused tests for Log Returns and Ensemble logic
    - Test `np.log` transformation accuracy
    - Test simple ensemble averaging logic (mean of 3 numbers)
    - Test ensemble standard deviation calculation
  - [ ] 1.2 Update `ARIMA` model in `forecast_models.py`
    - Convert input prices to log returns before training
    - Ensure forecast returns log-return predictions
  - [ ] 1.3 Update `LSTM` model in `forecast_models.py`
    - Convert input prices to log returns before training/scaling
    - Ensure forecast returns log-return predictions
  - [ ] 1.4 Update `XGBoost` model in `forecast_models.py`
    - Feature engineering should handle log returns
    - Ensure forecast returns log-return predictions
  - [ ] 1.5 Implement `EnsemblePredictor` (Soft Voting)
    - Replace `ModelSelector` winner-takes-all logic
    - Aggregate predictions from all 3 models (Mean)
    - Calculate confidence (Std Dev of predictions)
  - [ ] 1.6 Ensure forecasting tests pass
    - Run ONLY the 2-8 tests written in 1.1

**Acceptance Criteria:**
- All 3 models train and predict using log returns
- Ensemble logic correctly computes the mean and standard deviation of component model predictions
- Tests in 1.1 pass

#### Task Group 2: Black-Litterman Optimization
**Assigned implementer:** api-engineer
**Dependencies:** Task Group 1

- [ ] 2.0 Implement Black-Litterman Optimization logic
  - [ ] 2.1 Write 2-8 focused tests for Black-Litterman integration
    - Test fetching/calculating Market Risk Aversion (mocked market data)
    - Test construction of Views matrix ($P$, $Q$) and Uncertainty matrix ($\Omega$)
    - Test basic `BlackLittermanModel` instantiation (mocked inputs)
  - [ ] 2.2 Implement Market Data Fetching
    - Fetch `^GSPC` (S&P 500) data using `yfinance` in `portfolio_optimization.py` or helper
    - Calculate market covariance and risk aversion ($\delta$)
  - [ ] 2.3 Implement Black-Litterman Logic
    - Replace `EfficientFrontier` with `BlackLittermanModel` in `optimize_portfolio`
    - Map Ensemble Forecasts to Views ($Q$)
    - Map Ensemble Confidence to Uncertainty ($\Omega$)
  - [ ] 2.4 Update Portfolio Optimization Output
    - Optimize weights using BL posterior returns/covariance
    - Convert posterior log returns back to simple arithmetic returns for display
  - [ ] 2.5 Ensure optimization tests pass
    - Run ONLY the 2-8 tests written in 2.1

**Acceptance Criteria:**
- Portfolio optimization uses `BlackLittermanModel` instead of `EfficientFrontier`
- Market data (`^GSPC`) is used for the Prior
- Ensemble forecasts are used as Views with confidence-based uncertainty
- Output returns are displayed as simple annual percentages
- Tests in 2.1 pass

### Testing

#### Task Group 3: Test Review & Gap Analysis
**Assigned implementer:** testing-engineer
**Dependencies:** Task Groups 1-2

- [ ] 3.0 Review and validation
  - [ ] 3.1 Review tests from Task Groups 1-2
    - Review the tests written for forecasting updates
    - Review the tests written for BL integration
  - [ ] 3.2 Analyze test coverage gaps for Black-Litterman flow
    - Identify if end-to-end optimization flow needs integration testing
    - Ensure fallback logic (if market data fails) is tested
  - [ ] 3.3 Write up to 10 additional strategic tests
    - Add integration test: "Data -> Ensemble Forecast -> Black-Litterman -> Weights"
    - Test fallback scenario (e.g., S&P 500 fetch fails)
  - [ ] 3.4 Run feature-specific tests
    - Run all tests from 1.1, 2.1, and 3.3
    - Verify robust execution of the new pipeline

**Acceptance Criteria:**
- End-to-end optimization flow is verified
- Fallback mechanisms (if any) are tested
- Feature-specific tests pass

## Execution Order

Recommended implementation sequence:
1. Forecasting Models Update (Task Group 1)
2. Black-Litterman Optimization (Task Group 2)
3. Testing & Gap Analysis (Task Group 3)
