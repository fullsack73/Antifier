# 3) 제품 기획안

본 문서는 Antifier의 제품 범위, 사용자, 핵심 기능, 현재 로드맵을 정리합니다.

Transformer·ARIMA·동일가중 혼합 예측의 실패 원인은 별도 offline diagnostic
campaign으로 조사합니다. 합성 대조군과 시간 정보/직접 예측/학습량/입력 정보의
통제 실험 결과를 구분하며, 소비된 과거 데이터의 개선을 새 alpha 검증이나
production 승격으로 해석하지 않습니다.

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
- Financial Statement: ticker별 주요 재무 지표, Finviz/yfinance benchmark 비교, 규칙 기반 건전성·저평가 평가, 점수화 결과를 대시보드로 확인하고 전체 재무제표는 팝업에서 확인
- Optimizer: MPT 또는 Black-Litterman 기반 포트폴리오 최적화
- Benchmark: 포트폴리오 성과를 S&P 500과 risk-free asset 기준으로 비교
- Portfolio Manager: 현재 보유 종목과 현금 주입을 바탕으로 리밸런싱 주문 계산
- Stock Screener: predefined universe와 filter 조건을 기반으로 종목 탐색
- Language Selector: 영어/한국어 UI 전환

## D. 구현 완료 범위

- 인터랙티브 주가 차트와 기간 선택
- LSTM, LightGBM, ARIMA, ARIMA + Transformer, Transformer, lightweight ensemble 계열 forecast/회귀 흐름
- 미래 가격 예측과 Monte Carlo 스타일 future prediction 응답
- 사용자 요청으로 Transformer 및 ARIMA+Transformer 서비스 경로에 직접 기간 예측 적용. GMV 기본값은 유지하며 production 수익률 일반화 승격과는 구분
- 재무제표, 주요 재무 지표, 규칙 기반 건전성·저평가 평가 대시보드 조회
- Financial Statement 종합 점수와 predefined ticker universe 기반 screening
- Ledoit-Wolf global minimum-variance 기본 최적화와 opt-in MPT/Black-Litterman
- 종목별 및 sector/industry/country별 최소·최대 비중 hard constraint, 사전 feasibility 검사, 구조화된 오류
- 최종 실행 weight 기준 risk contribution, 집중도, covariance, 분류 exposure와 constraint slack 진단
- forecast method 선택과 expected return 기반 optimization
- rolling rebalance portfolio backtest CLI와 risk parity, 6-month momentum, low-volatility, market-cap, standalone 12-1 momentum, signal-stack baseline을 포함한 보수적 model promotion gate
- signal/portfolio construction/execution을 분리하는 alpha diagnostics와 training-window IC calibration 기반 `adaptive_signal_tilt` research candidate
- point-in-time factor 입력 계약, beta/sector/size residual target, regularized/capped coefficient를 사용하는 research-only `factor_neutral_alpha_tilt` 기반 구조
- Transformer clip 전후 출력, forecast 분포/tie, OOS uncertainty와 signal-only gate를 분리 진단하는 forecast research 기반 구조
- ticker별 재학습 없이 absolute/relative/pairwise/listwise objective를 비교하는 pooled cross-sectional walk-forward baseline
- 명시적 position embedding, ordered OHLCV patch, direct 21/63일 target, optional frozen Kronos context와 completed-OOS GMV fallback을 사용하는 research-only pooled Patch Transformer 경로
- completed-OOS record만 사용하는 deterministic confidence gate와 gate 실패 시 exact-GMV fallback을 보장하는 research overlay
- 기존 ARIMA + Transformer를 21일 실현 변동성 변화 예측에 재사용하고 Ledoit-Wolf correlation과 결합하는 conditional-risk research 경로
- rolling FF3 exposure, shrinkage/EWMA factor covariance, shrinkage/floor specific risk와 exact Ledoit-Wolf fallback을 사용하는 research-only factor-model GMV 경로
- SEC filing-date PIT fundamental loader와 날짜별 universe membership을 적용하되, 공개 가격의 delisted coverage 한계를 숨기지 않는 experimental research foundation
- shrinkage/nested covariance conditioning, exact equal-risk-contribution, hierarchical risk parity, regime/minimum-CVaR, completed-feedback online allocator ensemble과 capped-simplex 제약을 검증하는 risk allocator research 경로
- point-in-time market-cap enforcement, no-lookahead price/FX alignment, paired block bootstrap와 Holm multiple-testing correction을 포함한 quant-standard validation guardrail
- candidate 4-case validation 후 standard 180-case와 별도 2024-2025 locked holdout으로 이어지는 staged gauntlet, basket/regime별 target 재사용, SQLite forecast cache, case checkpoint/resume
- 2019-2025 French 12-industry fresh research에서 pooled relative-return 후보와 conditional-volatility GMV가 각각 signal/risk gate를 통과하지 못해 production Ledoit-Wolf GMV를 유지한 검증 기록
- 이미 소비된 동일 French 12-industry origin의 FF3 factor-risk smoke에서 변동성은 13.1933%에서 12.9661%로 낮아졌지만 paired 95%/Holm gate를 통과하지 못했고 fresh validation도 아니므로 production Ledoit-Wolf GMV를 유지한 기록
- 동결 후 처음 개봉한 2012-2018 French 12-industry historical holdout의 완전한 63일 origin 27개에서 고정 FF3 factor-risk GMV가 변동성을 10.5515%에서 10.5426%로 0.89 bp만 낮추고 Sharpe와 paired 95%/Holm gate를 개선하지 못해 production Ledoit-Wolf GMV를 유지한 검증 기록
- 이미 소비된 Kronos 4-case origin diagnostic에서 pooled Patch Transformer가 rank IC는 개선했지만 tail-spread/paired 95% gate를 통과하지 못해 production Ledoit-Wolf GMV를 유지한 검증 기록
- 2024-2025 dated Nasdaq-100 membership/공개 OHLCV validation에서 frozen pooled Patch Transformer가 absolute 및 paired 95% signal gate를 통과하지 못해 GMV overlay를 실행하지 않고 production Ledoit-Wolf GMV를 유지한 검증 기록
- 같은 consumed origin에서 고정 gamma 2.5%의 GMV + Patch Transformer/Kronos alpha tilt가 수익률·Sharpe를 소폭 높였지만 변동성과 paired 95% gate를 개선하지 못해 diagnostic-only로 유지한 기록
- 동일 고정 gamma에서 Transformer 단독, ARIMA+Transformer, ARIMA 단독, Kronos/Patch 계열 6개 signal을 비교했으나 모두 plain GMV 대비 변동성이 증가하고 95% gate를 통과하지 못해 모델 선택을 보류한 기록
- 최적화 진행률 SSE stream, 화면 이동/새로고침 후 job 재연결, 명시 취소
- 저장된 portfolio result 조회
- production GMV 결과와 실제 가격 provenance를 strict calendar-forward observation으로 변환하는 baseline-only adapter, network-free fixture replay와 append-only correctness ledger
- 동일 최초 production GMV에서 buy-and-hold, immutable fixed-target rebalance, 63일 rolling reoptimization을 비교하는 additive shadow contract v3과 forward-only 사전등록 경로. 실제 future outcome 8개 전까지 `forward_pending`이며 자동 승격은 없음
- 2026-08-30에 고정한 LLM 단독, production GMV, 뉴스 보정 GMV의 입력 hash와 buy-and-hold 계약을 잠그고 구성 이후 63/126/252개 공통 일별 수익 관측만 평가하는 forward-only CLI. 뉴스 provenance 부재는 `non_reproducible_diagnostic`으로 유지하며 자동 승격은 없음
- 과거 세 포트폴리오는 GMV 학습 데이터가 끝난 2024-08-29 다음 거래일부터 소급 forward holdout으로 평가. 252일 및 2026-08-28까지의 설명용 결과에서 GMV가 수익률·Sharpe·낙폭 기준 우세했고 뉴스 보정 GMV와 LLM 단독 모두 paired 95% gate를 통과하지 못했으므로 production 변경은 없음
- 기존 equal weight, Ledoit-Wolf GMV, historical MPT/BL, risk parity, low-volatility를 동일 비용·turnover 조건으로 두 panel에서 재현 진단한 결과, GMV는 변동성과 risk forecast MAE가 가장 낮았지만 수익률·Sharpe·drawdown·turnover 우위는 일관되지 않아 risk-only production 목적만 재확인하고 승격·성과 주장은 하지 않은 기록
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
- Yahoo FX ticker는 quote currency 기준 원 환율을 기본 표시하고 정방향/역방향 통화쌍 전환을 제공합니다.

