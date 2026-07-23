# TODO - Portfolio Alpha v2 Research

- 등록 일시: 2026-07-23 18:24 (KST)
- 작성자: Codex
- 에이전트: Codex
- 진행 시점: point-in-time factor/fundamental 데이터와 validation과 분리된 research universe를 확보한 뒤
- 현재 상태: v2 코드 기반 완료, 실제 PIT dataset/research universe 확보와 objective 비교 대기

> 완료된 TODO는 이 파일을 삭제하고, `docs/reports/`에 작업 기록을 남깁니다.

## 배경

- `adaptive_signal_tilt` v1은 signal/construction/execution 분리 진단과 relative-return IC calibration을 구현했지만 live validation에서 0/4로 탈락했습니다.
- construction은 약 19.5~20% active share와 signal-weight rank correlation 1.0을 유지했고 execution도 평균 신호의 약 84~105%를 보존했습니다.
- 실패 원인은 4개 validation case 중 3개에서 평균 cross-sectional rank IC와 top-minus-bottom spread가 음수였던 signal layer입니다.
- rolling positive-IC weighting이 적은 관측에서 reversal 같은 단일 component에 집중되는 구조적 불안정성도 관찰됐습니다.
- 이 결과는 validation 후보 기각에만 사용하며 같은 4개 case에 맞춘 feature/weight 재튜닝에는 사용하지 않습니다.
- 2024-2025 locked holdout은 실행하지 않아 잠금 상태를 유지했습니다.

## 목표

- validation과 겹치지 않는 research/train universe와 기간을 먼저 확정합니다.
- 단순 cross-sectional median 제거를 넘어 market beta, sector, size 등 공통요인을 제거한 forward residual return을 target으로 사용합니다.
- point-in-time quality/profitability, valuation, liquidity feature를 survivorship/look-ahead 없이 결합합니다.
- component weight는 research split에서 regularization, weight cap, minimum observation gate를 적용해 단일 신호 집중을 방지합니다.
- pairwise/listwise ranking objective와 단순 regularized linear baseline을 복잡도 순으로 비교합니다.

## 검증 순서

1. research/train 내부 walk-forward에서 feature와 calibration 방식을 선택합니다.
2. 고정된 4-case validation은 선택된 단일 후보에만 실행합니다.
3. validation 통과 후보만 standard sensitivity gauntlet으로 보냅니다.
4. 모든 gate를 통과한 단일 후보에만 `--gauntlet-preset holdout`을 최종 1회 실행합니다.

## 산출물

- point-in-time dataset provenance와 survivorship 정책
- factor-residual target과 no-lookahead 회귀 테스트
- regularized component/ranking model 비교 보고서
- 새 cache namespace와 candidate validation 기록
- 통과 시에만 standard 및 locked-holdout 결과

## 2026-07-23 진행

- `factor_neutral_alpha_tilt` research-only 후보와 PIT long-table 계약을 구현했습니다.
- `available_date` 기준 snapshot, beta/sector/log-size residual target, ridge regularization, feature weight cap, minimum observation gate를 구현했습니다.
- CLI에 `--factor-data`, `--factor-provenance`와 `factor-neutral-alpha-v2-*` namespace를 추가했습니다.
- synthetic no-lookahead/미래 fundamental 격리 회귀 테스트를 추가했습니다.
- 실제 PIT dataset과 validation 비중복 research universe가 없어 pairwise/listwise 비교와 candidate validation은 실행하지 않았습니다.
- locked holdout은 계속 잠금 상태입니다.

## 참고

- v1 완료 보고서: `docs/reports/260723-1824-01-portfolio-alpha-redesign.md`
- v1 validation 결과: `logs/portfolio_gauntlet_candidate_adaptive_20260723.json`
- v2 기반 보고서: `docs/reports/260723-1921-01-portfolio-alpha-v2-foundation.md`
