# Minimum-Variance–Momentum Blend Research

- Split: `fama-french-10-industry-minvar-momentum-research-1970-1999-v1`
- Namespace: `construction-v2-minvar-momentum-industry-portfolios`
- Gate: `rejected`
- Promotion eligible: `False`

## Momentum signal

- Periods: `120`
- Mean rank IC: `0.0675`
- Mean top-bottom spread: `0.0141`
- P(IC>0): `0.9720`
- P(spread>0): `0.9855`

## Portfolio

| Model | CAGR | Volatility | Sharpe | Max DD | Turnover |
|---|---:|---:|---:|---:|---:|
| equal_weight | 0.1369 | 0.1333 | 0.5498 | -0.4717 | 0.0183 |
| min_variance | 0.1484 | 0.1195 | 0.6829 | -0.4221 | 0.1051 |
| momentum_12_1_rank_tilt | 0.1444 | 0.1367 | 0.5878 | -0.4432 | 0.2083 |
| minvar_momentum_blend | 0.1459 | 0.1270 | 0.6325 | -0.4275 | 0.1137 |

## Paired vs min_variance

- P(lower volatility): `0.0000`
- P(higher Sharpe): `0.0645`

## Paired vs momentum_12_1_rank_tilt

- P(lower volatility): `1.0000`
- P(higher Sharpe): `0.9410`

## Guardrail

- Component weights are fixed 50/50 without a tuning grid.
- Candidate must improve both component baselines.
- Validation remains sealed unless signal, dual-baseline, deterministic, and six-hypothesis Holm gates all pass.
