# 과거 세 포트폴리오 forward 성과 비교

- 일시: 2026-08-31 00:29 (KST)
- 작성자: 사용자 요청 기반
- 에이전트: Codex
- 작업 유형: 포트폴리오 분석 / retrospective forward holdout / research tooling

## 요약

`tests/portfolios/past/`의 LLM 단독, GMV, 뉴스 기반 LLM 보정 GMV를 동일한 USD 조정주가와 고정 비중 buy-and-hold 계약으로 비교했습니다.

고정 252개 수익 관측에서 GMV가 누적수익률 9.09%, Sharpe 0.502, 최대낙폭 -8.07%로 세 포트폴리오 중 가장 우수했습니다. 뉴스 보정 GMV는 변동성이 GMV보다 2.35 bp 낮았지만 누적수익률은 0.95%p, Sharpe는 0.073 낮았고 최대낙폭도 더 컸습니다. LLM 단독은 누적수익률 5.11%, Sharpe 0.180, 최대낙폭 -14.18%로 가장 뒤처졌습니다.

63·126·252개 모든 milestone에서 뉴스 보정 GMV와 LLM 단독은 GMV 대비 paired 95% 개선 gate를 통과하지 못했습니다. 따라서 이번 결과는 production GMV를 유지한다는 결론을 지지하지만, 2024년에 사전등록한 실험이 아니라 2026년에 수행한 소급 forward holdout이므로 승격 가능한 calendar-forward 증거로 취급하지 않습니다.

## 구성 시점 판정

파일명과 두 LLM 포트폴리오 ID에는 `2019-08-30`이 들어 있지만 이는 유효한 구성일이 아닙니다. GMV 입력의 `market_data_provenance`는 다음을 명시합니다.

- 학습 조회 시작: 2019-08-30
- 학습 조회 종료(exclusive): 2024-08-30
- 실제 가격 사용 종료: 2024-08-29

따라서 세 포트폴리오가 사용할 수 있는 첫 forward 가격은 2024-08-30으로 고정했습니다. 2019-08-30부터 성과를 계산하면 GMV 생성에 쓰인 5년 가격을 결과에 다시 사용하는 look-ahead가 되므로 허용하지 않았습니다.

## 입력과 계산 계약

- 입력: `tests/portfolios/past/GMV_baseline_past.json`, `tests/portfolios/past/llm-refined-GMV_past.json`, `tests/portfolios/past/llm_scratch_past.json`
- 평가 사양: `data/research/derived/three_portfolio_past_forward_spec_v1.json`
- 시장 데이터: Yahoo chart v8 adjusted close, USD
- 평가 시작: 2024-08-30
- 정렬: 종목별 첫 관측 이전 채움 금지, 첫 관측 이후에만 forward-fill, 전체 종목 공통일
- 경로: fractional buy-and-hold, 리밸런싱·거래비용 없음
- 현금: GMV 0%, 뉴스 보정 GMV 0%, LLM 단독 5%; 연 3.5% 복리
- 연율화: 252 거래일
- 통계: 21일 paired circular block bootstrap 5,000회, seed `20260830`, 95% gate
- 증거 분류: `retrospective_forward_holdout`, `preregistered_before_outcome=false`
- 뉴스 보정 분류: `non_reproducible_diagnostic`

## 구성 비교

| 포트폴리오 | 종목 수 | 위험자산 | 현금 | GMV 대비 active share |
|---|---:|---:|---:|---:|
| GMV | 48 | 100% | 0% | 0% |
| 뉴스 보정 GMV | 48 | 100% | 0% | 8.20% |
| LLM 단독 | 26 | 95% | 5% | 94.98% |

뉴스 보정 GMV는 GMV와 같은 48개 종목을 유지하면서 `SW`와 `TKO`를 각각 3.0%p 줄이고 `MRK`를 1.2%p 늘리는 등 제한적인 tilt를 적용했습니다. LLM 단독은 GMV와 거의 다른 성장주 중심 구성이어서 결과 차이를 뉴스 보정 효과와 같은 수준으로 해석할 수 없습니다.

## 고정 milestone 결과

| 수익 관측 | 종료일 | GMV | 뉴스 보정 GMV | LLM 단독 |
|---:|---|---:|---:|---:|
| 63 | 2024-11-29 | 4.79% | 4.62% | 3.88% |
| 126 | 2025-03-05 | 4.37% | 3.88% | 2.80% |
| 252 | 2025-09-04 | 9.09% | 8.15% | 5.11% |

### 252개 수익 관측 상세

| 포트폴리오 | 누적수익률 | CAGR | 연율 변동성 | Sharpe | 최대낙폭 | $100 최종가치 |
|---|---:|---:|---:|---:|---:|---:|
| GMV | 9.09% | 9.09% | 11.90% | 0.502 | -8.07% | $109.09 |
| 뉴스 보정 GMV | 8.15% | 8.15% | 11.88% | 0.429 | -8.30% | $108.15 |
| LLM 단독 | 5.11% | 5.11% | 14.13% | 0.180 | -14.18% | $105.11 |

뉴스 보정 GMV의 GMV 대비 bootstrap 확률은 낮은 변동성 63.88%, 높은 수익률 20.74%, 높은 Sharpe 20.62%였습니다. Sharpe 차이의 95% 구간은 `-0.287~+0.102`로 0을 포함합니다.

LLM 단독의 GMV 대비 확률은 낮은 변동성 2.96%, 높은 수익률 34.96%, 높은 Sharpe 31.46%였습니다. Sharpe 차이의 95% 구간은 `-1.523~+0.888`입니다. 두 후보 모두 낮은 변동성과 높은 Sharpe의 95% gate에서 `rejected`입니다.

## 전체 가용 forward 구간

