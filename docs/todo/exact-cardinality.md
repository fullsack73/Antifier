# TODO - Exact cardinality constraints

- 등록 일시: 2026-08-27 00:43 (Asia/Seoul)
- 작성자: 사용자 요청 기반
- 에이전트: Codex
- 진행 시점: mixed-integer solver 배포 정책과 runtime gate 확정 후

## 목표

- 정확한 최대 보유 종목 수와 최소 lot/holding을 mixed-integer optimization으로 지원할지 검토합니다.

## 요구사항

- CI와 Linux/Windows/macOS installer에서 동작하는 mixed-integer solver가 필요합니다.
- timeout, optimality gap, deterministic seed, solver unavailable fallback을 API에 명확히 기록해야 합니다.
- 현재 min-holding heuristic 및 unconstrained baseline과 solution quality/runtime을 비교해야 합니다.

## 작업 요약

- 현재 continuous PyPortfolioOpt/CVXPY 구조에서 thresholding을 exact cardinality hard constraint로 표시하는 것은 부정확하므로 구현하지 않았습니다.

## 선행조건

- 재배포 가능한 solver 라이선스와 세 플랫폼 build 검증
- universe size별 runtime/memory budget, timeout 및 fallback 정책

## 참고

- 관련 문서: `docs/02-specs.md`, `docs/03-product-plan.md`, `tools/BUILD.md`
- todo-list 한 줄 요약: mixed-integer solver 지원성과 재현 가능한 fallback 정책이 확보되면 exact max-names를 검토합니다.
