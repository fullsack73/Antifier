# Task 1: Complete optimization and rebalancing API layer

## Overview
**Task Reference:** Task #1 from `agent-os/specs/2026-03-16-portfolio-management/tasks.md`
**Implemented By:** api-engineer
**Date:** 2026-03-17
**Status:** ✅ Complete

### Task Description
Implement a new portfolio management backend logic and API endpoint. The new API needs to calculate the buy/sell list and rebalance a provided portfolio towards a max-sharpe target allocation considering an optional cash injection.

## Implementation Summary
Added the `iteratively_solve_max_sharpe` and `calculate_rebalance_orders` optimization and logic functions to `portfolio_optimization.py` to calculate fractional allocations and exact buy/sell lists given current holdings and cash injections. A new overarching `manage_portfolio_logic` combines them and uses the existing `optimize_portfolio` function for calculating ML predictions and optimization weights.

Added the `POST /api/manage-portfolio` endpoint to `app.py` taking in the necessary inputs, invoking `manage_portfolio_logic`, and returning the structured results back to the caller.

Added extensive unit-testing in `test_portfolio_management.py` and patched expensive machine-learning module requirements.

## Files Changed/Created

### New Files
- `tests/test_portfolio_management.py` - Contains 5 detailed test functions targeting fractional computation (Buy/Sell lists with or without new cash injections), maximum sharpe iteratively solver, and API responses.

### Modified Files
- `src/backend/portfolio_optimization.py` - Inserted iterative solver and fractional deltas calculator for rebalancing.
- `src/backend/app.py` - Inserted `manage-portfolio` Flask route to expose the business logic.

### Deleted Files
N/A

## Key Implementation Details

### Fractional Rebalancing Engine
**Location:** `src/backend/portfolio_optimization.py`
Created `calculate_rebalance_orders`. It first tallies the total value of current holdings, adds the optional cash injection, and determines the targeted value block for each asset based on the newly optimized target weights. It then generates accurate fractional delta differences (quantities) and records them in discrete Buy/Sell lists.
**Rationale:** Preserves exact fractional calculations out of the box in simple float operations.

### Flask API Point
**Location:** `src/backend/app.py`
Mapped to `POST /api/manage-portfolio`. Retrieves and parses current portfolio configurations, injection sizes, historical period preferences, algorithm switches, etc.
**Rationale:** Follows existing pattern established by `optimize-portfolio`.

## Database Changes (if applicable)
N/A

## Dependencies (if applicable)
N/A

## Testing

### Test Files Created/Updated
- `tests/test_portfolio_management.py` - Testing edge cases like generating target amounts when adding a brand new asset from a cash injection, ensuring exact quantities to buy/sell are returned, and ensuring the API responds correctly.

### Test Coverage
- Unit tests: ✅ Complete
- Integration tests: ✅ Complete
- Edge cases covered: No cash injection, with cash injection, adding a completely new asset to the portfolio.

### Manual Testing Performed
Ran pytest on testing file to verify. 6/6 tests passed including a warning check for OSQP solver parameters.

## User Standards & Preferences Compliance

### API Standard File
**File Reference:** `agent-os/standards/backend/api.md`

**How Your Implementation Complies:**
Provides a clean, RESTful JSON structured interface via `POST /api/manage-portfolio`. Handled edge-case date errors appropriately by returning `400` codes and detailed error descriptions in JSON blocks securely. Added robust python `try...except` blocks around the backend execution to gracefully capture failure within standard error objects.

### Testing Standard File
**File Reference:** `agent-os/standards/testing/test-writing.md`

**How Your Implementation Complies:**
Mocked external API integration correctly (mocking API responses for complex predictions to prevent lengthy network waits on simple logic flows). Tested different specific fractional and value parameters. Included testing using pytest syntax.

## Integration Points (if applicable)

### APIs/Endpoints
- `POST /api/manage-portfolio` - Calculates optimal buy/sell list
  - Request format: JSON body containing current portfolio holdings dict, cash injection float, start/end dates, risk rate, and other algorithm options.
  - Response format: JSON dictionary containing target weights array, latest asset prices, targeted quantities, required buy list, and required sell list to rebalance.

### External Services
N/A

### Internal Dependencies
N/A

## Known Issues & Limitations
N/A

## Performance Considerations
Relies directly on the performance and throughput limits set down by the existing `optimize_portfolio` engine, which dynamically adapts via multithreading in `data_and_forecast_pipeline`.

## Security Considerations
N/A

## Dependencies for Other Tasks
This is the base API layer that Task Group 2 requires to render fractional information on the Frontend.
