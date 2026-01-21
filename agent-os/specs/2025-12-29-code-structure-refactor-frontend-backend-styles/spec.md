# Specification: Code Structure Refactor - Frontend/Backend/Styles

## Goal
Reorganize the codebase by separating frontend and backend files into dedicated folders and consolidating CSS files into a single stylesheet, improving project maintainability and code organization without changing any functionality.

## User Stories
- As a developer, I want frontend and backend code in separate folders so that I can navigate the codebase more easily
- As a developer, I want all styles in one file so that I can manage styling from a single location
- As a developer, I want configuration files organized in a dedicated folder so that I can quickly find and modify application settings

## Core Requirements

### Functional Requirements
- Create `src/frontend/` directory containing all React components and frontend assets
- Create `src/backend/` directory containing all Python backend modules
- Create `src/frontend/config/` subdirectory for configuration files (i18n.js, translationLoader.js)
- Merge `index.css` content into `App.css` and remove `index.css`
- Move `assets/`, `locales/`, and `i18n/` folders into `src/frontend/`
- Update all import statements to reflect new file locations using relative paths
- Ensure application builds and runs identically after refactoring

### Non-Functional Requirements
- Zero functionality changes - purely structural refactoring
- All existing features must work exactly as before
- Build process must complete successfully with new structure
- Import paths must use relative references (no path aliases)
- Maintain all existing styling without visual changes

## Visual Design
No visual changes - this is a code structure refactoring only.

## Reusable Components

### Existing Code to Leverage
- Current Vite configuration and proxy setup will remain functional
- Existing import patterns in .jsx and .py files provide templates for updates
- Current CSS selectors and styles will be preserved in merged file

### New Components Required
None - this is a reorganization task only.

## Technical Approach

### Folder Structure Changes
**Before:**
```
src/
├── App.css
├── App.jsx
├── index.css
├── main.jsx
├── [14 other .jsx files]
├── [10 .py files]
├── assets/
├── locales/
├── i18n/
├── i18n.js
└── translationLoader.js
```

**After:**
```
src/
├── frontend/
│   ├── App.css (merged)
│   ├── App.jsx
│   ├── main.jsx
│   ├── [14 other .jsx files]
│   ├── assets/
│   ├── locales/
│   ├── i18n/
│   └── config/
│       ├── i18n.js
│       └── translationLoader.js
└── backend/
    ├── app.py
    ├── cache_init.py
    ├── cache_manager.py
    ├── cache_warmer.py
    ├── financial_statement.py
    ├── forecast_models.py
    ├── hedge_analysis.py
    ├── portfolio_optimization.py
    ├── stock_screener.py
    └── ticker_lists.py
```

### Frontend Files (Move to src/frontend/)
- All .jsx files: App.jsx, DateInput.jsx, FinancialStatement.jsx, FutureChart.jsx, FutureDateInput.jsx, Hedge.jsx, LanguageSelector.jsx, main.jsx, Optimizer.jsx, RegressionChart.jsx, Selector.jsx, StockChart.jsx, StockScreener.jsx, TickerInput.jsx
- App.css (with index.css merged in)
- Folders: assets/, locales/, i18n/

### Backend Files (Move to src/backend/)
- All .py files: app.py, cache_init.py, cache_manager.py, cache_warmer.py, financial_statement.py, forecast_models.py, hedge_analysis.py, portfolio_optimization.py, stock_screener.py, ticker_lists.py

### Config Files (Move to src/frontend/config/)
- i18n.js
- translationLoader.js

### CSS Consolidation
- Merge all content from `index.css` into `App.css`
- Preserve both color schemes (index.css uses one palette, App.css uses another)
- Keep all selectors and rules intact
- Delete `index.css` after merge

### Import Updates Required

**Frontend .jsx files:**
- Update component imports to reference files in same directory
- Update i18n import from `./i18n` to `./config/i18n`
- Change CSS import from `./index.css` to `./App.css` in main.jsx
- Update asset/image imports to use correct relative paths

**Frontend config files (i18n.js, translationLoader.js):**
- Update locales path from `./locales/` to `../locales/`

**Backend .py files:**
- Update imports like `from cache_manager import cached` to reference files in same directory (no path change needed since all in src/backend/)
- Example: `from cache_manager import cached` remains the same

**Root files:**
- index.html: Update script source from `/src/main.jsx` to `/src/frontend/main.jsx`

### Testing
- Manual verification: Build succeeds with `npm run dev`
- Visual verification: All pages render identically
- Functional verification: All features work (charts, stock screener, optimizer, i18n)
- Backend verification: API endpoints respond correctly
- Style verification: No visual differences in UI

## Out of Scope
- Further subfolder organization (components/, charts/, utils/)
- Implementing path aliases in Vite configuration
- Code quality improvements or refactoring logic
- Adding new features or functionality
- Performance optimizations
- Modifying component behavior or styling beyond consolidation

## Success Criteria
- All files successfully moved to new folder structure
- Application builds without errors
- All features function identically to before refactoring
- No visual styling differences
- All import statements updated correctly
- index.css successfully merged into App.css and removed
- Backend Python imports work correctly
