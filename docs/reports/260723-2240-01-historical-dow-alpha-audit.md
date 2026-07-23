# Historical DJIA Alpha Audit

- 실행 일시: 2026-07-23 22:40 KST
- 상태: completed, candidate rejected
- 결과: `logs/historical_dow_relative_2008_2025_identity_aliased.json`

## 다운로드와 provenance

- historical membership source:
  `Historical components of the Dow Jones Industrial Average`
  pinned revision `1362314398`
- raw HTML: 366,681 bytes
- raw SHA-256:
  `e4d33734caf137eb574a2c0dabf85ef35e00d0dd5038e98b1cd9a5059929a08e`
- 2005-2024 full-composition snapshots: 14
- reconstructed membership events: 70
- unique historical tickers: 49
- 각 snapshot은 정확히 30개 ticker로 재구성되는지 검증했습니다.
- source는 CC BY-SA 4.0 secondary public history이며 provenance에 출처,
  attribution, pinned revision, hash를 기록했습니다.

## 가격 identity

- 2007-2025 adjusted price panel: 4,780 rows × 49 ticker columns
- corporate continuity alias:
  `KFT→MDLZ`, `UTX→RTX`, `DWDP→DD`
- price CSV와 alias 파일 SHA를 provenance에 기록했습니다.
- Yahoo에서 완전히 누락된 active symbol은 `WBA`입니다.
- SEC submissions와 company ticker endpoint는 이 실행 환경에서 403을
  반환해 다운로드하지 못했습니다. bulk archive 우회 다운로드는 하지
  않았습니다.

## coverage 결함 수정

- 기존 코드는 manifest ticker를 가격 열로 먼저 필터링한 뒤 active universe
  size를 계산해 delisted symbol을 분모에서 제거했습니다.
- 이제 원 manifest active universe 30개가 분모이며 missing ticker,
  available count, prediction count, period coverage를 모두 기록합니다.
- final aggregate coverage: `98.57%`
- minimum period coverage: `93.33%`

## signal 결과

| Metric | Static current-DOW | Historical membership |
|---|---:|---:|
| Mean rank IC | 0.0539 | 0.0289 |
| Positive IC rate | 57.63% | 58.73% |
| Mean top-bottom spread | 0.0165 | 0.0076 |
| P(mean IC > 0) | 98.50% | 84.80% |
| P(mean spread > 0) | 96.65% | 77.80% |

- historical run은 63개 OOS period를 사용했습니다.
- mean IC와 spread는 양수지만 dependent-period 95% bootstrap gate에서
  탈락했습니다.
- static current-DOW의 강한 결과는 survivorship bias의 영향을 받은 것으로
  판단합니다.

## 결정

- `relative_ridge`를 freeze하거나 optimizer 기본값에 연결하지 않습니다.
- 동일 feature/target family의 Transformer hyperparameter 탐색을 진행하지
  않습니다.
- 기존 optimizer 기본값은 유지합니다.
- 다음 factor 연구는 PIT sector/SIC와 immutable split hash가 준비된 뒤
  별도 hypothesis로 수행합니다.

## Historical PIT factor 후속 실행

- 로컬 SEC companyfacts와 historical ticker-to-CIK interval을 결합해
  2009-2025 filing-date PIT feature `712`행, `47/49` ticker를 생성했습니다.
- `DIS`는 2019년 전후 CIK를 분리했습니다.
- `GM`은 구 법인에서 사용 가능한 annual feature가 없고 `WBA`는 가격이
  없어 제외됐습니다.
- broad sector는 static business-category proxy입니다. dated SEC SIC가
  아니므로 security-master provenance는 `promotion_safe=false`입니다.
- 이 provenance가 factor research의 promotion 판정에 전파되지 않던 결함을
  수정했습니다.

| Objective | Mean rank IC | Top-bottom spread | P(IC > 0) | P(spread > 0) |
|---|---:|---:|---:|---:|
| Price-only residual ridge | 0.0252 | 0.0044 | 87.20% | 75.90% |
| Full PIT factor ridge | 0.0581 | 0.0114 | 98.00% | 94.55% |
| Compact quality ridge | -0.0053 | -0.0056 | 42.80% | 25.40% |

