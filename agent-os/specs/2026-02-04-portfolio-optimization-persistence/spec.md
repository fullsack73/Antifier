# Specification: Portfolio Optimization Persistence

## Goal
Decouple the expensive forecasting process (ML training/prediction) from the cheap optimization process (mathematical solver) to allow users to rapidly iterate on portfolio constraints (target return, risk tolerance, risk-free rate) without re-running forecasts when the underlying data settings (tickers, date range) haven't changed.

## User Stories
- As a user, I want to change my "Target Return" or "Risk Free Rate" and hit "Optimize" again to see a new portfolio instantly, instead of waiting for the ML models to retrain.
- As a user, I want to be informed if my constraints are impossible (e.g., return too high) and be encouraged to try different values without penalty of wait time.
- As a system, I want to reuse valid forecast results (`mu`, `S`) from memory to reduce server load and improve response time.

## Core Requirements
### Functional Requirements
- **Intelligent Cache Reuse**: identifying when a request shares the same forecasting parameters (`start_date`, `end_date`, `tickers`, `forecast_method`) as a previous request.
- **Conditional Pipeline Execution**:
  - **Cold Start**: Fetch Data -> Forecast -> Optimize.
  - **Warm Start**: Retrieve cached Forecast -> Optimize (with new constraints: Target Return, Risk Tolerance, Risk-free Rate).
- **Error Feedback**: If optimization fails (e.g., "infeasible solution"), the error message must explicitly suggest adjusting constraints and trying again (implying it will be fast).

### Non-Functional Requirements
- **Performance**: Warm start optimization should take < 1 second (excluding network latency).
- **Consistency**: The cached forecast must be exactly what was generated for the given date range/tickers.

## Visual Design
- **No new visual assets required.**
- **Error Message Update**: The existing error display container in `Optimizer.jsx` will show the enhanced message.

## Reusable Components
### Existing Code to Leverage
- **Frontend**: `src/frontend/Optimizer.jsx` (Existing UI flow).
- **Backend Logic**: `src/backend/portfolio_optimization.py` `optimize_portfolio` function.
- **Caching**: `src/backend/cache_manager.py` (`@cached` decorator or `get_cache()` instance).
- **Math models**: `pypfopt` library usage in `portfolio_optimization.py` (EfficientFrontier).

### New Components Required
- **Refactored Backend Function**: Separation of `optimize_portfolio` into `get_forecast_data` (cached) and `run_optimization` (fast).

## Technical Approach
### Backend (`src/backend/portfolio_optimization.py`)
1.  **Extract Forecasting Logic**: Move data fetching, cleaning, and forecasting logic into a dedicated function `data_and_forecast_pipeline(tickers, start_date, end_date, ...)` decorated with `@cached`.
    -   Input: Tickers, Date Range, Forecast Method.
    -   Output: `mu` (Expected Returns), `S` (Covariance Matrix), `latest_prices`.
    -   Cache Strategy: Use L1 (Memory) and L2 (Disk/Redis) to persist this expensive step.
2.  **Optimize Portfolio Function**: Refactor `optimize_portfolio` to:
    -   Call `data_and_forecast_pipeline`.
    -   Use the returned `mu` and `S` to run `EfficientFrontier` with the *current* request's `target_return`, `risk_tolerance`, or `risk_free_rate`.
    -   Handle `pypfopt` exceptions and return a structured error message like: "Optimization failed: [Reason]. Try adjusting your Target Return or Risk Tolerance."

### Frontend (`src/frontend/Optimizer.jsx`)
1.  **Error Handling**: Ensure the error message returned from the backend is displayed clearly to the user.
2.  **UX**: No changes to the button. The "Optimize" button simply remains valid to click again.

## Out of Scope
- Disk persistence of the *forecast objects* beyond what the existing `cache_manager` provides (no new file formats).
- "Forecast Only" button in the UI.
- Changing the ML algorithms logic.

## Success Criteria
- User can run an initial optimization (takes ~10-30s).
- User changes "Target Return" or "Risk Free Rate" and clicks "Optimize" again.
- Result appears in < 2s.
- Optimization errors explicitly guide the user to retry with different parameters.
