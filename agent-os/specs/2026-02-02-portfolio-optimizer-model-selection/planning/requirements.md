# Spec Requirements: portfolio-optimizer-model-selection

## Initial Description
i want to modify the app to let user have more choice in running the portfolio optimizer, such as being able to choice between Black-Litterman model and MPT, ML-based ensemble and lightweight prediction methods

## Requirements Discussion

### First Round Questions

**Q1:** I assume we should add a "Model Strategy" selection method (like a dropdown) to the top of the existing `Optimizer` page. Is that correct, or do you envision a completely separate page/wizard for advanced optimization?
**Answer:** not exactly, i was thinking we should add the selector as part of the input section of `src/frontend/Optimizer.jsx`, so it should belong to where other input componets are located at.

**Q2:** For the **Black-Litterman model**, it requires "investor views" (subjective beliefs about returns). I assume we should add a UI section where users can optionally add views (e.g., "AAPL will return 5%"), while fetching market capitalizations automatically for the equilibrium portfolio. Is this the right level of complexity?
**Answer:** no, i don't think we should implement that right now i might make that as a part of "Advanced Settings" option later in the development. so when i say to have 'choice', i mean the ability to use parameter-predetermined BL model(which is used by default as of now) OR MPT

**Q3:** Regarding the **ML-based ensemble**, I assume this refers to using our existing regression models (LightGBM/XGBoost) to predict *expected returns* which are then fed into the Mean-Variance optimizer, rather than using historical averages. Is that accurate?
**Answer:** by that i meant how `src/backend/portfolio_optimization.py` handle things. which is training ARIMA, LSTM and XGBoost respectively, and generating 1 year ahead forecast by ensemble. but, if you were to get the exact idea, you best read `portfolio_optimization.py` and `forecast_models.py` top to bottom and figure things out.

**Q4:** For **Lightweight Prediction**, I assume you mean simpler statistical methods like Exponential Moving Averages (EMA) or simple historical mean returns to estimate parameters without training full ML models. Is that correct?
**Answer:** yes. that, and other methods ensembled. it's at `src/backend/lightweight_forecast.py`, and it is used as a backup in case of ML optimization failing.

**Q5:** The **MPT (Modern Portfolio Theory)** option is currently the standard. I assume this choice should accept historical data as usual but perhaps allow toggling between different covariance estimation methods (e.g., sample covariance vs. Ledoit-Wolf shrinkage) if desired, or keep it simple?
**Answer:** no, MPT is NOT the current standard. `agent-os/product/tech-stack.md` says otherwise, but that's because i left it unupdated. and i think it's best we keep it simple.

**Q6:** Do you want the results section to allow **comparing models** (e.g., seeing MPT weights vs. Black-Litterman weights side-by-side), or should running a new model simply overwrite the displayed results?
**Answer:** no. we produce single portfolio with chosen method.

**Q7:** With ML models potentially taking longer to train/predict, I assume we should implement a specific "Training/Optimization" progress state or spinner in the UI to handle the asynchronous nature of the request.
**Answer:** i already implemented that. so don't bother.

**Q8:** **Exclusions**: Are there any specific optimization constraints (like sector limits, turnover constraints) that we should explicitly *exclude* from this iteration to keep the scope manageable?
**Answer:** no, i'd let user take control and fine tune things to their own ways.

### Existing Code to Reference
**Similar Features Identified:**
- `src/frontend/Optimizer.jsx`: Uses its own input components (not shared with global components).
- `src/backend/portfolio_optimization.py`: Contains existing BL and ML pipeline.
- `src/backend/forecast_models.py`: Contains the `EnsemblePredictor`.
- `src/backend/lightweight_forecast.py`: Contains `lightweight_ensemble_forecast`.

### Visual Assets
**Files Provided:**
No visual assets provided.
(Bash check confirmed no files found)

## Requirements Summary

### Functional Requirements
- **Model Selection UI**:
  - Add a "Model Strategy" dropdown to the input section of `Optimizer.jsx`.
  - Dropdown options:
    1. **Black-Litterman (Default)**: Uses existing ML ensemble for views + Market Caps.
    2. **Deep Learning Ensemble**: Uses ML ensemble (ARIMA, LSTM, XGBoost) directly as expected returns (skipping BL market prior).
    3. **Lightweight Prediction**: Uses `lightweight_forecast.py` methods directly as expected returns.
    4. **Classic MPT**: Uses historical covariance and returns (standard Mean-Variance).

- **Backend Integration**:
  - Update `optimize_portfolio` in `portfolio_optimization.py` to accept a `model` parameter.
  - Implement switching logic:
    - **BL**: Keep existing logic (ML Views + Market Caps).
    - **Ensemble (Deep Learning)**: Use `mu_views` from ML directly into `EfficientFrontier` (skipping BL step).
    - **Lightweight**: Call `lightweight_ensemble_forecast` -> Use as `mu` -> `EfficientFrontier`.
    - **MPT**: Use `risk_models.CovarianceShrinkage` and historical returns (or CAGR) -> `EfficientFrontier`.

### Reusability Opportunities
- **Existing ML Pipeline**: Reuse `ml_forecast_returns` for both BL and Ensemble modes.
- **Existing Lightweight Logic**: Reuse logic currently serving as fallback.
- **Progress Handling**: Leverage existing progress callback mechanisms.

### Scope Boundaries
**In Scope:**
- Adding dropdown to `Optimizer.jsx`.
- Plumbing selection through API to Backend.
- Refactoring `optimize_portfolio` to branch logic based on selection.

**Out of Scope:**
- "Investor Views" UI for Black-Litterman.
- Side-by-side model comparison.
- Advanced constraint configuration (beyond existing inputs).
- Updating `DateInput` or `TickerInput` components (as `Optimizer.jsx` uses its own).

### Technical Considerations
- **Default Behavior**: Ensure Black-Litterman remains the default if no selection is made.
- **Performance**: ML Ensemble is computationally expensive; ensure non-ML options (MPT, Lightweight) feel faster/responsive.
- **Fallback**: Existing fallback logic (ML -> Lightweight) might need adjustment. If user *explicitly* selects ML, should it fail hard or fall back? (Assume fall back with warning, or fail if user explicitly wanted ML). *Decision: If user explicitly selects a method, try that method. Fallbacks should be handled gracefully but might be irrelevant if user chose "Lightweight" directly.*
