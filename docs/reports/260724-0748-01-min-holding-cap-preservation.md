# Minimum-Holding Cap Preservation

## 결정

- `min_holding_weight` 적용 뒤에도 solver의 effective
  `max_asset_weight`를 보존하도록 수정했습니다.
- Production optimizer와 walk-forward backtest가 같은 sparse capped
  normalization을 사용합니다.
- Forecast, covariance, objective, transaction cost, promotion gate는
  변경하지 않았습니다.

## 결함

기존 `apply_min_holding_threshold`는 threshold 미만 position을 0으로 만든
뒤 남은 weight를 합계 1로 단순 재정규화했습니다.

재현:

- solver weights: `[60%, 36%, 4%]`
- minimum holding: `5%`
- maximum asset weight: `60%`
- 기존 결과: `[62.5%, 37.5%, 0%]`

Solver가 지킨 hard cap을 post-processing이 다시 위반했습니다. 응답의
performance도 이 cap 위반 weight로 계산됐습니다.

## 수정

`apply_min_holding_threshold`가 선택적으로 `max_asset_weight`를 받습니다.

1. long-only weight를 정규화합니다.
2. threshold 이상 position을 선택합니다.
3. 선택 종목 수로 cap이 불가능하면 원래 weight가 큰 탈락 종목을
   `ceil(1 / cap)`까지 최소 재도입합니다.
4. 선택 subset을 capped simplex 방식으로 합계 1에 재분배합니다.
5. threshold가 cap보다 커 두 제약이 동시에 불가능하면 threshold 제거보다
   hard cap을 우선 보존합니다.
6. Default threshold가 0이고 기존 weight가 이미 cap을 지키면 O(n) 검증 후
   즉시 반환해 불필요한 projection을 실행하지 않습니다.

재현 결과:

- 수정 weight: `[60%, 40%, 0%]`
- 합계: `100%`
- 최대 종목비중: `60%`

Production optimizer의 `optimizer_controls`에 다음을 추가했습니다.

- `requested_max_asset_weight`
- `effective_max_asset_weight`

## 영향

- `min_holding_weight > 0` 또는 solver의 극소 weight cleanup 경로에 영향
- 기존 research backtest 기본값은 minimum holding `0`이므로 과거
  candidate 성과를 이 수정으로 재판정하지 않습니다.
- Rebalance band/turnover cap 때문에 controlled live weight가 target cap으로
  즉시 이동하지 못하는 것은 별도 execution constraint이며
  `pre_control_weights`와 `controlled_weights`로 계속 구분합니다.

## 검증

- threshold 제거 후 hard cap 보존
- cap 때문에 필요한 최소 종목 재도입
- 합계 1 불변식
- production optimizer output cap
- backtest target cap
- 기존 portfolio backtest suite