### 2. Portfolio Optimization

- 사용자는 ticker group 또는 개별 ticker를 입력할 수 있어야 합니다.
- 검증된 cross-sectional alpha가 없는 제한 데이터 환경의 production 기본값은 expected-return forecast를 사용하지 않는 Ledoit-Wolf global minimum variance입니다.
- Black-Litterman과 classic MPT max-Sharpe는 사용자가 명시적으로 선택할 수 있지만 기본값으로 사용하지 않습니다.
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
- Optimizer 고급 설정은 전체 종목 cap, L2, 최소 보유 비중, 종목별 override, 그룹별 최소/최대 비중을 제공하고, 현재 portfolio weight가 있을 때만 turnover penalty/band/cap을 활성화합니다. UI percent와 API decimal 단위를 혼동하지 않게 표시합니다.
- Portfolio Manager는 실제 보유 포트폴리오에 의미 있는 rebalance band, turnover cap, turnover penalty, 최소 보유 비중을 노출합니다.
- hard constraint는 최적화 solver와 threshold/turnover 이후 실제 반환 weight 모두에서 검증하며, 결과 UI는 충족, binding, metadata 부족, 계산 불가를 구분합니다.
- 그룹 제약은 현재 시점 yfinance 분류 coverage가 완전할 때만 지원합니다. point-in-time 분류가 없는 historical 실행에는 최신 분류를 소급 적용하지 않습니다.

