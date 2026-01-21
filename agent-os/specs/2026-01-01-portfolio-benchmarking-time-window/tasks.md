# Task Breakdown: Portfolio Benchmarking Time Window

## Overview
Total Tasks: 3 task groups
Assigned roles: api-engineer, ui-designer, testing-engineer

**Note:** No database layer required - this feature is stateless with ephemeral calculations only.

## Task List

### Backend API Layer

#### Task Group 1: Portfolio Benchmarking API Endpoint
**Assigned implementer:** api-engineer
**Dependencies:** None

- [x] 1.0 Complete backend API for portfolio benchmarking
  - [x] 1.1 Write 2-8 focused tests for portfolio benchmarking endpoint
    - Limit to 2-8 highly focused tests maximum
    - Test only critical behaviors: valid portfolio calculation, date validation, missing ticker handling, S&P 500 data fetch, risk-free calculation
    - Skip exhaustive coverage of all edge cases
  - [x] 1.2 Create portfolio benchmarking calculation module in `src/backend/portfolio_benchmark.py`
    - Function: `calculate_portfolio_benchmark(portfolio_data, budget, start_date, end_date, risk_free_rate)`
    - Parse portfolio JSON to extract weights and ticker list
    - Validate portfolio structure (weights, prices present)
    - Calculate shares for each ticker: (budget × weight) / price_at_start_date
    - Handle tickers with zero/missing prices appropriately
  - [x] 1.3 Implement historical data fetching for portfolio tickers
    - Use yfinance to fetch historical prices for all tickers in date range
    - Fetch S&P 500 (^GSPC) historical data for same period
    - Handle missing data gracefully (skip dates or notify)
    - Reuse `validate_date_range()` pattern from existing app.py
    - Follow existing `generate_data()` pattern for yfinance usage
  - [x] 1.4 Build timeline calculations
    - Build portfolio_timeline: for each date, sum(shares × price_on_date) across all tickers
    - Build sp500_timeline: calculate sp500_shares = budget / sp500_price_at_start, track sp500_shares × price_on_date
    - Build riskfree_timeline: for each date, calculate days_elapsed, value = budget × (1 + rate)^(days_elapsed/365)
    - Ensure all three timelines have consistent date keys
  - [x] 1.5 Calculate aggregated summary metrics
    - Portfolio: initial_value (budget), final_value, profit_loss
    - S&P 500: initial_value (budget), final_value, profit_loss
    - Risk-free: initial_value (budget), final_value, profit_loss
    - Calculate return percentages for each
  - [x] 1.6 Create Flask endpoint `/api/benchmark-portfolio` (POST)
    - Accept JSON payload: portfolio_data, budget, start_date, end_date, risk_free_rate
    - Call calculation module from 1.2
    - Return JSON response with: portfolio_timeline, sp500_timeline, riskfree_timeline, summary
    - Follow existing Flask endpoint patterns from app.py
    - Handle CORS configuration (already set up in app.py)
  - [x] 1.7 Implement comprehensive error handling
    - Return 400 for validation errors (invalid dates, missing fields, invalid JSON structure)
    - Return 404 for missing ticker data
    - Return 500 for calculation failures
    - Provide clear, user-friendly error messages
    - Follow existing error handling patterns from app.py
  - [x] 1.8 Ensure API layer tests pass
    - Run ONLY the 2-8 tests written in 1.1
    - Verify critical calculation behaviors work
    - Test with sample portfolio JSON
    - Do NOT run the entire test suite at this stage

**Acceptance Criteria:**
- The 2-8 tests written in 1.1 pass
- Endpoint accepts POST requests with required parameters
- Returns correct timeline data for portfolio, S&P 500, and risk-free asset
- Calculates accurate profit/loss for all three investment types
- Handles missing ticker data gracefully
- Date validation prevents invalid ranges
- Error responses follow RESTful standards (400, 404, 500)

### Frontend Layer

#### Task Group 2: Portfolio Benchmarking UI Components
**Assigned implementer:** ui-designer
**Dependencies:** Task Group 1