- full PIT factor는 가격-only 기준선을 개선했지만 spread 95% 기준과
  Holm-adjusted significance를 통과하지 못했습니다.
- full PIT factor raw p-value는 `0.0545`, 3-objective adjusted p-value는
  `0.1635`입니다.
- 결론은 `no_signal_candidate`, `promotion_eligible=false`입니다.
- 이 결과는 재무 팩터 방향의 추가 데이터 정제를 지지하지만 Transformer
  hyperparameter 탐색이나 validation 실행을 정당화하지 않습니다.

## Split 및 lineage 잠금

- research split은
  `data/research/derived/historical_dow_factor_research_split_v1.json`으로
  잠갔습니다.
- v1 split manifest digest:
  `073af1a44a502a2923de95db64fa0c1e8719d1742e066339fe6a69ca32434577`
- split은 evaluation interval, experiment namespace, 세 objective, universe,
  price, factor SHA-256과 모든 학습 hyperparameter를 함께 고정합니다.
- 실행 시 universe→price→factor lineage를 교차검증하며 서로 다른 universe나
  price로 만든 파일 조합은 거부합니다.
- 재실행 결과:
  `split.promotion_safe=true`, `data_lineage.status=verified`,
  `data_promotion_safe=false`, `signal_gate_passed=false`,
  `promotion_eligible=false`.

## Nested ridge penalty 연구

- 새 objective와 기존 세 benchmark를 포함한 v2 split을 실행 전에 잠갔습니다.
- v2 digest:
  `8e10ff8245c7806ee775cbf37052bd9bfc005839e667ccffdee5218bb84a1ae5`
- 각 outer OOS 시점에서 이미 outcome이 완료된 inner 3기간만 사용해
  ridge penalty를 `[1, 5, 20, 100]`에서 선택했습니다.
- overlapping rebalance에서도 inner validation 시점까지 완료되지 않은
  target은 penalty 선택에 들어가지 않습니다.

| Metric | Fixed penalty | Nested penalty |
|---|---:|---:|
| Mean rank IC | 0.0581 | 0.0627 |
| Top-bottom spread | 0.0114 | 0.0153 |
| P(mean IC > 0) | 98.00% | 98.70% |
| P(mean spread > 0) | 94.55% | 97.45% |

- nested candidate는 개별 signal-only 95% gate를 통과했습니다.
- 그러나 네 objective의 Holm-adjusted p-value는 `0.1020`으로 familywise
  gate를 통과하지 못했습니다.
- fixed ridge 대비 paired improvement 확률은 IC `81.70%`, spread
  `93.50%`로 95% improvement gate도 탈락했습니다.
- 결론: 고정 penalty보다 수치는 개선됐지만 유의한 우월성은 입증되지 않아
  validation 또는 portfolio construction으로 넘기지 않습니다.

## Official market-factor beta

- Kenneth French Data Library의 daily U.S. `Mkt-RF`, `SMB`, `HML`, `RF`와
  FRED `DGS3MO`를 공식 URL에서 내려받아 SHA provenance를 생성했습니다.
- FRED yield는 factor date 이후 관측을 쓰지 않는 backward-asof 방식으로
  정렬했습니다.
- v3 split은 official factor file SHA와
  `market_beta_policy=fama_french_market_total_return`을 잠갔습니다.
- v3 digest:
  `98959efc85ab09f3fb696d6b7425557091a12841510aca21f4c4a643b115255b`

| Metric | Internal equal-weight beta | French market beta |
|---|---:|---:|
| Mean rank IC | 0.0627 | 0.0618 |
| Top-bottom spread | 0.0153 | 0.0149 |
| P(mean IC > 0) | 98.70% | 98.60% |
| P(mean spread > 0) | 97.45% | 97.15% |

- official market-beta 후보도 개별 signal gate는 통과했습니다.
- 5-objective Holm-adjusted p-value는 `0.1275`로 탈락했습니다.
- 기존 nested model 대비 paired improvement는 IC `38.80%`, spread
  `6.85%`로 악화됐습니다.
- authoritative factor를 썼다는 이유만으로 승격하지 않으며 이 후보는
  폐기합니다.
