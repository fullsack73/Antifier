# Spec Requirements: Portfolio Benchmarking Time Window

## Initial Description
create feauture in which the user can benchmark the portfolios(.json files containing ticker, weights generated my portfolio optimizer) for specific window of time

## Requirements Discussion

### First Round Questions

**Q1:** Portfolio Storage & Selection - I assume users can upload or select existing .json portfolio files from their system, similar to how they currently select tickers. Is that correct, or should they choose from previously saved portfolios in the app?
**Answer:** No, the app won't save users' portfolios, they will have to upload the json file themselves.

**Q2:** Benchmarking Metrics - I'm thinking we should calculate key performance metrics like total return, annualized return, volatility (standard deviation), Sharpe ratio, and maximum drawdown. Should we include all of these, or would you prefer a different set of metrics?
**Answer:** It's gonna be like a simulation in which user designates budget and portfolio. So, benchmark metric would be how much the portfolio earned or lost.

**Q3:** Time Window Selection - I assume users should be able to specify custom date ranges (start date and end date) for the benchmarking window, similar to the existing date input patterns in your app. Is that correct, or should we provide preset windows (1 month, 3 months, 1 year, etc.)?
**Answer:** Yeah, just reusing date range component and the feature should do.

**Q4:** Comparison Capabilities - Should users be able to compare multiple portfolios side-by-side during the same time window (e.g., comparing Portfolio A vs Portfolio B over the same period), or is this a single-portfolio-at-a-time analysis?
**Answer:** No user won't be comparing between portfolios, they will simulate single portfolio's performance.

**Q5:** Market Benchmark Comparison - I'm assuming we should compare the portfolio's performance against standard market benchmarks like S&P 500 or a custom index during the same time window. Is that correct, or should this be optional?
**Answer:** Guess it would be nice to be able to compare with S&P 500 index and perhaps with riskless asset. So yeah we should do that.

**Q6:** Results Visualization - I'm thinking we should display a line chart showing portfolio value over time within the selected window, plus a summary table with calculated metrics. Should we also include comparative visualizations if comparing multiple portfolios?
**Answer:** We need a line for portfolio, and another two for S&P 500 and riskless asset. And below that, we need a result table comprising each financial products' surplus/deficit.

**Q7:** Portfolio File Format - I assume the .json files contain ticker symbols as keys and their weights as values (matching the output format from your portfolio optimizer). Can you confirm this structure, or provide an example?
**Answer:** JSON file looks like the provided example with structure: {prices: {}, return: float, risk: float, sharpe_ratio: float, weights: {ticker: weight}, portfolio_id: string}

**Q8:** Results Storage - Should users be able to save or export their benchmark results to a .json file for future reference, or is this just an on-demand analysis view?
**Answer:** No I don't think we need to save benchmark results at the moment.

**Q9:** Scope Boundaries - Are there any specific features or calculations you definitely DON'T want included in this initial version (e.g., transaction costs, dividend adjustments, sector breakdowns)?
**Answer:** Not that I can think of one.

### Follow-up Questions

**Follow-up 1:** Budget Input - For the simulation, should users enter a dollar amount (e.g., $10,000) that gets allocated across the portfolio weights, or should they enter the number of shares for each ticker based on the weights?
**Answer:** Yes, user should enter a dollar amount which gets distributed accordingly to the weights of the portfolio.

**Follow-up 2:** Risk-Free Asset Rate - What rate should we use for the risk-free asset comparison? Should it be configurable (user enters the rate), or use a standard rate like the current 10-year Treasury yield?
**Answer:** User should be able to enter the rate of riskless asset.

**Follow-up 3:** Existing Features Reference - You mentioned reusing the date range component. Could you point me to the date input component files, the backend logic that fetches historical price data, and any chart visualization components that display time-series line charts?
**Answer:** Refer to DateInput.jsx, app.py (specifically generate_data function), StockChart.jsx, and RegressionChart.jsx.

### Existing Code to Reference

**Similar Features Identified:**
- **Date Input Component**: `src/frontend/DateInput.jsx` - Reusable date range selector with validation and debouncing
- **Backend Data Fetching**: `src/backend/app.py` - Specifically the `generate_data()` and `validate_date_range()` functions for fetching historical stock prices
- **Chart Visualization Components**: 
  - `src/frontend/StockChart.jsx` - Line chart component using Plotly for time-series data
  - `src/frontend/RegressionChart.jsx` - Multi-line chart component with markers and lines
