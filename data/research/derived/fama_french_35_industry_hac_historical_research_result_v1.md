# Risk Allocator Research

- Split: `fama-french-35-industry-hac-historical-research-2000-2014-v1`
- Namespace: `mean-v2-hac-historical-industry-portfolios`
- Rows: 4277
- Tickers: 35
- Data promotion safe: `True`
- Split locked: `True`
- Risk gate passed: `False`
- Promotion eligible: `False`

## Performance

| Model | CAGR | Volatility | Sharpe | Sortino | Max DD | Daily CVaR | Risk exposure | Avg turnover | Risk MAE | P(vol lower) | P(Sharpe higher) | Gate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| equal_weight | 0.0875 | 0.1794 | 0.4557 | 0.6395 | -0.4922 | 0.0268 | 0.9168 | 0.0227 | 0.0633 | NA | NA | baseline |
| min_variance | 0.1045 | 0.1590 | 0.5901 | 0.8320 | -0.4838 | 0.0239 | 0.9935 | 0.1361 | 0.0544 | NA | NA | baseline |
| risk_parity | 0.0897 | 0.1818 | 0.4630 | 0.6500 | -0.5288 | 0.0273 | 0.9408 | 0.0258 | 0.0646 | NA | NA | baseline |
| momentum_6m | 0.0898 | 0.1992 | 0.4401 | 0.6139 | -0.5659 | 0.0300 | 0.9780 | 0.2386 | 0.0703 | NA | NA | baseline |
| historical_bl | 0.0775 | 0.1945 | 0.3872 | 0.5416 | -0.5470 | 0.0291 | 0.9616 | 0.0282 | 0.0679 | NA | NA | baseline |
| hac_historical_bl | 0.0889 | 0.2023 | 0.4318 | 0.6070 | -0.5514 | 0.0303 | 0.9808 | 0.1436 | 0.0711 | 0.0000 | 0.9020 | rejected |

## Guardrail

- Research split only; no default or promotion change.
- A risk candidate must improve its closest baseline and survive the inverse-vol guard.
- Freeze a candidate before any validation run.
