# Country ETF Nonlinear Forecast Research

- 실행 시각: 2026-07-24 00:49 KST
- 역할: research-only nonlinear model audit
- 결론: compact histogram gradient boosting 폐기

## 사전 명세

- target: 63거래일 cross-sectional relative return
- predictor: PIT-safe price feature 8개
- candidate: `relative_hist_gradient_boosting`
- loss: absolute error
- learning rate: `0.05`
- iterations: `64`
- maximum leaves: `7`
- minimum leaf rows: `20`
- L2 regularization: `5.0`
- early stopping: disabled
- random seed: `42`
- signal date마다 동일한 총 sample weight를 부여합니다.
- baseline: `relative_ridge`, penalty `5.0`

## 데이터 계약

- Yahoo Finance adjusted prices, country ETF 15개
- 기간: 2007-01-01~2025-12-31
- 크기: 4,780×15, 약 1.3 MiB
- 전 ticker usable observation: 4,780
- price SHA: `7ba7ace8c9d913eb4f10531b00b8c4c7f72b7c4217a3da9d4e4d61c106d831dc`
- research evaluation: 2010-01-01~2016-09-30
- split digest: `259660d6e8182a631faa6f2583b22c5a95337db45e668bcba2e8cb30dcd3f165`
- static ETF basket은 survivorship-safe production universe로 주장하지 않으며 `promotion_safe=false`입니다.
- 2017년 이후 가격은 다운로드됐지만 research 결과가 통과하기 전 validation/holdout outcome을 열지 않습니다.

## 결과

| Model | OOS periods | Rank IC | Positive IC | Top-bottom | P(IC>0) | P(spread>0) | Seconds | Peak MiB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Relative ridge | 27 | 0.0164 | 48.15% | -0.0030 | 67.95% | 35.80% | 3.65 | 6.81 |
| Hist gradient boosting | 27 | -0.0139 | 51.85% | 0.0001 | 39.80% | 50.90% | 8.23 | 6.79 |

- nonlinear minus ridge rank IC는 `-0.0303`, spread는 `+0.0031`입니다.
- paired P(higher IC)는 `25.65%`, P(higher spread)는 `57.35%`입니다.
- 두 모델 모두 개별 signal gate와 Holm correction을 통과하지 못했습니다.
- nonlinear candidate는 ridge보다 약 2.25배 느리고 paired improvement gate에서도 탈락했습니다.

## 승격 판정 수정

- 비교 baseline의 개별 signal gate가 통과해도 candidate의 paired gate가 실패하면 candidate가 승격되지 않도록 `passed_candidate_objectives`를 분리했습니다.
- research CLI의 `signal_gate_passed`와 `promotion_eligible`은 paired comparison이 있을 때 candidate-specific 통과 목록만 사용합니다.

## 판정

- `relative_hist_gradient_boosting`은 폐기합니다.
- 같은 research interval에서 tree depth, iteration, learning rate, loss를 재튜닝하지 않습니다.
- 2017+ validation과 2022+ holdout은 실행하지 않습니다.
- Transformer 규모/하이퍼파라미터 확대 근거도 생기지 않았습니다.
