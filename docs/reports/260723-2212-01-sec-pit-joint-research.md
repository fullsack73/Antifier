# SEC PIT Joint Forecast Research

- 실행 일시: 2026-07-23 22:12 KST
- 상태: diagnostic complete, no candidate frozen
- 결과 파일: `logs/dow29_pit_compact_quality_2008_2025.json`

## 데이터

- 사용자가 제공한 로컬 `companyfacts/` archive만 SEC 원본으로 사용했습니다.
- SEC bulk/API 다운로드는 실행하지 않았습니다.
- Yahoo SEC filing metadata는 30개 ticker의 CIK 매핑에만 사용했고 29개를 매핑했습니다.
- 2009-2025 filing-date PIT feature는 449 rows, 29 tickers입니다.
- feature missing rate는 quality `0%`, profitability `8.02%`, valuation `0.22%`, liquidity `14.48%`입니다.
- 로컬 companyfacts에는 submissions/SIC가 없어 sector 449 rows가 모두 `Unknown`입니다.
- current DOW ticker list를 과거에 고정 적용했으므로 survivorship-safe가 아니며 `promotion_eligible=false`입니다.

## 구현

- `factor_residual_ridge`에 PIT quality, profitability, valuation, liquidity를 실제 predictor로 연결했습니다.
- 각 signal date 최신 filing만 선택하고 cross-sectional winsorized z-score를 적용했습니다.
- 결측은 중립값 0과 feature별 missing indicator로 분리했습니다.
- 동일 residual target의 price-only `factor_residual_price_ridge`를 대조군으로 추가했습니다.
- PIT factor CSV는 provenance SHA-256이 일치해야 research CLI가 실행됩니다.
- dependent signal period를 위한 circular block bootstrap 95% gate와 동시 objective Holm-Bonferroni 보정을 추가했습니다.
- 각 predictor의 raw OOS IC와 bootstrap, feature-family Holm 보정을 기록합니다.
- sector metadata를 로컬로 추가할 수 있도록 `--submissions-dir` 입력을 구현했습니다.

## 결과

| Objective | Periods | Mean rank IC | Positive IC | Top-bottom | P(IC>0) | P(spread>0) | 결과 |
|---|---:|---:|---:|---:|---:|---:|---|
| `relative_ridge` | 59 | 0.0539 | 57.63% | 0.0165 | 98.50% | 96.65% | 개별 gate 통과, Holm 탈락 |
| `factor_residual_price_ridge` | 58 | 0.0015 | 50.00% | -0.0067 | 51.95% | 20.60% | 탈락 |
| `factor_residual_ridge` | 58 | -0.0046 | 43.10% | -0.0079 | 44.45% | 15.05% | 탈락 |
| `factor_residual_quality_ridge` | 58 | -0.0476 | 39.66% | -0.0104 | 5.45% | 5.75% | 탈락 |

- `relative_ridge`의 raw multiple-testing p-value는 `0.0335`, 4개 objective Holm-adjusted p-value는 `0.1340`입니다.
- PIT 재무 결합은 동일 target의 price-only 대조군을 개선하지 못했습니다.
- factor 모델의 OOS RMSE는 price-only `0.0913`, PIT joint `0.0921`입니다.
- raw feature IC는 profitability `0.0478`, quality `0.0254`, valuation `-0.0173`, liquidity `0.0071`입니다. 16-feature Holm 보정 후 유의한 feature는 없습니다.
- quality+profitability만 학습한 compact ridge도 음의 IC로 실패해 feature 제거만으로 개선되지 않았습니다.

## 결정

- 최적화/예측 기본값은 변경하지 않습니다.
- factor candidate와 Transformer hyperparameter 탐색을 진행하지 않습니다.
- 다음 필수 입력은 날짜별 historical constituent manifest와 PIT sector/SIC metadata입니다.
- promotion-safe research에서 통계 gate를 통과한 단일 후보만 freeze한 뒤 validation으로 이동합니다.
