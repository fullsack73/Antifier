# Portfolio Gauntlet Pipeline

## Summary

포트폴리오 생성 모델을 반복 개선할 수 있도록 장시간 ML gauntlet을 staged/resumable 구조로 변경했습니다.

- `candidate` preset은 SP500 bull, tech crash, defensive inflation/rate shock, mixed ETF-like sideways 4개 대표 구간을 먼저 평가합니다.
- candidate preset은 기본 63거래일 리밸런싱과 primary `arima_transformer_rank_bl` 후보 하나를 사용해 초기 선별 비용을 줄입니다.
- 각 basket/regime의 forecast와 pre-control target weight를 한 번만 생성하고 rebalance band/max turnover sensitivity가 같은 target을 재생합니다.
- rank forecast prediction은 SQLite에 즉시 저장되며 프로세스가 중단돼도 다음 실행에서 재사용됩니다.
- 완료된 case는 JSONL checkpoint에 append되고 `--resume`으로 건틀렛을 이어갈 수 있습니다.
- cache schema version과 experiment namespace를 key에 포함해 호환되지 않는 모델 설정 사이의 stale forecast 재사용을 막습니다.
- candidate가 통과한 경우에만 기존 `standard` 180-case 승격 검증을 실행하는 흐름을 문서화했습니다.

## Changed Files

- `src/backend/portfolio_backtest.py`
- `tools/backtest_portfolio_models.py`
- `tests/test_portfolio_backtest.py`
- `docs/02-specs.md`
- `docs/03-product-plan.md`
- `docs/todo/portfolio-gauntlet-live-run.md`

## Verification

- `PYTHONPATH=src/backend .venv/bin/python -m py_compile src/backend/portfolio_backtest.py tools/backtest_portfolio_models.py`
- `PYTHONPATH=src/backend .venv/bin/python -m pytest tests/test_portfolio_backtest.py -q`
- `PYTHONPATH=src/backend .venv/bin/python -m pytest tests -q`
- `PYTHONPATH=src/backend .venv/bin/python tools/backtest_portfolio_models.py --help`

## Operational Flow

1. `--gauntlet-preset candidate`로 4개 대표 시장 구간을 선별합니다.
2. 중단되면 동일 output, namespace와 `--resume`을 사용합니다.
3. candidate가 생존하면 동일 forecast cache/namespace로 `standard`를 실행합니다.
4. 다른 모델 설정이나 후보는 새 `--forecast-cache-namespace`를 사용합니다.

## Remaining Work

- primary candidate live 결과는 `260723-1703-01-live-candidate-gauntlet.md`에 기록했으며 0/4로 탈락했습니다.
- cross-sectional rank IC가 개선된 새 candidate 설계
- secondary `transformer_rank_bl` 후보의 별도 비교
