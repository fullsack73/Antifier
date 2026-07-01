# Financial Statement USD Normalization

## Summary

- Financial Statement dashboard company values now normalize market cap to USD when FX data is available.
- Valuation metrics are calculated from USD-normalized price and per-share financial inputs when those source fields exist.
- The API now returns display currency, source currency, financial currency, and conversion metadata for the dashboard.
- The UI shows the USD display currency and the original source currency when they differ.

## Reason

Non-US tickers can expose quote prices and financial statement values in local currencies or different quote units. The dashboard should use the same USD basis as the rest of Antifier before scoring and displaying valuation-related metrics.

## Verification

- Added regression tests for non-USD market cap normalization and mixed quote/reporting currency valuation recalculation.
