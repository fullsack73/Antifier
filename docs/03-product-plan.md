# 3) 제품 기획안

본 문서는 Antifier의 제품 범위, 사용자, 핵심 기능, 현재 로드맵을 정리합니다.

## A. 서비스 개요

Antifier는 개인 투자자, 트레이더, 금융 분석가가 주식 데이터 분석, 예측, 재무제표 확인, 포트폴리오 최적화를 한 곳에서 수행하도록 돕는 금융 분석 웹앱입니다. 이름은 소액 개인 투자자를 뜻하는 한국어 표현인 "개미"에서 출발했습니다.

Antifier는 투자 판단을 자동으로 대신하는 서비스가 아니라 데이터 기반 의사결정을 지원하는 분석 도구입니다.

## B. 대상 사용자

- 개인 투자자: 여러 종목의 가격, 추세, 재무 지표를 빠르게 비교하고 싶은 사용자
- 활동적인 트레이더: 단기 기회 탐색을 위해 차트, 회귀, 예측, pairs/correlation 분석이 필요한 사용자
- 금융 분석가/학습자: 포트폴리오 이론, forecast strategy, 재무제표 지표를 실험하고 검증하려는 사용자

대표 문제:

- 데이터 수집, 차트 작성, 회귀/예측, 재무제표 확인, 포트폴리오 계산이 여러 도구에 흩어져 있음
- 반복 분석이 수동으로 이루어져 시간이 오래 걸리고 일관성이 떨어짐
- 모델 선택, 수익률 가정, 포트폴리오 제약을 한 화면에서 실험하기 어려움

제품 해법:

- 주식 시각화부터 forecast, screening, pairs/correlation analysis, benchmark, portfolio optimization까지 한 SPA 안에서 연결합니다.
- 자동 계산을 제공하되 모델/기간/위험 가정은 사용자가 조정하도록 유지합니다.

## C. 앱 구성

현재 UI는 외부 라우터 없이 sidebar/view state 기반으로 주요 화면을 전환합니다.

- Stock Analysis: ticker, 기간, 모델, forecast horizon을 선택하고 가격/회귀/미래 예측 차트를 확인
- Pairs Analysis: 두 종목의 상관관계와 회귀 기반 관계 분석
- Financial Statement: ticker별 주요 재무 지표, Finviz/yfinance benchmark 비교, 규칙 기반 투자 신호, 점수화 결과를 대시보드로 확인하고 전체 재무제표는 팝업에서 확인
- Optimizer: MPT 또는 Black-Litterman 기반 포트폴리오 최적화
- Benchmark: 포트폴리오 성과를 S&P 500과 risk-free asset 기준으로 비교
- Portfolio Manager: 현재 보유 종목과 현금 주입을 바탕으로 리밸런싱 주문 계산
- Stock Screener: predefined universe와 filter 조건을 기반으로 종목 탐색
- Language Selector: 영어/한국어 UI 전환

## D. 구현 완료 범위

- 인터랙티브 주가 차트와 기간 선택
- LSTM, LightGBM, ARIMA, ARIMA + Transformer, Transformer, lightweight ensemble 계열 forecast/회귀 흐름
- 미래 가격 예측과 Monte Carlo 스타일 future prediction 응답
- 재무제표, 주요 재무 지표, 규칙 기반 투자 신호 대시보드 조회
- Financial Statement 종합 점수와 predefined ticker universe 기반 screening
- MPT/Black-Litterman 포트폴리오 최적화
- forecast method 선택과 expected return 기반 optimization
- rolling rebalance portfolio backtest CLI와 risk parity, 6-month momentum, low-volatility, market-cap, standalone 12-1 momentum, signal-stack baseline을 포함한 보수적 model promotion gate
- signal/portfolio construction/execution을 분리하는 alpha diagnostics와 training-window IC calibration 기반 `adaptive_signal_tilt` research candidate
- point-in-time factor 입력 계약, beta/sector/size residual target, regularized/capped coefficient를 사용하는 research-only `factor_neutral_alpha_tilt` 기반 구조
- Transformer clip 전후 출력, forecast 분포/tie, OOS uncertainty와 signal-only gate를 분리 진단하는 forecast research 기반 구조
- ticker별 재학습 없이 absolute/relative/pairwise/listwise objective를 비교하는 pooled cross-sectional walk-forward baseline
- SEC filing-date PIT fundamental loader와 날짜별 universe membership을 적용하는 survivorship-safe research data foundation
- shrinkage/nested covariance conditioning, exact equal-risk-contribution, hierarchical risk parity, regime/minimum-CVaR, completed-feedback online allocator ensemble과 capped-simplex 제약을 검증하는 risk allocator research 경로
- point-in-time market-cap enforcement, no-lookahead price/FX alignment, paired block bootstrap와 Holm multiple-testing correction을 포함한 quant-standard validation guardrail
- candidate 4-case validation 후 standard 180-case와 별도 2024-2025 locked holdout으로 이어지는 staged gauntlet, basket/regime별 target 재사용, SQLite forecast cache, case checkpoint/resume
- 최적화 진행률 SSE stream, 화면 이동/새로고침 후 job 재연결, 명시 취소
- 저장된 portfolio result 조회
- 포트폴리오 benchmark와 리밸런싱 계산
- pairs/correlation/regression 분석
- 영어/한국어 국제화
- PyInstaller 기반 installer build와 GitHub Actions CI

## E. 핵심 요구사항

### 1. Stock Analysis

