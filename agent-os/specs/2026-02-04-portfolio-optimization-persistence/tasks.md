# Task Breakdown: Portfolio Optimization Persistence

## Overview
Total Tasks: 13
Assigned roles: api-engineer, ui-designer, testing-engineer

## Task List

### Backend Layer

#### Task Group 1: Backend Optimization Refactoring
**Assigned implementer:** api-engineer
**Dependencies:** None

- [ ] 1.0 Complete backend optimization refactoring
  - [ ] 1.1 Write 2-8 focused tests for caching and conditional execution logic
    - Limit to 2-8 highly focused tests maximum
    - Test critical cache hit/miss scenarios for `data_and_forecast_pipeline`
    - Test warm start vs. cold start execution paths in `optimize_portfolio`
    - Skip exhaustive coverage of mathematical correctness (covered by existing tests)
  - [ ] 1.2 Implement `data_and_forecast_pipeline` function
    - Extract data fetching, cleaning, and forecasting logic from `optimize_portfolio`
    - Decorate with `@cached` to enable L1/L2 caching
    - Ensure it returns `mu`, `S`, `latest_prices`, and `tickers`
  - [ ] 1.3 Refactor `optimize_portfolio` to use pipeline
    - Call `data_and_forecast_pipeline` first
    - Implement logic to use returned data for `EfficientFrontier`
    - Ensure `target_return`, `risk_tolerance`, and `risk_free_rate` are applied AFTER forecast retrieval
  - [ ] 1.4 Implement structured error handling
    - Catch `pypfopt` exceptions (e.g., infeasible solution)
    - Return specific JSON error response suggesting constraint adjustment
  - [ ] 1.5 Ensure backend tests pass
    - Run ONLY the 2-8 tests written in 1.1
    - Verify cache reuse works as expected
    - Do NOT run the entire test suite at this stage

**Acceptance Criteria:**
- Tests confirm `data_and_forecast_pipeline` is cached correctly
- `optimize_portfolio` runs significantly faster on second call with same forecast params
- Changing `target_return` triggers warm start (re-optimization only)
- Changing `tickers` triggers cold start (re-forecast)
- Error messages explicitly guide user to adjust constraints

### Frontend Layer

#### Task Group 2: Frontend UX Updates
**Assigned implementer:** ui-designer
**Dependencies:** Task Group 1

- [ ] 2.0 Complete frontend UX updates
  - [ ] 2.1 Write 2-8 focused tests for error display and submission flow
    - Limit to 2-8 highly focused tests maximum
    - Test error message rendering when optimization fails
    - Test that "Optimize" button remains clickable after error
    - Skip exhaustive testing of all chart rendering (existing functionality)
  - [ ] 2.2 Update `Optimizer.jsx` error handling
    - Modify error state display to be more prominent/helpful
    - Parse backend specific error messages
  - [ ] 2.3 Verify "Optimize" button behavior
    - Ensure no state changes prevent re-clicking "Optimize" after a result or error
    - Verify loading state clears correctly on rapid re-submission
  - [ ] 2.4 Ensure frontend tests pass
    - Run ONLY the 2-8 tests written in 2.1
    - Verify error messages appear correctly
    - Do NOT run the entire test suite at this stage

**Acceptance Criteria:**
- Tests confirm error messages are displayed correctly
- Users can immediately click "Optimize" again after an error or success
- UI reflects the speed improvement of warm starts (though implicitly)

### Testing

#### Task Group 3: Test Review & Gap Analysis
**Assigned implementer:** testing-engineer
**Dependencies:** Task Groups 1-2

- [ ] 3.0 Review existing tests and fill critical gaps only
  - [ ] 3.1 Review tests from Task Groups 1-2
    - Review the 2-8 tests written by api-engineer (Task 1.1)
    - Review the 2-8 tests written by ui-designer (Task 2.1)
    - Total existing tests: approximately 4-16 tests
  - [ ] 3.2 Analyze test coverage gaps for THIS feature only
    - Identify critical user workflows that lack test coverage (e.g., full E2E flow of cold start -> warm start)
    - Focus ONLY on gaps related to persistence and cache reuse
    - Do NOT assess entire application test coverage
  - [ ] 3.3 Write up to 10 additional strategic tests maximum
    - Add maximum of 10 new tests to fill identified critical gaps
    - Focus on integration points: Frontend calling Backend -> Backend reusing Cache -> Result returning
    - Verify "Risk Free Rate" change triggers warm start
    - Do NOT write comprehensive coverage for all scenarios
  - [ ] 3.4 Run feature-specific tests only
    - Run ONLY tests related to this spec's feature (tests from 1.1, 2.1, and 3.3)
    - Expected total: approximately 10-26 tests maximum
    - Do NOT run the entire application test suite
    - Verify critical workflows pass

**Acceptance Criteria:**
- All feature-specific tests pass
- Critical workflow (Cold Start -> Warm Start) is verified
- No more than 10 additional tests added by testing-engineer
- Testing focused exclusively on caching reuse and error handling

## Execution Order

Recommended implementation sequence:
1. Backend Optimization Refactoring (Task Group 1)
2. Frontend UX Updates (Task Group 2)
3. Test Review & Gap Analysis (Task Group 3)
