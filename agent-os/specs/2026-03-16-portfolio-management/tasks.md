# Task Breakdown: Portfolio Management

## Overview
Total Tasks: 3 Task Groups
Assigned roles: api-engineer, ui-designer, testing-engineer

## Task List

### API Layer

#### Task Group 1: Backend Optimization and Rebalancing API
**Assigned implementer:** api-engineer
**Dependencies:** None

- [ ] 1.0 Complete optimization and rebalancing API layer
  - [ ] 1.1 Write 2-8 focused tests for the new `manage-portfolio` API endpoint and rebalancing calculations.
    - Test maximum Sharpe ratio iterative optimization loop.
    - Test the exact fractional calculation logic for Buy/Sell lists considering the cash injection.
  - [ ] 1.2 Implement the Portfolio Management optimization logic in `src/backend/portfolio_optimization.py` (or related service files).
    - Iteratively adjust target return/risk space to calculate the max Sharpe ratio allocation.
  - [ ] 1.3 Create new Flask API endpoint (e.g., `POST /api/manage-portfolio`) to receive configuration settings, historical parameters, cash injection, and current portfolio holdings.
  - [ ] 1.4 Implement the logic to generate exact fractional "Buy List" and "Sell List" comparing current holdings to target optimized weights.
  - [ ] 1.5 Ensure API layer tests pass
    - Run ONLY the 2-8 tests written in 1.1
    - Verify calculating the difference states (buy/sell list) works correctly given various mock inputs.

**Acceptance Criteria:**
- The 2-8 tests written in 1.1 pass.
- The Flask endpoint accurately computes the target maximum Sharpe allocation over the specified space.
- The computation perfectly outputs the fractional deltas needed (Buy list / Sell list).

### Frontend Components

#### Task Group 2: UI Design and Components
**Assigned implementer:** ui-designer
**Dependencies:** Task Group 1

- [ ] 2.0 Complete UI components
  - [ ] 2.1 Write 2-8 focused tests for `PortfolioManager` UI components.
    - Focus on manual holdings input parsing, form submission to the backend, and charting renders.
  - [ ] 2.2 Create the `PortfolioManager.jsx` base page/component structure.
    - Setup routing or tab navigation to access this new feature.
  - [ ] 2.3 Implement the manual holdings input UI.
    - Fields for entering ticker (e.g., `msft`) and quantity (e.g., `2`), along with a cash injection input field.
  - [ ] 2.4 Re-use and integrate the configuration settings panel mirrored from `Optimizer.jsx`.
    - Dropdowns/inputs for optimization method (Black-Litterman vs MPT), forecast method (Historical vs ML/Lightweight), and historical time periods.
    - Manage candidate "spaces" (using the tickers from the user's current holdings input or allowing a CSV upload).
  - [ ] 2.5 Build the Results View.
    - Implement the two `react-plotly.js` pie charts (Current Allocation vs. Target Allocation) side by side.
    - Build exact fractional Buy and Sell list tables.
  - [ ] 2.6 Ensure UI component tests pass
    - Run ONLY the 2-8 tests written in 2.1.
    - Ensure styling matches existing application framework.

**Acceptance Criteria:**
- The 2-8 tests written in 2.1 pass.
- Users can successfully manually input their exact holding quantities and configure all optimization details interactively.
- The output pie charts and buy/sell tables render accurately based on backend API responses.

### Testing

#### Task Group 3: Test Review & Gap Analysis
**Assigned implementer:** testing-engineer
**Dependencies:** Task Group 1, Task Group 2

- [ ] 3.0 Review existing tests and fill critical gaps only
  - [ ] 3.1 Review tests from Task Groups 1-2.
    - Review the 2-8 tests written by api-engineer (Task 1.1).
    - Review the 2-8 tests written by ui-designer (Task 2.1).
  - [ ] 3.2 Analyze test coverage gaps for THIS feature only.
    - Evaluate if exact edge case scenarios for zero initial positions, massive cash injections, or invalid space configurations are handled securely.
  - [ ] 3.3 Write up to 10 additional strategic tests maximum.
    - Add end-to-end testing workflow for a typical user entering a 3-asset portfolio, generating a max Sharpe optimization, and verifying the Buy/Sell fractions.
  - [ ] 3.4 Run feature-specific tests only.
    - Run ONLY tests related to this portfolio-management spec's feature constraints.

**Acceptance Criteria:**
- All feature-specific tests pass.
- Critical user workflows (calculating the rebalance delta based on manual input and interactive configuration) are fully verified.
- Testing limits (maximum ~10 additional tests added) are fully respected.

## Execution Order
Recommended implementation sequence:
1. API Layer (Task Group 1): Establishes the core mathematical optimization logic and backend routes.
2. Frontend Design (Task Group 2): Connects the user experience to the core algorithmic API.
3. Test Review & Gap Analysis (Task Group 3): Validates complete end-to-end robustness.
