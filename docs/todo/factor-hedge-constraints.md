# TODO - Factor hedge constraints

- 등록 일시: 2026-08-27 00:43 (Asia/Seoul)
- 작성자: 사용자 요청 기반
- 에이전트: Codex
- 진행 시점: point-in-time factor dataset과 hedge instrument 정책 확정 후

## 목표

- 시장, 섹터, size, value 등 factor exposure의 목표 범위 또는 중립 제약을 검증 가능한 production 기능으로 설계합니다.

## 요구사항

- signal date 이전에 공개된 factor loading만 사용하는 point-in-time 데이터가 필요합니다.
- hedge instrument의 거래 가능성, 통화, 비용, liquidity와 노출 추정 오차를 함께 모델링해야 합니다.
- 동일 universe의 unconstrained baseline 대비 tracking error, turnover, 비용, residual exposure를 walk-forward로 검증해야 합니다.

## 작업 요약

- 현재 yfinance 분류만으로는 factor loading과 hedge effectiveness를 신뢰성 있게 계산할 수 없어 이번 hard constraint 범위에 포함하지 않았습니다.

## 선행조건

- versioned factor exposure dataset, provenance hash, as-of policy, hedge instrument 목록
- exposure drift 및 위기 구간을 포함한 out-of-sample validation gate

## 참고

- 관련 문서: `docs/02-specs.md`, `docs/03-product-plan.md`
- todo-list 한 줄 요약: point-in-time factor exposure와 검증된 hedge instrument를 확보한 뒤 factor hedge 제약을 연구합니다.
