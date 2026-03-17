# Task 2: Complete UI components

## Overview
**Task Reference:** Task #2 from `agent-os/specs/2026-03-16-portfolio-management/tasks.md`
**Implemented By:** ui-designer
**Date:** 2026-03-17
**Status:** ✅ Complete

### Task Description
Build a complete `PortfolioManager` UI component providing a manual holdings input interface, configuration settings mirrored from Optimizer.jsx, dual pie charts for current vs target allocation, and Buy/Sell list tables.

## Implementation Summary
Created `PortfolioManager.jsx` as a new React component that allows users to manually enter their current portfolio holdings (ticker + quantity pairs), specify optional cash injection, and configure optimization parameters (forecast method, optimization method, date range, risk-free rate). The component submits to the `POST /api/manage-portfolio` endpoint and renders results including dual `react-plotly.js` pie charts showing current vs target allocation, metric cards (return, risk, Sharpe ratio), and exact fractional Buy/Sell list tables.

The component re-uses existing CSS class patterns from `Optimizer.jsx` (form groups, selects, inputs, modal overlays, weights cards, result cards) and introduces new styles under the `.manager-*` namespace for component-specific layouts like the holdings input rows and charts row.

Navigation was wired through `Selector.jsx` and `App.jsx` to provide a dedicated sidebar entry for Portfolio Manager. Full i18n support was added in both English and Korean locales.

## Files Changed/Created

### New Files
- `src/frontend/PortfolioManager.jsx` - Main Portfolio Manager component with holdings input, form, charts, and tables.
- `src/frontend/PortfolioManager.test.jsx` - 6 focused vitest tests covering rendering, interaction, API submission, results rendering, error handling, and modal behavior.

### Modified Files
- `src/frontend/App.jsx` - Added `PortfolioManager` import and `manager` view route.
- `src/frontend/Selector.jsx` - Added `manager` navigation button in sidebar.
- `src/frontend/App.css` - Added section `14b. COMPONENT: PORTFOLIO MANAGER` with styles and responsive rules.
- `src/frontend/locales/en/translation.json` - Added `navigation.manager` and `manager.*` translation keys.
- `src/frontend/locales/ko/translation.json` - Added `navigation.manager` and `manager.*` translation keys in Korean.

### Deleted Files
N/A

## Key Implementation Details

### Holdings Input UI
**Location:** `src/frontend/PortfolioManager.jsx`

Dynamic array-based holdings form with add/remove functionality. Each row has a ticker text input (auto-uppercased) and quantity number input. Users can also upload a CSV file with `TICKER,QUANTITY` format through a modal dialog.

**Rationale:** Follows the interactive input pattern from the spec while keeping the UI simple and intuitive. The CSV upload reuses the modal pattern from Optimizer.jsx.

### Configuration Panel
**Location:** `src/frontend/PortfolioManager.jsx`

Mirrors the Optimizer.jsx configuration with forecast method (Lightweight/Deep Learning), optimization method (Black-Litterman/MPT), date range, and risk-free rate. Reuses `optimizer-form-group`, `optimizer-input`, and `optimizer-select` CSS classes for visual consistency.

**Rationale:** Spec requirement to mirror `Optimizer.jsx` settings panel. Re-using existing CSS classes ensures visual consistency.

### Results View (Charts + Tables)
**Location:** `src/frontend/PortfolioManager.jsx`

Dual `react-plotly.js` donut charts rendered side-by-side showing current allocation (based on holdings × prices) and target allocation (based on optimized weights × total target value). Buy and Sell list tables use the existing `allocation-table` styles with green/red color coding. Metric result cards reuse the `optimizer-result-card` pattern.

**Rationale:** Direct implementation of spec requirements for dual pie charts and fractional Buy/Sell list tables.

## Database Changes (if applicable)
N/A

## Dependencies (if applicable)
N/A — all dependencies (`react-plotly.js`, `axios`, `i18next`) were already in `package.json`.

## Testing

### Test Files Created/Updated
- `src/frontend/PortfolioManager.test.jsx` - 6 tests covering all major UI behaviors.

### Test Coverage
- Unit tests: ✅ Complete
- Integration tests: ✅ Complete (form submission → API mock → results render)
- Edge cases covered: Empty input validation, API error display, modal open/close behavior.

### Manual Testing Performed
Ran `npx vitest run src/frontend/PortfolioManager.test.jsx` — 6/6 tests passed.

## User Standards & Preferences Compliance

### Frontend Component Standards
**File Reference:** `agent-os/standards/frontend/components.md`

**How Your Implementation Complies:**
Uses functional components with hooks (`useState`, `useRef`), follows existing naming conventions (`PortfolioManager.jsx`), and reuses established CSS class patterns from `Optimizer.jsx`.

### CSS Standards
**File Reference:** `agent-os/standards/frontend/css.md`

**How Your Implementation Complies:**
All new styles use CSS custom properties from the design system (`:root` variables). New classes are namespaced under `.manager-*` to avoid conflicts. Responsive breakpoints match existing patterns.

### Accessibility Standards
**File Reference:** `agent-os/standards/frontend/accessibility.md`

**How Your Implementation Complies:**
All form inputs have associated `<label>` elements via `htmlFor`. Buttons have descriptive text. Remove buttons have `aria-label` attributes. Modal overlay supports click-outside-to-close.

### Testing Standards
**File Reference:** `agent-os/standards/testing/test-writing.md`

**How Your Implementation Complies:**
Tests use vitest + @testing-library/react + userEvent for realistic interaction simulation. Axios is mocked to isolate frontend logic. Tests cover rendering, interaction, submission, success/error states, and modal behavior.

## Integration Points (if applicable)

### APIs/Endpoints
- `POST /api/manage-portfolio` - Submits current holdings and configuration, receives optimized weights, prices, buy/sell lists.

### External Services
N/A

### Internal Dependencies
- Depends on the `POST /api/manage-portfolio` endpoint implemented in Task Group 1.

## Known Issues & Limitations
N/A

## Performance Considerations
Plotly.js charts are rendered client-side. For portfolios with many assets, chart rendering is fast due to simple pie chart data structure.

## Security Considerations
N/A

## Dependencies for Other Tasks
Task Group 3 (Test Review & Gap Analysis) depends on these tests for review.
