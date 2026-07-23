# 52-Week-High Momentum Research

- Split: `fama-french-30-industry-high-momentum-research-1973-1999-v1`
- Namespace: `alpha-v11-high-momentum-industry-portfolios`
- Gate: `rejected`
- Promotion eligible: `False`

## Signal

| Signal | Periods | Mean rank IC | Positive IC | Mean top-bottom |
|---|---:|---:|---:|---:|
| Raw 12-1 momentum | 108 | 0.1098 | 0.6759 | 0.0215 |
| 52-week-high blend | 108 | 0.0985 | 0.6759 | 0.0163 |

- P(higher IC): `0.1870`
- P(higher spread): `0.0790`

## Portfolio

| Model | CAGR | Volatility | Sharpe | Max DD | Turnover |
|---|---:|---:|---:|---:|---:|
| equal_weight | 0.1335 | 0.1319 | 0.5169 | -0.4265 | 0.0153 |
| risk_parity | 0.1327 | 0.1261 | 0.5288 | -0.4281 | 0.0180 |
| momentum_12_1_rank_tilt | 0.1491 | 0.1392 | 0.5955 | -0.4022 | 0.1002 |
| high_momentum_rank_tilt | 0.1466 | 0.1393 | 0.5791 | -0.4069 | 0.1104 |

- P(higher return): `0.0970`
- P(higher Sharpe): `0.0925`

## Guardrail

- Component weights and horizons were locked before the run.
- Candidate and raw momentum use identical rank-tilt construction.
- Validation remains sealed unless absolute, paired, portfolio, and Holm gates all pass.
