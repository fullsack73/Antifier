We're continuing our implementation of Portfolio Benchmarking Time Window by implementing task group number 1:

## Implement this task and its sub-tasks:

#### Task Group 1: Portfolio Benchmarking API Endpoint
**Assigned implementer:** api-engineer
**Dependencies:** None

- [ ] 1.0 Complete backend API for portfolio benchmarking
  - [ ] 1.1 Write 2-8 focused tests for portfolio benchmarking endpoint
    - Limit to 2-8 highly focused tests maximum
    - Test only critical behaviors: valid portfolio calculation, date validation, missing ticker handling, S&P 500 data fetch, risk-free calculation
    - Skip exhaustive coverage of all edge cases
  - [ ] 1.2 Create portfolio benchmarking calculation module in `src/backend/portfolio_benchmark.py`
    - Function: `calculate_portfolio_benchmark(portfolio_data, budget, start_date, end_date, risk_free_rate)`
    - Parse portfolio JSON to extract weights and ticker list
    - Validate portfolio structure (weights, prices present)
    - Calculate shares for each ticker: (budget × weight) / price_at_start_date
    - Handle tickers with zero/missing prices appropriately
  - [ ] 1.3 Implement historical data fetching for portfolio tickers
    - Use yfinance to fetch historical prices for all tickers in date range
    - Fetch S&P 500 (^GSPC) historical data for same period
    - Handle missing data gracefully (skip dates or notify)
    - Reuse `validate_date_range()` pattern from existing app.py
    - Follow existing `generate_data()` pattern for yfinance usage
  - [ ] 1.4 Build timeline calculations
    - Build portfolio_timeline: for each date, sum(shares × price_on_date) across all tickers
    - Build sp500_timeline: calculate sp500_shares = budget / sp500_price_at_start, track sp500_shares × price_on_date
    - Build riskfree_timeline: for each date, calculate days_elapsed, value = budget × (1 + rate)^(days_elapsed/365)
    - Ensure all three timelines have consistent date keys
  - [ ] 1.5 Calculate aggregated summary metrics
    - Portfolio: initial_value (budget), final_value, profit_loss
    - S&P 500: initial_value (budget), final_value, profit_loss
    - Risk-free: initial_value (budget), final_value, profit_loss
    - Calculate return percentages for each
  - [ ] 1.6 Create Flask endpoint `/api/benchmark-portfolio` (POST)
    - Accept JSON payload: portfolio_data, budget, start_date, end_date, risk_free_rate
    - Call calculation module from 1.2
    - Return JSON response with: portfolio_timeline, sp500_timeline, riskfree_timeline, summary
    - Follow existing Flask endpoint patterns from app.py
    - Handle CORS configuration (already set up in app.py)
  - [ ] 1.7 Implement comprehensive error handling
    - Return 400 for validation errors (invalid dates, missing fields, invalid JSON structure)
    - Return 404 for missing ticker data
    - Return 500 for calculation failures
    - Provide clear, user-friendly error messages
    - Follow existing error handling patterns from app.py
  - [ ] 1.8 Ensure API layer tests pass
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

## Understand the context

Read @agent-os/specs/2026-01-01-portfolio-benchmarking-time-window/spec.md to understand the context for this spec and where the current task fits into it.

## Perform the implementation

Implement all tasks assigned to you in your task group.

Focus ONLY on implementing the areas that align with **areas of specialization** (your "areas of specialization" are defined above).

Guide your implementation using:
- **The existing patterns** that you've found and analyzed.
- **User Standards & Preferences** which are defined below.

Self-verify and test your work by:
- Running ONLY the tests you've written (if any) and ensuring those tests pass.
- IF your task involves user-facing UI, and IF you have access to browser testing tools, open a browser and use the feature you've implemented as if you are a user to ensure a user can use the feature in the intended way.


## Update tasks.md task status

In the current spec's `tasks.md` find YOUR task group that's been assigned to YOU and update this task group's parent task and sub-task(s) checked statuses to complete for the specific task(s) that you've implemented.

Mark your task group's parent task and sub-task as complete by changing its checkbox to `- [x]`.

DO NOT update task checkboxes for other task groups that were NOT assigned to you for implementation.


## Document your implementation

Using the task number and task title that's been assigned to you, create a file in the current spec's `implementation` folder called `[task-number]-[task-title]-implementation.md`.

For example, if you've been assigned implement the 3rd task from `tasks.md` and that task's title is "Commenting System", then you must create the file: `agent-os/specs/2026-01-01-portfolio-benchmarking-time-window/implementation/3-commenting-system-implementation.md`.

Use the following structure for the content of your implementation documentation:

