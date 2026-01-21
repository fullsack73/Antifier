# Specification: Portfolio Optimizer Log Return & Black-Litterman

## Goal
Update the portfolio optimization engine to improve prediction accuracy and allocation stability by implementing Log Returns for training, Soft Voting Ensemble for forecasting, and the Black-Litterman model for optimization.

## User Stories
- As a **Financial Analyst**, I want the forecasting models to use log returns instead of simple returns so that the predictions better satisfy statistical assumptions (stationarity, additivity).
- As an **Investor**, I want the portfolio optimizer to use the Black-Litterman model instead of Mean-Variance Optimization so that the resulting allocations are less extreme and incorporate market equilibrium assumptions.
- As a **User**, I want the system to combine predictions from multiple models (ARIMA, LSTM, XGBoost) via a soft voting ensemble so that I get a more robust and reliable forecast.

## Core Requirements
### Functional Requirements
- **Log Returns Transformation**: All forecasting models (`ARIMA`, `LSTM`, `XGBoost`) must transform price data into log returns (`ln(P_t / P_{t-1})`) before training and forecasting.
- **Ensemble Forecasting**:
  - Implement a "Soft Voting" mechanism that averages the predictions from all trained models.
  - Calculate the standard deviation across model predictions to serve as the confidence metric.
  - Replace the "winner-takes-all" `ModelSelector`.
- **Black-Litterman Optimization**:
  - Fetch historical data for S&P 500 (`^GSPC`) to calculate market parameters.
  - Calculate Market Risk Aversion ($\delta$) using the S&P 500 data.
  - Use the Ensemble Forecasts as "Investor Views" ($Q$ vector) with an Identity picking matrix ($P$).
  - Use the Ensemble Standard Deviation to construct the View Uncertainty Matrix ($\Omega$).
  - Generate optimal weights using the Black-Litterman posterior returns and covariance.
- **Output standardization**: Convert final optimized expected returns from log scale back to simple arithmetic annual returns for user display.

### Non-Functional Requirements
- **Robustness**: The optimization must fall back gracefully if the S&P 500 data cannot be fetched (e.g., use default risk aversion).
- **Performance**: Black-Litterman calculation should not significantly increase the runtime compared to the previous Efficient Frontier method.

## Visual Design
No new UI screens. The existing "Portfolio Optimization" results will transparently use the new engine.

## Reusable Components
### Existing Code to Leverage
- **Libraries**: `PyPortfolioOpt` (specifically `black_litterman`, `risk_models`, `efficient_frontier`), `yfinance`, `scikit-learn`, `numpy`.
- **Classes**: Existing `ARIMA`, `LSTM`, `XGBoost` model structures in `src/backend/forecast_models.py`.
- **Data**: `cache_manager.py` for caching S&P 500 data.

### New Components Required
- **Ensemble Logic**: A mechanism to aggregate forecasts (Weighted average or simple mean) and compute consensus uncertainty.
- **Black-Litterman Integration**: New logic in `src/backend/portfolio_optimization.py` to instantiate and solve `BlackLittermanModel`.

## Technical Approach
### Forecasting (`src/backend/forecast_models.py`)
- Modify `ARIMA`, `LSTM`, `XGBoost` `train` methods to compute `log_returns = np.log(prices / prices.shift(1))`.
- Update `forecast` methods to return log return predictions.
- Create `EnsemblePredictor` class or function:
    - Train all 3 models.
    - Collect predictions $\mu_1, \mu_2, \mu_3$.
    - View $Q = \text{mean}(\mu_1, \mu_2, \mu_3)$.
    - Confidence $\sigma = \text{std}(\mu_1, \mu_2, \mu_3)$.

### Portfolio Optimization (`src/backend/portfolio_optimization.py`)
- **Market Data**: `yf.download("^GSPC")` to get market prices.
- **Prior**:
    - Calculate market covariance matrix (using `risk_models`).
    - Calculate market implied risk aversion ($\delta$).
- **Views**:
    - $Q$: Ensemble forecast results.
    - $P$: Identity matrix (1.0 for the asset corresponding to the view).
    - $\Omega$: Diagonal matrix with variance of ensemble predictions (or proportional logic).
- **Optimization**:
    - `bl = BlackLittermanModel(cov_matrix, P=P, Q=Q, omega=omega, delta=delta)`
    - `rets = bl.bl_returns()`
    - `cov = bl.bl_cov()`
    - Optimize for Max Sharpe or Target Volatility using the posterior `rets` and `cov`.

## Out of Scope
- Frontend UI modifications.
- Implementing "Relative Views" (e.g., Asset A will outperform Asset B).
- Other optimization objectives (e.g., Min CVaR).

## Success Criteria
- Optimization runs successfully without errors using the new pipeline.
- Portfolio allocations are generated using Black-Litterman logic.
- Expected returns displayed to the user are in simple annual percentage format.
- "Corner solutions" (100% allocation to one asset) are reduced compared to standard Mean-Variance optimization.
