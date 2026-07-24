# Risk Allocator Research

- Split: `fama_french_35_industry_continuous_trend_research_v1`
- Namespace: `continuous_trend_risk_parity_v1`
- Rows: 3523
- Tickers: 35
- Data promotion safe: `True`
- Split locked: `True`
- Risk gate passed: `False`
- Promotion eligible: `False`

## Performance

| Model | CAGR | Volatility | Sharpe | Sortino | Max DD | Daily CVaR | Risk exposure | Avg turnover | Risk MAE | P(vol lower) | P(Sharpe higher) | Gate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| equal_weight | 0.0705 | 0.2186 | 0.3173 | 0.4449 | -0.5653 | 0.0330 | 1.0000 | 0.0339 | 0.0768 | NA | NA | baseline |
| min_variance | 0.0942 | 0.1577 | 0.5056 | 0.7139 | -0.4368 | 0.0236 | 0.9998 | 0.2125 | 0.0527 | NA | NA | baseline |
| risk_parity | 0.0666 | 0.2105 | 0.3041 | 0.4261 | -0.5690 | 0.0317 | 1.0000 | 0.0331 | 0.0741 | NA | NA | baseline |
| momentum_6m | 0.0656 | 0.2158 | 0.2977 | 0.4150 | -0.5676 | 0.0324 | 0.9997 | 0.2883 | 0.0757 | NA | NA | baseline |
| continuous_trend_risk_parity | 0.0512 | 0.1124 | 0.2987 | 0.4109 | -0.2096 | 0.0170 | 0.6182 | 0.1169 | 0.0404 | 1.0000 | 0.4535 | rejected |

## Guardrail

- Research split only; no default or promotion change.
- A risk candidate must improve its closest baseline and survive the inverse-vol guard.
- Freeze a candidate before any validation run.
