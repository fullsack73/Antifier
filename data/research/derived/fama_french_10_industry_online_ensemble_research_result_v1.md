# Risk Allocator Research

- Split: `fama-french-10-industry-online-ensemble-research-1928-1969-v1`
- Namespace: `risk-v10-online-allocator-ensemble`
- Rows: 12030
- Tickers: 10
- Data promotion safe: `True`
- Split locked: `True`
- Risk gate passed: `False`
- Promotion eligible: `False`

## Performance

| Model | CAGR | Volatility | Sharpe | Sortino | Max DD | Daily CVaR | Risk exposure | Avg turnover | Risk MAE | P(vol lower) | P(Sharpe higher) | Gate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| equal_weight | 0.0885 | 0.1702 | 0.4991 | 0.7123 | -0.8113 | 0.0264 | 0.9833 | 0.0182 | 0.0472 | NA | NA | baseline |
| min_variance | 0.0838 | 0.1386 | 0.5466 | 0.7783 | -0.7505 | 0.0215 | 0.9918 | 0.0666 | 0.0408 | NA | NA | baseline |
| risk_parity | 0.0859 | 0.1586 | 0.5088 | 0.7242 | -0.8055 | 0.0247 | 0.9865 | 0.0265 | 0.0447 | NA | NA | baseline |
| momentum_6m | 0.0998 | 0.1708 | 0.5585 | 0.7896 | -0.7947 | 0.0266 | 0.9928 | 0.3210 | 0.0473 | NA | NA | baseline |
| online_allocator_ensemble | 0.0916 | 0.1579 | 0.5434 | 0.7692 | -0.7903 | 0.0246 | 0.9914 | 0.1617 | 0.0448 | 1.0000 | 0.1980 | rejected |

## Guardrail

- Research split only; no default or promotion change.
- A risk candidate must improve its closest baseline and survive the inverse-vol guard.
- Freeze a candidate before any validation run.
