# CSV 기반 포트폴리오 전략 비교 기능

- 일시: 2026-11-12 18:17 KST
- 에이전트: Codex
- 작업 유형: 기능 추가

## 제공 범위

기존 벤치마크의 고정 비중 보유 모드를 유지하고 `전략 백테스트` 모드를 추가했다.
`ticker` 열의 CSV에서 시작 시점의 유효 학습 자료를 가진 공통 후보 풀을 확정하고
GMV, production 직접 Transformer 예측을 넣은 MPT, GMV+고정 2.5% rank overlay를
비교한다. 마지막 전략은 실험으로 표시하며 자동 승격/종합 우승 판정은 없다.

CSV 검증/중복 제거, 평가 날짜, 학습 기간, 재조정 간격, 독립 예측 horizon,
초기 자금, 최대 목표 비중, 비용, 밴드, 총 회전율 제한, 무위험 수익률을 설정한다.
실행 전 작업량을 확인하고 기존 optimization job 진행률/취소/상태 조회와
브라우저 저장 job ID를 재사용한다. 완료 결과는 `backtest_` prefix로 보존하며
일반 포트폴리오 목록과 구분해 조회/JSON 다운로드한다.

결과는 비용 후 자산·낙폭 곡선, CAGR·변동성·Sharpe·최대낙폭·회전율·비용과
재조정별 예측/학습 종료일/실행 비중/이후 수익률/fallback 기록을 제공한다.
영어·한국어 문구를 함께 추가했다.

## 계산 및 방어 조건

- 기존 `run_portfolio_model_backtest`의 비용·현금·밴드·회전율 회계를 재사용한다.
- 같은 origin의 동일 예측을 MPT와 overlay가 공유한다. 모델 확대/HPO는 없다.
- 학습 입력은 재조정일 전까지다. 시작 시점의 자료 부족 종목은 공통 제외 내역에 기록한다.
- 평가 중 결측/비정상 가격은 사후 종목 삭제 대신 실패 처리한다. 기존 데이터 수집기에
  `preserve_missing` opt-in과 별도 raw cache key를 추가해 자동 ffill을 우회한다.
  다른 조회의 기존 ffill 동작과 기존 cache namespace는 유지한다.
- 요청 범위에서 가격 시작/끝이 7일 넘게 어긋나면 실패한다. 실제 평가 날짜를 반환한다.
- 가격은 기존 FX helper로 USD 정규화한다. 환산 불가 시 실패한다.
- 예측이 없으면 해당 origin의 모델 전략은 GMV로 대체하고 명시한다. MPT solver
  실패도 기록한다. 연구용 일반 성과 게이트를 통과했다고 주장하지 않는다.
- 최초 비용을 실제 최초 거래일에 일수익률로 반영하고 복리가 엔진 순자산/summary와
  일치하는지 검산한다. 공통 엔진 export TODO는 별도로 유지한다.
- 백테스트 엔진에 optional cancel_event만 추가해 실행 중 재조정 사이에도 취소한다.
- CSV 1MB/500종목, 예상 50,000 forecast, 동시 비교 작업 1개로 제한한다.

## 검증

- 백테스트·엔진 focused: 102 passed (34.69s).
- 최종 CSV/백테스트/데이터 수집 focused: 35 passed (1.06s).
- 프론트엔드 전체: 38 passed (6.12s).
- ESLint 통과, production build 통과 (19.66s). 기존 Plotly chunk 크기 경고가 남는다.
- 실제 브라우저에서 CSV → preview → background job → 결과 곡선/성과 표를 확인했다.
  가격·예측은 격리된 synthetic fixture, 최적화/거래/결과 저장/API는 실제 구현이다.
  이 검사는 실데이터 예측력이나 투자 성과 검증이 아니다.
- 미래 평가 가격 변경이 최초 학습 입력/목표에 영향을 주지 않음, 공통 달력,
  최초 비용/순자산/낙폭 일치, no-view 동일 GMV 대체, 취소, 저장 후 재조회,
  raw 결측 보존 및 분리 cache key를 테스트했다.
- `git diff --check` 통과.
- 최종 전체 검증 완료: frontend 38 passed, lint/build exit 0, backend 557 passed (368.18s), 전체 exit 0. `logs/strategy-backtest-20261112/verification.log`,
  `verification.status`, `verification-checks.json`에 실제 결과를 기록한다.

## 운영 및 한계

- 기존 사용자 서버를 재시작하지 않았다. 새 API를 사용하려면 백엔드 재시작이 필요하다.
- 확인용 5019/5179 임시 서버는 종료했다. 기존 5000 포트 서버는 변경하지 않았다.
- CSV 고정 종목군은 역사적 상장 전체나 생존편향 제거를 보장하지 않는다.
- 공개 조정 가격·이론적 종가 체결이며 실거래/장시간 부하/대규모 500종목 ML 실행은 미검증이다.
- 가격 CSV 업로드, 자동 파라미터 탐색, 실제 주문 실행은 제외했다.
- 기존 미커밋 BL 연구 및 Yahoo session 수정은 보존했으며 커밋/푸시는 하지 않았다.
