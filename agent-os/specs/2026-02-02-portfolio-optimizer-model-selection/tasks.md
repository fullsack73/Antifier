# Task Breakdown: Portfolio Optimizer Model Selection

## Overview
Total Tasks: 13
Assigned roles: api-engineer, ui-designer, testing-engineer

## Task List

### API Layer

#### Task Group 1: Backend Logic & Strategy Implementation
**Assigned implementer:** api-engineer
**Dependencies:** None

- [x] 1.0 Complete Backend Strategy Logic
  - [x] 1.1 Write 2-8 focused tests for `optimize_portfolio` strategy selection
    - Test default behavior (Black-Litterman)
    - Test parameter passing for new strategies (MPT, Deep Learning, Lightweight)
    - Verify data fetching mock calls for each path
  - [x] 1.2 Refactor `optimize_portfolio` signature in `src/backend/portfolio_optimization.py`
    - Accept `model_strategy` parameter (default: "BL")
    - Update caching decorator key generation if needed to include strategy
  - [x] 1.3 Implement "Classic MPT" strategy logic
    - Branch: If model="MPT" -> Use `mu = mean_historical_return(prices)` (or CAGR)
    - Use `S = risk_models.sample_cov(prices)` (or shrinkage)
    - Skip ML view generation
  - [x] 1.4 Implement "Deep Learning Ensemble" strategy logic
    - Branch: If model="Ensemble" -> Call `ml_forecast_returns` to get `mu_views`
    - Use `mu_views` directly as `mu` for `EfficientFrontier` (skip Black-Litterman mapping)
  - [x] 1.5 Implement "Lightweight Prediction" strategy logic
    - Branch: If model="Lightweight" -> Call `lightweight_ensemble_forecast` for each ticker
    - Construct `mu` series from results
  - [x] 1.6 Update `app.py` endpoint (if necessary)
    - Ensure `/api/optimize` endpoint retrieves `model_strategy` from JSON body and passes it to `optimize_portfolio`
  - [x] 1.7 Ensure API layer tests pass
    - Run ONLY the 2-8 tests written in 1.1
    - Verify all strategies produce a result dictionary
    - Do NOT run the entire test suite

**Acceptance Criteria:**
- `optimize_portfolio` accepts `model_strategy`
- "MPT" uses historical data only
- "Ensemble" uses ML predictions directly
- "Lightweight" uses lightweight forecast module
- Default remains "Black-Litterman"

### Frontend Components

#### Task Group 2: UI Implementation
**Assigned implementer:** ui-designer
**Dependencies:** Task Group 1

- [x] 2.0 Complete UI Updates
  - [x] 2.1 Write 2-8 focused tests for `Optimizer` component updates
    - Test that "Model Strategy" dropdown renders
    - Test that changing dropdown updates state
    - Test that form submission includes new parameter
  - [x] 2.2 Add Translation Keys
    - Update `src/frontend/locales/en/translation.json`
    - Update `src/frontend/locales/ko/translation.json`
    - Keys: `optimizer.modelStrategy`, and options (`bl`, `ensemble`, `lightweight`, `mpt`)
  - [x] 2.3 Update `src/frontend/Optimizer.jsx` State & UI
    - Add `modelStrategy` state (default: "BL")
    - Add `<select>` dropdown in the form grid
    - Use correct translation keys
  - [x] 2.4 Update Form Submission
    - Include `model_strategy` in the API payload in `handleSubmit`
  - [x] 2.5 Ensure UI component tests pass
    - Run ONLY the 2-8 tests written in 2.1
    - Verify UI matches existing style

**Acceptance Criteria:**
- User can select between 4 strategies
- Dropdown is localized (English/Korean)
- Selection is sent to backend API correctly
- UI matches existing Application design

### Testing

#### Task Group 3: Test Review & Gap Analysis
**Assigned implementer:** testing-engineer
**Dependencies:** Task Groups 1-2

- [x] 3.0 Review and Gap Analysis
  - [x] 3.1 Review tests from Task Groups 1-2
    - Review backend strategy tests
    - Review frontend state tests
  - [x] 3.2 Analyze test coverage gaps
    - Focus on the integration: Does Frontend selection actually trigger correct Backend path?
  - [x] 3.3 Write up to 10 additional strategic tests
    - Add integration test ensuring "Lightweight" option returns (should be faster/different structure if applicable)
    - Add boundary test for invalid model selection (fallback)
  - [x] 3.4 Run feature-specific tests only
    - Run tests from 1.1, 2.1, and 3.3
    - Verify full flow success

**Acceptance Criteria:**
- All feature-related tests pass
- Integration verified between UI selection and Backend execution
- Strategies execute without runtime errors

## Execution Order

Recommended implementation sequence:
1. API Layer (Task Group 1)
2. Frontend Components (Task Group 2)
3. Testing (Task Group 3)
