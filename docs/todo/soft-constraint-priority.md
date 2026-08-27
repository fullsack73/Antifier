# TODO - Soft constraint priority

- 등록 일시: 2026-08-27 00:43 (Asia/Seoul)
- 작성자: 사용자 요청 기반
- 에이전트: Codex
- 진행 시점: penalty calibration과 사용자 설명 계약 확정 후

## 목표

- 위반 가능한 soft constraint를 hard constraint와 명확히 구분하고 우선순위 및 비용을 투명하게 표시합니다.

## 요구사항

- return, risk, exposure마다 다른 penalty 단위를 비교 가능한 기준으로 정규화해야 합니다.
- 요청 priority, realized slack, penalty contribution, hard/soft 상태를 API와 UI에 함께 노출해야 합니다.
- scale sensitivity와 conflicting soft constraint를 다양한 universe에서 검증해야 합니다.

## 작업 요약

- 임의 penalty 숫자는 사용자 의도와 실제 우선순위를 왜곡하므로 이번 릴리스는 선형 hard constraint와 기존 L2/turnover objective만 유지했습니다.

## 선행조건

- penalty normalization 정책, deterministic tie-breaking, documented calibration dataset
- hard-only baseline 대비 feasibility, stability, turnover validation

## 참고

- 관련 문서: `docs/02-specs.md`, `docs/03-product-plan.md`
- todo-list 한 줄 요약: hard constraint와 구분되는 penalty 단위·우선순위·slack 설명 계약을 연구합니다.
