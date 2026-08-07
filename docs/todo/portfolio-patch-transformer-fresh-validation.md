# TODO - Pooled Patch Transformer Fresh Validation

- 등록 일시: 2026-08-01 22:03 (KST)
- 작성자: Codex
- 에이전트: Codex
- 진행 시점: 새로운 untouched PIT OHLCV/universe split을 확보한 뒤

> 완료된 TODO는 이 파일을 삭제하고, `docs/reports/`에 작업 기록을 남깁니다.

## 목표

- frozen pooled Patch Transformer 사양을 이미 소비된 4-case validation과 겹치지 않는 데이터에서 검증합니다.

## 요구사항

- delisted-inclusive dated security identity 또는 promotion-safe PIT universe/price provenance를 사용합니다.
- split manifest에 OHLCV, universe, PIT factor, Kronos checkpoint/model revision, model config와 seed를 잠급니다.
- pooled ridge, frozen Kronos score, plain GMV를 baseline으로 사용합니다.
- absolute signal gate와 paired rank-IC/top-bottom spread 95% gate를 통과한 단일 candidate만 거래비용·turnover가 포함된 GMV overlay validation으로 넘깁니다.
- 이번 consumed-validation 결과에 맞춰 patch size, loss, active share, model capacity 또는 signal 조합을 재튜닝하지 않습니다. 고정 gamma `0.025`의 다중 모델 diagnostic도 gamma나 모델 선택 근거로 재사용하지 않습니다.

## 작업 요약

- 구현과 consumed-validation diagnostic은 완료됐지만 해당 origin은 이전 Kronos benchmark에서 이미 사용됐으므로 promotion evidence가 아닙니다.

## 선행조건

- untouched universe/기간과 provenance가 확정되어야 합니다.
- 필요한 경우 licensed delisted-inclusive 데이터 export가 제공되어야 합니다.

## 참고

- 관련 문서: `docs/reports/260801-2203-01-pooled-patch-transformer.md`
- fixed-gamma diagnostic: `docs/reports/260807-1646-01-gmv-dl-tilt.md`
- signal-model comparison: `docs/reports/260807-1701-02-gmv-signal-model-comparison.md`
- todo-list 한 줄 요약: Pooled Patch Transformer를 untouched PIT OHLCV split에서 최종 검증
