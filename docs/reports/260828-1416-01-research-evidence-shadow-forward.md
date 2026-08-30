# Research Evidence and Calendar-Forward Shadow Foundation

- 작업 일시: 2026-08-28 14:16 KST
- 범위: 포트폴리오 연구 증거 정책, consumed split 차단, append-only shadow 기반
- 결론: production `MIN_VARIANCE + RISK_ONLY` 유지, 미래 성과 검증 주장은 아직 없음

## 결정

- Licensed CRSP/CCM 수준의 delisted-inclusive PIT 개별주 자료 부재를 accepted product limitation으로 고정했습니다. 이를 blocker나 반복 TODO로 남기지 않습니다.
- 공개 Yahoo OHLCV와 dated Nasdaq membership을 사용하는 개별주 alpha는 experimental입니다. SEC filing date는 covered fundamental availability만 PIT이며 완전한 historical universe/price identity를 보장하지 않습니다. French industry portfolio는 aggregate portfolio evidence입니다.
- Production 기본값은 Ledoit-Wolf global minimum variance와 effective `RISK_ONLY`를 그대로 유지했습니다. 새 Transformer, forecast model, covariance estimator 또는 optimizer candidate를 추가하지 않았습니다.

## 구현

- `data/research/research_policy_v1.json`
  - production/experimental/unavailable evidence scope
  - alpha/risk/execution lane별 primary endpoint, guard, stop rule
  - shadow automatic promotion 금지
- `research_split.py`, `data/research/evidence_consumption_v1.jsonl`
  - schema v2 policy/candidate/dataset hash
  - DOW, Nasdaq, French 대표 split 8개의 consumed hash-chain 기록
  - consumed split과 같은 lineage의 겹치는 구간을 selection/tuning/validation/promotion에 재사용하지 못하도록 차단
  - acknowledged diagnostic/reproduction만 허용하고 promotion 불가
- `shadow_forward.py`, `tools/shadow_forward.py`
  - campaign 생성 이후 as-of만 허용하는 SQLite ledger
  - UPDATE/DELETE trigger, payload SHA, append chain, duplicate/conflict/backfill 차단
  - as-of universe/provenance/coverage/failure와 production baseline signal/weight/risk/execution 기록
  - baseline-only campaign candidate injection 거부
  - horizon maturity 전 realized outcome 사용 금지, failure/partial attempt 별도 기록
  - mature-only descriptive evaluation과 `production_auto_promotion=false`
- `tools/manage_research_evidence.py`
  - policy/registry audit, consumption append, evidence-use 검사

## Gate 해석

- Alpha: 기존 completed-OOS IC/spread 95% bootstrap와 Holm gate를 유지하며 실패 시 portfolio construction을 열지 않습니다.
- Risk: primary endpoint를 사전 고정하고, Sharpe는 superiority, 비-primary risk/calibration·turnover·concentration은 prospective non-inferiority guard로 분리했습니다. 과거 결과에 맞춘 threshold/margin 변경이나 재채점은 하지 않았습니다.
- Execution/correctness: cash, cost, turnover, constraint, price coverage 항등식만 검증하며 alpha 개선으로 표현하지 않습니다.

## 검증

- 신규 split/shadow fixture 및 CLI: `19 passed`
- production statistics/backtest/risk/API constraint 회귀: `184 passed`
- 전체 backend: `431 passed in 99.14s`
- evidence registry audit: consumed split 8개, hash chain 정상
- 프론트엔드 변경 없음: lint/Vitest/build 미실행

## 현재 제한

- 실제 campaign 이후 미래 observation이 아직 누적되지 않았으므로 calendar-forward 성과가 검증됐다고 주장하지 않습니다.
- 현재 승격 가능한 alpha candidate가 없어 production baseline campaign만 지원·검증했습니다. Candidate는 campaign 생성 전에 별도 사양으로 등록해야 하며 기존 baseline campaign에 소급 추가할 수 없습니다.
- 기존 historical 보고서와 실패 기록은 수정하거나 삭제하지 않았습니다.
