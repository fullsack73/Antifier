# Kronos signal-only benchmark

## 결론

- `logs/portfolio_gauntlet_standard_full_20260727.json`은 `180/180` 완료됐습니다.
- `adaptive_signal_tilt` survival은 `1/180`이어서 미승격입니다.
- pinned `Kronos-small`은 4개 candidate universe의 absolute signal gate를 통과했습니다.
- 기존 ARIMA/Transformer 대비 paired uplift는 95%에 못 미쳤습니다.
- 최종 상태: `signal_passed_incremental_unconfirmed`. production/default model 변경 없음.

## 비교 계약

- Universe/origin: 기존 candidate cache가 고정한 4개 universe, 24개 origin
- Horizon/context: 63 / 504 거래일
- Input: yfinance adjusted OHLC, timestamp alignment 필수, close-only 합성 금지
- Baseline: 같은 current OHLC에서 ARIMA+Transformer/Transformer 432개 fresh forecast
- Kronos: 216개 zero-shot batch forecast
- Repository: `shiyu-coder/Kronos@67b630e67f6a18c9e9be918d9b4337c960db1e9a`
- Model: `NeoQuasar/Kronos-small@901c26c1332695a2a8f243eb2f37243a37bea320`
- Tokenizer: `NeoQuasar/Kronos-Tokenizer-base@0e0117387f39004a9016484a186a908917e22426`
- Sampling: seed 42, `T=1.0`, `top_p=0.9`, `sample_count=1`
- Device/runtime: MPS, PyTorch 2.13.0

과거 candidate cache의 adjusted-close digest는 현재 OHLC와 216/216 불일치했습니다. yfinance의 사후 adjusted-price 변경 가능성 때문에 prediction 재사용을 거부하고, cache는 split template로만 사용했습니다.

## 결과

| Model | Mean rank IC | Positive IC | Mean top-bottom | Coverage | Absolute gate |
|---|---:|---:|---:|---:|---|
| ARIMA + Transformer rank | 0.0112 | 50.0% | -0.0012 | 100% | rejected |
| Transformer rank | 0.0173 | 50.0% | 0.0040 | 100% | rejected |
| Kronos-small zero-shot | 0.1176 | 66.7% | 0.0446 | 100% | passed |

Kronos absolute circular-block bootstrap:

- P(mean rank IC > 0): 99.70%
- P(mean top-bottom spread > 0): 99.85%
- 4개 universe 기본 gate: 4/4

Kronos paired improvement:

| Baseline | P(higher rank IC) | P(higher spread) |
|---|---:|---:|
| ARIMA + Transformer | 83.75% | 91.10% |
| Transformer | 82.20% | 90.05% |

Absolute signal은 유의했지만 incremental 95% gate는 실패했습니다. 같은 결과에서 model size, sampling, context를 재튜닝하지 않습니다.

## 비용

- Baseline cold-cache fill span: 약 1,686초
- Kronos MPS inference: 약 694.7초, 216 predictions
- Model + tokenizer snapshot: 114,844,309 bytes
- 첫 cold run process peak RSS: 약 678.6 MiB
- Baseline SQLite: 432 rows, `PRAGMA integrity_check = ok`
- Kronos checkpoint: 24 valid JSONL rows

## 구현

- `tools/benchmark_kronos_forecasts.py`
  - OHLC 필수 검증
  - baseline/Kronos 동일 input alignment
  - pinned repo/model/tokenizer
  - baseline SQLite cache, Kronos JSONL checkpoint/resume
  - absolute/paired block bootstrap와 4-universe gate
- `requirements-kronos-research.txt`
  - production/installer/CI와 분리된 optional research dependency
- `tests/test_kronos_benchmark.py`
  - exact close digest alignment, close-only 거부, 3-model 비교, paired decision 회귀 테스트

## 후속

새 untouched split 또는 licensed delisted-inclusive PIT OHLC 전에는 Kronos를 core portfolio model, installer, default gauntlet, locked holdout에 넣지 않습니다.
