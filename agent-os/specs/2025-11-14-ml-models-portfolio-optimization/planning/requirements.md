# Requirements Documentation

## Initial Concept
Implementing ML models to the portfolio optimization feature

## Research Conversation

### Initial Questions and Answers

**Q1:** I assume you want to integrate multiple ML models (like LightGBM, XGBoost, Random Forest) to enhance the existing PyPortfolioOpt optimization, potentially for predicting expected returns or risk estimates. Is that correct, or are you looking to replace the current Modern Portfolio Theory approach entirely with ML-based optimization?
**Answer:** Using LSTM, ARIMA and XGBoost for return & risk forecast. Full ML-approach with multicore processing. Leave MPT method as backup when ML based analysis fails.

**Q2:** I'm thinking you'll want to train models on historical stock data to predict future returns/volatility as inputs to the portfolio optimizer. Should we use features like historical returns, volume, technical indicators, and financial ratios, or would you like to specify different feature sets?
**Answer:** Yes, train models with returns, volume etc.

**Q3:** For model selection, I assume we should provide users a choice between different ML algorithms (e.g., ensemble methods, gradient boosting, neural networks) and display model performance metrics. Should we auto-select the best-performing model, or let users manually choose?
**Answer:** Auto-selecting models.

**Q4:** I'm thinking we should integrate this into the existing Portfolio Optimization page (where users currently input tickers, risk tolerance, and target returns). Should we add a new "ML-Enhanced Optimization" toggle/section, or create a completely separate page for ML-based portfolio optimization?
**Answer:** The goal is to replace current methods of portfolio optimization (which is MPT + Prophet) entirely. No separate section is required.

**Q5:** For the ML training pipeline, I assume we should cache trained models and retrain periodically (daily/weekly) rather than training on every request for performance. Is that correct, or would you prefer on-demand training with loading indicators?
**Answer:** Yes, caching & retraining would be the best choice.

**Q6:** I'm assuming you want to display ML model performance metrics (R², RMSE, Sharpe ratio improvements) and feature importance visualizations alongside the optimized portfolio results. Should we also show comparison charts between traditional MPT optimization vs ML-enhanced optimization?
**Answer:** It'd be nice, but it doesn't have to be seen at frontend. Just log them using print() or something.

**Q7:** Are there any specific constraints or features you want to exclude from this implementation? For example, should we skip certain model types, avoid real-time training, or not implement certain visualization components in the first version?
**Answer:** No.

### Existing Code to Reference

**Similar Features Identified:**
- Feature: Portfolio Optimization - Path: `src/portfolio_optimization.py`
  - Current implementation uses PyPortfolioOpt with MPT (Efficient Frontier)
  - Uses Prophet for return forecasting (lightweight + Prophet hybrid approach)
  - Has caching infrastructure via cache_manager
  - Includes multicore processing capabilities (ThreadPoolExecutor, ProcessPoolExecutor)
  - Contains forecast_returns() function that needs to be replaced with ML models
  - Contains optimize_portfolio() main function that orchestrates the pipeline
  
- Feature: Forecast Models - Path: `src/forecast_models.py`
  - Partially implemented ARIMA class
  - Already has ARIMA forecasting logic that can be expanded
  - Contains fallback mechanisms for failed forecasts
  
- Components to reuse:
  - Cache manager integration (@cached decorator, l1_ttl, l2_ttl)
  - Batch data fetching (get_stock_data function with yfinance)
  - Data sanitization (sanitize_tickers function)
  - Multicore processing pattern (ThreadPoolExecutor/ProcessPoolExecutor)
  - Logging infrastructure (logger.info patterns)
  - Error handling patterns (try/except with fallbacks)

## Visual Assets

### Files Provided:
No visual files found

### Visual Insights:
No visual assets provided.

## Requirements Summary

### Functional Requirements

