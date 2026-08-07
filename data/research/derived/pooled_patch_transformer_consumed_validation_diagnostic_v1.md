# Pooled Patch Transformer Diagnostic

- Decision: `rejected`
- Role: research-only; consumed validation origins; not promotion-safe
- Origins: 24
- Kronos scores: 216

| Model | Rank IC | Positive IC | Top-bottom | Gate | Fits | Seconds |
|---|---:|---:|---:|---|---:|---:|
| arima | 0.0278 | 0.6000 | 0.0052 | rejected | 0 | 0.0 |
| transformer | 0.1446 | 0.4667 | 0.0047 | rejected | 0 | 0.0 |
| arima_transformer | 0.1090 | 0.5333 | 0.0127 | rejected | 0 | 0.0 |
| frozen_kronos_score | 0.1344 | 0.7333 | 0.0280 | rejected | 0 | 0.0 |
| patch_without_kronos | 0.0885 | 0.6667 | 0.0095 | rejected | 15 | 73.5 |
| patch_with_kronos | 0.1403 | 0.8000 | -0.0015 | rejected | 15 | 71.9 |

## Paired evidence

- with_kronos_vs_kronos_score: rank IC 0.5610, spread 0.0220; gate `rejected`
- with_kronos_vs_without_kronos: rank IC 0.8075, spread 0.2990; gate `rejected`

## Latest GMV overlay

- Signal gate: `rejected`
- Exact GMV fallback: `True`
- Realized active share: 0.0000

## Patch+Kronos fixed-gamma GMV + DL tilt

- Gamma: `0.0250`
- Mean raw/executed active share: 0.0178 / 0.0192
- P(higher return): 0.8550
- P(higher Sharpe): 0.7775
- P(lower volatility): 0.0585
- Portfolio gate: `rejected`

## Fixed-gamma signal model comparison

| Rank | Signal | Return diff | Vol diff | Sharpe diff | P(return) | P(Sharpe) | Gate |
|---:|---|---:|---:|---:|---:|---:|---|
| 1 | patch_with_kronos | 0.0017 | 0.0005 | 0.0055 | 0.8550 | 0.7775 | rejected |
| 2 | transformer | 0.0016 | 0.0004 | 0.0053 | 0.7510 | 0.7225 | rejected |
| 3 | frozen_kronos_score | 0.0013 | 0.0003 | 0.0042 | 0.7485 | 0.7070 | rejected |
| 4 | patch_without_kronos | 0.0011 | 0.0005 | 0.0027 | 0.7475 | 0.6450 | rejected |
| 5 | arima | 0.0009 | 0.0003 | 0.0026 | 0.6580 | 0.6060 | rejected |
| 6 | arima_transformer | 0.0005 | 0.0003 | 0.0011 | 0.5790 | 0.5465 | rejected |
