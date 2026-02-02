# Implementation: UI - Portfolio Optimizer Model Selection

## Overview
Implemented the "Model Strategy" selection in the Portfolio Optimizer UI. This allows users to choose between Black-Litterman, Deep Learning Ensemble, Lightweight Prediction, and Classic MPT strategies.

## Changes

### 1. New Tests (`src/frontend/Optimizer.test.jsx`)
Created a new test file to verify:
- Rendering of the "Model Strategy" dropdown.
- State updates upon selection.
- Inclusion of `model_strategy` in the API payload during form submission.

### 2. Localization
Added translation keys for English and Korean locales:
- `optimizer.modelStrategy`
- Options: `bl`, `ensemble`, `lightweight`, `mpt`

### 3. Optimizer Component (`src/frontend/Optimizer.jsx`)
- Added `modelStrategy` state variable initialized to `"BL"`.
- Added a new `<select>` form element for strategy selection.
- Linked the label and select for accessibility and testing.
- Updated `handleSubmit` to include `model_strategy` in the POST request to `/api/optimize-portfolio`.

## Verification
- Ran 3 focused tests in `src/frontend/Optimizer.test.jsx`.
- All tests passed.

## Next Steps
- Testing engineer to perform integration testing with the backend.