2024-08-30~2026-08-28의 499개 수익 관측은 종료일이 사전에 고정되지 않은 움직이는 구간이므로 `descriptive_only`이며 promotion gate를 적용하지 않았습니다.

| 포트폴리오 | 누적수익률 | CAGR | 연율 변동성 | Sharpe | 최대낙폭 | $100 최종가치 |
|---|---:|---:|---:|---:|---:|---:|
| GMV | 33.12% | 15.54% | 11.40% | 1.023 | -8.25% | $133.12 |
| 뉴스 보정 GMV | 32.78% | 15.39% | 11.29% | 1.021 | -8.30% | $132.78 |
| LLM 단독 | 10.39% | 5.12% | 12.65% | 0.186 | -14.18% | $110.39 |

전체 구간에서도 GMV가 뉴스 보정 GMV보다 누적수익률 0.34%p, Sharpe 0.0023, 최대낙폭 0.05%p 우세했습니다. 뉴스 보정 GMV는 연율 변동성이 0.11%p 낮아 두 경로가 매우 유사했지만 종합 우위는 확인되지 않았습니다.

## 결론

1. 고정 252일 종합 1위는 GMV입니다.
2. 뉴스 보정 GMV는 GMV와 거의 같은 위험 경로였지만 수익률과 Sharpe를 개선하지 못했고 모든 milestone gate가 기각됐습니다.
3. LLM 단독은 5% 현금에도 변동성·낙폭이 더 크고 수익률·Sharpe가 낮아 이번 구간에서 명확히 열위였습니다.
4. production 기본값과 자동 승격 정책은 변경하지 않습니다. 결과는 투자 판단을 대신하지 않는 분석 보조 자료입니다.

## 변경 범위

- 과거 입력과 평가 계약을 self-hash spec으로 고정했습니다.
- 기존 forward CLI를 캠페인 날짜에 종속되지 않도록 일반화하고, 소급 평가 여부와 사전등록 여부를 결과에 노출했습니다.
- 전체 가용 구간은 통계 gate와 분리된 설명용 결과로 추가했습니다.
- 관련 아키텍처·기능·제품 문서를 갱신했습니다.

## TODO / report workflow

- 작업 시작 시 `docs/todo/00-todo-list.md`와 관련 `three-portfolio-forward-performance.md`를 확인했습니다.
- 기존 TODO는 2026-08-30에 새로 고정한 별도 포트폴리오의 실제 미래 관측을 추적하므로 유지합니다.
- 이번 과거 holdout 요청은 현재 작업에서 평가·검증·보고까지 완료되어 새 TODO를 만들지 않았습니다.
- 완료 기록은 본 보고서에 남깁니다.

## 검증

- `python3 -m py_compile tools/three_portfolio_forward.py`: 통과
- `PYTHONPATH=src/backend python3 tools/three_portfolio_forward.py --help`: 통과
- `PYTHONPATH=src/backend python3 -m pytest tests/test_three_portfolio_forward.py tests/test_portfolio_statistics.py -q`: 13개 통과
- 두 spec self-hash 및 세 과거 입력 SHA-256/weight/cash 일치: 통과
- Yahoo USD adjusted-close 71개 고유 ticker 조회 및 500개 공통 가격 관측: 통과
- 63/126/252 milestone 성숙과 bootstrap deterministic seed: 통과
- 자동 승격 없음, 과거 사전등록 주장 없음: 통과
- `PYTHONPATH=src/backend python3 -m pytest tests -q`: 로컬 system Python에 `flask`, `yfinance`, `scipy`, `sklearn`, `cvxpy`, `pypfopt`, `tensorflow`가 없어 30개 module collection error로 전체 suite 실행 불가. 변경 경로의 targeted tests는 정상입니다.

## 입력·결과 무결성

- Past spec SHA-256: `9bb644ccfc3f54eb87a9df0ab62e26ff853bfb2da84ca9e25fd9de53478f4975`
- GMV input SHA-256: `9e65507364657f5be1b33d00d11a8b149d000afef714617446c74f910c386bc4`
- 뉴스 보정 GMV input SHA-256: `4927247ce7534ce8bc3d25bc9eed963b4b66a5ce7dd0181d22e38e663a182366`
- LLM 단독 input SHA-256: `4f70e67db265dfa888f5cbb2e8486959c0e1e533c2beb88c2b7d160845d91659`
- 최종 live price snapshot SHA-256: `8a571c43a66426e67eea7059653c1c118739368daca993d7b6f7a41d14c0874e`
- 252일 price snapshot SHA-256: `4ec40d6d174aa8e0bbef4a0702678b17602a71c9995e0faf188795e15a290610`
- Result SHA-256: `9db47415d3fdd29ab1bd1deb80c0accb17d38a2df77eff7e61c2073b0feb3d90`

## 리스크/이슈

- 이 평가는 구성 시점 이후만 사용하지만 결과를 본 뒤 수행한 소급 holdout이므로 사전등록 calendar-forward 증거보다 약합니다.
- 뉴스 원문/as-of/digest와 LLM model/prompt/config가 없어 뉴스 보정의 point-in-time 무결성과 생성 과정을 재현할 수 없습니다.
- Yahoo adjusted close는 공급자가 기업행사를 반영해 과거 값을 재작성할 수 있고, 반복 조회의 원시 부동소수점 값이 미세하게 달라질 수 있습니다. 표시 정밀도의 성과 순위와 결론은 반복 실행에서 동일했으며 최종 실행 hash를 기록했습니다.
- 거래비용, 세금, bid-ask spread, 정수 주식과 실제 체결은 반영하지 않았습니다.

## 참고

- 관련 문서: `docs/01-folder-architecture.md`, `docs/02-specs.md`, `docs/03-product-plan.md`, `docs/todo/00-todo-list.md`
