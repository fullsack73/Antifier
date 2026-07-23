# Lightweight OOS-Uncertainty Research

- Split: `fama-french-17-industry-lightweight-uncertainty-research-1971-1999-v1`
- Namespace: `forecast-v5-lightweight-oos-uncertainty`
- Rows/tickers: `7832` / `17`
- Deterministic gate: `rejected`
- Statistical gate: `rejected`
- Promotion eligible: `False`

## Performance

| Model | CAGR | Volatility | Sharpe | Max DD | Avg turnover | Mean rank IC | Top-bottom |
|---|---:|---:|---:|---:|---:|---:|---:|
| equal_weight | 0.1295 | 0.1304 | 0.5093 | -0.4246 | 0.0176 | NA | NA |
| risk_parity | 0.1326 | 0.1288 | 0.5347 | -0.4381 | 0.0211 | NA | NA |
| historical_bl | 0.1278 | 0.1284 | 0.5035 | -0.4394 | 0.0136 | 0.0577 | 0.0072 |
| lightweight_bl | 0.1310 | 0.1336 | 0.5100 | -0.4397 | 0.0653 | 0.0223 | -0.0004 |
| calibrated_lightweight_bl | 0.1309 | 0.1309 | 0.5169 | -0.4327 | 0.0215 | 0.0223 | -0.0004 |

## Paired Evidence

- P(higher return): `0.3940`
- P(higher Sharpe): `0.7105`
- Holm return adjusted p: `0.6060`
- Holm Sharpe adjusted p: `0.5790`

## Calibration

- Mean completed observations: `6.0000`
- Mean raw OOS RMSE: `0.5751`
- Median raw OOS RMSE: `0.5332`

## Guardrail

- Point forecasts and ensemble weights are unchanged.
- Only targets completed inside each training window calibrate uncertainty.
- Validation and holdout remain sealed unless every research gate passes.
