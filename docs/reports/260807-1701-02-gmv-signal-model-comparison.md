# 작업 기록 - GMV Alpha Tilt Signal 모델 비교

- 일시: 2026-08-07 17:01 (KST)
- 작성자: Codex
- 에이전트: Codex
- 작업 유형: 포트폴리오 연구 진단

## 요약

- 동일한 GMV, gamma `0.025`, 거래비용 및 실행 제약에서 signal 모델만 교체해 비교했습니다.
- Transformer 단독, ARIMA+Transformer, ARIMA 단독과 기존 frozen Kronos/Patch 계열을 동일 15개 evaluation origin에 적용했습니다.
- 모든 후보가 plain GMV보다 수익률과 Sharpe를 소폭 높였지만 변동성도 증가했고, paired 95% portfolio gate는 전부 탈락했습니다.
- 결과는 consumed validation 기반 `diagnostic_only`이며 모델 선택이나 production 변경에 사용할 수 없습니다.

## 공통 사양

- 포트폴리오: `w=project_capped_simplex(w_GMV+gamma*alpha_tilt)`
- alpha tilt: 횡단면 score rank 중심화, L1 norm 2
- gamma: `0.025`
- 실행: 거래비용 10 bps, rebalance band 2%, turnover cap 35%, 자산별 cap 20%
- 비교 구간: 3개 case, 15개 rebalance period, 결합 daily observation 945개
- plain GMV: 연환산 수익률 `19.3827%`, 변동성 `24.0570%`, Sharpe `0.8057`

## 결과

| 순위 | Signal | 수익률 | 변동성 | Sharpe | Δ수익률 | ΔSharpe | P(수익률↑) | P(Sharpe↑) | Gate |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | Patch Transformer + Kronos | 19.5567% | 24.1085% | 0.8112 | +0.1740%p | +0.0055 | 85.50% | 77.75% | rejected |
| 2 | Transformer | 19.5387% | 24.0925% | 0.8110 | +0.1560%p | +0.0053 | 75.10% | 72.25% | rejected |
| 3 | Kronos | 19.5119% | 24.0913% | 0.8099 | +0.1293%p | +0.0042 | 74.85% | 70.70% | rejected |
| 4 | Patch Transformer | 19.4901% | 24.1086% | 0.8084 | +0.1074%p | +0.0027 | 74.75% | 64.50% | rejected |
| 5 | ARIMA | 19.4715% | 24.0903% | 0.8083 | +0.0888%p | +0.0026 | 65.80% | 60.60% | rejected |
| 6 | ARIMA + Transformer | 19.4308% | 24.0832% | 0.8068 | +0.0481%p | +0.0011 | 57.90% | 54.65% | rejected |

## Signal 진단

| Signal | Mean rank IC | Positive IC | Top-bottom spread | Gate |
|---|---:|---:|---:|---|
| ARIMA | 0.0278 | 60.00% | 0.5164% | rejected |
| Transformer | 0.1446 | 46.67% | 0.4714% | rejected |
| ARIMA + Transformer | 0.1090 | 53.33% | 1.2660% | rejected |
| Kronos | 0.1344 | 73.33% | 2.8019% | rejected |
| Patch Transformer | 0.0885 | 66.67% | 0.9541% | rejected |
| Patch Transformer + Kronos | 0.1403 | 80.00% | -0.1471% | rejected |

## 데이터 계보와 해석

- Transformer와 ARIMA+Transformer는 기존 frozen forecast cache의 동일 date/ticker 예측을 사용했습니다.
- ARIMA 단독은 같은 ARIMA+Transformer cache payload에 보존된 `components.ARIMA`를 추출했습니다. 별도 재학습으로 사양을 바꾸지 않았습니다.
- ARIMA+Transformer는 두 구성요소의 단순 평균입니다. 이번 표본에서는 Transformer 단독보다 낮아 ARIMA 결합이 signal을 희석했습니다.
- 그러나 여러 모델을 이미 소비된 origin에서 비교했으므로 위 순위 자체도 선택 근거가 아닙니다.

## 검증

- focused backend tests: `10 passed`
- full backend tests: `380 passed, 1 skipped`
- 1-epoch CLI smoke: 6개 signal 비교 JSON/Markdown 생성 완료
- artifact JSON parse 및 Markdown 재생성 완료
- result SHA-256: `da16ebe18b11eb9875ebb5191e407cca9ec1602083114b2eef2ca628be30b895`

## 참고

- `data/research/derived/pooled_patch_transformer_consumed_validation_diagnostic_v1.json`
- `data/research/derived/pooled_patch_transformer_consumed_validation_diagnostic_v1.md`
- `docs/todo/portfolio-patch-transformer-fresh-validation.md`
