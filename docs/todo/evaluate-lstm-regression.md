# TODO - LSTM 회귀/forecast 모델 동작 재검토

- 등록 일시: 2026-07-01 16:53 KST
- 작성자: austinjung
- 에이전트: Codex
- 진행 시점: Stock Analysis 회귀/forecast 모델 UX 개선 시

> 완료된 TODO는 이 파일을 삭제하고, `docs/reports/`에 작업 기록을 남깁니다.

## 목표

- Stock Analysis의 회귀/forecast 모델 선택에서 LSTM을 어떤 역할로 사용할지 명확히 정리하고 필요한 코드와 UI를 맞춥니다.

## 요구사항

- 현재 `App.jsx`의 기본 모델, `ModelSelector`, `forecast_models.py`, `app.py`의 모델 분기 동작을 함께 검토합니다.
- LSTM, LightGBM, ARIMA, ARIMA + Transformer, Transformer, lightweight fallback의 용도를 사용자에게 혼동 없이 보여야 합니다.
- LSTM을 회귀 기본값으로 유지할지, 다른 모델과 비교 가능하게 둘지, 특정 경로로만 제한할지 결정합니다.
- 모델 변경 시 chart label, formula, future prediction 응답, 테스트를 함께 맞춥니다.

## 작업 요약

- frontend 모델 selector UX와 backend model type parsing을 점검합니다.
- README와 `docs/03-product-plan.md`의 모델 설명을 실제 동작과 맞춥니다.
- 모델별 최소 데이터 길이와 실패 fallback 정책을 테스트합니다.

## 선행조건

- "make regress use LSTM?"의 의도가 기본 회귀 모델 변경인지, LSTM 경로 정상화인지 확인이 필요합니다.

## 참고

- 관련 문서: `docs/02-specs.md`, `docs/03-product-plan.md`
- 기존 루트 TODO: `make regress use LSTM?`
- todo-list 한 줄 요약: `evaluate-lstm-regression.md` | 시점: Stock Analysis 회귀/forecast 모델 UX 개선 시 | 목표: LSTM 회귀 사용 의도와 모델 선택 동작을 재검토
