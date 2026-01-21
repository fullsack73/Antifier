# Spec Requirements: Code Structure Refactor - Frontend/Backend/Styles

## Initial Description
I need to refactor the structure of the code, i want to integrate styles into one file(instead of current two) and seperate frontend files and backend files into their respective folders

## Requirements Discussion

### First Round Questions

**Q1:** Frontend/Backend Separation - I assume you want to create two new folders: `src/frontend/` for all React components (.jsx files) and `src/backend/` for all Python files (.py files). Is that correct, or would you prefer a different naming convention like `src/client/` and `src/server/`?

**Answer:** yeah go with src/frontend and src/backend

**Q2:** Style File Integration - I see you currently have `App.css` and `index.css`. I'm thinking we should merge these into a single `src/frontend/styles.css` (or `src/frontend/main.css`). Should we keep all styles in one file, or would you prefer to organize component-specific styles as well?

**Answer:** integrating into App.css would be feasible

**Q3:** Shared Resources - For folders like `assets/`, `locales/`, and `i18n/`, which are used by the frontend but aren't components - should these stay at the `src/` root level, move into `src/frontend/`, or have a separate `src/shared/` folder?

**Answer:** i think they belong more in src/frontend

**Q4:** Cache and Utility Files - Files like `cache_init.py`, `cache_manager.py`, `cache_warmer.py`, and `ticker_lists.py` are backend utilities. Should these go directly in `src/backend/` or in a subfolder like `src/backend/utils/`?

**Answer:** let them stay in src/backend

**Q5:** Import Path Updates - After moving files, all import statements will need updating. Should we update imports to use relative paths (e.g., `../../backend/app.py`) or would you prefer configuring path aliases (e.g., `@backend/app.py`) in vite.config.js?

**Answer:** we should use relative path. and also, the parts of the frontend .jsx files that imports styles from index.css should be updated with App.css

**Q6:** File Organization Within Folders - Within `src/frontend/`, should we keep all .jsx files flat, or organize them into subfolders like `src/frontend/components/` for UI components, `src/frontend/charts/` for chart components, etc.?

**Answer:** let's not put them in subfolders yet.

**Q7:** Configuration Files - The `i18n.js` and `translationLoader.js` files configure internationalization. Should these go in `src/frontend/config/` or stay alongside the components in `src/frontend/`?

**Answer:** and yes, they would need frontend/config

**Q8:** Out of Scope - I assume this refactoring is purely about reorganizing files and folders, NOT about changing any functionality, adding new features, or modifying the build configuration beyond necessary path updates. Is that correct, or are there other improvements you'd like to include?

**Answer:** yes, this is only reorganizing. no feature update should be done

### Existing Code to Reference

No similar existing features identified for reference.

## Visual Assets

### Files Provided:
No visual assets provided.

## Requirements Summary

### Functional Requirements

**Folder Structure Changes:**
- Create `src/frontend/` directory for all React/JavaScript files
- Create `src/backend/` directory for all Python files
- Create `src/frontend/config/` subdirectory for configuration files
- Move `assets/`, `locales/`, and `i18n/` folders into `src/frontend/`

**Style File Consolidation:**
- Merge `index.css` into `App.css`
- Keep the consolidated file as `src/frontend/App.css`
- Update all imports from `index.css` to reference `App.css`

**File Movements:**
- **Frontend files to `src/frontend/`:**
  - All .jsx files: App.jsx, DateInput.jsx, FinancialStatement.jsx, FutureChart.jsx, FutureDateInput.jsx, Hedge.jsx, LanguageSelector.jsx, main.jsx, Optimizer.jsx, RegressionChart.jsx, Selector.jsx, StockChart.jsx, StockScreener.jsx, TickerInput.jsx
  - App.css (with merged styles from index.css)
  - assets/ folder
  - locales/ folder
  - i18n/ folder (note: separate from i18n.js file)

- **Config files to `src/frontend/config/`:**
  - i18n.js
  - translationLoader.js

- **Backend files to `src/backend/`:**
  - All .py files: app.py, cache_init.py, cache_manager.py, cache_warmer.py, financial_statement.py, forecast_models.py, hedge_analysis.py, portfolio_optimization.py, stock_screener.py, ticker_lists.py

**Import Path Updates:**
- Update all relative imports in .jsx files to reflect new folder structure
- Update Python imports to reflect new backend folder structure
- Update CSS imports from `index.css` to `App.css`
- Use relative paths (no path aliases)

### Reusability Opportunities

No specific reusability opportunities identified as this is a structural refactoring.

### Scope Boundaries

**In Scope:**
- Creating new folder structure (src/frontend/, src/backend/, src/frontend/config/)
- Moving all files to appropriate directories
- Merging index.css into App.css
- Updating all import statements (JavaScript, Python, CSS)
- Ensuring application continues to function identically after refactoring

**Out of Scope:**
- Adding new features or functionality
- Changing component logic or behavior
- Further subfolder organization (e.g., components/, charts/, utils/)
- Implementing path aliases in build configuration
- Modifying styling beyond merging the two CSS files
- Performance improvements or optimizations
- Code quality improvements or refactoring

### Technical Considerations

**Import Updates Required:**
- Frontend .jsx files: Update relative imports for other components, config files, and assets
- Frontend config files (i18n.js, translationLoader.js): Update paths to locales and other resources
- Backend .py files: Update Python imports for other backend modules
- main.jsx: Update imports for App component and CSS
- Vite configuration: May need to verify that new structure works with existing proxy configuration

**CSS Consolidation:**
- Merge all styles from index.css into App.css
- Preserve all existing styles and selectors
- Ensure no style conflicts or overwrites
- Update all CSS import statements in .jsx files

**Testing Requirements:**
- Verify application builds successfully after changes
- Verify all pages/components render correctly
- Verify all API calls to backend still work
- Verify internationalization still functions
- Verify styling appears identical to before refactoring

**File Structure Before:**
```
src/
├── App.css
├── App.jsx
├── index.css
├── main.jsx
├── [all other .jsx files]
├── [all .py files]
├── assets/
├── locales/
├── i18n/
├── i18n.js
└── translationLoader.js
```

**File Structure After:**
```
src/
├── frontend/
│   ├── App.css (merged with index.css)
│   ├── App.jsx
│   ├── main.jsx
│   ├── [all other .jsx files]
│   ├── assets/
│   ├── locales/
│   ├── i18n/
│   └── config/
│       ├── i18n.js
│       └── translationLoader.js
└── backend/
    └── [all .py files]
```
