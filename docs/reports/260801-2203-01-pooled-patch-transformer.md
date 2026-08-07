# 작업 기록 - Pooled Patch Transformer 연구 경로

- 일시: 2026-08-01 22:03 (KST)
- 작성자: Codex
- 에이전트: Codex
- 작업 유형: 연구 기능 추가/진단

## 요약

- 기존 단변량 Transformer의 위치 정보 부재, one-step MSE/recursive forecast, in-sample uncertainty 문제를 production과 분리된 새 research 경로로 교체했습니다.
- ordered OHLCV patch, 명시적 position embedding, pooled date×ticker 학습, direct 21/63일 target, price/PIT/Kronos context, completed-OOS gate와 exact-GMV fallback을 구현했습니다.
- 로컬 frozen Kronos 24 origin/216 score에서 ablation diagnostic을 실행했지만 이미 소비된 validation이므로 `promotion_safe=false`로 고정했습니다.
- candidate는 tail-spread와 paired 95% gate에서 탈락했으며 production Ledoit-Wolf GMV는 변경하지 않았습니다.

## 변경 범위

- `pooled_patch_transformer.py`: patch/context 생성, Kronos checkpoint 검증, TensorFlow pooled model, walk-forward gate
- `research_pooled_patch_transformer.py`: no-Kronos/Kronos ablation, Kronos baseline, paired bootstrap, latest GMV overlay, fixed-gamma portfolio diagnostic
- regression tests, architecture/spec/product docs, fresh validation TODO

## 주요 결과

| Model | Mean rank IC | Positive IC | Top-bottom spread | Signal gate |
|---|---:|---:|---:|---|
| Frozen Kronos score | 0.1344 | 73.33% | 2.8019% | rejected |
| Patch Transformer, no Kronos | 0.0885 | 66.67% | 0.9541% | rejected |
| Patch Transformer + Kronos | 0.1403 | 80.00% | -0.1471% | rejected |

- Patch+Kronos vs no-Kronos P(higher IC/spread): `80.75% / 29.90%`
- Patch+Kronos vs frozen Kronos P(higher IC/spread): `56.10% / 2.20%`
- Patch+Kronos absolute P(positive IC/spread): `99.90% / 45.45%`
- 최신 completed-OOS sequential gate는 tail spread 실패로 비활성화됐고 GMV overlay active share는 정확히 `0`이었습니다.
- OHLCV SHA-256: `d7b5fc00a98226a4ddb818246b4ca271f1899d1cefd4afda3181e31b32b10e7b`
- result SHA-256: `da16ebe18b11eb9875ebb5191e407cca9ec1602083114b2eef2ca628be30b895`

## 검증

- `PYTHONPATH=src/backend .venv/bin/python -m pytest -q tests/test_pooled_patch_transformer.py tests/test_forecast_gmv_pipeline.py`: `8 passed`
- `PYTHONPATH=src/backend .venv/bin/python -m pytest -q tests`: `378 passed, 1 skipped`
- TensorFlow 2.20 actual walk-forward: no-Kronos/Kronos 각각 15 fits, coverage 100%
- Kronos checkpoint signature/horizon 검증, no-lookahead training cutoff, position embedding/direct-head regression 포함

## 리스크/이슈

- 사용한 24 origin은 기존 Kronos benchmark가 이미 소비한 4-case validation이므로 모델 선택이나 승격에 재사용할 수 없습니다.
- TensorFlow origin별 재학습은 정확하지만 retracing 경고와 약 70초/model ablation 비용이 있습니다.
- frozen Kronos 입력은 평균 순위를 개선했지만 tail selection을 악화시켜 Kronos 단독보다 우월하지 않았습니다.

## 다음 작업

- `docs/todo/portfolio-patch-transformer-fresh-validation.md`의 untouched PIT OHLCV split이 준비되기 전에는 HPO, portfolio validation, production 연결을 진행하지 않습니다.

## 참고

- `data/research/derived/pooled_patch_transformer_consumed_validation_diagnostic_v1.json`
- `docs/reports/260730-1638-01-kronos-signal-benchmark.md`
- `docs/reports/260731-0157-01-gmv-forecast-research-closure.md`
- `docs/reports/260807-1646-01-gmv-dl-tilt.md`
- `docs/reports/260807-1701-02-gmv-signal-model-comparison.md`
