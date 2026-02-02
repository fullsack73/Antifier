# Task Breakdown: Code Structure Refactor - Frontend/Backend/Styles

## Overview
Total Task Groups: 4
Assigned roles: ui-designer, api-engineer, testing-engineer

**Note:** This is a code structure refactoring task. No new functionality is being added. The focus is on reorganizing files, consolidating styles, and updating imports while maintaining identical application behavior.

## Task List

### Style Consolidation

#### Task Group 1: CSS File Merge
**Assigned implementer:** ui-designer
**Dependencies:** None

- [x] 1.0 Consolidate CSS files
  - [x] 1.1 Create new folder structure
    - Create `src/frontend/` directory
    - Create `src/frontend/config/` subdirectory
  - [x] 1.2 Merge CSS files
    - Read all content from `src/index.css`
    - Append content to `src/App.css`
    - Preserve all selectors, rules, and color scheme definitions from both files
    - Ensure no duplicate declarations conflict
  - [x] 1.3 Move merged CSS to new location
    - Move merged `App.css` to `src/frontend/App.css`
    - Delete `src/index.css`

**Acceptance Criteria:**
- `src/frontend/` and `src/frontend/config/` directories exist
- All styles from both CSS files preserved in `src/frontend/App.css`
- `src/index.css` no longer exists
- No CSS rules lost or modified

### Frontend File Relocation

#### Task Group 2: Move Frontend Files and Update Imports
**Assigned implementer:** ui-designer
**Dependencies:** Task Group 1

- [x] 2.0 Relocate and update frontend files
  - [x] 2.1 Move React component files
    - Move all .jsx files to `src/frontend/`:
      - App.jsx, DateInput.jsx, FinancialStatement.jsx, FutureChart.jsx, FutureDateInput.jsx
      - Hedge.jsx, LanguageSelector.jsx, main.jsx, Optimizer.jsx, RegressionChart.jsx
      - Selector.jsx, StockChart.jsx, StockScreener.jsx, TickerInput.jsx
  - [x] 2.2 Move frontend asset folders
    - Move `src/assets/` to `src/frontend/assets/`
    - Move `src/locales/` to `src/frontend/locales/`
    - Move `src/i18n/` to `src/frontend/i18n/`
  - [x] 2.3 Move configuration files
    - Move `src/i18n.js` to `src/frontend/config/i18n.js`
    - Move `src/translationLoader.js` to `src/frontend/config/translationLoader.js`
  - [x] 2.4 Update imports in main.jsx
    - Change `import App from "./App.jsx"` to `import App from "./App.jsx"` (no change needed - same directory)
    - Change `import "./index.css"` to `import "./App.css"`
  - [x] 2.5 Update imports in App.jsx
    - Update component imports (no path change - same directory)
    - Change `import i18n from "./i18n"` to `import i18n from "./config/i18n"`
    - Change `import "./App.css"` to `import "./App.css"` (no change needed)
  - [x] 2.6 Update imports in other .jsx components
    - Update all component imports to reference same directory (no ../needed)
    - Update any asset imports to use correct relative paths
  - [x] 2.7 Update imports in config files
    - In `config/i18n.js`: Change `import { loadTranslations } from './translationLoader'` to `import { loadTranslations } from './translationLoader'` (no change needed)
    - In `config/translationLoader.js`: Update locales path from `./locales/` to `../locales/`
  - [x] 2.8 Update index.html
    - Change `<script type="module" src="/src/main.jsx"></script>` to `<script type="module" src="/src/frontend/main.jsx"></script>`

**Acceptance Criteria:**
- All .jsx files in `src/frontend/`
- All asset folders in `src/frontend/`
- Config files in `src/frontend/config/`
- All imports updated correctly
- No broken import statements
- index.html references correct main.jsx path

### Backend File Relocation

#### Task Group 3: Move Backend Files and Update Imports
**Assigned implementer:** api-engineer
**Dependencies:** None (can run parallel to Task Groups 1-2)

- [x] 3.0 Relocate and update backend files
  - [x] 3.1 Create backend directory
    - Create `src/backend/` directory
  - [x] 3.2 Move Python backend files
    - Move all .py files to `src/backend/`:
      - app.py, cache_init.py, cache_manager.py, cache_warmer.py
      - financial_statement.py, forecast_models.py, hedge_analysis.py
      - portfolio_optimization.py, stock_screener.py, ticker_lists.py
  - [x] 3.3 Update Python imports
    - Review all Python files for local imports
    - Update import statements if needed (likely no changes since all files move together to same directory)
    - Example: `from cache_manager import cached` remains unchanged
    - Example: `from ticker_lists import get_ticker_group` remains unchanged
  - [x] 3.4 Verify Python module resolution
    - Ensure all backend files can import each other correctly
    - Check that Flask app can still be run from new location

**Acceptance Criteria:**
- All .py files in `src/backend/`
- Python imports work correctly
- No broken module references
- Backend can still run from new location

### Verification and Testing

#### Task Group 4: Test and Verify Refactoring
**Assigned implementer:** testing-engineer
**Dependencies:** Task Groups 1, 2, 3

- [ ] 4.0 Verify refactoring completeness
  - [ ] 4.1 Verify file structure
    - Confirm all files moved to correct locations
    - Verify no files remain in old `src/` root (except for new frontend/ and backend/ folders)
    - Check that `src/index.css` has been deleted
  - [ ] 4.2 Test build process
    - Run `npm run dev` to start development server
    - Verify build completes without errors
    - Check for any import resolution errors in console
  - [ ] 4.3 Test frontend functionality
    - Verify application loads in browser
    - Test all pages render correctly
    - Verify no visual styling differences
    - Test internationalization (language switching)
    - Verify all charts display correctly (StockChart, RegressionChart, FutureChart)
    - Test stock screener functionality
    - Test portfolio optimizer functionality
    - Test hedge analysis functionality
  - [ ] 4.4 Test backend functionality
    - Verify Flask backend starts without errors
    - Test API endpoints respond correctly
    - Verify Python imports work correctly
    - Check cache functionality still works
  - [ ] 4.5 Visual regression check
    - Compare UI appearance before and after refactoring
    - Verify all styles applied correctly
    - Check responsive design on different screen sizes
  - [ ] 4.6 Document verification results
    - List any issues found
    - Confirm all acceptance criteria met
    - Verify zero functionality changes

**Acceptance Criteria:**
- Application builds successfully
- All features work identically to before refactoring
- No visual differences in UI
- No console errors or warnings
- Backend API endpoints respond correctly
- Internationalization works correctly
- All original functionality preserved

## Execution Order

Recommended implementation sequence:
1. **Task Group 1** (Style Consolidation) - Must complete first to set up folder structure and merge CSS
2. **Task Group 2** (Frontend File Relocation) - Depends on Task Group 1 for folder structure
3. **Task Group 3** (Backend File Relocation) - Can run in parallel with Task Groups 1-2, but easier to do sequentially
4. **Task Group 4** (Verification and Testing) - Must be last to verify everything works

**Alternative parallel execution:**
- Task Groups 1 and 3 can be done in parallel (frontend and backend are independent)
- Task Group 2 depends on Task Group 1
- Task Group 4 must wait for all others to complete

## Notes

- **No new tests required**: This is a refactoring task with zero functionality changes, so existing tests (if any) should continue to pass without modification
- **Focus on imports**: The main challenge is ensuring all import paths are updated correctly
- **Relative paths only**: No path aliases - use relative imports only
- **Zero functionality changes**: Application must behave identically after refactoring
- **CSS preservation**: All styles must be preserved exactly during merge
