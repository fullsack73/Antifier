# Production GMV Shadow 운영 품질 구현

- 일시: 2026-08-28 15:35 KST
- 작성자: Codex
- 작업 유형: backend 기능 추가, CLI, 회계/검증 강화, fixture test, 정책 문서

## 요약

- Production `MIN_VARIANCE + RISK_ONLY` Ledoit-Wolf global minimum variance의 objective와 weight 계산은 변경하지 않았습니다.
- 실제 optimizer 결과와 사용 가격 panel에서 production baseline shadow observation을 생성하는 재사용 adapter를 구현했습니다.
- Shadow observation contract v2는 caller boolean 대신 raw notional, wealth, price, constraint와 rerun hash에서 correctness를 재계산합니다.
- 현재 등록 가능한 candidate를 새로 만들지 않았고 baseline-only collection만 구현했습니다.
- 실제 미래 observation이 아직 없으므로 calendar-forward 성과가 검증됐다고 주장하지 않습니다.

## 실제 운영 흐름

1. `tools/shadow_forward.py collect-baseline`이 immutable campaign과 run specification을 읽습니다.
2. `production_baseline_observation.py`가 as-of local date에서 exclusive end date를 만들고 production optimizer를 같은 입력으로 두 번 호출합니다.
3. `portfolio_optimization.py`의 기존 `RISK_ONLY` data pipeline, Ledoit-Wolf covariance, `EfficientFrontier.min_volatility()`, hard constraint와 post-control 진단을 그대로 사용합니다.
4. Adapter가 requested/eligible universe, ordered USD price SHA, explicit no-view, 실행 weight/cash, covariance risk, turnover/cost와 coverage를 optimizer 결과에서 파생합니다.
5. 네트워크와 계산이 모두 끝난 뒤 observation 하나만 SQLite ledger transaction에서 append됩니다. 주문, broker 호출, result persistence와 production 자동 변경은 없습니다.
6. 이후 `record-outcome`은 campaign horizon이 성숙한 실제 미래 가격만 받아 price hash를 확인하고 as-of weight/cash와 pre/post-cost wealth로 realized metrics를 계산합니다.

## Correctness 계약

- `weight + cash = 1`
- `traded_notional = Σ|executed - current|`
- `turnover = traded_notional / reference_wealth`
- `transaction_cost = traded_notional × transaction_cost_rate`
- `post_cost_wealth = reference_wealth - transaction_cost`
- `Σexecuted_notional + executed_cash = post_cost_wealth`
- executed notional과 저장 weight/cash의 정규화 일치
- weight ticker의 eligible universe 포함
- eligible universe 기준 price coverage와 missing ticker 일치
- long-only, common cap, asset/group/min-holding constraint 재계산
- 동일 input result hash와 최대 weight 차이로 deterministic rerun 확인

Caller가 전달한 기존 `*_passed` boolean은 v2 판정에 사용하지 않습니다. Physical SQLite schema v1과 기존 observation contract v1 row는 migration 없이 유지하며 hash-chain과 append-only trigger도 보존합니다.

## 실패와 재실행

- Complete, partial coverage, network failure, data missing, calculation failure를 모두 baseline/candidate 출력과 분리해 append-only로 기록합니다.
- 동일 campaign/as-of의 semantic payload가 같으면 `recorded_at`이 달라도 duplicate로 처리합니다. Data hash나 결과가 바뀌면 conflicting duplicate로 거부합니다.
- Campaign 생성 전 historical backfill은 계속 금지합니다.
- Live optimizer 호출에서 예상하지 못한 예외가 발생해도 calculation-failure observation으로 변환할 수 있습니다.
- `--fixture-capture`는 네트워크 없이 live mode와 같은 adapter와 ledger validator를 재생합니다.

## Outcome maturity

- Horizon 이전 outcome은 terminal result가 아니라 `immature` attempt입니다.
- 성공 outcome은 supplied price panel의 canonical SHA와 source provenance를 검증합니다.
- Missing ticker와 partial coverage는 terminal result 대신 attempt에 보존합니다.
- Gross market return과 transaction cost를 포함한 realized return을 분리하고 realized volatility, drawdown, risk forecast error/MAE/ratio를 기록합니다.
- Complete observation과 연결된 mature outcome만 campaign 평가에 포함합니다.
- 모든 결과는 `production_auto_promotion=false`, `manual_review_only=true`입니다.

## 주요 변경 파일

- `src/backend/portfolio_optimization.py`: optimizer input price hash/provenance와 opt-in observation covariance context
- `src/backend/production_baseline_observation.py`: live/fixture 공용 production baseline adapter
- `src/backend/shadow_forward.py`: contract v2 strict 재계산, semantic duplicate, outcome hash/cost/maturity
- `tools/shadow_forward.py`: baseline-only `collect-baseline` command
- `tests/test_production_baseline_observation.py`, `tests/fixtures/shadow_forward/`: dependency-injected/offline 회귀
- `tests/test_portfolio_backtest.py`: production GMV 결과 보존 회귀
- `docs/01-folder-architecture.md`, `docs/02-specs.md`, `docs/03-product-plan.md`: 현재 운영 정책

## 검증

- Targeted backend: `130 passed in 23.93s`
- 전체 backend: `441 passed in 102.58s`
- CLI help와 offline `collect-baseline` smoke: observation 1개 recorded
- Shadow ledger integrity: campaign 1, observation 1, outcome/attempt 0, hash chain `ok`
- `git diff --check`: 통과
- Frontend 변경 없음: lint, Vitest, build 미실행

## 제한 및 비범위

- Licensed delisted-inclusive PIT 개별주 자료 부재는 accepted product limitation으로 유지합니다.
- 새 alpha/risk/execution candidate, Transformer, forecast model, covariance estimator와 optimizer family를 추가하지 않았습니다.
- Consumed DOW/Nasdaq/French split을 재사용하거나 historical backtest를 추가 탐색하지 않았습니다.
- 기존 gate, 과거 연구 보고서와 실패 기록을 수정하지 않았습니다.
- 실제 미래 observation/outcome이 누적되기 전에는 성과 검증 또는 승격 근거가 아닙니다.
- Scheduler 등록, 자동 주문과 production 자동 승격은 구현하지 않았습니다. Scheduler는 같은 one-shot CLI를 호출해야 합니다.
