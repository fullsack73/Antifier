# Financial Benchmark Merge Fallback

## Summary

- Financial Statement dashboard benchmark loading now merges Finviz group valuation data with yfinance representative peer averages.
- Finviz remains the preferred source for valuation metrics such as P/E and P/B.
- Metrics not available from Finviz, including ROE, ROA, margins, growth, liquidity, debt/equity, and beta, are filled from the industry representative ticker dataset when possible.

## Reason

Finviz group valuation can return partial data for an industry. The previous implementation returned as soon as any Finviz benchmark existed, so profitability metrics such as ROE still displayed the absolute-rule fallback message even when an industry representative dataset was available.

## Verification

- Added a regression test for mixed Finviz/yfinance benchmark sources.
