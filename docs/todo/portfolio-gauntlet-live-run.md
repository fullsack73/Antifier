# TODO - Live Portfolio Gauntlet Run

- 등록 일시: 2026-07-10 14:46 (KST)
- 작성자: Codex
- 에이전트: Codex
- 진행 시점: 외부 yfinance 네트워크와 장시간 백테스트 실행을 허용할 수 있을 때

> 완료된 TODO는 이 파일을 삭제하고, `docs/reports/`에 작업 기록을 남깁니다.

## 목표

- 구현된 `tools/backtest_portfolio_models.py --gauntlet-preset standard` runner로 실제 market data 기반 portfolio promotion gauntlet을 실행합니다.
- 결과 JSON과 Markdown summary를 `logs/` 아래에 저장하고, candidate model이 여러 basket/regime/sensitivity에서 생존하는지 확인합니다.

## 진행 기록

- 2026-07-10 15:00 (KST): 기본 `standard` 모델 세트로 live run을 시작했으나 `arima_transformer_rank_bl`와 `transformer_rank_bl`가 rebalance마다 ticker별 TensorFlow 학습을 반복해 1/180도 완료하기 전 중단했습니다.
- 2026-07-10 15:09 (KST): ML rank 모델을 제외한 baseline/signal-stack 180-case live gauntlet은 완료했습니다.
  - JSON: `logs/portfolio_gauntlet_standard_20260710_baselines.json`
  - Summary: `logs/portfolio_gauntlet_standard_20260710_baselines.md`
  - 기록: `docs/reports/260710-1509-01-live-baseline-gauntlet-run.md`

## 남은 작업

- 기본 `standard` 모델 세트에 ML rank 모델을 포함할지 재검토합니다.
- ML rank 모델을 포함하려면 forecast cache, per-basket/regime forecast reuse, 또는 별도 소규모 candidate gauntlet으로 분리해야 합니다.

## 실행 예시

```bash
PYTHONPATH=src/backend .venv/bin/python tools/backtest_portfolio_models.py \
  --gauntlet-preset standard \
  --fetch-market-caps \
  --output logs/portfolio_gauntlet_standard_YYYYMMDD.json
```

## 요구사항

- SP500 sample, DOW, tech basket, defensive basket, mixed ETF-like basket을 포함합니다.
- bull, crash, inflation/rate shock, sideways regime을 포함합니다.
- transaction cost 10 bps를 유지합니다.
- rebalance band 2%, 3%, 5%와 max turnover 20%, 35%, 50% sensitivity를 확인합니다.
- 생성된 `.json`과 `.md` summary의 `promotion_gauntlet` 결과를 검토하고, default forecast method 변경 여부는 별도 수동 판단으로 남깁니다.

## 참고

- 관련 구현 기록: `docs/reports/260710-1446-01-portfolio-gauntlet-baselines.md`
- 관련 실행 기록: `docs/reports/260710-1509-01-live-baseline-gauntlet-run.md`
