# Portfolio Alpha v2 Foundation

## Summary

point-in-time factor 데이터가 확보되기 전에 안전하게 연구를 시작할 수 있도록 `factor_neutral_alpha_tilt`의 데이터 계약, no-lookahead 경계, factor-residual target, regularized linear baseline을 구현했습니다.

- public API, optimizer UI, default forecast, 기본 backtest/gauntlet 모델은 변경하지 않았습니다.
- candidate validation, standard gauntlet, locked holdout은 실행하지 않았습니다.
- 실제 데이터가 없는 상태에서 synthetic 결과를 모델 선택 근거로 사용하지 않습니다.

## Point-in-time contract

long-form CSV는 `available_date`, `ticker`, `sector`, `market_cap`, `quality`, `profitability`, `valuation`, `liquidity`를 요구합니다.

- `available_date`가 signal date 이하인 ticker별 최신 row만 사용합니다.
- 동일 ticker/available_date 중복, 잘못된 날짜, 비양수 market cap은 거부합니다.
- quality/profitability/valuation/liquidity는 값이 높을수록 선호되는 방향으로 입력해야 합니다.
- provenance JSON은 `source`, `retrieved_at`, `universe_policy`, `survivorship_policy`를 요구하며 파일 digest와 함께 결과에 기록합니다.

## Target and model

- 완료된 training-window forward return만 calibration target으로 사용합니다.
- cross-section에서 trailing market beta, sector dummy, log market cap을 ridge residualization해 공통요인을 제거합니다.
- PIT feature는 snapshot별 winsorization과 z-score를 적용합니다.
- linear ridge coefficient의 절대합을 1로 정규화하고 feature별 절대 weight를 기본 45%로 제한합니다.
- 기본 40개 calibration observation 미만이면 fallback score를 만들지 않고 실패합니다.
- 최종 score는 equal-weight 주변 20% target active-share long-only tilt로 변환합니다.

## CLI

```bash
PYTHONPATH=src/backend .venv/bin/python tools/backtest_portfolio_models.py \
  --csv research-prices.csv \
  --factor-data pit-factors.csv \
  --factor-provenance pit-factors.provenance.json \
  --models equal_weight historical_bl risk_parity factor_neutral_alpha_tilt \
  --forecast-cache-namespace factor-neutral-alpha-v2-research
```

이 명령은 validation과 겹치지 않는 research split에서만 먼저 사용합니다.

## Remaining work

- survivorship-safe PIT dataset과 별도 research universe 확보
- provenance 검토와 결측/지연 공시 정책 확정
- research walk-forward에서 regularized linear, pairwise, listwise objective 비교
- 선택된 단일 specification freeze
- 그 뒤에만 기존 4-case validation 실행
- validation 통과 시에만 standard와 locked holdout 실행

## Verification

- `PYTHONPATH=src/backend .venv/bin/python -m pytest tests/test_portfolio_backtest.py -q`: 36 passed
- Python compile verification passed for backend and CLI modules
- `git diff --check` passed