- [x] 2.0 Complete UI components for portfolio benchmarking
  - [x] 2.1 Write 2-8 focused tests for UI components
    - Limit to 2-8 highly focused tests maximum
    - Test only critical component behaviors: file upload handling, form submission, chart rendering, error display
    - Skip exhaustive testing of all component states and interactions
  - [x] 2.2 Create PortfolioBenchmark.jsx main component
    - File input with hidden input and styled button trigger (reference Optimizer.jsx pattern)
    - Budget input (number field with dollar symbol/placeholder)
    - Integrate existing DateInput.jsx component for date range selection
    - Risk-free rate input (number field with percentage helper text)
    - Submit button (disabled while loading)
    - Handle portfolio JSON file upload (FileReader, readAsText, JSON.parse)
    - Validate uploaded JSON structure (check for weights, prices)
    - Call `/api/benchmark-portfolio` endpoint on form submission
    - Display loading state during API call
    - Display error messages for upload/API failures
    - Reuse form styling: optimizer-input, optimizer-form-group classes
  - [x] 2.3 Create BenchmarkChart.jsx component
    - Use react-plotly.js for chart rendering
    - Three line traces with data from API response:
      - Portfolio line (cyan color: #06b6d4)
      - S&P 500 line (blue color: #3b82f6)
      - Risk-free line (gray color: #94a3b8)
    - Follow RegressionChart.jsx styling patterns:
      - Dark theme background (paper_bgcolor, plot_bgcolor)
      - Consistent axis styling (color, gridcolor)
      - Legend configuration
    - Y-axis labeled "Portfolio Value ($)"
    - X-axis labeled "Date" with tickformat '%Y-%m-%d'
    - Responsive design (autosize, useResizeHandler)
    - Props: portfolioData, sp500Data, riskfreeData
  - [x] 2.4 Create BenchmarkResultsTable.jsx component
    - Table with three rows: Portfolio, S&P 500, Risk-free asset
    - Columns: Investment Type, Initial Value, Final Value, Profit/Loss, Return %
    - Color-code profit/loss (green for positive, red for negative)
    - Format currency values with $ symbol and commas
    - Format percentages with % symbol
    - Comparison section showing portfolio vs benchmark differences
    - Follow StockScreener table styling patterns
    - Props: summary data from API response
  - [x] 2.5 Update Selector.jsx to add "Benchmark" navigation option
    - Add new view option with icon and label
    - Follow existing view option patterns
    - Use i18n for label text
  - [x] 2.6 Update App.jsx to integrate PortfolioBenchmark
    - Import PortfolioBenchmark component
    - Add new view condition for activeView === "benchmark"
    - Follow existing view routing pattern (similar to "optimizer", "hedge")
  - [x] 2.7 Add internationalization keys
    - Add English translations to locales/en/translation.json:
      - benchmark.title, benchmark.uploadPortfolio, benchmark.budget, benchmark.riskFreeRate
      - benchmark.portfolio, benchmark.sp500, benchmark.riskFree
      - benchmark.initialValue, benchmark.finalValue, benchmark.profitLoss, benchmark.returnPercent
    - Add Korean translations to locales/ko/translation.json (matching keys)
    - Follow existing i18n key patterns
  - [x] 2.8 Ensure UI component tests pass
    - Run ONLY the 2-8 tests written in 2.1
    - Verify critical component behaviors work
    - Test file upload and form submission
    - Do NOT run the entire test suite at this stage

**Acceptance Criteria:**
- The 2-8 tests written in 2.1 pass
- Portfolio JSON file upload works with validation
- Form inputs accept and validate user data
- DateInput component integrates correctly
- Chart renders with three distinct lines
- Results table displays aggregated metrics with proper formatting
- Navigation to benchmark view works
- All UI text is internationalized (English and Korean)
- Styling matches existing dark theme patterns

### Testing & Integration

#### Task Group 3: Test Review & Integration Testing
**Assigned implementer:** testing-engineer
**Dependencies:** Task Groups 1-2

- [x] 3.0 Review existing tests and add critical integration tests
  - [x] 3.1 Review tests from Task Groups 1-2
    - Review the 2-8 tests written by api-engineer (Task 1.1)
    - Review the 2-8 tests written by ui-designer (Task 2.1)
    - Total existing tests: approximately 4-16 tests
  - [x] 3.2 Analyze test coverage gaps for portfolio benchmarking feature
    - Identify critical user workflows that lack test coverage
    - Focus ONLY on gaps related to portfolio benchmarking requirements
    - Prioritize end-to-end workflows over unit test gaps
    - Key workflows to assess:
      - Complete user flow: upload portfolio → set parameters → view results
      - Portfolio with missing ticker data handling
      - Invalid date range handling
      - Invalid JSON file handling
  - [x] 3.3 Write up to 10 additional strategic tests maximum
    - Add maximum of 10 new tests to fill identified critical gaps
    - Focus on integration points and end-to-end workflows:
      - Integration test: API endpoint with real yfinance data (if feasible)
      - Integration test: Frontend form submission to API
      - End-to-end test: Complete benchmark workflow with sample portfolio
      - Error scenario tests: Invalid portfolio JSON, missing tickers, invalid dates
    - Do NOT write comprehensive coverage for all scenarios
    - Skip edge cases unless business-critical
  - [x] 3.4 Run feature-specific tests only
    - Run ONLY tests related to portfolio benchmarking feature (tests from 1.1, 2.1, and 3.3)
    - Expected total: approximately 14-26 tests maximum
    - Do NOT run the entire application test suite
    - Verify all critical workflows pass
    - Document any test failures and required fixes

**Acceptance Criteria:**
- All feature-specific tests pass (approximately 14-26 tests total)
- Critical user workflows for portfolio benchmarking are covered
- No more than 10 additional tests added by testing-engineer
- End-to-end workflow (upload → submit → results) is tested
- Error handling paths are verified
- Testing focused exclusively on portfolio benchmarking feature

## Execution Order

Recommended implementation sequence:
1. Backend API Layer (Task Group 1) - Implement API endpoint and calculation logic
2. Frontend Layer (Task Group 2) - Build UI components and integrate with API
3. Testing & Integration (Task Group 3) - Review tests and add integration coverage

## Additional Notes

- **No Database Required**: This feature is entirely stateless, so no database migrations or models are needed
- **Reuse Patterns**: Heavy emphasis on reusing existing patterns from Optimizer.jsx, DateInput.jsx, RegressionChart.jsx
- **Date Validation**: Leverage existing `validate_date_range()` function from app.py
- **Data Fetching**: Follow yfinance usage patterns from existing `generate_data()` function
- **Styling**: All styling should match existing dark theme and component patterns
- **i18n**: All new UI text must have English and Korean translations