#### Core ML Models
- **LSTM Model**: Implement LSTM neural network for time series forecasting of stock returns and risk
- **ARIMA Model**: Extend existing ARIMA implementation for return & volatility forecasting
- **XGBoost Model**: Implement XGBoost gradient boosting for ensemble predictions
- **Auto-Selection**: Automatically select best-performing model based on validation metrics

#### Training Features
- **Feature Engineering**: Use historical returns, volume, and other market indicators as training features
- **Multicore Processing**: Leverage ProcessPoolExecutor for parallel model training across multiple tickers
- **Model Caching**: Cache trained models with TTL (time-to-live) for performance
- **Periodic Retraining**: Implement scheduled model retraining (daily/weekly)

#### Portfolio Optimization Integration
- **Replace Current Method**: Completely replace MPT + Prophet approach with ML-based optimization
- **Fallback Mechanism**: Keep MPT as backup when ML-based analysis fails
- **No UI Changes**: No separate section needed; seamlessly replace backend logic
- **Performance Metrics Logging**: Log model performance (R², RMSE, Sharpe ratio) to console/backend logs only

#### Data Pipeline
- **Batch Processing**: Maintain existing batch data fetching with yfinance
- **Caching Strategy**: Leverage existing cache_manager for stock data and model predictions
- **Data Cleaning**: Reuse existing data sanitization and cleaning logic
- **Error Handling**: Robust error handling with fallback to MPT when ML fails

### Reusability Opportunities

**Existing Components to Reuse:**
- `cache_manager.py`: @cached decorator, cache infrastructure
- `get_stock_data()`: Batch stock data fetching with yfinance
- `sanitize_tickers()`: Ticker symbol sanitization
- `ThreadPoolExecutor/ProcessPoolExecutor`: Multicore processing patterns
- Logging infrastructure: logger.info/warning/error patterns
- Error handling: try/except blocks with fallback mechanisms
- `forecast_models.py`: ARIMA base class to extend

**Backend Patterns to Follow:**
- Cache TTL strategy (l1_ttl=900, l2_ttl=14400)
- Batch data download for performance
- DataFrame alignment for covariance matrix calculation
- Weight filtering (> 1e-4 threshold)
- Latest price fetching for portfolio allocation

### Scope Boundaries

**In Scope:**
- Implement LSTM, ARIMA, XGBoost models for return/risk forecasting
- Auto-select best model based on validation metrics
- Multicore training for parallel processing
- Model caching and periodic retraining
- Replace forecast_returns() function with ML-based implementation
- Keep MPT as fallback mechanism
- Log performance metrics to backend (no frontend display)
- Integrate seamlessly into existing optimize_portfolio() pipeline

**Out of Scope:**
- Frontend UI changes or new sections
- Real-time model training during user requests (use cached models)
- Manual model selection by users
- Frontend display of model performance metrics or comparison charts
- New visualization components
- Changes to existing API endpoints structure

### Technical Considerations

**Integration Points:**
- Replace `forecast_returns()` function in portfolio_optimization.py
- Maintain compatibility with `optimize_portfolio()` pipeline
- Ensure output format matches expected mu (expected returns Series)
- Keep cache_manager integration (@cached decorator)

**Existing System Constraints:**
- Flask backend architecture
- React frontend (no changes needed)
- Python 3.x runtime
- Existing tech stack: pandas, numpy, yfinance, scikit-learn, LightGBM

**Technology Additions Needed:**
- LSTM: tensorflow/keras or pytorch
- XGBoost: xgboost library
- ARIMA: pmdarima (already exists)

**Performance Requirements:**
- Multicore processing for training efficiency
- Model caching to avoid retraining on every request
- Fallback to MPT must be fast if ML fails
- Lightweight execution for production use

**Similar Code Patterns to Follow:**
- Batch processing with yfinance.download()
- Cache decorator usage: @cached(l1_ttl=X, l2_ttl=Y)
- Multicore execution: ProcessPoolExecutor(max_workers=cpu_count())
- Error handling: try/except with fallback to simpler method
- Logging: logger.info() for pipeline stages, logger.warning() for issues
- Data alignment: filter data to match forecast tickers before optimization
