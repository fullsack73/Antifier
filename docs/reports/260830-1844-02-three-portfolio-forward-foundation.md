# 세 포트폴리오 forward 검증 기반 구축

- 일시: 2026-08-30 18:44 (KST)
- 작성자: 사용자 요청 기반
- 에이전트: Codex
- 작업 유형: research tooling / 사전 등록 / 자동화

## 요약

`three-portfolio-forward-performance` TODO의 미래 데이터 의존 부분을 제외한 실행 기반을 완료했습니다. 세 입력 JSON의 파일 hash와 weight/cash snapshot, 2026-08-31 첫 eligible date, 63/126/252 일별 수익 milestone, 연 3.5% 현금, 252일 연율화, 21일 paired circular block bootstrap 5,000회와 수동 검토 계약을 immutable spec으로 고정했습니다.

2026-08-30 현재 구성 이후 관측은 0개이므로 상태는 `forward_pending`, 다음 milestone은 63입니다. 실제 252개 수익 관측과 전체 검증 전에는 TODO를 완료로 처리하지 않습니다.

## 변경 범위

- `data/research/derived/three_portfolio_forward_spec_v1.json`: 세 portfolio와 평가 계약 self-hash 사양
- `tools/three_portfolio_forward.py`: spec/input 검증, Yahoo chart v8 live/offline adjusted-close 정렬, buy-and-hold 성과와 paired bootstrap 평가 CLI
- `tests/test_three_portfolio_forward.py`: hash drift, pre-formation pending, 63/126/252 milestone 결정성 회귀 테스트
- `docs/01-folder-architecture.md`, `docs/02-specs.md`, `docs/03-product-plan.md`: 새 research-only forward 경로 기록
- `docs/todo/three-portfolio-forward-performance.md`: 구현 진행 상태와 정확한 일별 수익 관측 계약 반영

## 고정 계약

- Spec SHA-256: `7c2c1edf73dd105d59e79edf0ff1476aa1255629e91188e6be6d4c530ce449fb`
- GMV input SHA-256: `1042892937d0093c25a691c7452bbde43242f3ebec3379570f58c246e666d96b`
- 뉴스 보정 GMV input SHA-256: `7ba69790d472e1d4e5e406cf02b88ead9af3fc142bc2192f4ddcfec7c5fb0243`
- LLM 단독 input SHA-256: `0d86e82e55c634be514186ee90f936ff03f8561b7370bf1cb0756a4936fbca61`
- Historical backfill: 금지
- Production 자동 승격: 금지
- 뉴스 provenance: `unavailable`, `non_reproducible_diagnostic`

## 현재 실행

- As-of: `2026-08-30`
- Status: `forward_pending`
- Common price observations: `0`
- Completed return observations: `0`
- Next milestone: `63`
- Result SHA-256: `cb842a64c9878752b5d085be63a85e3ced9d920bc6d7d67aa2311d51fad32c09`

## 지속 실행

현재 task를 매주 화요일 09:00 KST에 재개하는 heartbeat `forward`를 등록했습니다. 새 milestone이 성숙할 때만 결과를 기록하며 252 milestone과 요구사항 전체가 검증된 뒤 TODO 파일과 인덱스 항목을 제거하고 완료 보고서를 남깁니다.

## 검증

- `python3 -m py_compile tools/three_portfolio_forward.py`: 통과
- `python3 tools/three_portfolio_forward.py --help`: 통과
- `PYTHONPATH=src/backend python3 -m pytest tests/test_three_portfolio_forward.py tests/test_portfolio_statistics.py -q`: 12개 통과
- Pre-formation current-status deterministic 실행: 통과
- Yahoo chart v8 live smoke: 39/39 ticker, 2026-08-27~2026-08-28 조정종가 2개 공통 관측 확인
- 전체 backend pytest: 현재 system Python에 `flask`, `yfinance`, `scipy`, `sklearn`, `cvxpy`, `pypfopt`, `tensorflow`가 없어 30개 module collection error로 실행 불가. 새 경로 targeted collection과 테스트는 정상
- 문서 링크, placeholder, `git diff --check`: 통과

## 리스크/이슈

- 미래 시장 관측은 시간 경과 전 생성하거나 소급할 수 없습니다.
- live CLI는 Python 표준 라이브러리로 Yahoo chart v8 adjusted-close를 조회하며 USD currency를 강제합니다. Yahoo data availability가 없으면 partial result를 만들지 않고 오류로 종료합니다.
- 뉴스 원문/as-of/digest와 LLM model/prompt/config는 기존 입력에 없어 복원할 수 없습니다.

## 다음 작업

- 63/126/252 일별 수익 관측 milestone이 성숙할 때 heartbeat에서 동일 CLI를 실행하고 결과를 수동 검토합니다.

## 참고

- 관련 문서: `docs/todo/three-portfolio-forward-performance.md`, `docs/reports/260830-1825-01-three-portfolio-performance.md`