### 2-1. Portfolio Research Evidence

- Licensed CRSP/CCM 수준의 delisted-inclusive PIT 개별주 자료를 현재 확보할 수 없다는 점은 accepted product limitation입니다. 이를 다음 연구의 blocker나 반복 TODO로 두지 않습니다.
- Production은 검증된 `MIN_VARIANCE + RISK_ONLY` Ledoit-Wolf GMV만 유지합니다. 공개 데이터 기반 개별주 alpha와 aggregate French portfolio 연구는 experimental이며 production alpha 일반화 근거가 아닙니다.
- Alpha, risk, execution/correctness는 서로 다른 primary endpoint와 stop rule을 사용합니다. Alpha signal gate 실패 시 overlay/allocator를 열지 않고, execution invariant 통과를 성과 개선으로 표현하지 않습니다.
- DOW, Nasdaq, French의 이미 확인한 split은 consumed registry로 추적하며 candidate 선택·튜닝·승격에 다시 사용하지 않습니다. 과거 보고서는 당시 결정 기록으로 그대로 보존합니다.
- Historical holdout 추가 탐색 대신 campaign 생성 이후만 기록할 수 있는 append-only calendar-forward shadow ledger를 축적합니다. 현재 승격 가능한 alpha candidate가 없으므로 production baseline부터 관측하며 자동 승격은 지원하지 않습니다.
- GMV 운용 정책 비교는 alpha나 새 optimizer 연구가 아니며, 같은 production GMV target을 유지·실행하는 방식만 비교합니다. Historical 성과를 추가 탐색하지 않고 forward mature observation만 paired 평가합니다.
- Baseline collection은 실제 production optimizer 결과에서 universe/data hash, explicit no-view, weight/cash, risk와 실행 회계를 파생합니다. Success/partial/network/data/calculation failure를 같은 one-shot CLI로 기록하고 raw notional·비용·wealth·constraint·coverage·deterministic rerun을 ledger에서 재검산합니다.
- 이 기능은 운영 관측과 correctness를 개선한 것이며 alpha, Sharpe 또는 calendar-forward 성과 개선을 검증한 결과가 아닙니다. 실제 미래 outcome이 성숙하기 전까지 baseline 평가는 descriptive/insufficient 상태입니다.

### 3. Screening / Financial Statement

