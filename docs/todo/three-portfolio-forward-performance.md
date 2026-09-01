# TODO - 세 포트폴리오 calendar-forward 성과 검증

- 등록 일시: 2026-08-30 18:25 (Asia/Seoul)
- 작성자: 사용자 요청 기반
- 에이전트: Codex
- 진행 시점: 2026-08-30 구성 이후 63/126/252개의 공통 일별 수익 관측이 성숙할 때

## 목표

- `tests/portfolios/`의 LLM 단독, production GMV, 뉴스 기반 LLM 보정 GMV를 구성 이후 데이터만으로 비교합니다.
- 2026-08-30 이전 자료로 계산한 후향적 결과와 진짜 out-of-sample 성과를 분리합니다.

## 요구사항

- 세 입력 JSON과 그 SHA-256을 고정하고 관찰 중 비중, 종목, 현금 비중을 변경하지 않습니다.
- 시작점은 구성 이후 첫 공통 거래일의 조정 종가로 두고 63/126/252 공통 일별 수익 관측이 성숙할 때만 중간 평가합니다.
- USD 조정 종가, 동일 데이터 공급자, buy-and-hold, 무리밸런싱, fractional unit을 공통 적용합니다.
- LLM 단독의 미배분 10%는 현금으로 보존하고 구성 시점 입력과 같은 연 3.5% 수익률을 적용합니다.
- 총수익률, CAGR, 연율 변동성, Sharpe, 최대낙폭을 계산하고 21일 paired circular block bootstrap으로 GMV 대비 차이를 평가합니다.
- 뉴스 보정 포트폴리오에는 뉴스 원문/식별자, 공개 시각, 수집 시각, digest와 LLM 모델·prompt/config provenance를 추가합니다. 이를 복원할 수 없으면 `news-adjusted` 결과를 비재현 diagnostic으로 명시합니다.
- 95% gate를 통과해도 자동 승격이나 투자 판단을 수행하지 않습니다.

## 작업 요약

- 2026-08-30 현재 구성 이후 공통 거래 관측은 0개입니다.
- 현재 보고서는 2021-08-30~2026-08-28의 후향적/in-sample 비교만 완료했습니다.
- 세 입력 weight와 SHA-256, 현금, 평가 milestone, bootstrap 설정을 `data/research/derived/three_portfolio_forward_spec_v1.json`에 고정했습니다.
- `tools/three_portfolio_forward.py`는 spec/input drift를 거부하고 dependency-free Yahoo chart v8 live 경로 또는 offline CSV로 같은 평가를 실행합니다.
- 뉴스 provenance는 복원할 수 없어 사양과 모든 결과에서 `non_reproducible_diagnostic`으로 고정했습니다.
- 매주 화요일 09:00 KST에 같은 task를 재개하는 heartbeat `forward`를 등록했습니다. 252개 수익 관측과 전체 검증 전에는 이 TODO를 삭제하지 않습니다.

## 선행조건

- 각 milestone의 공통 거래일 조정 종가가 모두 성숙할 것
- 고정 입력 JSON과 뉴스 provenance를 변경 불가능한 형태로 보존할 것

## 참고

- 관련 문서: `docs/02-specs.md`, `docs/03-product-plan.md`, `docs/reports/260830-1825-01-three-portfolio-performance.md`, `docs/reports/260830-1844-02-three-portfolio-forward-foundation.md`
- todo-list 한 줄 요약: 2026-08-30에 고정한 LLM 단독, GMV, 뉴스 보정 GMV를 63/126/252 공통 거래일에 calendar-forward로 재평가합니다.
