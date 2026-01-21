We're continuing our implementation of Portfolio Benchmarking Time Window by implementing task group number 2:

## Implement this task and its sub-tasks:

#### Task Group 2: Portfolio Benchmarking UI Components
**Assigned implementer:** ui-designer
**Dependencies:** Task Group 1

- [ ] 2.0 Complete UI components for portfolio benchmarking
  - [ ] 2.1 Write 2-8 focused tests for UI components
    - Limit to 2-8 highly focused tests maximum
    - Test only critical component behaviors: file upload handling, form submission, chart rendering, error display
    - Skip exhaustive testing of all component states and interactions
  - [ ] 2.2 Create PortfolioBenchmark.jsx main component
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
  - [ ] 2.3 Create BenchmarkChart.jsx component
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
  - [ ] 2.4 Create BenchmarkResultsTable.jsx component
    - Table with three rows: Portfolio, S&P 500, Risk-free asset
    - Columns: Investment Type, Initial Value, Final Value, Profit/Loss, Return %
    - Color-code profit/loss (green for positive, red for negative)
    - Format currency values with $ symbol and commas
    - Format percentages with % symbol
    - Comparison section showing portfolio vs benchmark differences
    - Follow StockScreener table styling patterns
    - Props: summary data from API response
  - [ ] 2.5 Update Selector.jsx to add "Benchmark" navigation option
    - Add new view option with icon and label
    - Follow existing view option patterns
    - Use i18n for label text
  - [ ] 2.6 Update App.jsx to integrate PortfolioBenchmark
    - Import PortfolioBenchmark component
    - Add new view condition for activeView === "benchmark"
    - Follow existing view routing pattern (similar to "optimizer", "hedge")
  - [ ] 2.7 Add internationalization keys
    - Add English translations to locales/en/translation.json:
      - benchmark.title, benchmark.uploadPortfolio, benchmark.budget, benchmark.riskFreeRate
      - benchmark.portfolio, benchmark.sp500, benchmark.riskFree
      - benchmark.initialValue, benchmark.finalValue, benchmark.profitLoss, benchmark.returnPercent
    - Add Korean translations to locales/ko/translation.json (matching keys)
    - Follow existing i18n key patterns
  - [ ] 2.8 Ensure UI component tests pass
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
@agent-os/standards/frontend/accessibility.md
@agent-os/standards/frontend/components.md
@agent-os/standards/frontend/css.md
@agent-os/standards/frontend/responsive.md
@agent-os/standards/testing/test-writing.md
