# Verification Prompt: Backend Implementation

## Verifier Role
**backend-verifier**

## Standards to Apply
- `agent-os/standards/global/*`
- `agent-os/standards/backend/*`
- `agent-os/standards/testing/*`

## Task Groups to Verify

### Task Group 1: API Endpoint Development
**Assigned to:** api-engineer

**Tasks to verify:**
1. Create benchmark-portfolio endpoint in app.py
2. Add request validation (portfolio JSON structure, date format, budget validation)
3. Implement historical price fetching for user portfolio tickers
4. Implement S&P 500 benchmark calculation
5. Implement risk-free asset calculation
6. Calculate portfolio performance metrics
7. Format aggregated results (profit/loss, returns, final values)
8. Add error handling and appropriate HTTP status codes

**Verification Checklist:**
- [ ] API endpoint POST /api/benchmark-portfolio exists in app.py
- [ ] Request validation follows backend/api.md standards
- [ ] Error handling follows global/error-handling.md standards
- [ ] Portfolio JSON structure validated correctly (prices, return, risk, sharpe_ratio, weights, portfolio_id)
- [ ] Date validation reuses existing validate_date_range() function
- [ ] Budget validation (positive number) implemented
- [ ] Historical prices fetched using yfinance for portfolio tickers
- [ ] S&P 500 benchmark (^GSPC ticker) calculated correctly
- [ ] Risk-free calculation: budget × (1 + annual_rate)^(days/365)
- [ ] Portfolio performance calculation uses ticker weights from JSON
- [ ] Aggregated profit/loss calculated for all three strategies
- [ ] Response format matches spec.md (portfolio, sp500_benchmark, risk_free_asset objects)
- [ ] HTTP status codes appropriate (200 for success, 400 for validation errors, 500 for server errors)
- [ ] Code follows global/coding-style.md
- [ ] Comments follow global/commenting.md
- [ ] Function naming follows global/conventions.md
- [ ] Tests written per testing/test-writing.md (2-8 tests as specified)

**Implementation Reference:**
- Spec file: `agent-os/specs/2026-01-01-portfolio-benchmarking-time-window/spec.md`
- Tasks file: `agent-os/specs/2026-01-01-portfolio-benchmarking-time-window/tasks.md`
- Implementation prompt: `agent-os/specs/2026-01-01-portfolio-benchmarking-time-window/implementation/prompts/1-portfolio-benchmarking-api-endpoint.md`

## Verification Instructions

1. **Read all standards files** in the specified directories
2. **Read the spec.md** to understand the full requirements
3. **Review the implementation** files created by api-engineer
4. **Check compliance** with each item in the verification checklist
5. **Test the API endpoint** by:
   - Running the Flask server
   - Sending POST requests with valid portfolio JSON
   - Testing invalid inputs (missing fields, invalid dates, negative budget)
   - Verifying response format matches spec
   - Checking calculations are correct
6. **Run existing tests** and verify they pass
7. **Document findings** in a verification report with:
   - List of compliant items (✅)
   - List of non-compliant items (❌) with specific issues
   - Suggestions for fixes if any issues found
   - Overall assessment: PASS or FAIL

## Expected Artifacts to Verify
- `src/backend/app.py` (modified with new endpoint)
- Test files for the endpoint (location per testing standards)
- Any new utility functions created

## Success Criteria
- All checklist items marked as compliant
- All tests pass
- API endpoint works correctly with valid inputs
- Error handling works correctly with invalid inputs
- Code quality meets all applicable standards
