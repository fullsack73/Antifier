# Raw Momentum Rank-Tilt Research

- Split: `fama-french-17-industry-raw-momentum-research-2000-2011-v1`
- Namespace: `alpha-v12-raw-momentum-industry-portfolios`
- Gate: `rejected`
- Promotion eligible: `False`

## Signal

| Signal | Periods | Mean rank IC | Positive IC | Mean top-bottom |
|---|---:|---:|---:|---:|
| Lightweight point forecast | 48 | -0.0120 | 0.4792 | -0.0042 |
| Raw 12-1 momentum | 48 | 0.0042 | 0.4583 | -0.0025 |

- P(higher IC): `0.6245`
- P(higher spread): `0.5695`

## Portfolio

| Model | CAGR | Volatility | Sharpe | Max DD | Turnover |
|---|---:|---:|---:|---:|---:|
| equal_weight | 0.0588 | 0.2109 | 0.2693 | -0.5375 | 0.0306 |
| risk_parity | 0.0620 | 0.2024 | 0.2868 | -0.5280 | 0.0384 |
| historical_bl | 0.0559 | 0.2114 | 0.2562 | -0.5352 | 0.0275 |
| lightweight_bl | 0.0491 | 0.2140 | 0.2256 | -0.5661 | 0.1193 |
| momentum_12_1_rank_tilt | 0.0594 | 0.2175 | 0.2700 | -0.5426 | 0.1872 |

- P(higher return vs lightweight): `0.9635`
- P(higher Sharpe vs lightweight): `0.9540`

## Guardrail

- The raw momentum specification was frozen before this run.
- The closest baseline is the current lightweight BL default.
- Validation remains sealed unless absolute signal, paired signal, portfolio, guard, and Holm gates all pass.
