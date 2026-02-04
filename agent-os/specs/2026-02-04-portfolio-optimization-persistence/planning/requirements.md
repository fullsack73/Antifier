# Spec Requirements: portfolio-optimization-persistence

## Initial Description
in #file:portfolio_optimization.py, if user fails to generate a portfolio that satisfies user's target return & risk tolerance, user has to wait for entire forecast and optimization process to be done if they were to try out different return and risk.

## Requirements Discussion

### First Round Questions

**Q1:** I assume you want to separate the "Forecasting" (expensive) step from the "Optimization" (cheap) step. Is that correct, or do you prefer to keep them as one generic call that intelligently caches intermediate results?
**Answer:** yes. training & forecasting seperated from optimization. BUT when iniital call, they will go together without stopping. but when the date. range(training set) hasn't changed, the app should ONLY call optimization with changed variables(target return, risk).
to put it clearly: IF initial call, forecast and optimize. IF NOT initial call AND date range unchanged, optimize only.

**Q2:** I'm thinking we should persist the "Forecast Results" (Expected Returns & Covariance Matrix) to disk so they can be reused across server restarts. Should we do this, or is in-memory caching sufficient?
**Answer:** no, current caching method will have to do for now.

**Q3:** I assume the reuse validity should be based on `tickers`, `start_date`, `end_date`, and `forecast_method`. If any of these change, we must re-run forecasting. Is that correct?
**Answer:** yes. like i mentioned before if variables used for training and forecast(date range and tickers, method) change, we need to run the process again for a new model.

**Q4:** I'm thinking of updating the frontend `Optimizer.jsx` to have a "Generate Forecast" stage followed by an "Optimize" stage where users can tweak constraints without re-waiting. Should we change the UI flow this way, or keep the single "Optimize" button and just speed it up backend-side?
**Answer:** i don't think we need a new button for this. just use existing optimize button

**Q5:** For the persistence mechanism, should we reuse the existing `logs/portfolio_results` directory structure or create a new `logs/forecasts` directory for these intermediate states?
**Answer:** let's reuse portfolio_results

**Q6:** If the optimization fails to find a solution (e.g., target return too high), should the potential error message now explicitly suggest "Try different constraints using the existing forecast"?
**Answer:** yup. we should say that to the user explicitly after the error message

### Existing Code to Reference
The user explicitly pointed to the following files to reference and understand:
- `src/frontend/Optimizer.jsx`
- `src/backend/portfolio_optimization.py`

These files contain the current implementation of the portfolio optimization logic and UI.

### Follow-up Questions
No follow-up questions were needed as the user provided clear instructions.

## Visual Assets

### Files Provided:
No visual assets provided.

### Visual Insights:
No visual assets provided.

## Requirements Summary

### Functional Requirements
- **Intelligent Forecasting Reuse**: The system must detect when a user initiates an optimization request that uses the same forecasting inputs (tickers, start date, end date, risk-free rate, forecast method) as a previous run.
- **Conditional Execution logic**:
    - **Initial Call / New Inputs**: Run full pipeline: Fetch Data -> Forecast -> Optimize.
    - **Subsequent Call (Same Inputs)**: Skip Fetch/Forecast. reuse cached forecast results (Expected Returns `mu`, Covariance Matrix `S`). Run Optimize only with new constraints (Target Return, Risk Tolerance, Risk-free rate).
- **Backend Caching**: Use existing in-memory caching mechanisms (no disk persistence for forecasts required per user request).
- **Optimization Error Handling**: If optimization fails (e.g., impossible constraints), the error message must explicitly inform the user they can retry with different constraints without re-running the forecast.
- **UI Interaction**:
    - No new buttons or major UI flow changes.
    - The "Optimize" button remains the single entry point.
    - The user experience should just be "faster" on the second try.

### Reusability Opportunities
- **Backend**: `src/backend/portfolio_optimization.py` - Modify `optimize_portfolio` function to intelligently check for cached forecast results.
- **Frontend**: `src/frontend/Optimizer.jsx` - No major structural changes, but ensure it handles the updated error messages and potentially faster response times smoothly.

### Scope Boundaries
**In Scope:**
- Modifying `optimize_portfolio` in `portfolio_optimization.py` to implement the separation logic.
- Ensuring `mu` (expected returns) and `S` (covariance matrix) are cached in memory.
- Updating error messages to suggest retrying with different constraints.
- Keeping the existing "Optimize" button workflow in `Optimizer.jsx`.

**Out of Scope:**
- Disk persistence for forecast results (user explicitly rejected this).
- Creating new UI buttons or separate "Forecast" vs "Optimize" stages in the UI.
- Changing the fundamental forecasting or optimization algorithms (BL, MPT, etc.) themselves, only how they are called.

### Technical Considerations
- **Cache Keys**: The cache key for the forecast steps needs to be robust, including `tickers` (hashed or sorted list), `start_date`, `end_date`, and `forecast_method`.
- **State Management**: The backend needs to hold the state of the "last successful forecast" or use a keyed cache to retrieve it.
- **Concurrency**: Ensure that multiple users (or parallel requests) don't clobber each other's cached forecasts if using global variables suitable for a single-user local app context (standard Flask dev server), but ideally use a proper cache per request parameters.
