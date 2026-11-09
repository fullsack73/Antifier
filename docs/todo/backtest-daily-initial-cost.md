# 공통 백테스트 일수익률 export의 최초 비용 일치

- 발견: 2026-11-09 세 포트폴리오 비교 최종 회계 검산
- 근거: `docs/reports/261109-2034-01-improved-forecast-three-portfolios.md`

`src/backend/portfolio_backtest.py`의 `run_portfolio_model_backtest`에서
summary 순자산/수익률은 초기 비용을 포함하지만 `include_daily_returns`의
export는 비용 후 첫 자산값을 기준으로 pct_change해 최초 거래비용을 제외한다.

공유 export를 수정할 때 모든 호출자와 통계 도구를 확인하고, 일수익률 복리가
summary 순자산 변화와 일치하는 회귀를 추가한다. 이미 비용을 별도로 보정하는
도구에서 이중 차감되지 않게 한다. 초기 현금/고정비중/GMV/ML target을 포함한다.
과거 consumed 연구를 소급 재채점해 후보 선택이나 승격 근거로 사용하지 않는다.

현재 `tools/compare_improved_forecast_portfolios.py`는 자체 검산/조건부 보정을
적용해 이 비교의 일수익률과 순자산을 일치시킨다. Production engine 변경은
이번 세 포트폴리오 비교 범위에서 수행하지 않았다.
