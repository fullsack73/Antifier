# Cash-Accrual Quality Research

## 결정

- 공식 French accrual benchmark는 accrual-quality의 경제적 방향성을 확인했습니다.
- 그러나 50/50 accrual-quality-momentum은 raw momentum 대비 paired spread gate를 통과하지 못했습니다.
- SEC cash-accrual `(operating_cash_flow-net_income)/assets`를 추가한 nested ridge도 fresh Nasdaq-100 2017 research에서 baseline을 개선하지 못했습니다.
- 두 후보 모두 production/default alpha로 승격하지 않습니다.
- French 2000+와 Nasdaq 2018+는 이번 후보를 위해 열거나 재튜닝하지 않습니다.

## 공식 benchmark data

- source: Kenneth R. French Data Library
- archive: `25_Portfolios_ME_AC_5x5_CSV.zip`
- source URL: `https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/25_Portfolios_ME_AC_5x5_CSV.zip`
- archive size: `531,845` bytes
- archive SHA-256: `f1689fb365ba35a4a13453c78d40adf0c9c8ffa90deebda26c045e44a60456f5`
- source definition: annual change in operating working capital divided by prior book equity
- derived panel: 1963-07-31~1999-12-31, 438 months × 25 size/accrual portfolios
- derived price SHA-256: `a9d91e6ef12a0d4fb344fc163cff487169595725e83bed01d7b74f8b105eb035`
- survivorship policy: official portfolios include eligible NYSE, AMEX, and NASDAQ firms through time

French working-capital accrual은 SEC cash-accrual과 관련된 경제적 benchmark지만 동일한 회계 정의가 아닙니다. 두 결과를 같은 feature의 독립 복제로 해석하지 않습니다.

## French locked research

- split: `fama-french-25-size-accrual-quality-momentum-research-1969-1998-v1`
- namespace: `alpha-v13-accrual-quality-momentum`
- manifest digest: `0a80b4ea817f9f9bf368acdb70d2bf5046c318f5a1dceabe3a1a78d4bab20293`
- evaluation: 1969-07-31~1998-07-31, 30 non-overlapping annual periods
- candidate: inverse accrual quintile 50% + 12-1 momentum 50%
- baseline: 12-1 momentum

| Signal | Mean rank IC | Positive IC | Top-bottom | P(IC>0) | P(spread>0) |
|---|---:|---:|---:|---:|---:|
| accrual-quality-momentum | 0.2044 | 76.67% | 4.34% | 100.00% | 98.45% |
| accrual-quality diagnostic | 0.1636 | 76.67% | 3.78% | 100.00% | 100.00% |
| 12-1 momentum | 0.1405 | 63.33% | 3.37% | 97.85% | 94.15% |

Candidate minus momentum:

- delta rank IC: `+0.0639`
- delta spread: `+0.00973`
- P(higher rank IC): `95.50%`
- P(higher spread): `84.75%`
- Holm-adjusted p-value: `0.1525`
- decision: paired gate rejected

Raw accrual-quality는 5개 quintile 값이 각 size bucket에 반복돼 tie-rate gate를 실패했습니다. 경제 방향은 강했지만 candidate promotion 근거로 사용하지 않습니다.

## SEC feature implementation

- opt-in feature set: `core-cash-accrual`
- formula: `(operating_cash_flow-net_income)/assets`
- direction: higher means less accrual-dependent earnings
- filing frequency: quarterly TTM
- availability: filing date only
- missing policy: cross-sectional neutral value plus explicit missing indicator
- existing core feature set and existing artifacts remain unchanged by default

Local `companyfacts/`, pinned Nasdaq-100 membership, dated ticker-to-CIK security master, existing Yahoo price panel만 사용했습니다. 추가 SEC/network download는 없었습니다.

Generated feature data:

- interval: 2015-01-01~2017-12-31
- rows/tickers: 979 / 87
- cash-accrual valid rows: 578 / 979 (`59.04%`)
- feature SHA-256: `63ef6784f456ceaf06191ce7ea608f727cc49a10a6c74f026383bdb553bfa22f`

## SEC locked research

- split: `nasdaq100-cash-accrual-research-2017-v1`
- namespace: `pit-factor-v7-cash-accrual-nasdaq100`
- manifest digest: `b516321a62249f3fe8fa80843f983afcf6efe424ecbe262d164b12b8d1acbb44`
- safe interval: 2017-01-01~2017-09-30
- target: same quarterly PIT factor-residual return
- baseline: `factor_residual_nested_ridge`
- candidate: `factor_residual_cash_accrual_nested_ridge`

Historical Nasdaq membership begins 2016-12-31, so only six fitted OOS periods were usable after completed-target and minimum-training gates. This low power was declared before the run.

| Model/feature | Periods | Mean rank IC | Positive IC | Top-bottom |
|---|---:|---:|---:|---:|
| nested baseline | 6 | -0.0298 | 33.33% | 0.74% |
| cash-accrual nested | 6 | -0.0451 | 33.33% | -0.74% |
| cash-accrual feature diagnostic | 6 | -0.0465 | 50.00% | -1.11% |

Dependent-period bootstrap와 paired gate는 최소 관측 수 미달이었습니다. Candidate 방향도 baseline보다 나빠 exact feature/model을 폐기합니다.

## 구현 및 검증

- French monthly value-weighted parser와 provenance builder 추가
- accrual signal-only research runner 추가
- SEC annual/quarterly TTM opt-in cash-accrual 생성 추가
- pooled nested ridge에 opt-in cash-accrual objective와 paired comparison 추가
- empty inner-fold가 `KeyError`를 내던 경로를 명시적 insufficient-data 처리로 수정
- future filing/amendment가 이전 feature row와 signal을 바꾸지 않는 회귀 테스트 추가
- backend pytest 255개 통과: non-cross-sectional 227개와 cross-sectional 28개를 desktop PTY 제한 때문에 shard로 실행
- French result SHA-256: `c12515d2996940cfd494c9b11cd015be9ee61fac068ed7ee3f0b960fc93c67bb`
- SEC result SHA-256: `f4fa228a9683745a0c7f311d384f7e4af367eaf0b0e4eb61b9b1000757779240`

## 후속

- Transformer hyperparameter 확대 근거는 생기지 않았습니다.
- 같은 Nasdaq/DOW 기간에서 accrual 정의, penalty, missing policy를 재튜닝하지 않습니다.
- 다음 feature family는 analyst-independent revision 또는 macro/regime처럼 현재 PIT 4-factor와 다른 정보원을 사용하고, 더 긴 canonical historical universe를 먼저 확보해야 합니다.
