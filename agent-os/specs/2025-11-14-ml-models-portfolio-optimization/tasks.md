# Task Breakdown: ML-Based Portfolio Optimization

## Overview
Total Tasks: 3 Task Groups (Backend-only implementation)
Assigned roles: api-engineer, testing-engineer

## Task List

### ML Models Implementation

#### Task Group 1: ML Forecast Models
**Assigned implementer:** api-engineer
**Dependencies:** None

- [x] 1.0 Complete ML models implementation
  - [x] 1.1 Write 2-8 focused tests for ML models
    - Limit to 2-8 highly focused tests maximum
    - Test only critical model behaviors (e.g., LSTM forecast output format, ARIMA fallback, XGBoost feature engineering, model selection logic)
    - Skip exhaustive coverage of all edge cases
  - [x] 1.2 Extend ARIMA class in forecast_models.py
    - Add volatility forecasting capability
    - Extend forecast() method to return both returns and risk
    - Maintain existing fallback pattern for failed forecasts
    - Keep suppress_warnings and seasonal parameters
  - [x] 1.3 Create LSTMModel class in forecast_models.py
    - Implement __init__() with model configuration (layers, units, dropout)
    - Implement train() method for time series training
    - Implement forecast() method returning expected annual return
    - Use TensorFlow/Keras for LSTM implementation
    - Add error handling with fallback to simpler model
  - [x] 1.4 Create XGBoostModel class in forecast_models.py
    - Implement feature engineering pipeline (returns, volume, technical indicators)
    - Implement train() method with hyperparameter tuning
    - Implement forecast() method returning expected annual return
    - Use xgboost library for gradient boosting
    - Add error handling with fallback mechanism
  - [x] 1.5 Create ModelSelector class in forecast_models.py
    - Implement validate_model() to calculate R², RMSE metrics
    - Implement select_best_model() to auto-select best performer
    - Train all three models (LSTM, ARIMA, XGBoost) on validation set
    - Return best model based on validation metrics
    - Log model selection decisions
  - [x] 1.6 Ensure ML models tests pass
    - Run ONLY the 2-8 tests written in 1.1
    - Verify each model produces valid forecast output
    - Do NOT run the entire test suite at this stage

**Acceptance Criteria:**
- The 2-8 tests written in 1.1 pass
- LSTM, ARIMA, XGBoost models all produce valid forecasts
- ModelSelector correctly identifies best-performing model
- Error handling and fallbacks work correctly
- Logging outputs model performance metrics

### Portfolio Optimization Integration

#### Task Group 2: ML Integration and Caching
**Assigned implementer:** api-engineer
**Dependencies:** Task Group 1

- [x] 2.0 Complete portfolio optimization integration
  - [x] 2.1 Write 2-8 focused tests for integration
    - Limit to 2-8 highly focused tests maximum
    - Test only critical integration points (e.g., ml_forecast_returns() output format, multicore processing, cache integration, MPT fallback)
    - Skip exhaustive testing of all scenarios
  - [x] 2.2 Create ml_forecast_returns() function in portfolio_optimization.py
    - Replace forecast_returns() with new ML-based implementation
    - Accept DataFrame input, return pandas Series of expected returns
    - Use ProcessPoolExecutor for parallel ticker processing
    - Follow existing pattern from lines 325-340
    - Integrate ModelSelector for each ticker
  - [x] 2.3 Implement model caching strategy
    - Add @cached decorator for trained models (l1_ttl=3600, l2_ttl=86400)
    - Add @cached decorator for predictions (l1_ttl=900, l2_ttl=14400)
    - Follow existing cache_manager patterns
    - Implement cache key generation for models and predictions
  - [x] 2.4 Implement multicore processing
    - Use ProcessPoolExecutor(max_workers=cpu_count()) for training
    - Process each ticker independently with best model
    - Handle partial failures gracefully
    - Aggregate results into single pandas Series
  - [x] 2.5 Add fallback mechanism to MPT
    - Keep existing forecast_returns() as fallback_forecast_returns()
    - Wrap ml_forecast_returns() in try/except block
    - Fall back to lightweight/Prophet method on ML failure
    - Log fallback events with logger.warning()
  - [x] 2.6 Update optimize_portfolio() function
    - Replace forecast_returns() call with ml_forecast_returns()
    - Maintain all existing parameters and signature
    - Ensure DataFrame alignment logic still works
    - Keep existing error handling patterns
  - [x] 2.7 Add performance metrics logging
    - Log R² and RMSE during model training
    - Log model selection decisions per ticker
    - Log processing time for multicore execution
    - Log cache hit/miss rates
  - [x] 2.8 Ensure integration tests pass
    - Run ONLY the 2-8 tests written in 2.1
    - Verify ml_forecast_returns() produces compatible output
    - Verify optimize_portfolio() still works end-to-end
    - Do NOT run the entire test suite at this stage

**Acceptance Criteria:**
- The 2-8 tests written in 2.1 pass
- ml_forecast_returns() integrates seamlessly with optimize_portfolio()
- Multicore processing works correctly across multiple tickers
- Model and prediction caching reduces response time
- Fallback to MPT works when ML fails
- Performance metrics logged to console

### Testing

#### Task Group 3: Test Review & Gap Analysis
**Assigned implementer:** testing-engineer
**Dependencies:** Task Groups 1-2

- [ ] 3.0 Review existing tests and fill critical gaps only
  - [ ] 3.1 Review tests from Task Groups 1-2
    - Review the 2-8 tests written by api-engineer for ML models (Task 1.1)
    - Review the 2-8 tests written by api-engineer for integration (Task 2.1)
    - Total existing tests: approximately 4-16 tests
  - [ ] 3.2 Analyze test coverage gaps for THIS feature only
    - Identify critical ML workflows that lack test coverage
    - Focus ONLY on gaps related to ML portfolio optimization
    - Do NOT assess entire application test coverage
    - Prioritize end-to-end workflows and failure scenarios
  - [ ] 3.3 Write up to 10 additional strategic tests maximum
    - Add maximum of 10 new tests to fill identified critical gaps
    - Focus on integration points: ML models → ml_forecast_returns() → optimize_portfolio()
    - Test fallback scenarios: ML failure → MPT backup
    - Test multicore processing with multiple tickers
    - Test cache behavior for models and predictions
    - Do NOT write comprehensive coverage for all edge cases
    - Skip performance benchmarks unless business-critical
  - [ ] 3.4 Run feature-specific tests only
    - Run ONLY tests related to ML portfolio optimization (tests from 1.1, 2.1, and 3.3)
    - Expected total: approximately 14-26 tests maximum
    - Do NOT run the entire application test suite
    - Verify critical ML forecasting workflows pass
    - Verify optimize_portfolio() end-to-end integration works

**Acceptance Criteria:**
- All feature-specific tests pass (approximately 14-26 tests total)
- Critical ML forecasting workflows are covered
- Fallback mechanism to MPT is tested
- No more than 10 additional tests added by testing-engineer
- Testing focused exclusively on ML portfolio optimization feature

## Execution Order

Recommended implementation sequence:
1. ML Models Implementation (Task Group 1)
2. Portfolio Optimization Integration (Task Group 2)
3. Test Review & Gap Analysis (Task Group 3)

## Notes

- This is a backend-only implementation with no frontend changes
- No database layer changes required
- No API endpoint structure changes
- Focus on Python/Flask backend code in src/ directory
- Reuse existing cache_manager, get_stock_data, sanitize_tickers functions
- Follow existing logging patterns with logger.info/warning
- Maintain compatibility with existing optimize_portfolio() pipeline
