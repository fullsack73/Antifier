# TODO 구현과 선행조건 점검

## 구현

- 후보 진행 분모를 단계별 실제 집합으로 수정. 초기/전체 지도와 부분 현재 예측,
  전체 풀, 신규 계산/캐시 적중을 분리. 재사용 완료 이벤트와 한영 표시 추가.
- 일수익률은 기존 관측 달력을 유지하며 첫 구간을 최초 자금에 연결. 전략 비교는 합산된 첫 구간을 최초 비용일/다음날로 분리해 중복 차감 방지,
  이전 export 비교 도구의 조건부 보정은 새 계약 표시가 없을 때만 유지.
- 백테스트 설정을 평가 기간/학습 일정/자금·거래 조건으로 구분. 기존 색상과
  컴포넌트를 유지하고 중복 CSS 정리, 비활성 상태와 폼/표/진행률 접근성 개선.

## 검증

- 관련 pytest 168개 통과. lint/Vitest 48개/build 통과.
- 브라우저 390/1440px에서 실행 전, 작업량 미리보기, 진행, 실패, 완료 fixture를 렌더링.
  한영 실행 전 화면과 가로 넘침 없음, 40/40과 전체 풀457·신규5·캐시35 표시 확인.
  실행 중 백테스트/서버는 중단하거나 재시작하지 않음.
- 로그와 화면: `logs/todo-completion-20261115/`.
- 첫 전체 검증은 관측 수를 늘리는 변경을 감지해 616통과/1실패. 관측 수를
  보존하도록 수정 후 관련 153개 통과. 최종 전체 backend 618개 통과(109.76초), 종료 코드 0.

## 남은 선행조건

- Factor hedge: versioned PIT exposure dataset 및 hedge instrument 정책 없음.
- PIT liquidity: 기존 Yahoo OHLCV는 있으나 corporate-action/누락22종목 정책,
  notional·participation 계약과 impact calibration·coverage gate가 미확정.
- Soft constraints: penalty 단위 정규화·calibration dataset·tie-breaking 계약 미확정.
- Exact cardinality: 재배포 solver·세 OS build·runtime/fallback 정책 미검증.
- 예측 진단: 기존 210분 예산 종료. 7개 원래 task ID 보존. 추가 예산과
  독립 후속 계약 없이 source drift를 우회하거나 원본 campaign을 수정하지 않음.
- Calendar forward: 2026-11-15 기준 첫 시작일 이후 평일만 세어도 공통 수익 관측은
  최대54개로 최초63개 milestone 미성숙. 252개 완료 조건까지 TODO 유지.

과거 연구를 재채점하거나 production 전략을 승격하지 않는다.

## 완료 정리

`backtest-ui-taste-redesign.md`, `candidate-search-progress-denominator.md`,
`backtest-daily-initial-cost.md`는 구현·관련 회귀 검증 완료로 삭제하고 인덱스에서 제거했다.
나머지 6개 TODO에는 확인한 선행조건을 추가했다.
