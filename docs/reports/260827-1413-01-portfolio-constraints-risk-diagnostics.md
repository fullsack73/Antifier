# 작업 기록 - Portfolio Constraints and Risk Diagnostics

- 일시: 2026-08-27 14:13 (KST)
- 작성자: Codex
- 에이전트: Codex
- 작업 유형: production 기능 추가/검증/문서화

## 요약

- production 포트폴리오 최적화에 종목별 최소·최대 비중, sector/industry/country 그룹 최소·최대 비중, 전체 종목 cap을 추가했습니다.
- `max_asset_weight`, L2, 최소 보유 비중, turnover penalty, rebalance band, 최대 turnover를 Optimizer API/UI와 Portfolio Manager의 의미 있는 흐름에 연결했습니다.
- 최종 반환 weight 기준 risk contribution, 집중도, covariance, 분류 exposure와 제약 충족·slack·binding 진단을 API와 Optimizer 결과 화면에 추가했습니다.
- PyPortfolioOpt/CVXPY/Scipy의 기존 로컬 구조를 사용했으며 `gs-quant`, 기관 자격증명, 원격 유료 데이터 의존성을 추가하지 않았습니다.

## 구현

- `portfolio_constraints.py`가 입력 정규화, 선형 feasibility 검사, solver 제약, 최소 보유 비중 projection, 사후 제약 재검증과 구조화 오류를 담당합니다.
- MIN_VARIANCE, BL, MPT와 target return/risk 경로가 동일한 asset/group constraint model을 사용합니다.
- lower/upper 합계, 공통 cap, asset/group 충돌은 `scipy.optimize.linprog`로 함께 검사하고, target return 상한과 risk tolerance 하한도 solver 전에 계산합니다.
- threshold와 turnover control 이후 실제 반환 weight를 다시 검증합니다. 이 단계에서 제약을 만족하지 못하면 위반 결과를 반환하지 않고 `POST_CONTROL_CONSTRAINT_VIOLATION`으로 실패합니다.
- 현재 분류는 `yfinance.info` source, as-of, 종목별 값과 dimension별 coverage를 기록합니다. 최신 분류를 historical point-in-time 데이터처럼 사용하지 않으며 관련 metadata 누락이나 호출 실패를 명시적으로 처리합니다.
- 구조화 오류는 code, 사람이 읽을 수 있는 message, constraint, requested/feasible value, affected ticker/group을 제공합니다. 예기치 않은 pipeline/solver 세부 내용은 로그에만 남기고 API 응답에는 노출하지 않습니다.
- risk contribution, HHI/effective holdings, 최대 비중과 기존 covariance diagnostics를 최종 반환 weight 및 실제 cash exposure에 맞춰 계산합니다. covariance universe 밖의 노출은 수익·리스크 숫자를 만들어내지 않고 unavailable 상태와 coverage를 반환합니다.

## UI와 계약

- UI의 비율 입력은 percent, API는 decimal 규칙을 유지합니다.
- Optimizer 고급 설정에서 asset/group 제약 행을 추가·삭제하고 실행 전 핵심 제약 수를 검토할 수 있습니다.
- 현재 portfolio weight가 로드된 Optimizer 흐름과 Portfolio Manager에만 turnover 제어를 표시·전달합니다.
- MIN_VARIANCE에서 target return/risk tolerance를 금지하는 기존 계약과 background progress/cancellation/persistence 구조를 유지했습니다.
- 영어·한국어 locale, README와 API/product/folder 문서를 함께 갱신했습니다.

## 검증

- `npm run lint`: 통과
- `npm test`: 7 files, 21 tests 통과
- `npm run build`: 통과; 기존 Plotly large-chunk 비차단 경고만 발생
- `PYTHONPATH=src/backend .venv/bin/python -m pytest tests`: 410 tests 통과
- 추가 확인: strict JSON serialization, 외부 metadata 실패, 구조화 오류, MIN_VARIANCE/BL/MPT 공통 제약, threshold/turnover 사후 검증, SSE/background parameter 전달을 회귀 테스트로 검증했습니다.
- `git diff --check`, locale JSON parse, backend module compile을 통과했습니다. Production dependency는 변경하지 않았고, 전체 backend test collection과 맞추기 위해 CI 전용 목록에 기존 runtime 고정값 `tensorflow==2.20.0`을 명시했습니다.

## 리스크와 결정

- 현재 yfinance 분류에는 historical point-in-time 보장이 없으므로 near-live 범위 밖의 그룹 제약은 거부합니다.
- exact cardinality는 continuous solver의 thresholding으로 가장하지 않았습니다.
- factor hedge, PIT liquidity, soft constraint priority는 데이터 provenance와 별도 검증 계약이 필요해 production 범위에 포함하지 않았습니다.

## 후속 작업

- [Factor hedge constraints](../todo/factor-hedge-constraints.md)
- [Point-in-time liquidity constraints](../todo/pit-liquidity-constraints.md)
- [Soft constraint priority](../todo/soft-constraint-priority.md)
- [Exact cardinality constraints](../todo/exact-cardinality.md)

## 관련 문서

- [Folder Architecture](../01-folder-architecture.md)
- [Specs](../02-specs.md)
- [Product Plan](../03-product-plan.md)
- [TODO List](../todo/00-todo-list.md)
