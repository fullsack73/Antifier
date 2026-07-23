# Lightweight Rank-Tilt Research

- Split: `fama-french-35-industry-lightweight-rank-tilt-research-1983-1999-v1`
- Namespace: `forecast-v6-lightweight-rank-tilt`
- Rows/tickers: `4635` / `35`
- Signal gate: `rejected`
- Portfolio gate: `rejected`
- Promotion eligible: `False`

## Performance

| Model | CAGR | Volatility | Sharpe | Max DD | Avg turnover |
|---|---:|---:|---:|---:|---:|
| equal_weight | 0.1415 | 0.1258 | 0.6698 | -0.3427 | 0.0202 |
| risk_parity | 0.1422 | 0.1241 | 0.6817 | -0.3370 | 0.0221 |
| historical_bl | 0.1514 | 0.1345 | 0.6993 | -0.3543 | 0.0197 |
| lightweight_bl | 0.1420 | 0.1268 | 0.6688 | -0.3297 | 0.1861 |
| lightweight_rank_tilt | 0.1437 | 0.1334 | 0.6533 | -0.3487 | 0.1945 |

## Signal

- Mean rank IC: `-0.0125`
- Positive rank-IC rate: `0.4394`
- Mean top-bottom spread: `-0.0003`

## Paired vs lightweight_bl

- P(higher return): `0.7445`
- P(higher Sharpe): `0.2840`

## Paired vs equal_weight

- P(higher return): `0.7535`
- P(higher Sharpe): `0.2880`

## Guardrail

- Existing lightweight point forecasts are unchanged.
- Cross-sectional order is the only forecast input to weights.
- Validation and holdout remain sealed unless every gate passes.
