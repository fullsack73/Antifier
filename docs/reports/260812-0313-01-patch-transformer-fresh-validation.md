# 작업 기록 - Pooled Patch Transformer Fresh Validation

- 일시: 2026-08-12 03:13 (KST)
- 작성자: Codex
- 에이전트: Codex
- 작업 유형: frozen research candidate 최종 검증/TODO 완료

## 결론

- 2024-2025의 미사용 Nasdaq-100 PIT universe/OHLCV split에서 frozen `pooled_patch_transformer_with_kronos` 후보를 8개 분기 origin으로 검증했습니다.
- 후보의 평균 rank IC는 `-0.0570`, top-minus-bottom spread는 `-2.4831%`로 absolute signal gate를 통과하지 못했습니다.
- pooled relative ridge와 frozen Kronos 각각에 대한 paired rank-IC/spread 95% gate도 모두 탈락했습니다.
- 선행 signal gate가 실패했으므로 plain Ledoit-Wolf GMV 대비 5% active-share overlay validation은 실행하지 않았습니다. 후보는 승격하지 않으며 production Ledoit-Wolf GMV를 그대로 유지합니다.

## 잠긴 검증 계약

- split: `nasdaq100-patch-transformer-fresh-validation-2024-2025-v1`
- 평가 구간: `2024-01-01`~`2025-12-31`; 기존 consumed diagnostic의 2019-2023 origin과 겹치지 않음
- split manifest SHA-256: `94f52f1149967c736e2214636f1f9e13b0cf27e0e3312bcf96a2bd02e659cee9`
- OHLCV SHA-256: `1fc401ce21707b384398c932b93dbd11d5c0accd748802903779578cb5339896`
- dated universe canonical SHA-256: `2be905a14655e55373a562d96aec280f27833d4c13663f8a060b2a4944ea2741`
- PIT factor SHA-256: `d1ed438e99cf7528b1e2b4606a223282179b8dcb44df497c63f0ae5dc6952ce6`
- Kronos repository/model/tokenizer revision: `67b630e` / `901c26c` / `0e01173`
- Patch Transformer: relative 21/63일 target, lookback 504, patch 5, `d_model=32`, 2 blocks, seed 42
- 실행 제약: 10 bps 비용, 2% rebalance band, 35% turnover cap, 자산별 20% cap, 5% active share
- frozen 후보 사양에 따라 PIT factor 파일은 계약에 잠갔지만 candidate feature로 사용하지 않았습니다.
- 기존 consumed-validation 고정 gamma `0.025` diagnostic은 설정 또는 모델 선택 근거로 재사용하지 않았습니다.

OHLCV는 당시 구성종목 179개 중 Yahoo에서 검증 가능한 157개의 실제 auto-adjusted OHLCV를 포함합니다. 각 평가 origin의 전체 active universe 101개를 분모로 계산한 coverage는 최소 `95.05%`, 마지막 origin은 `100%`였습니다. 누락 종목은 origin별로 결과 JSON에 명시했습니다.

## 결과

| Model | Mean rank IC | Positive IC | Top-bottom spread | Absolute gate |
|---|---:|---:|---:|---|
| Pooled relative ridge | 0.0003 | 25.00% | 0.8238% | 비교 기준 |
| Frozen Kronos score | -0.0632 | 50.00% | -3.7049% | rejected |
| Pooled Patch Transformer + Kronos | -0.0570 | 25.00% | -2.4831% | rejected |

| Paired comparison | P(IC improvement) | P(spread improvement) | 95% gate |
|---|---:|---:|---|
| Candidate vs relative ridge | 12.65% | 1.65% | rejected |
| Candidate vs frozen Kronos | 55.25% | 79.90% | rejected |

- 최종 decision: `signal_rejected`
- promotion eligible: `false`
- GMV overlay: `not_run`
- 결과 JSON SHA-256: `202f99b51e29dc13f8f423cf3d65de62cce0af25d4fbfc85baa1d44f1b0c66d1`
- Kronos checkpoint SHA-256: `57ae99634c9dc72dddf780c50864f04cdf80a3b1960a72599bce5f5335f2ac74`

## 구현

- immutable split과 data/provenance SHA를 검증하는 `tools/validate_pooled_patch_transformer.py`를 추가했습니다.
- 기존 pooled ridge, Kronos checkpoint, Patch Transformer, GMV 실험 엔진을 재사용해 새 의존성이나 production 연결을 추가하지 않았습니다.
- walk-forward Patch Transformer에 고정 평가 구간을 추가하되, 평가 전 완료된 origin은 training history로 유지했습니다.
- coverage 분모를 다운로드 가능한 가격 열이 아니라 전체 PIT active universe로 수정하고 누락 ticker를 기록했습니다.
- Kronos 횡단면 추론을 고정 batch로 checkpoint할 수 있게 해 큰 universe에서도 재시작 가능하게 했습니다.

## 검증

- fresh validation CLI를 완주하고 동일 Kronos checkpoint 재사용 실행도 exit code 0으로 재현했습니다.
- Kronos checkpoint: 고정 training/evaluation origin 20개 모두 완료
- focused regression: `14 passed`
- `PYTHONPATH=src/backend .venv/bin/python -m pytest -q tests`: `391 passed in 94.94s`

## 산출물

- `data/research/derived/nasdaq100_ohlcv_2017_2026.csv`
- `data/research/derived/nasdaq100_ohlcv_2017_2026.provenance.json`
- `data/research/derived/nasdaq100_patch_transformer_fresh_validation_split_v1.json`
- `data/research/derived/nasdaq100_patch_transformer_fresh_validation_result_v1.json`
- `data/research/derived/nasdaq100_patch_transformer_fresh_validation_result_v1.md`
- `logs/nasdaq100_patch_transformer_fresh_validation_kronos_batch16_v1.jsonl`
