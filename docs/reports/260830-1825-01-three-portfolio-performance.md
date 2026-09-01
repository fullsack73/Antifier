# 세 포트폴리오 성과 비교

- 일시: 2026-08-30 18:25 (KST)
- 작성자: 사용자 요청 기반
- 에이전트: Codex
- 작업 유형: 포트폴리오 분석 / 문서

## 요약

`tests/portfolios/`의 LLM 단독 구성, production GMV, 뉴스 기반 LLM 보정 GMV를 동일한 USD 조정주가와 연 3.5% 무위험수익률로 비교했습니다.

점추정치에서는 뉴스 보정 GMV가 가장 높은 기대수익률과 Sharpe, 가장 낮은 공분산 추정 변동성을 보였습니다. 그러나 GMV 대비 차이는 작고 21일 paired circular block bootstrap의 95% 성과 gate를 통과하지 못했습니다. LLM 단독은 10% 현금과 더 분산된 위험자산 비중 덕분에 5년 buy-and-hold 최대낙폭이 가장 작았지만 기대수익률과 Sharpe는 두 GMV 계열보다 낮았습니다.

세 포트폴리오는 2026-08-30에 구성됐고 데이터는 2026-08-28까지만 있으므로 구성 이후 실현 성과는 0개 관측입니다. 아래 수치는 모두 후향적/in-sample diagnostic이며 production 변경이나 향후 우위의 근거가 아닙니다.

## 입력과 계산 계약

- 구성 파일: `tests/portfolios/GMV_baseline.json`, `tests/portfolios/llm-refined-GMV.json`, `tests/portfolios/llm-scratch.json`
- 시장 데이터: yfinance adjusted close, `auto_adjust=true`, USD, 2021-08-30~2026-08-28
- 가격 관측: 선택된 39개 고유 ticker 모두 1,255개 관측으로 누락 없음
- 구성 시점 진단: GMV 결과의 `optimizer_expected_returns`와 같은 Ledoit-Wolf 공분산 사용
- 공분산 공통 구간: 2024-03-27~2026-08-28, 608개 관측
- 역사 경로: 최초 비중으로 fractional buy-and-hold, 리밸런싱·거래비용 없음
- 현금: LLM 단독의 비중 합이 90%이므로 나머지 10%를 현금으로 보존하고 연 3.5% 복리 적용
- 연율화: 252 거래일, daily simple return, Sharpe는 일별 초과수익의 연율 평균을 연율 변동성으로 나눔
- 통계: 21일 paired circular block bootstrap 5,000회, seed `20260830`, 95% gate

GMV JSON의 `return=14.8106%`, `risk=9.7246%`, `sharpe_ratio=1.1631`을 동일 입력으로 정확히 재현했습니다.

## 구성 비교

| 포트폴리오 | 종목 수 | 위험자산 | 현금 | 위험자산 내 유효 보유 수 | 최대 위험자산 비중 |
|---|---:|---:|---:|---:|---:|
| GMV | 19 | 100% | 0% | 16.60 | 9.13% |
| 뉴스 보정 GMV | 19 | 100% | 0% | 16.29 | 9.13% |
| LLM 단독 | 25 | 90% | 10% | 24.22 | 6.11% |

뉴스 보정 GMV는 GMV와 종목 19개가 모두 같고 active share는 7.10%, gross L1 비중 차이는 14.20%입니다. LLM 단독은 GMV와 5개 종목만 겹치며 active share는 76.68%입니다.

## 구성 시점 역사 진단

| 포트폴리오 | 역사 기대수익률 | Ledoit-Wolf 변동성 | Sharpe |
|---|---:|---:|---:|
| 뉴스 보정 GMV | 15.0673% | 9.5531% | 1.2109 |
| GMV | 14.8106% | 9.7246% | 1.1631 |
| LLM 단독 | 10.1480% | 10.3075% | 0.6450 |

뉴스 보정 GMV는 GMV보다 기대수익률이 0.2567%p 높고 변동성이 0.1716%p 낮으며 Sharpe가 0.0478 높습니다. LLM 단독은 10% 현금을 포함해도 GMV보다 기대수익률이 4.6626%p 낮고 변동성이 0.5829%p 높습니다.

이 표의 기대수익률은 optimizer 입력 당시 역사 수익률 진단이고 예측이나 실현수익률이 아닙니다. 뉴스 보정 JSON에는 비중만 있고 뉴스 source/as-of와 LLM provenance가 없으므로 보정 과정 자체는 재현하거나 point-in-time 여부를 검증할 수 없습니다.

## 고정 비중 buy-and-hold 결과

### 전체 가격 구간: 2021-08-30~2026-08-28

| 포트폴리오 | 누적수익률 | CAGR | 연율 변동성 | Sharpe | 최대낙폭 | $100 최종가치 |
|---|---:|---:|---:|---:|---:|---:|
| 뉴스 보정 GMV | 92.26% | 14.04% | 11.35% | 0.912 | -15.65% | $192.26 |
| GMV | 91.16% | 13.91% | 11.36% | 0.900 | -15.76% | $191.16 |
| LLM 단독 | 69.69% | 11.21% | 11.13% | 0.701 | -11.55% | $169.69 |

뉴스 보정 GMV는 GMV보다 누적수익률이 1.10%p 높았지만 일별 수익률 상관계수가 0.9968로 사실상 같은 경로였습니다. LLM 단독은 수익과 Sharpe가 낮은 대신 최대낙폭을 GMV보다 4.21%p 줄였습니다.

