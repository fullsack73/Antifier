# Verification Prompt: Frontend Implementation

## Verifier Role
**frontend-verifier**

## Standards to Apply
- `agent-os/standards/global/*`
- `agent-os/standards/frontend/*`
- `agent-os/standards/testing/*`

## Task Groups to Verify

### Task Group 2: UI Components Development
**Assigned to:** ui-designer

**Tasks to verify:**
1. Create PortfolioBenchmark.jsx component
2. Integrate DateInput.jsx for date range selection
3. Add portfolio file upload functionality
4. Add budget input field
5. Create BenchmarkChart.jsx for visualization
6. Create BenchmarkResultsTable.jsx for aggregated results display
7. Add i18n support for all new text
8. Style components following existing patterns

**Verification Checklist:**
- [ ] PortfolioBenchmark.jsx exists in src/frontend/
- [ ] Component structure follows frontend/components.md standards
- [ ] DateInput.jsx properly integrated and reused
- [ ] Portfolio file upload accepts .json files only
- [ ] File upload UI follows Optimizer.jsx pattern
- [ ] Budget input validates positive numbers
- [ ] Form layout uses existing classes (optimizer-input, optimizer-form-group)
- [ ] BenchmarkChart.jsx created with Plotly
- [ ] Chart displays 3 lines: Portfolio, S&P 500, Risk-free asset
- [ ] Chart follows RegressionChart.jsx patterns for multi-line display
- [ ] BenchmarkResultsTable.jsx created
- [ ] Table displays only 3 rows (Portfolio, S&P 500, Risk-free) with aggregated metrics
- [ ] Table columns: Strategy, Initial Value, Final Value, Profit/Loss, Return (%)
- [ ] i18n translations added to locales/en/ and locales/ko/
- [ ] All user-facing text uses t() function
- [ ] CSS follows frontend/css.md standards
- [ ] Responsive design follows frontend/responsive.md standards
- [ ] Accessibility follows frontend/accessibility.md standards
- [ ] Component follows global/coding-style.md
- [ ] Comments follow global/commenting.md
- [ ] Naming follows global/conventions.md
- [ ] Tests written per testing/test-writing.md (2-8 tests as specified)

**Implementation Reference:**
- Spec file: `agent-os/specs/2026-01-01-portfolio-benchmarking-time-window/spec.md`
- Tasks file: `agent-os/specs/2026-01-01-portfolio-benchmarking-time-window/tasks.md`
- Implementation prompt: `agent-os/specs/2026-01-01-portfolio-benchmarking-time-window/implementation/prompts/2-portfolio-benchmarking-ui-components.md`

## Verification Instructions

1. **Read all standards files** in the specified directories
2. **Read the spec.md** to understand the full requirements
3. **Review the implementation** files created by ui-designer
4. **Check compliance** with each item in the verification checklist
5. **Test the UI components** by:
   - Starting the development server
   - Navigating to the portfolio benchmarking feature
   - Uploading a valid portfolio JSON file
   - Selecting a date range
   - Entering a budget amount
   - Submitting the form and verifying chart displays
   - Verifying table shows correct aggregated results
   - Testing responsive design on different screen sizes
   - Testing accessibility with keyboard navigation and screen readers
   - Testing both English and Korean translations
6. **Take screenshots** of:
   - The full component with form
   - The chart visualization
   - The results table
   - Responsive layouts (desktop, tablet, mobile)
7. **Run existing tests** and verify they pass
8. **Document findings** in a verification report with:
   - List of compliant items (✅)
   - List of non-compliant items (❌) with specific issues
   - Screenshots of implemented features
   - Suggestions for fixes if any issues found
   - Overall assessment: PASS or FAIL

## Expected Artifacts to Verify
- `src/frontend/PortfolioBenchmark.jsx`
- `src/frontend/BenchmarkChart.jsx`
- `src/frontend/BenchmarkResultsTable.jsx`
- `src/frontend/locales/en/*.json` (updated)
- `src/frontend/locales/ko/*.json` (updated)
- CSS files or styles (if new styles added)
- Test files for components (location per testing standards)

## Success Criteria
- All checklist items marked as compliant
- All tests pass
- UI components render correctly and handle user interactions
- Form validation works properly
- Chart displays all three benchmark lines correctly
- Table shows aggregated results only (no ticker breakdown)
- Responsive design works on all screen sizes
- Accessibility requirements met
- i18n works for both English and Korean
- Code quality meets all applicable standards
