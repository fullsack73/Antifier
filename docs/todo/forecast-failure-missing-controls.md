# 예측 원인 진단의 미실행 통제와 미해결 질문

- 등록: 2026-11-09, 원래 8시간 campaign의 C 210분 한도로 7개 미실행
- 완료 기록: `docs/reports/261109-2024-01-forecast-failure-attribution-results.md`
- 결과/manifest/checkpoint: `logs/forecast_failure_20261109_resume_01/`
- 원래 예산의 실행과 검토는 종료. 새 예산 승인 없이 자동 재실행하지 않는다.

## 미실행 작업

모두 2025-07-10 origin의 `controls`다. 다음 id를 그대로 보존하며, 이미 실행한
작업이나 결과가 좋았던 표본으로 대체하지 않는다.

| 종목 | Seed | Task ID |
|---|---:|---|
| GOOGL | 44 | 4dd2efb3300e775fa6f8716fcace2bf44def955dac7ad37bbaea70885f043f61 |
| NVDA | 42 | 6d2b7e25a0489b7b66eb59546a1645ffac00deea2dcede81afc96f52d8beefd0 |
| NVDA | 43 | d4aec6aba3e04c463c73ed0759edb61814ec42ca97535aa3d7ea059fd3a36d66 |
| NVDA | 44 | da86fc75aba7ffd03fdca1da089252c5f3b258c7738d7dd2ed68f211aea9bf50 |
| INTC | 42 | 40f95923b42e8e66ff31f376283403e759496f876218e396035871aaaafbb19c |
| INTC | 43 | e26dadc42fa6d8de984726f5e273dffca1017d7693c6cf1d431e66c0a7237203 |
| INTC | 44 | 40ed79af84ce42b3674ea7e5ad137a855464068f90e1f41a4382ab3ec4f78738 |

## 추가 검증 전에 잠글 질문

- 직접 예측 효과 중 학습 target과 recursive feedback의 기여를 더 분리할 수 있는가.
- ARIMA의 수렴 실패 71/312건이 예측 오차에 미치는 인과 효과는 무엇인가.
- 시장 구간별 변화와 교정 모델의 독립/미래 데이터 일반화가 유지되는가.

과거 diagnostic을 새 holdout으로 부르거나 production 선택에 재사용하지 않는다.
원래 manifest의 source drift 보호를 우회하지 않으며 후속 실행은 독립적인
계약과 명시적인 checkpoint provenance를 사용한다.

## 2026-11-15 선행조건 점검

원래 예산은 종료됐다. 새 실행 시간 상한과 후속 진단 계약이 필요하다. 원본 task ID/checkpoint는 보존하고 source drift 보호를 우회하지 않았다.

점검 기록: `docs/reports/261115-0127-01-todo-completion.md`.