### 공분산 공통 구간: 2024-03-27~2026-08-28

| 포트폴리오 | 누적수익률 | CAGR | 연율 변동성 | Sharpe | 최대낙폭 | $100 최종가치 |
|---|---:|---:|---:|---:|---:|---:|
| 뉴스 보정 GMV | 46.81% | 17.28% | 9.63% | 1.347 | -7.46% | $146.81 |
| GMV | 45.92% | 16.99% | 9.84% | 1.294 | -7.63% | $145.92 |
| LLM 단독 | 27.95% | 10.77% | 10.52% | 0.699 | -7.55% | $127.95 |

이 구간에서도 뉴스 보정 GMV의 점추정치가 가장 좋지만, 동일 종료 시점 자료로 비중을 만든 뒤 같은 과거 구간에 적용한 결과이므로 out-of-sample 증거가 아닙니다.

## 통계 판정

전체 5년 경로에서 뉴스 보정 GMV의 GMV 대비 bootstrap 확률은 낮은 변동성 68.56%, 높은 수익률 63.28%, 높은 Sharpe 64.56%였습니다. 차이의 95% 구간은 연율 수익률 `-0.62%p~+0.84%p`, 변동성 `-0.094%p~+0.057%p`, Sharpe `-0.055~+0.080`으로 모두 0을 포함합니다.

공분산 공통 구간에서는 뉴스 보정 GMV의 낮은 변동성 확률이 100%였지만 높은 Sharpe 확률은 82.62%에 그쳐 95% gate를 통과하지 못했습니다. 따라서 뉴스 보정 효과는 `점추정치 우세, 통계적 우위 미확인`으로 판정합니다.

LLM 단독도 GMV 대비 95% lower-volatility/higher-Sharpe gate를 통과하지 못했습니다. 전체 5년에서는 낮은 변동성 확률 79.70%, 높은 Sharpe 확률 20.84%였고, 공분산 공통 구간에서는 각각 1.92%, 8.18%였습니다.

## 결론

1. 현재 숫자상 1위는 뉴스 보정 GMV지만 GMV와의 차이는 작고 통계적으로 확정되지 않았습니다.
2. production GMV는 뉴스 보정 없이도 거의 같은 수익 경로와 더 단순하고 재현 가능한 계약을 가집니다. 이번 결과로 production 기본값을 바꾸지 않습니다.
3. LLM 단독은 최대낙폭 방어라는 부분 장점이 있으나 기대수익률과 위험조정성과의 열위가 커 종합 우위로 볼 수 없습니다.
4. 진짜 성과 비교는 2026-08-30 이후 63/126/252 공통 거래일이 성숙한 뒤 고정된 비중과 평가 계약으로 다시 수행해야 합니다.

## 변경 범위

- 현재 비교와 한계를 이 보고서에 기록했습니다.
- 구성 이후 검증을 `docs/todo/three-portfolio-forward-performance.md`와 TODO 인덱스에 등록했습니다.
- 제품 코드, portfolio JSON, production 정책은 변경하지 않았습니다.

## 검증

- 세 JSON 파싱 및 비중 유한성: 통과
- 비중 합: GMV `1.0`, 뉴스 보정 GMV `0.9999999999999998`, LLM 단독 `0.9000000000000005`
- 선택된 39개 ticker 가격 coverage: 39/39, ticker별 1,255/1,255 관측
- GMV 제공 성과 재현: return/risk/Sharpe 모두 부동소수점 오차 없이 일치
- bootstrap: 5,000회 deterministic rerun 조건 기록
- 문서 링크, TODO 인덱스, placeholder, 파일명, `git diff --check`: 통과

## 입력 무결성

- Code revision: `0f8a2e618cdd1a0d6457f3da370825cef56449f2`
- GMV JSON SHA-256: `1042892937d0093c25a691c7452bbde43242f3ebec3379570f58c246e666d96b`
- 뉴스 보정 GMV JSON SHA-256: `7ba69790d472e1d4e5e406cf02b88ead9af3fc142bc2192f4ddcfec7c5fb0243`
- LLM 단독 JSON SHA-256: `0d86e82e55c634be514186ee90f936ff03f8561b7370bf1cb0756a4936fbca61`
- Pipeline cache SHA-256: `1ed1b022492763c5ed7b8ea1d5edbe57a2fac63ba0fa3ddd3e7d4656deaa8ed1`
- Raw adjusted-close cache SHA-256: `e0f1fd514bb3d3b99f32e1d4086c453a894059b8cedc99f00c348f4ec9347296`
- GMV aligned market-data SHA-256: `9e914b7223a682fb9739bce37314f49c525372c4ee1f65dfddc5a601718e0590`

## 리스크/이슈

- 모든 수익 경로는 구성에 사용된 과거 데이터를 다시 사용하므로 look-ahead/in-sample 편향이 있습니다.
- 거래비용, 세금, 정수 주식, bid-ask spread와 실제 체결은 반영하지 않았습니다.
- 뉴스 보정의 뉴스·LLM provenance가 없어 전략 생성의 재현성과 point-in-time 무결성을 검증할 수 없습니다.
- 로컬 cache 파일은 재현 입력 해시를 기록했지만 저장소 추적 artifact가 아닙니다.

## 다음 작업

- `docs/todo/three-portfolio-forward-performance.md`의 사전 고정 계약에 따라 63/126/252 공통 거래일에 calendar-forward 평가합니다.

## 참고

- 관련 문서: `docs/02-specs.md`, `docs/03-product-plan.md`, `docs/todo/00-todo-list.md`
