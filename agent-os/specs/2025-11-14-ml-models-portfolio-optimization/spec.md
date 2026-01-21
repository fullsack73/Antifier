# Specification: ML-Based Portfolio Optimization

## Goal
Replace the existing MPT + Prophet portfolio optimization approach with a full ML-based system using LSTM, ARIMA, and XGBoost models for return and risk forecasting, with automatic model selection and multicore processing for enhanced prediction accuracy.

## User Stories
- As an investor, I want the system to use advanced ML models to forecast stock returns so that I can make more accurate portfolio allocation decisions
- As a portfolio optimizer user, I want the system to automatically select the best-performing model for each stock so that I get optimal predictions without manual intervention
- As a user, I want the system to seamlessly integrate ML predictions without UI changes so that my workflow remains unchanged while benefiting from improved forecasts

## Core Requirements

### Functional Requirements
- Implement LSTM neural network for time series forecasting of stock returns and volatility
- Extend existing ARIMA implementation to forecast both returns and risk
- Implement XGBoost gradient boosting model for ensemble predictions
- Auto-select best-performing model per ticker based on validation metrics (R², RMSE)
- Train models using historical returns, volume, and other market indicators as features
- Replace `forecast_returns()` function entirely with ML-based forecasting
- Maintain MPT method as fallback when ML predictions fail
- Cache trained models with TTL for performance optimization
- Support periodic model retraining (daily/weekly batches)
- Process multiple tickers in parallel using multicore processing

### Non-Functional Requirements
- Performance: Leverage ProcessPoolExecutor for parallel model training across tickers
- Caching: Use existing cache_manager infrastructure with appropriate TTL settings
- Logging: Log model performance metrics (R², RMSE, Sharpe ratio) to backend console only
- Error Handling: Graceful fallback to MPT when ML models fail with clear logging
- Compatibility: Maintain output format (pandas Series) compatible with existing optimize_portfolio() pipeline

## Visual Design
No visual changes required. Backend-only implementation with no frontend modifications.

## Reusable Components

### Existing Code to Leverage
- **cache_manager.py**: @cached decorator for caching trained models and predictions (l1_ttl, l2_ttl parameters)
- **portfolio_optimization.py**: 
  - `get_stock_data()` for batch stock data fetching with yfinance
  - `sanitize_tickers()` for ticker symbol sanitization
  - `ProcessPoolExecutor` pattern for parallel processing (lines 325-340)
  - `ThreadPoolExecutor` pattern for I/O-bound tasks (line 132)
  - Logging infrastructure (logger.info, logger.warning patterns)
  - Error handling with try/except and fallback mechanisms
- **forecast_models.py**: 
  - Existing ARIMA class structure to extend
  - Fallback mechanism pattern for failed forecasts
- **Data pipeline patterns**:
  - Batch data download using yf.download()
  - DataFrame alignment for optimization pipeline
  - Weight filtering (> 1e-4 threshold)

### New Components Required
- **LSTM Model Class**: LSTM neural network not in existing codebase; requires TensorFlow/Keras or PyTorch implementation
- **XGBoost Model Class**: XGBoost gradient boosting not currently used; requires xgboost library integration
- **Model Selection Engine**: Auto-selection logic based on validation metrics doesn't exist; needed to choose best model per ticker
- **Feature Engineering Pipeline**: Extract returns, volume, and technical indicators as training features
- **Model Cache System**: Cache layer specifically for trained models (extending cache_manager patterns)

## Technical Approach

### Backend (Python/Flask)
- **ML Models**:
  - Create `LSTMModel` class with train() and forecast() methods
  - Extend `ARIMA` class in forecast_models.py to forecast both returns and volatility
  - Create `XGBoostModel` class with feature engineering pipeline
  - Implement `ModelSelector` class to validate and auto-select best model
- **Integration**:
  - Replace `forecast_returns()` function in portfolio_optimization.py with `ml_forecast_returns()`
  - Maintain signature compatibility: input DataFrame, output pandas Series of expected returns
  - Keep fallback to lightweight/Prophet method when ML fails
- **Multicore Processing**:
  - Use ProcessPoolExecutor for parallel model training (CPU-bound)
  - Process each ticker independently with its best-selected model
  - Follow existing pattern from lines 325-340 in portfolio_optimization.py
- **Caching Strategy**:
  - Cache trained models: @cached(l1_ttl=3600, l2_ttl=86400) for 1-hour/1-day TTL
  - Cache predictions: @cached(l1_ttl=900, l2_ttl=14400) matching existing stock data cache
  - Implement model retraining trigger based on cache expiration
- **Logging**:
  - Log model performance metrics during training (R², RMSE, validation scores)
  - Log model selection decisions per ticker
  - Log fallback events when ML predictions fail

### Testing
- Unit tests for each model class (LSTM, ARIMA, XGBoost)
- Integration tests for ml_forecast_returns() function
- Performance tests for multicore processing efficiency
- Fallback mechanism tests to verify MPT backup works

## Out of Scope
- Frontend UI changes or new visualization components
- Manual model selection interface for users
- Frontend display of model performance metrics or comparison charts
- Real-time model training during user requests (rely on cached models)
- Changes to existing API endpoint structure
- Modifications to React components (Optimizer.jsx remains unchanged)

## Success Criteria
- ML models successfully forecast returns for 90%+ of tickers in typical requests
- Multicore processing reduces forecasting time by 50%+ compared to sequential processing
- Model caching reduces response time to <2 seconds for cached predictions
- Fallback to MPT occurs gracefully with logged warnings when ML fails
- Integration maintains full compatibility with existing optimize_portfolio() pipeline
