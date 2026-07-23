# TODO - Live Portfolio Gauntlet Run

- 등록 일시: 2026-07-10 14:46 (KST)
- 작성자: Codex
- 에이전트: Codex
- 진행 시점: 외부 yfinance 네트워크와 장시간 백테스트 실행을 허용할 수 있을 때

> 완료된 TODO는 이 파일을 삭제하고, `docs/reports/`에 작업 기록을 남깁니다.

## 목표

- 구현된 `tools/backtest_portfolio_models.py`의 staged `candidate` → `standard` runner로 실제 market data 기반 portfolio promotion gauntlet을 실행합니다.
- 결과 JSON과 Markdown summary를 `logs/` 아래에 저장하고, candidate model이 여러 basket/regime/sensitivity에서 생존하는지 확인합니다.

## 진행 기록

- 2026-07-10 15:00 (KST): 기본 `standard` 모델 세트로 live run을 시작했으나 `arima_transformer_rank_bl`와 `transformer_rank_bl`가 rebalance마다 ticker별 TensorFlow 학습을 반복해 1/180도 완료하기 전 중단했습니다.
- 2026-07-10 15:09 (KST): ML rank 모델을 제외한 baseline/signal-stack 180-case live gauntlet은 완료했습니다.
  - JSON: `logs/portfolio_gauntlet_standard_20260710_baselines.json`
  - Summary: `logs/portfolio_gauntlet_standard_20260710_baselines.md`
  - 기록: `docs/reports/260710-1509-01-live-baseline-gauntlet-run.md`
- 2026-07-23 16:30 (KST): 장시간 실행 구조를 staged/resumable gauntlet으로 개선했습니다.
  - basket/regime별 forecast와 target weight를 한 번만 계산하고 execution sensitivity에서 재사용합니다.
  - ML forecast를 SQLite에 prediction 단위로 즉시 저장해 프로세스 중단 후에도 재사용합니다.
  - 완료 case를 JSONL checkpoint에 append하고 `--resume`으로 이어서 실행할 수 있습니다.
  - 4개 대표 시장 구간, 기본 63거래일 리밸런싱, primary ML candidate 1개로 구성된 `candidate` preset을 추가했습니다.
  - 기록: `docs/reports/260723-1630-01-portfolio-gauntlet-pipeline.md`
- 2026-07-23 16:35 (KST): primary `arima_transformer_rank_bl` live candidate run을 시작했습니다.
  - 결과: `logs/portfolio_gauntlet_candidate_20260723.json`
  - checkpoint: `logs/portfolio_gauntlet_candidate_20260723.json.checkpoint.jsonl`
  - forecast cache: `logs/portfolio_gauntlet_forecasts.sqlite3`
  - namespace: `arima-transformer-rank-v1`
- 2026-07-23 16:59 (KST): live candidate run 4/4를 약 23분 30초에 완료했으며 primary candidate는 0/4 survival로 탈락했습니다.
  - raw forecast 216개를 SQLite에 저장했습니다.
  - default uncertainty에서 candidate weight가 equal weight와 거의 동일했고, uncertainty를 낮춘 재생 실험도 모두 0/4였습니다.
  - rank IC는 SP500 bull 0.0152, tech crash -0.0060, defensive inflation/rate shock 0.1161, mixed ETF-like sideways 0.0212로 일관된 cross-sectional alpha가 없었습니다.
  - candidate gate 탈락에 따라 standard 180-case는 실행하지 않았습니다.
  - 기록: `docs/reports/260723-1703-01-live-candidate-gauntlet.md`

## 남은 작업

- cross-sectional rank IC와 positive IC rate를 개선할 새 forecast candidate를 설계합니다.
- `transformer_rank_bl`을 같은 staged gate에서 별도 후보로 비교할지 결정합니다.
- 새 candidate가 4-case gate를 통과한 경우에만 같은 forecast cache로 `standard` 180-case를 실행합니다.

## 실행 예시

```bash
PYTHONPATH=src/backend .venv/bin/python tools/backtest_portfolio_models.py \
  --gauntlet-preset candidate \
  --fetch-market-caps \
  --forecast-cache-namespace arima-transformer-rank-v1 \
  --output logs/portfolio_gauntlet_candidate_YYYYMMDD.json
```

중단 후 재개:

```bash
PYTHONPATH=src/backend .venv/bin/python tools/backtest_portfolio_models.py \
  --gauntlet-preset candidate \
  --fetch-market-caps \
  --forecast-cache-namespace arima-transformer-rank-v1 \
  --output logs/portfolio_gauntlet_candidate_YYYYMMDD.json \
  --resume
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
- 후속 alpha 진단/재설계: `docs/todo/portfolio-alpha-diagnostics-redesign.md`
