# Risk–Momentum Blend Research

- Split: `fama-french-12-industry-risk-momentum-research-1970-1999-v1`
- Namespace: `construction-v1-risk-momentum-industry-portfolios`
- Gate: `rejected`
- Promotion eligible: `False`

## Momentum signal

- Periods: `120`
- Mean rank IC: `0.0868`
- Mean top-bottom spread: `0.0099`
- P(IC>0): `0.9975`
- P(spread>0): `0.9825`

## Portfolio

| Model | CAGR | Volatility | Sharpe | Max DD | Turnover |
|---|---:|---:|---:|---:|---:|
| equal_weight | 0.1357 | 0.1331 | 0.5423 | -0.4731 | 0.0178 |
| risk_parity | 0.1368 | 0.1306 | 0.5581 | -0.4625 | 0.0235 |
| momentum_12_1_rank_tilt | 0.1447 | 0.1368 | 0.5893 | -0.4445 | 0.1981 |
| risk_momentum_blend | 0.1387 | 0.1336 | 0.5610 | -0.4579 | 0.0676 |

## Paired vs risk_parity

- P(lower volatility): `0.0000`
- P(higher Sharpe): `0.5900`

## Paired vs momentum_12_1_rank_tilt

- P(lower volatility): `1.0000`
- P(higher Sharpe): `0.0435`

## Guardrail

- Component weights are fixed 50/50 without a tuning grid.
- Candidate must improve both component baselines.
- Validation remains sealed unless signal, dual-baseline, deterministic, and six-hypothesis Holm gates all pass.