- predefined universe는 CSV와 helper 모듈을 통해 관리합니다.
- Stock Screener의 기본 검색 기준은 Financial Statement 대시보드와 같은 0-100 종합 점수이며, raw 재무 지표가 비어 있거나 외부 데이터 호출이 실패해도 방어적으로 처리해야 합니다.
- Financial Statement는 건전성 60%와 저평가 정도 40%를 합산합니다. 매수·매도 대신 STRONG/FAVORABLE/MIXED/WEAK/VERY WEAK 평가 등급을 사용하며 수익률 예측으로 해석하지 않습니다.
- 업종/섹터 평균 비교는 Finviz group valuation의 산업 평균을 우선 사용하고, Finviz가 제공하지 않는 수익성/성장성/안정성/위험 지표는 yfinance 기반 산업별 대표 대형주 단순 평균으로 보완합니다.
- Finviz 산업/섹터 평균을 찾지 못하면 yfinance 기반 산업별 대표 대형주 단순 평균을 전체 benchmark fallback으로 사용합니다.
- 산업별 대표 ticker dataset이 없는 경우에는 섹터 대표 대형주 단순 평균을 마지막 benchmark fallback으로 사용합니다.
- 해외 종목의 Financial Statement 대시보드는 가격/주당 재무 값과 시가총액을 USD 기준으로 정규화하고, 원 통화와 표시 통화를 함께 보여줍니다.
- 비교 benchmark를 만들 수 없는 경우에는 절대 기준 점수화임을 UI에 명확히 표시합니다.
- custom CSV universe 지원은 TODO로 추적 중입니다.

### 4. Portfolio Management / Benchmark

- 기본 `새 GMV로 재최적화`는 현재 보유 수량과 최신 데이터로 production `MIN_VARIANCE + RISK_ONLY` Ledoit-Wolf 목표를 새로 계산합니다.
- `불러온 목표 비중으로 리밸런싱`은 Optimizer/Portfolio Manager/호환 JSON의 top-level `weights`만 고정 목표로 사용합니다. JSON의 과거 보유 수량, 가격과 거래 목록은 신뢰하지 않고 사용자가 별도로 입력한 실제 수량과 실행 시점 최신 가격을 사용합니다.
- 별도 기존 현금 입력은 없으며 `cash_injection`은 새 외부 자금입니다. 매도대금은 리밸런싱 내부 자금이고 weight 합계의 나머지는 비용 전 목표 cash, `remaining_cash`는 거래비용과 정수 반올림 이후 잔액입니다.
- Turnover는 매수와 매도의 절대 금액을 합한 gross L1 방식입니다. 고정 목표도 기존 band, gross turnover cap, transaction cost와 fractional-share 설정을 동일하게 적용합니다.
- 결과는 분석용 거래 제안일 뿐 실제 주문이나 broker 호출을 실행하지 않습니다. 과거 목표 복원은 미래 성과 검증, 연구 evidence 소비 또는 production optimizer 승격을 의미하지 않습니다.
- fractional share 허용 여부와 ticker별 예외를 고려합니다.
- benchmark는 동일한 기간과 통화 기준으로 비교해야 합니다.

## F. 다음 우선순위

현재 로드맵과 TODO 기준 우선순위:

- 배포 가능한 `collect-baseline` CLI로 immutable calendar-forward production baseline observation을 지속 축적하고 mature outcome을 수동 검토
- 세 고정 포트폴리오의 63/126/252 공통 일별 수익 관측을 calendar-forward로 축적하고 milestone별 수동 검토
- Stock Screener custom CSV universe 지원
- 회귀/forecast 모델 선택 UX와 LSTM 사용 의도 재검토
- 사용자 인증과 저장된 portfolio/watchlist/screening criteria
- 실시간 또는 준실시간 가격 데이터 연동
- alert/notification system
- RSI, MACD, Bollinger Bands, Moving Average 등 technical indicator 확장
- point-in-time factor hedge 및 ADV/liquidity constraint 연구
- 단위가 보정된 soft constraint priority와 mixed-integer exact cardinality 검증

## G. 비범위

- 매수/매도 추천을 단정적으로 제공하지 않습니다.
- 수익률 보장, 투자 자문, 자동 주문 실행은 현재 범위가 아닙니다.
- 계좌 연동, 실거래 broker API, 결제/구독 시스템은 현재 범위가 아닙니다.
- 대규모 멀티테넌트 서버 배포와 사용자별 데이터베이스 운영은 인증/저장 기능 결정 전까지 범위 밖입니다.