- **Styling Patterns**: Existing charts use consistent dark theme styling with cyan/blue color scheme

**Portfolio JSON Structure Reference:**
Example from `portfolio_1765538181036.json`:
```json
{
  "prices": {"ABBV": 223.98, "APH": 139.09, ...},
  "return": 0.3,
  "risk": 0.10040853992573658,
  "sharpe_ratio": 2.7388108641296194,
  "weights": {"ABBV": 0.00097, "APH": 0.0261, ...},
  "portfolio_id": "portfolio_1765538181036"
}
```

## Visual Assets

### Files Provided:
No visual assets provided.

### Visual Insights:
N/A - No visual mockups were provided. Development should follow existing UI patterns from StockChart and RegressionChart components.

## Requirements Summary

### Functional Requirements
- **Portfolio Upload**: Users upload a .json file containing portfolio data (tickers, weights, prices)
- **Budget Input**: Users specify a dollar amount to simulate investing in the portfolio
- **Time Window Selection**: Users select start and end dates for the benchmarking period
- **Risk-Free Rate Input**: Users enter the annual risk-free rate for comparison (e.g., 0.04 for 4%)
- **Performance Calculation**: Calculate portfolio value over time based on:
  - Initial budget allocated by weights
  - Historical price movements for each ticker
  - Calculate total profit/loss for each ticker and overall portfolio
- **Benchmark Comparisons**: Calculate performance for:
  - S&P 500 index over the same time period
  - Risk-free asset (compound interest based on user-provided rate)
- **Visualization**: Display a line chart with three lines:
  - Portfolio value over time
  - S&P 500 equivalent investment value over time
  - Risk-free asset value over time
- **Results Table**: Display a breakdown showing:
  - Each ticker's contribution (surplus/deficit)
  - Total portfolio performance
  - S&P 500 performance
  - Risk-free asset performance
  - Comparative metrics (difference between portfolio and benchmarks)

### Reusability Opportunities
- **DateInput Component**: Reuse existing date range selector component with auto-update on change
- **Chart Components**: Model after StockChart.jsx for single-line charts or RegressionChart.jsx for multi-line charts
- **Backend Data Fetching**: Leverage existing `generate_data()` function pattern from app.py for fetching historical price data
- **Date Validation**: Reuse `validate_date_range()` function from app.py
- **Styling**: Follow existing Plotly chart styling patterns (dark theme, cyan/blue colors, consistent typography)
- **API Integration**: Use existing Flask endpoint pattern with yfinance for fetching stock data

### Scope Boundaries

**In Scope:**
- Portfolio JSON file upload functionality
- Budget input field
- Date range selection (reusing DateInput component)
- Risk-free rate input field
- Historical price data fetching for all portfolio tickers
- S&P 500 data fetching (using ^GSPC ticker)
- Portfolio value calculation over time
- Risk-free asset value calculation (compound interest)
- Multi-line chart visualization (Portfolio, S&P 500, Risk-free)
- Results table with ticker-level breakdown
- Comparative performance metrics

**Out of Scope:**
- Saving benchmark results to database/file system
- Multiple portfolio comparison (only single portfolio at a time)
- Transaction costs or trading fees
- Dividend adjustments
- Sector or industry breakdown
- Real-time or intraday data
- Portfolio rebalancing during the time window
- Historical portfolio composition changes
- Tax implications
- Currency conversions (assumes USD)

### Technical Considerations
- **Frontend**: React component with file upload, form inputs, and Plotly chart
- **Backend**: New Flask endpoint for portfolio benchmarking calculations
- **Data Fetching**: Use yfinance library (already in tech stack) for historical prices
- **S&P 500 Symbol**: Use ^GSPC ticker for S&P 500 index data
- **Date Handling**: Follow existing date validation and formatting patterns
- **JSON Parsing**: Parse uploaded portfolio JSON to extract weights and tickers
- **Performance Calculation**: 
  - Allocate budget based on weights
  - Calculate shares purchased for each ticker (budget * weight / price_at_start)
  - Track value over time (shares * price_on_date)
  - Calculate risk-free value: initial_investment * (1 + rate) ^ (days/365)
- **Error Handling**: Handle missing data, invalid tickers, date range issues
- **Styling**: Match existing dark theme with Plotly styling from StockChart/RegressionChart
- **Translation Support**: Add i18n keys for new UI elements (following existing i18next pattern)
