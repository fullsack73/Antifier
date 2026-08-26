# Pooled Patch Transformer Fresh Validation

- Decision: `signal_rejected`
- Promotion eligible: `False`
- Split: `nasdaq100-patch-transformer-fresh-validation-2024-2025-v1`
- Evaluation origins: 8
- Minimum universe coverage: 95.05%

| Model | Mean rank IC | Top-bottom spread | Signal gate |
|---|---:|---:|---|
| relative_ridge | 0.0003 | 0.0082 | not_applicable |
| frozen_kronos_score | -0.0632 | -0.0370 | rejected |
| pooled_patch_transformer_with_kronos | -0.0570 | -0.0248 | rejected |

## Paired signal gates

- candidate_vs_relative_ridge: IC 12.65%, spread 1.65%; `rejected`
- candidate_vs_frozen_kronos: IC 55.25%, spread 79.90%; `rejected`

## GMV overlay validation

- Status: `not_run`
- Reason: absolute and paired 95% signal gates did not all pass
