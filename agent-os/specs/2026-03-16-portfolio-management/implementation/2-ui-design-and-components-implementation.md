# Task 2: UI Design and Components

## Overview
**Task Reference:** Task #2 from `agent-os/specs/2026-03-16-portfolio-management/tasks.md`
**Implemented By:** ui-designer
**Date:** 2026-03-17
**Status:** ✅ Complete

### Task Description
Implement the `PortfolioManager.jsx` React component. This UI feature allows users to provide existing holdings (either manually or via CSV upload), inject new cash, view the theoretical target allocation calculated by the optimization backend, and observe exact buy/sell orders. Crucially, the UI provides toggles for "Fractional Shares" trading globally and per-ticker, advanced settings matching `Optimizer.jsx`, and a custom Ticker Space feature via CSV upload.

## Implementation Summary
The implementation successfully created the robust `PortfolioManager` top-level React component. It supports robust dynamic form input arrays to manually add tickets and quantities. Following user requests, we built features identical to `Optimizer.jsx`, including fractional shares toggles globally and individually, "Advanced Settings" modals for forecasting and Black-Litterman values, and specific file uploads. Two different modals handle different file purposes: one for replacing target spaces and one for uploading initial holding quantities. We also implemented download functionality allowing CSV extracts of a user's holdings. Charts visually display current vs target weights utilizing `react-plotly.js`.

## Files Changed/Created

### New Files
- `src/frontend/PortfolioManager.test.jsx` - Contains Vitest unit tests to fulfill task acceptance criteria.

### Modified Files
- `src/frontend/PortfolioManager.jsx` - The main UI component was expanded with modals, tables, CSV export logic, settings, and fractional toggles.

### Deleted Files
N/A

## Key Implementation Details

### Fractional Share Override UI
**Location:** `src/frontend/PortfolioManager.jsx`

Following the logic existing in `Optimizer.jsx`, we introduced a `fractionalOverrides` map bounded to ticker names, and a top-level `allowFractional` global fallback. Upon fetching an initial payload, a user can review the expected `current` and `target` tickers and flip fractional availability for specific assets individually before recalculating.

**Rationale:** This creates a tight feedback loop where integer-shares constrain math calculations, and remaining capital is optimally redistributed by the ML backend according to exact user UI directives.

### Double-CSV Implementation
**Location:** `src/frontend/PortfolioManager.jsx`

The UI must handle two completely distinct uploading scenarios:
1. Uploading a user's initial holdings (`ticker, quantity`)
2. Uploading a user's custom Asset Space for target calculation (raw `tickers`)

**Rationale:** We utilized two hidden `input type='file'` refs pointing to two discrete reading logics so that user CSVs seamlessly construct the form states prior to payload submission.

## Dependencies (if applicable)

N/A

## Testing

### Test Files Created/Updated
- `src/frontend/PortfolioManager.test.jsx` - Tests component lifecycles, mocked API interactions, adding removals of dynamic inputs, and opening closing modals.

### Test Coverage
- Unit tests: ✅ Complete
- Integration tests: ⚠️ Partial (tested with Backend during End-to-End checks)
- Edge cases covered: Modal opening bounds, CSV parsing mock injections.

### Manual Testing Performed
Started the Vite dev server and Python Flask backend. Navigated locally to verify styles map to standard UI rules. Clicked modals, verified file uploads, toggled integer rounding to confirm accurate dynamic API recalculations.

## User Standards & Preferences Compliance

### Accessibility Guidelines
**File Reference:** `@agent-os/standards/frontend/accessibility.md`

**How Your Implementation Complies:** Forms are properly linked via `htmlFor` properties connecting labels and IDs. Modals trap clicks safely and visually label "Close" buttons.

### Components Standards
**File Reference:** `@agent-os/standards/frontend/components.md`

**How Your Implementation Complies:** The container strictly manages state internally and passes clean props to standard HTML elements. Side-effects from asynchronous Axios calls are cleanly wrapped in `useEffect` when dealing with allocations.

## Integration Points (if applicable)

### APIs/Endpoints
- `POST /api/manage-portfolio` - Submits current portfolio configurations and receives optimized buy/sell lists.
  - Request format: JSON dict with `current_holdings`, `cash_injection`, `allow_fractional`, etc.
  - Response format: JSON containing calculated target weights, prices, buy/sell amounts, and remaining cash.

## Known Issues & Limitations

### Limitations
1. **Ticker Validation**
   - Description: The UI currently trusts the user to enter valid Yahoo Finance tickers.
   - Reason: Real-time validation would require excessive rate-limited API calls before submission.
   - Future Consideration: Adding a dedicated ticker lookup endpoint with autocomplete debouncing.

## Performance Considerations
Pie chart renderings are lazily deferred down to `react-plotly.js` rendering to keep form manipulation fast. File parsers execute asynchronously inside FileReader onload callbacks without blocking the main event loop.

## Security Considerations
All CSV parsing handles raw string manipulation cleanly and drops explicitly crafted malformed inputs. Payload objects sent to the python API backend undergo server-side sanitization.

## Dependencies for Other Tasks
Task Group 3 (Testing Review) relies entirely on testing the specific DOM implementations rendered by this group.

## Notes
The fractional toggling exactly replicates the behavior expected inside `Optimizer.jsx`.
