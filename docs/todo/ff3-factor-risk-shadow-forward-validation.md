# TODO - FF3 factor-risk shadow-forward validation

- 등록 일시: 2026-08-28 03:07 (Asia/Seoul)
- 작성자: Codex
- 상태: 대기

## 목표

- 고정된 `factor_model_minimum_variance` 사양을 기존 연구와 겹치지 않는 미사용 shadow-forward 구간에서 Ledoit-Wolf GMV와 비교합니다.

## 선행조건

- 최소 20개 이상의 새 63거래일 OOS rebalance origin
- 동일한 PIT universe, 가격/factor provenance와 risk-free SHA-256
- 현재 smoke 결과를 이용한 window, half-life, shrinkage, floor 또는 cap 재선택 금지

## 완료 조건

- realized volatility와 Sharpe paired circular block bootstrap 95% 및 Holm gate
- drawdown, turnover, 집중도, fallback, predicted/realized volatility와 exposure drift 보고
- 통과 전 production Ledoit-Wolf GMV와 API/UI 기본값 유지

## 참고

- `docs/reports/260828-0307-01-ff3-factor-risk-experiment.md`
- `data/research/derived/fama_french_12_industry_ff3_factor_risk_smoke_split_v1.json`