### Financial Score: 건전성·저평가 평가

- 건전성 60점: ROE 10, ROA 8, 순이익률 8, 영업이익률 4, Debt/Equity 10, 부채/자산 10, 유동비율 6, 당좌비율 4. 절대 기준만 적용합니다.
- 저평가 40점: trailing P/E 20, P/B 12, P/S 8. 유효한 산업/섹터 benchmark를 우선하고 없으면 절대 기준을 사용합니다. 상대 점수는 업종 대비 가격 수준이며 내재가치를 추정하지 않습니다.
- 성장률, 베타, 예상 P/E, PEG는 가중치 0의 참고 지표입니다. 현금흐름과 금융회사/리츠 전용 건전성 지표는 현재 포함하지 않으며 해당 업종 점수는 제한적으로 해석합니다.
- 각 영역은 가중 데이터 충족률 70% 이상이어야 합니다. 건전성에는 부채/자산, 수익성 지표 1개 이상, 유동/당좌비율 1개 이상이 필수이고 저평가에는 trailing P/E가 필수입니다. 한 영역이라도 불충족하면 종합 점수는 null입니다. 결측 영역의 가중치를 다른 영역으로 이전하지 않습니다.
- `decision.components.health|valuation`은 score와 coverage를 제공합니다. `confidence`는 기존 API 호환 필드이며 통계적 신뢰도가 아닌 데이터 충족률입니다. 종합 점수는 반올림한 영역 점수의 60/40 합입니다.
- Yahoo Debt/Equity는 percentage point를 100으로 나눕니다. 무차입 0은 정상 값입니다. 대표 peer 평균은 대상 종목 제외 후 지표별 3개 이상일 때만 사용하고, 캐시는 업종과 제외 대상 ticker를 함께 키로 사용합니다. 스크리너 캐시는 계산 버전별 namespace로 분리합니다.

- 부채/자산 1 이상 또는 유동비율 0.75 미만이면 건전성 점수 상한은 35점입니다. 대표 종목 원자료도 24시간 공유 캐시해 제외 대상별 평균 계산이 외부 호출 수를 증폭시키지 않도록 합니다.

## 전략 비교 도구 확장 (2026-11-12)

사용자가 CSV 후보 종목, 평가 날짜, 학습 기간, 재조정 간격, 예측 기간과 공통
거래 조건을 지정해 전략들을 비교한다. 벤치마크 고정 비중 평가와 전략 백테스트를
구분하며 결과에는 비용 후 자산·낙폭 곡선, 성과 표, 재조정별 실행 비중과 예측,
실패 대체 기록을 제공한다. 실험 전략을 제공하는 것이 기본 전략 승격을 뜻하지 않는다.
가격 CSV 업로드, 자동 파라미터 탐색, 실제 주문 실행은 이 기능 범위에 포함하지 않는다.

전략 비교의 각 항목은 사용자가 Optimizer와 같은 최적화 방식·예측 모델 조합으로
설정한다. 고정 3전략 선택에 한정하지 않으며 같은 최적화 방식에서도 여러 예측
모델을 비교할 수 있다. 과거 BL 시장 prior 가정과 실패 대체를 명시한다.

### 후보 갱신 운용 기본값 (2026-11-13)

Optimizer, Portfolio Manager REOPTIMIZE, CSV 전략 백테스트에 보유·유사·랜덤 후보
갱신을 기본 제공한다. 초기 전체 평가 후 양수 실제 보유 전부와 유사 10개/탐색 최대
10개를 갱신한다. 기본 예측 지도 갱신은 252거래일, seed 42이며 가격 특징/고정 지도/
기존 전체 갱신을 선택할 수 있다. GMV의 risk-only 계약과 기존 거래 제어는 유지한다.

이 기능의 목적은 운용 과정과 계산량을 명시적으로 제어하는 것이다. 수익률 개선,
항상 40종목 이하 평가, 보정된 예측 확률을 보장하지 않는다. 모델 가중치 저장이나
공동 학습 모델, 새로운 현금 규칙은 포함하지 않는다. 기존 실행은 유지하고 새 코드가
로드된 신규 작업부터 적용한다. 실행 중인 작업을 끝낸 뒤 서버 재시작이 필요하다.
