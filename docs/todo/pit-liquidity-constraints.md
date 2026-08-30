# TODO - Point-in-time liquidity constraints

- 등록 일시: 2026-08-27 00:43 (Asia/Seoul)
- 작성자: 사용자 요청 기반
- 에이전트: Codex
- 진행 시점: historical ADV와 execution policy dataset 확보 후

## 목표

- ADV participation, 최소 거래대금, 예상 market impact를 point-in-time portfolio constraint로 설계합니다.
- 본 작업은 execution/correctness lane이며 alpha 성과 개선 또는 licensed PIT 데이터 확보 과제로 해석하지 않습니다.

## 요구사항

- split/dividend/corporate action을 조정한 historical price-volume과 signal-date 이전 ADV만 사용해야 합니다.
- portfolio notional, rebalance horizon, participation rate, 거래비용 단위를 명확히 고정해야 합니다.
- missing volume, 신규 상장, 거래정지, 극단적 volume spike를 포함한 walk-forward execution validation이 필요합니다.

## 작업 요약

- 최신 volume을 과거 liquidity처럼 사용하는 look-ahead 위험이 있어 이번 릴리스에서 구현하지 않았습니다.

## 선행조건

- point-in-time OHLCV provenance, corporate-action policy, portfolio notional 입력 계약
- realized slippage 또는 보수적 impact calibration과 coverage gate
- calendar-forward observation의 missing/partial coverage와 accounting invariant 기록

## 참고

- 관련 문서: `docs/02-specs.md`, `docs/03-product-plan.md`
- todo-list 한 줄 요약: point-in-time ADV와 corporate-action-adjusted 가격 데이터로 liquidity/participation 제약을 검증합니다.