```markdown
# Task [number]: [Task Title]

## Overview
**Task Reference:** Task #[number] from `agent-os/specs/2026-01-01-portfolio-benchmarking-time-window/tasks.md`
**Implemented By:** [Agent Role/Name]
**Date:** [Implementation Date]
**Status:** ✅ Complete | ⚠️ Partial | 🔄 In Progress

### Task Description
[Brief description of what this task was supposed to accomplish]

## Implementation Summary
[High-level overview of the solution implemented - 2-3 short paragraphs explaining the approach taken and why]

## Files Changed/Created

### New Files
- `path/to/file.ext` - [1 short sentence description of purpose]
- `path/to/another/file.ext` - [1 short sentence description of purpose]

### Modified Files
- `path/to/existing/file.ext` - [1 short sentence on what was changed and why]
- `path/to/another/existing/file.ext` - [1 short sentence on what was changed and why]

### Deleted Files
- `path/to/removed/file.ext` - [1 short sentence on why it was removed]

## Key Implementation Details

### [Component/Feature 1]
**Location:** `path/to/file.ext`

[Detailed explanation of this implementation aspect]

**Rationale:** [Why this approach was chosen]

### [Component/Feature 2]
**Location:** `path/to/file.ext`

[Detailed explanation of this implementation aspect]

**Rationale:** [Why this approach was chosen]

## Database Changes (if applicable)

### Migrations
- `[timestamp]_[migration_name].rb` - [What it does]
  - Added tables: [list]
  - Modified tables: [list]
  - Added columns: [list]
  - Added indexes: [list]

### Schema Impact
[Description of how the schema changed and any data implications]

## Dependencies (if applicable)

### New Dependencies Added
- `package-name` (version) - [Purpose/reason for adding]
- `another-package` (version) - [Purpose/reason for adding]

### Configuration Changes
- [Any environment variables, config files, or settings that changed]

## Testing

### Test Files Created/Updated
- `path/to/test/file_spec.rb` - [What is being tested]
- `path/to/feature/test_spec.rb` - [What is being tested]

### Test Coverage
- Unit tests: [✅ Complete | ⚠️ Partial | ❌ None]
- Integration tests: [✅ Complete | ⚠️ Partial | ❌ None]
- Edge cases covered: [List key edge cases tested]

### Manual Testing Performed
[Description of any manual testing done, including steps to verify the implementation]

## User Standards & Preferences Compliance

In your instructions, you were provided with specific user standards and preferences files under the "User Standards & Preferences Compliance" section. Document how your implementation complies with those standards.

Keep it brief and focus only on the specific standards files that were applicable to your implementation tasks.

For each RELEVANT standards file you were instructed to follow:

### [Standard/Preference File Name]
**File Reference:** `path/to/standards/file.md`

**How Your Implementation Complies:**
[1-2 Sentences to explain specifically how your implementation adheres to the guidelines, patterns, or preferences outlined in this standards file. Include concrete examples from your code.]

**Deviations (if any):**
[If you deviated from any standards in this file, explain what, why, and what the trade-offs were]

---

*Repeat the above structure for each RELEVANT standards file you were instructed to follow*

## Integration Points (if applicable)

### APIs/Endpoints
- `[HTTP Method] /path/to/endpoint` - [Purpose]
  - Request format: [Description]
  - Response format: [Description]

### External Services
- [Any external services or APIs integrated]

### Internal Dependencies
- [Other components/modules this implementation depends on or interacts with]

## Known Issues & Limitations

### Issues
1. **[Issue Title]**
   - Description: [What the issue is]
   - Impact: [How significant/what it affects]
   - Workaround: [If any]
   - Tracking: [Link to issue/ticket if applicable]

### Limitations
1. **[Limitation Title]**
   - Description: [What the limitation is]
   - Reason: [Why this limitation exists]
   - Future Consideration: [How this might be addressed later]

## Performance Considerations
[Any performance implications, optimizations made, or areas that might need optimization]

## Security Considerations
[Any security measures implemented, potential vulnerabilities addressed, or security notes]

## Dependencies for Other Tasks
[List any other tasks from the spec that depend on this implementation]

## Notes
[Any additional notes, observations, or context that might be helpful for future reference]
```


## User Standards & Preferences Compliance

IMPORTANT: Ensure that your implementation work is ALIGNED and DOES NOT CONFLICT with the user's preferences and standards as detailed in the following files:

@agent-os/standards/global/coding-style.md
@agent-os/standards/global/commenting.md
@agent-os/standards/global/conventions.md
@agent-os/standards/global/error-handling.md
@agent-os/standards/global/tech-stack.md
@agent-os/standards/global/validation.md
@agent-os/standards/backend/api.md
@agent-os/standards/backend/migrations.md
@agent-os/standards/backend/models.md
@agent-os/standards/backend/queries.md
@agent-os/standards/testing/test-writing.md
