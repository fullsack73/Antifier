# Spec Requirements: portfolio-optimizer-log-return-black-litterman

## Initial Description
i want to modify portfolio optimizer to use log return instead of price in model training, and use black-litterman instead of current MPT

## Requirements Discussion

### First Round Questions

**Q1:** I assume you want all forecasting models (`ARIMA`, `LSTM`, `XGBoost`) in `forecast_models.py` to be updated to use log returns (`ln(P_t / P_{t-1})`) instead of simple percentage returns. Is that correct?
**Answer:** yes.

**Q2:** For the Black-Litterman model, I assume we should use the returns forecasted by our ML models (ARIMA/LSTM/XGBoost) as the "investor views". Is that correct?
**Answer:** that's right. and, i'd also want to modify things to use soft voting ensemble of the three models instead of current winner-takes-all method

**Q3:** Black-Litterman requires a "prior" (market implied equilibrium returns). I assume we should use a market index like S&P 500 (from `snp.csv`) to calculate the market risk premium and implied returns. Is that correct?
**Answer:** yeah but, #file:snp.csv is just ticker list of snp 500's individual stocks. we should just fetch price of ^GSPC via yfinance

**Q4:** For the confidence levels in the views (forecasts), should we calculate this based on the model's prediction error (e.g., standard deviation of residuals) or use a static confidence interval?
**Answer:** let's use standard deviation for now

**Q5:** I assume you want to replace the current `EfficientFrontier` (Mean-Variance) implementation in `portfolio_optimization.py` completely with `BlackLittermanModel`, or should we keep Mean-Variance as an option?
**Answer:** let's replace it completely

**Q6:** When converting back to expected annual returns for the final portfolio optimization output, should we convert the log returns back to simple returns for display purposes?
**Answer:** yes, that would be better for user experience

### Existing Code to Reference
No similar existing features identified for reference, but will be modifying:
- `src/backend/forecast_models.py`
- `src/backend/portfolio_optimization.py`

### Follow-up Questions
None required.

## Visual Assets

### Files Provided:
No visual assets provided.

## Requirements Summary

### Functional Requirements
- **Log Returns Transformation**: Modify all forecasting models (`ARIMA`, `LSTM`, `XGBoost`) to transform price data into log returns (`ln(P_t / P_{t-1})`) before training and forecasting.
- **Ensemble Forecasting**: 
  - Replace the "ModelSelector" winner-takes-all logic with a **Soft Voting Ensemble**.
  - Combine predictions from all three models to generate a single "View" for each asset.
  - Calculate the aggregated/consensus standard deviation to use as confidence.
- **Black-Litterman Optimization**:
  - Replace `EfficientFrontier` (Mean-Variance) with Black-Litterman model logic.
  - **Market Benchmark**: Fetch historical data for S&P 500 (`^GSPC`) using `yfinance` to calculate market equilibrium returns (The Prior).
  - **Investor Views**: Use the Ensemble Forecasts (returns) as the views vector ($Q$) and the Identity matrix for the picking matrix ($P$) (assuming absolute views on each asset).
  - **View Confidence**: Use the ensemble standard deviation for the view uncertainty matrix ($\Omega$).
- **Output Conversion**: Ensure final expected returns are converted from log returns back to simple arithmetic annual returns for user display.

### Reusability Opportunities
- Utilize `PyPortfolioOpt`'s built-in `black_litterman` module (`pypfopt.black_litterman`).
- Reuse existing `CovarianceShrinkage` for risk models.
- Reuse `yfinance` integration for fetching generic market data.

### Scope Boundaries
**In Scope:**
- Modifying `forecast_models.py` internals (data prep and training).
- Creating/Modifying an ensemble mechanism in `forecast_models.py`.
- Rewriting the optimization logic in `portfolio_optimization.py`.
- Fetching `^GSPC` data.

**Out of Scope:**
- Frontend changes (assuming the API response structure remains compatible or minimal changes).
- Changing the inputs to the optimizer (tickers, weights constraints).
- Adding other distinct portfolio theories (e.g., HRP).

### Technical Considerations
- **Log Returns**: `np.log(prices / prices.shift(1))`.
- **Ensemble**: Average of predictions can be simple mean or weighted. "Soft voting" usually implies averaging probabilities in classification, but for regression/forecasting, it implies averaging the continuous outputs.
- **Exceptions**: Ensure fallback if `^GSPC` fetch fails (maybe default to a static risk aversion or risk premium).