- ticker는 안전한 문자 집합으로 제한합니다.
- 날짜 범위는 미래 종료일을 허용하지 않고 시작일이 종료일보다 앞서야 합니다.
- chart는 historical price, regression, future prediction을 분리해 보여줍니다.
- 통화 변환이 발생하면 원 통화와 표시 통화를 UI/응답에 드러냅니다.

### 2. Portfolio Optimization

- 사용자는 ticker group 또는 개별 ticker를 입력할 수 있어야 합니다.
- forecast method는 historical CAGR, lightweight ensemble, ARIMA + Transformer, Transformer 등 기존 선택지를 유지합니다.
- ARIMA + Transformer와 Transformer가 유효한 forecast를 만들지 못하면 임의의 양의 기대수익률을 넣지 않고 no-view로 처리해 prior-only view가 되도록 합니다.
- forecast 모델 기본값 변경은 거래비용과 turnover control을 포함한 walk-forward backtest에서 equal weight, minimum variance, historical BL/MPT, inverse-vol risk parity, 6-month momentum, low-volatility tilt, market-cap weight(가능한 경우), standalone 12-1 momentum, momentum BL, signal-stack BL baseline을 이긴 경우에만 검토합니다.
- ARIMA + Transformer와 Transformer는 portfolio promotion gauntlet에서 직접 기대수익률 입력이 아니라 weak rank feature 모델로만 경쟁합니다.
- research candidate는 raw signal, component weight, realized forward return, target/control weight, 비용 전후 성과를 기록하고 평균 rank IC와 top-minus-bottom spread가 양수인 경우에만 portfolio 성과 gate를 검토합니다.
- validation에 사용한 basket/regime 결과로 같은 후보를 재튜닝하지 않으며, validation과 standard를 통과한 단일 후보만 별도 locked holdout을 최종 1회 실행합니다.
- Portfolio Manager는 v1에서 UI 변경 없이 기본 `rebalance_band=0.02`, `max_turnover=0.35`를 적용해 미세 거래와 과도한 회전율을 줄입니다.
- 데이터 길이가 부족하거나 결측치가 많은 ticker는 명확한 처리 정책을 가져야 합니다.
- 결과는 저장/조회 가능해야 하고, 진행률은 SSE로 확인 가능해야 합니다.
- 장시간 최적화는 페이지를 떠났다가 돌아와도 진행률 또는 완료 결과를 복구할 수 있어야 합니다.
- 사용자는 실행 중인 최적화를 명시적으로 취소할 수 있어야 하며, 클라이언트가 닫혀 장시간 재연결되지 않는 job은 backend가 협력적으로 중단해야 합니다.

### 3. Screening / Financial Statement

- predefined universe는 CSV와 helper 모듈을 통해 관리합니다.
- Stock Screener의 기본 검색 기준은 Financial Statement 대시보드와 같은 0-100 종합 점수이며, raw 재무 지표가 비어 있거나 외부 데이터 호출이 실패해도 방어적으로 처리해야 합니다.
- Financial Statement의 STRONG BUY/BUY/HOLD 등 신호는 데이터 기반 분석 보조 신호이며 투자 자문이나 자동 매매 지시로 표현하지 않습니다.
- 업종/섹터 평균 비교는 Finviz group valuation의 산업 평균을 우선 사용하고, Finviz가 제공하지 않는 수익성/성장성/안정성/위험 지표는 yfinance 기반 산업별 대표 대형주 단순 평균으로 보완합니다.
- Finviz 산업/섹터 평균을 찾지 못하면 yfinance 기반 산업별 대표 대형주 단순 평균을 전체 benchmark fallback으로 사용합니다.
- 산업별 대표 ticker dataset이 없는 경우에는 섹터 대표 대형주 단순 평균을 마지막 benchmark fallback으로 사용합니다.
- 해외 종목의 Financial Statement 대시보드는 가격/주당 재무 값과 시가총액을 USD 기준으로 정규화하고, 원 통화와 표시 통화를 함께 보여줍니다.
- 비교 benchmark를 만들 수 없는 경우에는 절대 기준 점수화임을 UI에 명확히 표시합니다.
- custom CSV universe 지원은 TODO로 추적 중입니다.

### 4. Portfolio Management / Benchmark

- 현재 보유 수량, 현금 주입, 목표 weight를 바탕으로 리밸런싱 주문을 계산합니다.
- fractional share 허용 여부와 ticker별 예외를 고려합니다.
- benchmark는 동일한 기간과 통화 기준으로 비교해야 합니다.

## F. 다음 우선순위

현재 로드맵과 TODO 기준 우선순위:

- point-in-time/factor-neutral research data로 cross-sectional alpha v2를 설계하고 새 candidate가 4-case validation을 통과한 경우에만 standard와 locked holdout을 재개
- Stock Screener custom CSV universe 지원
- 회귀/forecast 모델 선택 UX와 LSTM 사용 의도 재검토
- 사용자 인증과 저장된 portfolio/watchlist/screening criteria
- 실시간 또는 준실시간 가격 데이터 연동
- alert/notification system
- RSI, MACD, Bollinger Bands, Moving Average 등 technical indicator 확장

## G. 비범위

- 매수/매도 추천을 단정적으로 제공하지 않습니다.
- 수익률 보장, 투자 자문, 자동 주문 실행은 현재 범위가 아닙니다.
- 계좌 연동, 실거래 broker API, 결제/구독 시스템은 현재 범위가 아닙니다.
- 대규모 멀티테넌트 서버 배포와 사용자별 데이터베이스 운영은 인증/저장 기능 결정 전까지 범위 밖입니다.
