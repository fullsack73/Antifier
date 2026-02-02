# Specification: Portfolio Optimizer Model Selection

## Goal
Empower users to choose between different portfolio optimization strategies, including Black-Litterman (default), Deep Learning Ensemble, Lightweight Prediction, and Classic MPT, to better suit their specific investment needs and data availability.

## User Stories
- As a user, I want to select "Deep Learning Ensemble" to use pure ML predictions without market equilibrium assumptions.
- As a user, I want to select "Classic MPT" to see a baseline efficient frontier based on historical data.
- As a user, I want to select "Lightweight" to get fast results for stocks with limited data.
- As a user, I want "Black-Litterman" to remain the default for the most robust general-purpose optimization.

## Core Requirements
### Functional Requirements
- **Model Selection**: Add a dropdown in the Optimizer to select the strategy.
- **Strategies**:
  - **Black-Litterman**: Current implementation (ML Views + Market Caps).
  - **Deep Learning Ensemble**: Use ML forecasts directly as expected returns.
  - **Lightweight Prediction**: Use simplified statistical forecasts.
  - **Classic MPT**: Use standard historical mean/CAGR.
- **Backend**: API must accept the selected strategy and execute the corresponding pipeline.

### Non-Functional Requirements
- **Performance**: Ensure non-ML methods (MPT, Lightweight) return faster than ML methods.
- **Backward Compatibility**: API must default to Black-Litterman if no model is specified.

## Visual Design
- **Integration**: Add "Model Strategy" dropdown to the existing input grid in `Optimizer.jsx`.
- **Style**: Match existing `.optimizer-select` and `.optimizer-form-group` styling.
- **Reference**: No specific mockups provided; follow existing UI patterns.

## Reusable Components
### Existing Code to Leverage
- **Frontend**: `Optimizer.jsx` (existing form structure).
- **Backend Model**: `EnsemblePredictor` in `forecast_models.py`.
- **Backend Logic**: `optimize_portfolio` in `portfolio_optimization.py` (caching, data fetching).
- **Backend Fallback**: `lightweight_ensemble_forecast` in `lightweight_forecast.py`.

### New Components Required
- **None**: Modification of existing components only.

## Technical Approach
- **Frontend**:
  - Add `modelStrategy` state to `Optimizer.jsx`.
  - Add `<select>` input using `t('optimizer.modelStrategy')`.
  - Update `handleSubmit` to include `model_strategy` in API payload.
- **Backend API**:
  - Update `optimize_portfolio` signature to accept `model`.
  - Implement branching logic to select `mu` (expected returns) generation method.
  - Pass `mu` to common `EfficientFrontier` optimization block.
- **I18n**: Add keys for `modelStrategy` and options in `en` and `ko` locales.

## Out of Scope
- User interface for manually entering Black-Litterman views.
- Developing new ML models (using existing ones).
- Comparison view (single result only).

## Success Criteria
- User can successfully generate extended efficient frontiers using all 4 methods.
- API handles switch correctly without errors.
- "Lightweight" and "MPT" selections execute significantly faster than ML-based ones.
