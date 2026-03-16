# Specification: Portfolio Management

## Goal
Enable users to manage their existing portfolios by calculating the optimal buy/sell actions required to rebalance their current asset allocations into a newly optimized target allocation (calculated via maximum Sharpe ratio).

## User Stories
- As an active investor, I want to upload my current portfolio weights and an optional new cash injection so that I can see exactly what fractional shares I need to buy or sell.
- As an active investor, I want the system to calculate an optimal target allocation using ML and optimization methods (e.g., Black-Litterman) over a defined historical period so that my new portfolio structure maximizes risk-adjusted returns.
- As an investor, I want to see visual pie charts comparing my current portfolio with the optimized target portfolio so that I can easily understand the proposed overall changes.

## Core Requirements
### Functional Requirements
- Provide an interactive UI to manually input current portfolio holdings (e.g., entering tickers like `msft` and quantities like `0.1` or `2`), alongside an input for optional additional cash injection.
- UI settings panel to configure the optimization method (Black-Litterman vs MPT), forecast method (Historical vs ML/Lightweight), historical time periods, and to manage candidate "spaces" (e.g., tickers in user's input portfolio or uploading a CSV of custom tickers) to find the target portfolio, mirroring the settings in `Optimizer.jsx`.
- Compute the optimal target portfolio iteratively by adjusting target returns and risks to find the maximum Sharpe ratio using the selected algorithms.
- Calculate exact difference in fractional shares between the current portfolio and the new target portfolio to produce a "Sell List" and a "Buy List".
- Render two pie charts (using Plotly.js) displaying the current allocation vs. optimized target allocation side by side.

### Non-Functional Requirements
- Maintain code modularity and reuse existing validation, error handling, and component styles from `src/frontend/Optimizer.jsx`.
- Ensure exact fractional outputs to maintain mathematical precision.
- Optimize backend iteration logic so that calculating the max Sharpe ratio over the defined space is performant.

## Visual Design
- Visual assets were not provided.
- Ensure the layout mirrors the existing data table and upload UI elements used in the `Optimizer` component.
- The two pie charts should be placed side-by-side on wide screens or stacked on smaller screens for responsive design.

## Reusable Components
### Existing Code to Leverage
- **Frontend Components**: Re-use the CSV/JSON upload modal logic, the advanced settings panel (forecast method, optimization method, history settings), and the fractional share constraints/redistribution tables from `src/frontend/Optimizer.jsx`. Re-use `Plotly.js` integration for the pie charts.
- **Backend Services**: Extend `src/backend/portfolio_optimization.py` leveraging the `optimize_portfolio` function and iteration loops for calculating max-Sharpe weights, using existing data-fetching pipelines (`data_and_forecast_pipeline`).
- **Patterns**: The handling of leftover cash and fractional logic is already well-defined in the `Optimizer` frontend state.

### New Components Required
- **PortfolioManager Frontend View**: A new page/component to specifically handle the dual-state (Current vs. Target) input, executing the backend request, and then rendering the dual pie charts alongside the Buy/Sell tables.

## Technical Approach
- **Database**: Portfolios can optionally be persisted as JSON using the existing mechanism in `portfolio_optimization.py`.
- **API**: A new or extended endpoint (e.g., `POST /api/manage-portfolio`) in the Flask backend that takes current holdings, space parameters, optimization configurations, and cash injection, calculates the maximum Sharpe target, and returns the comparative states.
- **Frontend**: Create a `PortfolioManager` React component using `useTranslation` for i18n, managing form state for the current holdings JSON upload, the cash injection amount, and configuration fields. Render charts with `react-plotly.js`.
- **Testing**: Add backend tests to ensure the rebalancing logic (calculating the buy/sell diffs) is mathematically accurate, paying close attention to fractional accuracy and the handling of the optional cash injection.

## Out of Scope
- Uninvested cash currently sitting inside the portfolio (unless explicitly modeled as an asset).
- Transaction fees or slippage calculations.
- Tax-loss harvesting calculations.

## Success Criteria
- The system correctly produces a mathematically precise buy/sell list in fractional shares using current market prices.
- The target portfolio returned by the backend represents the maximum Sharpe ratio on the efficient frontier.
- The dual pie-chart visualization renders smoothly and accurately reflects both the original state and the newly balanced state.
